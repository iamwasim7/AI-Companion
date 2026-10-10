# AI Companion

A Windows desktop assistant that provides context-aware programming help. Screen monitoring is always opt-in. This is a Final Year BSc.IT project.

**Status:** MVP complete (v1.1.1, Phases 1–11 + multi-provider update). 89 tests pass with no network calls; `dist/AI-Companion/AI-Companion.exe` launches and persists its DB/logs next to the exe.

## Tech stack

- Python 3.x
- PySide6
- OpenAI Python SDK
- SQLite (local `data/ai_companion.db`)

## Setup

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.main
```

## AI modes

- `mock` (default) — local deterministic replies; no API key or network access needed.
- `live` + provider `openai` — Responses API chat replies. In Settings, save your API key and switch the AI mode to live.
- `live` + provider `custom` — any OpenAI-compatible Chat Completions endpoint (NVIDIA NIM, Groq, Ollama, ...). In Settings, set the base URL (e.g. `https://integrate.api.nvidia.com/v1`), model ID, and API key.

The live providers send the recent messages from the current chat (plus a system instruction), use an explicit timeout, and never store API output server-side (`store=False` on OpenAI). Never commit `.env`.

## Privacy

The app never monitors the screen unless the user explicitly enables monitoring. Frames stay in memory for local change comparison, are never written to disk, and are never sent to OpenAI. Only short extracted error text goes to AI after local detection.

## Packaging (Windows)

```text
pip install -r requirements.txt
python -m PyInstaller ai-companion.spec --noconfirm
dist\AI-Companion\AI-Companion.exe
```

The exe is windowed (one-dir) and stores `data/ai_companion.db` + `logs/app.log`
beside itself. Tesseract OCR is not bundled — install it or set `TESSERACT_PATH`.
Copy `.env.example` to `.env` next to the exe and add `OPENAI_API_KEY` for live mode.

Optional installer: `installer.iss` (Inno Setup 6) wraps the PyInstaller
output into `dist-installer\AI-Companion-Setup-*.exe`. Build with `iscc installer.iss`.

## Project status

See `PROJECT_STATUS.md` for the current phase, completed work, and next tasks.