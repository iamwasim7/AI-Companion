# Project Status

## Current Phase

Phase 11 — Packaging (complete) · MVP DONE · v1.3.0 flexible AI provider & model configuration

## Completed Features

- Foundation and Phase 2 user interface (Dashboard, Chat, Monitoring, History, Settings, Floating Companion)
- Mock/live AI provider boundary; mock remains default without network access
- Live OpenAI Responses API provider with session context, `store=False`, timeout, off-thread `QThread` worker
- Phase 4: Screen capture subsystem (`ScreenCapture`, `ChangeDetector`, `MonitorService`) with pause/resume, screen selection, change sensitivity, FPS limiting
- Phase 5: OCR subsystem (`OCRService`, `OCRResult`, `preprocess_image`, `qimage_to_pil`) using local Tesseract OCR
- Phase 6: Error detection engine (`ErrorDetector`, `CodeDetector`, `ContextDetector`)
- Automatic detection of Python standard exceptions (`NameError`, `SyntaxError`, `TypeError`, etc.) and full tracebacks
- File path, line number, and offending code line extraction from tracebacks
- Categorization into `CONFIRMED ERROR`, `POSSIBLE ERROR`, and `GENERAL CONTEXT`
- Language heuristics (Python, JavaScript, HTML/CSS, SQL) and application context detection
- Unit tests for Config, AI Service, Screen Monitoring, OCR, and Detection (28 tests passing)
- Phase 7: end-to-end pipeline `monitoring.frame_changed → OCRWorker (off UI thread) → ErrorDetector → analysis.run → ErrorAnalysisService → AnalysisPanel` via `app/services/detection_pipeline.py`
- Structured JSON prompts (`SYSTEM_PROMPT`) now reach OpenAI; `MockProvider` returns schema-valid mock analyses; `response_parser` handles fences/malformed/plain-text gracefully
- `AnalysisPanel` embedded in Dashboard, persists each analysis to in-memory history, emits `analysis.completed`
- Cost guards: one OCR job at a time, 20s API cooldown, duplicate-error signature dedup, min-text + max-context clipping, screenshots never stored/sent
- Unit tests for pipeline helpers, prompts, and mock error analysis (36 tests passing)
- Phase 8: `NotificationService` (`app/services/notification_service.py`) with 30s cooldown, 180s duplicate suppression, ignore-list, max 3 active; notifies only on `analysis.completed` with confidence ≥ 0.4
- Phase 8: `CompanionService` (`app/services/companion_service.py`) centralises `IDLE/THINKING/ANALYZING/ALERT/RESPONDING/ERROR` reactions with safe auto-return-to-IDLE timers
- Phase 8: `FloatingCompanion` unread badge + `NotificationPopup` with View / Ask AI / Ignore / Dismiss; View opens Dashboard, Ask AI prefills Chat via `chat.prefill`; Dashboard notifications card with Dismiss
- Unit tests for notification policy/service (48 tests passing)
- Phase 9: SQLite at `data/ai_companion.db` (`settings/conversations/messages/detected_errors/application_events`) via `app/database/database.py` + `repositories.py`; UI never runs SQL
- Phase 9: `SessionStore` is write-through persistent with identical UI API; fresh installs start with genuinely empty history (no seed data); retention purge on startup/insert (`history_retention_days`, 0 = forever)
- Phase 9: Settings persist (theme, model, behavior, retention, interval, sensitivity) via `app/services/settings_service.py`; History has Delete selected; Settings shows DB path + retention control
- Unit tests for database + persistence (58 tests passing)
- Phase 10: integration test `detection → mock analysis → history → notification` (`tests/test_integration.py`, temp DB, no network)
- Phase 10: robustness tests (`tests/test_robustness.py`) — SDK error mapping, empty-key config error, provider-failure fallback, parser fences/partial/broken/confidence clamps, OCR missing-binary/null/bad-type, `MonitorService` start/pause/resume/stop + capture-error surfacing, companion force-idle, settings invalid-value rejection, DB reopen persistence
- Phase 10: extended headless smoke test exercises simulate-detection → mock analysis → notification → chat prefill → history selection
- Fixed first-run seed logic (fresh DB now seeds correctly)
- Headless offscreen UI smoke test passing (full loop: ANALYZING → RESPONDING → IDLE)

## Deliberately Not Implemented

- None — all MVP phases (1–11) are complete. Future/optional ideas (voice,
  cloud sync, auto-fix execution) remain out of scope per Master Spec §6.

## Live Mode Setup

