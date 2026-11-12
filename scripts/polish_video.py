"""Final pass on the demo video: level the voice, lay it over the picture, export.

The creative cut belongs in a timeline you can watch. This handles the parts a
command line does better than a human with a mouse: loudness normalisation to
a broadcast standard, exact audio offset, optional burned-in captions, and an
encode YouTube will not re-crush.

    # the usual case
    python scripts/polish_video.py --video cut.mp4 --audio voice.wav --out hito.mp4

    # the narration starts 1.4 s into the picture
    python scripts/polish_video.py --video cut.mp4 --audio voice.wav \
        --offset 1.4 --out hito.mp4

    # with captions burned in
    python scripts/polish_video.py --video cut.mp4 --audio voice.wav \
        --srt captions.srt --out hito.mp4

    # where does each spoken phrase start? (for timing captions)
    python scripts/polish_video.py --audio voice.wav --phrases
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# EBU R128, the level streaming platforms target. Quieter than you think, and
# consistent, which is what makes a laptop-mic recording stop sounding amateur.
TARGET_LUFS = -16.0
TARGET_LRA = 11.0
TARGET_PEAK = -1.5


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for candidate in Path("C:/").glob(
        "Users/*/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"
    ):
        return str(candidate)
    sys.exit("ffmpeg not found. Install it: winget install Gyan.FFmpeg")


def run(args: list[str], capture: bool = True) -> str:
    result = subprocess.run(args, capture_output=capture, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0 and capture:
        sys.exit(f"ffmpeg failed:\n{(result.stderr or '')[-1500:]}")
    return (result.stderr or "") + (result.stdout or "")


def measure_loudness(exe: str, audio: str) -> dict:
    """Pass one of two-pass loudnorm: measure what we actually have."""
    out = run([
        exe, "-hide_banner", "-i", audio,
        "-af", f"loudnorm=I={TARGET_LUFS}:LRA={TARGET_LRA}:TP={TARGET_PEAK}:"
               f"print_format=json",
        "-f", "null", "-",
    ])
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", out, re.DOTALL)
    if not match:
        print("  could not measure loudness; falling back to single pass")
        return {}
    stats = json.loads(match.group(0))
    print(f"  measured: {stats['input_i']} LUFS, peak {stats['input_tp']} dBTP")
    return stats


def stamp(seconds: float) -> str:
    return (f"{int(seconds // 3600):02d}:{int(seconds // 60 % 60):02d}:"
            f"{seconds % 60:06.3f}").replace(".", ",")


def phrase_starts(exe: str, audio: str) -> None:
    """Where each spoken phrase begins and ends, so captions can be timed.

    silencedetect reports the gaps, not the speech, so the phrases are what
    falls between them - including the one before the first gap, which a naive
    reading of silence_end misses entirely because nothing precedes it.
    """
    out = run([
        exe, "-hide_banner", "-i", audio,
        "-af", "silencedetect=noise=-32dB:d=0.45",
        "-f", "null", "-",
    ])
    duration_match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    duration = (
        int(duration_match.group(1)) * 3600
        + int(duration_match.group(2)) * 60
        + float(duration_match.group(3))
    ) if duration_match else 0.0

    gaps = sorted(
        zip((float(m) for m in re.findall(r"silence_start: (-?[\d.]+)", out)),
            (float(m) for m in re.findall(r"silence_end: ([\d.]+)", out)))
    )

    phrases: list[tuple[float, float]] = []
    cursor = 0.0
    for gap_start, gap_end in gaps:
        if gap_start > cursor + 0.05:
            phrases.append((cursor, gap_start))
        cursor = gap_end
    if duration and cursor < duration - 0.05:
        phrases.append((cursor, duration))

    if not phrases:
        print("\nNo speech detected. Is the file silent, or recorded very "
              "quietly? Try --phrases on a louder take.")
        return

    print(f"\n{len(phrases)} phrases in {duration:.1f}s of audio\n")
    print(f"{'#':>3}  {'start':>7}  {'end':>7}  srt timing")
    for index, (start, end) in enumerate(phrases, start=1):
        print(f"{index:>3}  {start:7.2f}  {end:7.2f}  "
              f"{stamp(start)} --> {stamp(end)}")
    print("\nThose are speech boundaries, not sentence boundaries - one phrase "
          "can hold two sentences, and a breath mid-sentence splits one. Use "
          "them as the skeleton and merge by hand.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", help="the cut screen recording")
    parser.add_argument("--audio", required=True, help="the narration")
    parser.add_argument("--out", default="hito-demo.mp4")
    parser.add_argument("--srt", help="captions to burn in")
    parser.add_argument("--offset", type=float, default=0.0,
                        help="seconds to delay the narration against the picture")
    parser.add_argument("--phrases", action="store_true",
                        help="only report where each spoken phrase starts")
    args = parser.parse_args()

    exe = ffmpeg()
    print(f"ffmpeg: {exe}\n")

    if args.phrases:
        phrase_starts(exe, args.audio)
        return 0

    if not args.video:
        sys.exit("--video is required unless you pass --phrases")

    print("1/3 measuring the narration")
    stats = measure_loudness(exe, args.audio)

    if stats:
        norm = (
            f"loudnorm=I={TARGET_LUFS}:LRA={TARGET_LRA}:TP={TARGET_PEAK}:"
            f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
            f"measured_TP={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
            f"offset={stats['target_offset']}:linear=true"
        )
    else:
        norm = f"loudnorm=I={TARGET_LUFS}:LRA={TARGET_LRA}:TP={TARGET_PEAK}"

    # A little high-pass takes out desk rumble and laptop fan without touching
    # the voice; nothing useful in a human voice lives below 80 Hz.
    audio_filter = f"highpass=f=80,{norm},aresample=48000"
    if args.offset > 0:
        audio_filter = f"adelay={int(args.offset * 1000)}|{int(args.offset * 1000)}," \
                       + audio_filter

    video_filter = "scale=1920:-2:flags=lanczos,format=yuv420p"
    if args.srt:
        srt = Path(args.srt).as_posix().replace(":", "\\:")
        video_filter = (
            f"subtitles='{srt}':force_style='FontName=Arial,FontSize=20,"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,BorderStyle=3,"
            f"Outline=1,Shadow=0,MarginV=40'," + video_filter
        )

    print("2/3 laying the voice over the picture")
    print("3/3 encoding for YouTube")
    run([
        exe, "-hide_banner", "-y",
        "-i", args.video,
        "-i", args.audio,
        "-filter_complex",
        f"[0:v]{video_filter}[v];[1:a]{audio_filter}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "19",
        "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-shortest",
        args.out,
    ], capture=True)

    size = Path(args.out).stat().st_size / 1e6
    print(f"\nwrote {args.out} ({size:.1f} MB)")
    print("Check it before uploading: the audio is normalised, not fixed - if "
          "the recording clipped, it is still clipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
