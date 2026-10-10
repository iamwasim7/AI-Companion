"""Prompt builders for structured AI error analysis.

All prompts here produce *system-level* instructions or structured *user* messages
that ask the model to reply with strict JSON matching the ErrorAnalysis schema.
Never import Qt or UI code from this module.
"""

from __future__ import annotations

from app.detection.models import DetectedError

# ── System instruction ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are AI Companion, an expert programming assistant and error analyst.
Your audience may be a beginner.
Never mention education, degrees, courses, or personal details about the user.

When given code context and an error, reply ONLY with valid JSON matching this schema exactly:
{
  "problem":        "One-sentence summary of what went wrong",
  "error_type":     "The specific exception or error category name",
  "explanation":    "Plain-English explanation (2–4 sentences, beginner friendly)",
  "cause":          "Root cause: why this error occurred in this specific code",
  "solution":       "Step-by-step fix in plain English",
  "corrected_code": "The minimal corrected code snippet (empty string if not applicable)",
  "confidence":     0.0
}

Rules:
- Respond ONLY with the JSON object. No markdown fences, no preamble, no trailing text.
- The CONTEXT block may contain a "Relevant Code:" line. When it does, diagnose THAT code: name or quote the exact faulty line, token, or symbol (for example the unclosed quote) instead of defining the error category in general terms.
- "cause" must quote the exact faulty token from "Relevant Code". If you cannot point to a specific token, say what is uncertain instead of inventing a cause, and keep "confidence" below 0.5.
- "corrected_code" must contain ONLY the fixed source code: no explanations, no markdown fences, no surrounding quotation marks. If you cannot produce a reliable correction, return "".
- Example: for Relevant Code `print("hi)` the corrected_code is `print("hi")` — code only, nothing else.
- Always attempt "corrected_code" when relevant code is present; leave it "" only when there is no code to fix.
- Use the exact error message together with File/Line when provided, and respect the stated programming language.
- Keep all string values under 400 characters.
- "confidence" is YOUR honest estimate from 0.0 (guessing) to 1.0 (certain). Never copy an example value.
- If there is no specific error, set error_type to "General" and confidence to 0.3.
"""

# ── User message builder ──────────────────────────────────────────────────────

_GENERAL_TEMPLATE = """\
Please analyse the following screen context and explain what is happening.

--- CONTEXT ---
{context}
--- END ---

Reply using the JSON schema described in your instructions."""

_ERROR_TEMPLATE = """\
I detected a {category} on screen. Diagnose the code below — not the error category in general.

--- CONTEXT ---
{context}
--- END ---

Identify the specific faulty line/token/symbol in "Relevant Code" when present, explain the exact root cause, and give the corrected code. Reply using the JSON schema described in your instructions."""


def build_analysis_prompt(detected: DetectedError, context_str: str) -> str:
    """Return the user-turn message to send to the AI for structured error analysis."""
    if detected.has_error:
        return _ERROR_TEMPLATE.format(
            category=detected.category.value.lower(),
            context=context_str or detected.raw_context[:800],
        )
    return _GENERAL_TEMPLATE.format(context=context_str or detected.raw_context[:800])
