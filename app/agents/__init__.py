"""Hito's four agents, plus the shared Claude wrapper.

  contract_parser  reads the PDF and proposes the milestone plan
  reviewer         the second pair of eyes that must approve every invoice
  collector        writes the collection message the risk model asks for
  splitter         turns one payment into collaborator payouts

Each one has a deterministic fallback with the same output contract, so the
product degrades instead of breaking when there is no API key.
"""
from . import collector, contract_parser, llm, reviewer, splitter

__all__ = ["contract_parser", "reviewer", "collector", "splitter", "llm"]