1. Open Settings.
2. Save an OpenAI API key locally (stays in `.env`, never in SQLite).
3. Set AI mode to `live`.
4. Use Chat. The app sends only the recent text in that chat, never any screen content without consent.
5. Enable Monitoring: significant screen changes run local OCR + detection; only concise error context is sent to OpenAI after a local error signal, never screenshots.
6. History persists in `data/ai_companion.db`; retention and clearing are in Settings. Screenshots are never stored.

## Next Tasks

- MVP is complete. Optional follow-ups: installer (Inno Setup), app icon,
  auto-update, cloud sync — all out of scope unless requested.

## Packaging

- Spec: `ai-companion.spec` (windowed, one-dir). Build with
  `python -m PyInstaller ai-companion.spec --noconfirm`.
- Output: `dist/AI-Companion/AI-Companion.exe` (~15 MB exe + `_internal/`).
- Verified: exe launches, stays running, creates `data/ai_companion.db`
  and `logs/app.log` next to the exe (frozen `PROJECT_ROOT` fix).
- Not bundled: Tesseract OCR binary (install separately or set
  `TESSERACT_PATH`); `.env` with `OPENAI_API_KEY` for live mode.

## Testing Status

- `python -m unittest discover -s tests -v` — passed (107 tests)
- `python tests/smoke_launch.py` — passed in mock mode
- No paid/live API requests made during testing
- v1.1.0: generic `CompatibleProvider` (Chat Completions + custom base URL) covers NVIDIA NIM, Groq, Ollama, etc.; provider/model/endpoint/key configured in Settings or `.env` (`AI_PROVIDER`, `CUSTOM_BASE_URL`, `CUSTOM_MODEL`, `CUSTOM_API_KEY`); 10 new provider tests, 88 total passing
- v1.1.1: HTTP-status error mapping (401 rejected key, 404 unknown model, 410 retired model, 429 quota) so live failures explain themselves; verified live against NVIDIA NIM (`meta/llama-3.2-11b-vision-instruct`); 89 tests passing
- Tester bugfix batch: retention 0 ("keep forever") now survives restart; API keys stripped before reaching the SDK; companion size/always-on-top persisted; dropped analyses logged; dead idle-reset branch removed; Copy button on Dashboard corrected-code block; 3 new regression tests, 92 total passing
- Cleanup: removed dead `app/ui/pages.py` placeholder and stale `startup_error.txt` (suite still green)
- `docs/DEMO_SCRIPT.md`: 5-minute demo walkthrough with failure fallbacks
- `installer.iss`: Inno Setup 6 definition for a one-click installer — compiled to `dist-installer/AI-Companion-Setup-1.1.1.exe` (~58 MB, per-user install, Start Menu + optional desktop shortcut, `.env` created from template only on first install). Verified share-safe via silent test install: builder's keys/history excluded, payload holds only the template `.env` plus empty `data/`+`logs/` dirs.
- Latency pass: preliminary "analyzing…" card on `detection.updated` (upgraded in place by `analysis.completed`, finalized with reason on `analysis.skipped`); single-pass Tesseract OCR (`image_to_data` only, ~1.5 s → ~0.5–0.8 s); 1280px OCR downscale cap (change-detector path untouched); latest-wins depth-1 OCR queue replacing silent drops; 15 new tests, 107 total passing
- **v1.2.0 — Universal Programming Error Detection** (2026-09-15):
  - NEW `app/detection/universal_patterns.py` — pure-data module containing 16-language signal tables (`LANGUAGE_SIGNALS`) and 13 universal error regex patterns (`UNIVERSAL_ERROR_PATTERNS`) covering Syntax, Compilation, Linker, Name/Reference, Type, Module/Import, Runtime/System errors and panics. Compiled once at import; zero runtime overhead.
  - ENHANCED `app/detection/code_detector.py` — `detect_language()` now uses signal-scoring across all 16 languages (Python, JavaScript, TypeScript, Java, C, C++, C#, Go, Rust, PHP, Ruby, Kotlin, Swift, Dart, SQL, R). Requires ≥2 signal hits to commit; falls back to original quick-check on no winner — all prior Python/JS tests unaffected.
  - ENHANCED `app/detection/error_detector.py` — 6-stage detect() pipeline: (1) OCR-tolerant frame scanning with smart-quote/no-quote support; (2a) Java thread exception; (2b) Go/Rust panic; (2c) compiler file:line error; (2d) strict Python/JS exception; **(2e) OCR-tolerant fallback** — catches `SyntaxError cannot assign to True` when OCR drops the colon; (3) universal error patterns; (4–6) existing generic/warning/GENERAL stages unchanged.
  - ENHANCED `app/ocr/ocr_service.py` — `MAX_OCR_WIDTH` raised 1280 → 1920 (no resize on standard 1080p; zero latency change); `preprocess_image()` detects dark terminals (avg < 110/255) and applies 1.5× contrast boost so light text on dark backgrounds sharpens for Tesseract.
  - EXPANDED `tests/test_detection.py` — 50 new tests in 4 new classes: `LanguageRecognitionTests` (20 tests, all 16 languages), `UniversalErrorDetectionTests` (14 tests, Java/C/C++/Rust/Go/C#/PHP/Ruby/linker/segfault/module/build), `OCRCorruptionTests` (8 tests, missing/replaced colon, smart quotes, missing comma, garbled garbage), `FalsePositiveTests` (8 tests, prose with "error"/"warning"/"exception"/"failed", normal code, log lines).
  - **160 tests passing, 0 failing, 1 skipped** (live-only mock assertion).
  - **No regression** — all 110 pre-existing tests continue to pass.
  - EXE NOT rebuilt (per specification — await explicit approval).
  - Detection is language-agnostic at its core. The system provides language-agnostic detection of common and recognizable programming errors from visible screen output across multiple programming languages and development environments. It does not guarantee detection of every possible error in every language.
- Code-aware AI analysis: prompts now require diagnosing the `Relevant Code` line (exact token/symbol), always attempting `corrected_code`, and honest confidence (schema example fixed); `NODE_HEADER_REGEX` keeps full spaced Windows drive paths; 7 new prompt/path tests, 188 total passing
- **v1.3.0 — Flexible AI Provider & Model Configuration** (2026-09-17):
  - NEW `AI_PROVIDER`, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` canonical env-var names. Legacy `CUSTOM_API_KEY`, `CUSTOM_BASE_URL`, `CUSTOM_MODEL`, `OPENAI_API_KEY` transparently accepted as fallbacks — existing NVIDIA `.env` files work unchanged.
  - `AI_PROVIDER` normalizes legacy values: `custom` → `openai_compatible`, `openai` → `openai_native`. Helper `_normalize_provider()` and `_read_ai_env()` added to `config.py`.
  - `AIService.from_config()` now dispatches on canonical provider names; unknown providers raise `AIConfigurationError` with a clear message (no key leakage).
  - NEW `CompatibleProvider.test_connection()` — sends a 1-token minimal request and returns `(bool, safe_message)`. Never exposes the API key in the result.
  - REMOVED hardcoded `AI_MODELS` tuple and model `QComboBox`. Model is now a free-text `QLineEdit`; any provider-specific model identifier can be entered without changing source code.
  - REDESIGNED Settings AI section: unified "AI Configuration" card replaces the old bifurcated "OpenAI key" + "Custom endpoint" layout. Fields: AI mode, provider (OpenAI-Compatible / OpenAI Native), explanation style, Base URL, Model, API Key, Test Connection button with live status chip.
  - Test Connection runs on a dedicated `QThread` — never blocks the UI (constraint §14).
  - `Config.get_ai_api_key()` centralises key retrieval; value never stored as a class attribute, never logged.
  - NEW `tests/test_ai_config.py` — 30 tests covering missing config errors, mock-mode offline guarantee, API key non-leakage across all error types, provider error normalization.
  - UPDATED `tests/test_config.py` — 18 tests (was 2): provider normalization, legacy env fallbacks, effective_model logic, mock mode.
  - UPDATED `tests/test_providers.py` — 26 tests (was 13): canonical provider selection, legacy "custom" compat, openai_native selection, unknown-provider error, Test Connection success/failure/minimal-request.
  - **242 tests passing, 1 skipped, 0 regressions** (+47 new tests over 195 baseline).
  - EXE NOT rebuilt — dev version verified first per specification.
- Code-aware analysis robustness: privacy-safe analysis-context log (`has_code`/`code_chars`, never content); `Relevant Code`-absent fallback now includes a capped, explicitly-unverified nearby-OCR window instead of nothing; 3 new context tests, 247 total passing.
- Selectable companion avatars: `classic` (painted) plus `cat_orange`, `cat_black`, `dog_golden`, `turtle`, `gecko` PNGs in `assets/companion/` (exact filenames); Settings dropdown + `companion.avatar` event + persistence; missing/unreadable files fall back to classic; 7 new avatar tests, 270 total passing.