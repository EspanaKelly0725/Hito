import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// The build lands in ../app/static, which FastAPI serves. The compiled output is
// committed so that a judge can run the project with pip + uvicorn only.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  base: "./",
  build: {
    outDir: "../app/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/mock": "http://127.0.0.1:8000",
    },
  },
})
