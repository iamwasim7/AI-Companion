"""Error detection engine for extracting programming exceptions and tracebacks."""

from __future__ import annotations

import re

from app.detection.code_detector import detect_application, detect_language
from app.detection.models import DetectedError, DetectionCategory
from app.detection.universal_patterns import (
    BARE_FILE_LINE_REGEX,
    COMPILER_FILE_LINE_REGEX,
    CS_PAREN_REGEX,
    FRAME_REGEX_TOLERANT,
    JAVA_EXCEPTION_REGEX,
    JAVA_FRAME_REGEX,
    OCR_TOLERANT_EXCEPTION_REGEX,
    ON_LINE_REGEX,
    PANIC_REGEX,
    PHP_RB_FILE_REGEX,
    RUST_ARROW_REGEX,
    UNIVERSAL_ERROR_PATTERNS,
)

# ---------------------------------------------------------------------------
# Known exception name sets (used for language disambiguation)
# ---------------------------------------------------------------------------

# Standard Python exceptions recognized by the parser
PYTHON_EXCEPTIONS = {
    "NameError",
    "SyntaxError",
    "TypeError",
    "ValueError",
    "IndexError",
    "KeyError",
    "AttributeError",
    "ImportError",
    "ModuleNotFoundError",
    "IndentationError",
    "TabError",
    "ZeroDivisionError",
    "FileNotFoundError",
    "UnboundLocalError",
    "RecursionError",
    "RuntimeError",
    "AssertionError",
    "NotImplementedError",
    "PermissionError",
    "TimeoutError",
    "MemoryError",
    "OverflowError",
    "UnicodeDecodeError",
    "UnicodeEncodeError",
    "JSONDecodeError",
}

# Standard JavaScript exceptions
JAVASCRIPT_EXCEPTIONS = {
    "ReferenceError",
    "TypeError",
    "SyntaxError",
    "RangeError",
    "URIError",
    "EvalError",
    "AggregateError",
}

# ---------------------------------------------------------------------------
# Regex patterns (originals preserved for backwards compatibility)
# ---------------------------------------------------------------------------

# Strict Python traceback frame (kept for reference; detection uses FRAME_REGEX_TOLERANT)
FRAME_REGEX = re.compile(
    r'File\s+["\'](?P<file>[^"\']+)["\'],\s+line\s+(?P<line>\d+)(?:,\s+in\s+(?P<func>\w+))?',
    re.IGNORECASE,
)

# Regex matching Node.js file:line headers: C:\path\test.js:1 or /path/test.js:1:2
# The optional prefix only consumes up to "(" (e.g. "at Object.<anonymous> (").
# It must NOT consume a bare space, otherwise a spaced Windows path like
# "d:\Hello Python\testjs.js:1" loses its "d:\Hello " drive prefix.
NODE_HEADER_REGEX = re.compile(
    r'^(?:.*?\()?(?P<file>(?:[A-Za-z]:[\\/]|[\\/]|(?:\.\.?[\\/]))?[^()\n:]+\.(?:js|mjs|cjs|jsx|ts|tsx)):(?P<line>\d+)(?::(?P<col>\d+))?\)?$',
    re.IGNORECASE,
)

# Regex matching JS stack frame lines: at Object.<anonymous> (C:\path\test.js:1:13)
JS_FRAME_REGEX = re.compile(
    r'^\s*at\s+(?:.*?\s+\()?(?P<file>(?:[A-Za-z]:[\\/]|[\\/]|(?:\.\.[/\\]))?[^()\n:]+\.(?:js|mjs|cjs|jsx|ts|tsx)):(?P<line>\d+)(?::(?P<col>\d+))?\)?',
    re.IGNORECASE,
)

# Regex matching a Python or JS exception line (with optional Uncaught prefix)
EXCEPTION_REGEX = re.compile(
    r'^(?:Uncaught\s+)?(?:[A-Za-z_][A-Za-z0-9_.]*\.)?(?P<type>[A-Z][A-Za-z0-9_]*(?:Error|Exception|Warning)):(?:\s+(?P<msg>.*))?$',
)

# Generic error indicators
GENERIC_ERROR_REGEX = re.compile(
    r'(?:fatal error|error TS\d+|npm ERR!|ReferenceError|TypeError|SyntaxError):\s*(?P<msg>.*)',
    re.IGNORECASE,
)

# Warning indicators for POSSIBLE ERROR
WARNING_REGEX = re.compile(
    r'(?:warning:|deprecated:|failed with exit code \d+|exit status \d+|exit code \d+)',
    re.IGNORECASE,
)


class ErrorDetector:
    """Parses text to detect and extract structured error information."""

    def detect(self, text: str) -> DetectedError:
        """Analyze text and return a DetectedError instance.

        Detection stages (in order, short-circuit on first CONFIRMED match):
          1.  Frame/location scanning (Python traceback, compiler file:line, JS stack)
          2a. Java thread exception header
          2b. Go/Rust panic
          2c. Compiler file:line error (non-Python/JS languages)
          2d. Strict Python/JS exception line (XxxError: message)
          2e. OCR-tolerant exception fallback (XxxError message, colon missing)
          3.  Universal error patterns (language-agnostic categories)
          4.  Generic confirmed patterns (existing GENERIC_ERROR_REGEX)
          5.  Warning / non-zero exit (POSSIBLE ERROR)
          6.  General context (no error found)

        All processing is local (regex + string ops). No extra OCR passes,
        no AI calls, no network requests -- meets the performance requirement.
        """
        if not text or not text.strip():
            return DetectedError(category=DetectionCategory.GENERAL_CONTEXT)

        lines = [line.strip() for line in text.splitlines()]
        raw_context = "\n".join(lines)
        language = detect_language(text)
        source_app = detect_application(text)

        # ------------------------------------------------------------------
        # Stage 1 — Frame / location scanning
        # ------------------------------------------------------------------
        has_traceback_header = any(
            "traceback (most recent call last)" in line.lower() for line in lines
        )
        last_frame_file = ""
        last_frame_line: int | None = None
        last_frame_col: int | None = None
        code_snippet = ""

        # 1a. Python traceback frames (OCR-tolerant: quotes optional/smart)
        for idx, line in enumerate(lines):
            match = FRAME_REGEX_TOLERANT.search(line)
            if match:
                last_frame_file = match.group("file")
                last_frame_line = int(match.group("line"))
                if idx + 1 < len(lines):
                    next_line = lines[idx + 1]
                    if not FRAME_REGEX_TOLERANT.search(next_line) and not EXCEPTION_REGEX.match(next_line):
                        code_snippet = next_line

        # 1b. Compiler file:line:col: error (GCC/Clang/Rust/Go/Java/C#/TS)
        for match in COMPILER_FILE_LINE_REGEX.finditer(raw_context):
            last_frame_file = match.group("file")
            last_frame_line = int(match.group("line"))
            col_str = match.group("col")
            if col_str:
                last_frame_col = int(col_str)

        # 1c. Node.js / JavaScript file headers and stack frames
        for idx, line in enumerate(lines):
            if line.startswith("^") and idx > 0:
                code_snippet = lines[idx - 1]
                if idx > 1:
                    header_match = NODE_HEADER_REGEX.search(lines[idx - 2])
                    if header_match:
                        last_frame_file = header_match.group("file")
                        last_frame_line = int(header_match.group("line"))

            if not last_frame_file or (last_frame_file and not last_frame_file.lower().endswith(".py")):
                js_match = JS_FRAME_REGEX.search(line) or NODE_HEADER_REGEX.search(line)
                if js_match:
                    frame_path = js_match.group("file")
                    if not frame_path.startswith("node:"):
                        last_frame_file = frame_path
                        last_frame_line = int(js_match.group("line"))

        # 1d. Extra location formats -- fill in ONLY when nothing found yet,
        # so primary scanners (Python frames, compiler lines, JS stacks)
        # are never clobbered by weaker heuristics.
        if not last_frame_file:
            for match in CS_PAREN_REGEX.finditer(raw_context):
                last_frame_file = match.group("file")
                last_frame_line = int(match.group("line"))
                if match.group("col"):
                    last_frame_col = int(match.group("col"))
                break
        if not last_frame_file:
            for match in RUST_ARROW_REGEX.finditer(raw_context):
                last_frame_file = match.group("file")
                last_frame_line = int(match.group("line"))
                if match.group("col"):
                    last_frame_col = int(match.group("col"))
                break
        if not last_frame_file:
            for line in lines:
                bare = BARE_FILE_LINE_REGEX.search(line)
                if bare:
                    last_frame_file = bare.group("file")
                    last_frame_line = int(bare.group("line"))
                    break
            if not last_frame_file:
                for line in lines:
                    on_line = ON_LINE_REGEX.search(line)
                    if on_line:
                        php_rb = PHP_RB_FILE_REGEX.search(line)
                        if php_rb:
                            last_frame_file = php_rb.group("file")
                            last_frame_line = int(on_line.group("line"))
                            break
        if not last_frame_file:
            for match in JAVA_FRAME_REGEX.finditer(raw_context):
                last_frame_file = match.group("file")
                last_frame_line = int(match.group("line"))
                break

        # ------------------------------------------------------------------
        # Stage 2a — Java thread exception
        # ------------------------------------------------------------------
        for line in lines:
            m = JAVA_EXCEPTION_REGEX.search(line)
            if m:
                err_type = m.group("type").split(".")[-1]
                return DetectedError(
                    category=DetectionCategory.CONFIRMED_ERROR,
                    language="Java",
                    error_type=err_type,
                    error_message=line,
                    file_path=last_frame_file,
                    line_number=last_frame_line,
                    relevant_code=code_snippet,
                    full_traceback=raw_context,
                    confidence=0.92,
                    source_application=source_app,
                    raw_context=raw_context,
                )

        # ------------------------------------------------------------------
        # Stage 2b — Go / Rust panic
        # ------------------------------------------------------------------
        for line in lines:
            m = PANIC_REGEX.search(line)
            if m:
                panic_msg = m.group("msg").strip()
                if language not in ("General", "Python", "JavaScript"):
                    effective_lang = language
                else:
                    # Unknown-panic fallback: sniff the file extension so a
                    # Rust panic isn't mislabelled (Go remains the default).
                    effective_lang = "Rust" if ".rs" in raw_context.lower() else "Go"
                return DetectedError(
                    category=DetectionCategory.CONFIRMED_ERROR,
                    language=effective_lang,
                    error_type="panic",
                    error_message=panic_msg,
                    file_path=last_frame_file,
                    line_number=last_frame_line,
                    relevant_code=code_snippet,
                    full_traceback=raw_context,
                    confidence=0.88,
                    source_application=source_app,
                    raw_context=raw_context,
                )

        # ------------------------------------------------------------------
        # Stage 2c — Compiler file:line error (non-Python/JS languages)
        # ------------------------------------------------------------------
        if last_frame_file and language not in ("Python", "JavaScript", "General"):
            for line in lines:
                m = re.search(r'\berror\s*:\s+(?P<msg>\S.+)', line, re.IGNORECASE)
                if m:
                    err_msg = m.group("msg").strip()
                    col_note = f" at column {last_frame_col}" if last_frame_col else ""
                    return DetectedError(
                        category=DetectionCategory.CONFIRMED_ERROR,
                        language=language,
                        error_type="Compiler Error",
                        error_message=err_msg + col_note,
                        file_path=last_frame_file,
                        line_number=last_frame_line,
                        column=last_frame_col,
                        relevant_code=code_snippet,
                        full_traceback=raw_context,
                        confidence=0.88,
                        source_application=source_app,
                        raw_context=raw_context,
                    )

        # ------------------------------------------------------------------
        # Stage 2d — Strict Python/JS exception line (XxxError: message)
        # ------------------------------------------------------------------
        for line in reversed(lines):
            match = EXCEPTION_REGEX.match(line)
            if match:
                err_type = match.group("type")
                err_msg = (match.group("msg") or "").strip()

                is_py_exc = err_type in PYTHON_EXCEPTIONS
                is_js_exc = err_type in JAVASCRIPT_EXCEPTIONS

                if is_py_exc or is_js_exc or err_type.endswith("Error") or err_type.endswith("Exception"):
                    effective_lang = language
                    if has_traceback_header or (last_frame_file and last_frame_file.lower().endswith(".py")):
                        effective_lang = "Python"
                    elif last_frame_file and any(last_frame_file.lower().endswith(ext) for ext in [".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"]):
                        effective_lang = "JavaScript"
                    elif is_js_exc and not is_py_exc:
                        effective_lang = "JavaScript"
                    elif is_py_exc and not is_js_exc:
                        effective_lang = "Python"
                    elif effective_lang == "General":
                        effective_lang = "Python" if has_traceback_header else "JavaScript" if is_js_exc else "Python"

                    confidence = 0.98 if (has_traceback_header or last_frame_file) else 0.88
                    return DetectedError(
                        category=DetectionCategory.CONFIRMED_ERROR,
                        language=effective_lang,
                        error_type=err_type,
                        error_message=err_msg,
                        file_path=last_frame_file,
                        line_number=last_frame_line,
                        relevant_code=code_snippet,
                        full_traceback=raw_context if (has_traceback_header or "    at " in raw_context) else "",
                        confidence=confidence,
                        source_application=source_app,
                        raw_context=raw_context,
                    )

        # ------------------------------------------------------------------
        # Stage 2e — OCR-tolerant exception fallback (colon missing/garbled)
        # Catches "SyntaxError cannot assign to True" when OCR drops the colon.
        # Confidence 0.82 (lower than strict 0.88) to reflect OCR ambiguity.
        # ------------------------------------------------------------------
        for match in OCR_TOLERANT_EXCEPTION_REGEX.finditer(raw_context):
            err_type = match.group("type")
            err_msg = match.group("msg").strip()

            # A bare code with no words ("Error 404") is an HTTP status, not
            # an exception -- require at least one letter in the message.
            if not re.search(r"[A-Za-z]", err_msg):
                continue

            # Only fire when the XxxError word starts its line (not mid-prose)
            line_start = raw_context.rfind("\n", 0, match.start()) + 1
            if not raw_context[line_start:match.end()].strip().startswith(err_type):
                continue

            is_py_exc = err_type in PYTHON_EXCEPTIONS
            is_js_exc = err_type in JAVASCRIPT_EXCEPTIONS

            if is_py_exc or is_js_exc or err_type.endswith("Error") or err_type.endswith("Exception"):
                effective_lang = language
                if has_traceback_header or (last_frame_file and last_frame_file.lower().endswith(".py")):
                    effective_lang = "Python"
                elif last_frame_file and any(last_frame_file.lower().endswith(ext) for ext in [".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"]):
                    effective_lang = "JavaScript"
                elif is_js_exc and not is_py_exc:
                    effective_lang = "JavaScript"
                elif is_py_exc and not is_js_exc:
                    effective_lang = "Python"
                elif effective_lang == "General":
                    effective_lang = "Python"

                return DetectedError(
                    category=DetectionCategory.CONFIRMED_ERROR,
                    language=effective_lang,
                    error_type=err_type,
                    error_message=err_msg,
                    file_path=last_frame_file,
                    line_number=last_frame_line,
                    relevant_code=code_snippet,
                    full_traceback=raw_context if has_traceback_header else "",
                    confidence=0.82,
                    source_application=source_app,
                    raw_context=raw_context,
                )

        # ------------------------------------------------------------------
        # Stage 3 — Universal error patterns (language-agnostic categories)
        # ------------------------------------------------------------------
        for category_label, pattern in UNIVERSAL_ERROR_PATTERNS:
            for line in reversed(lines):
                m = pattern.search(line)
                if m:
                    err_msg = line.strip()
                    confidence = 0.75 if category_label == "Compiler Error" else 0.80
                    if last_frame_col:
                        err_msg = f"at column {last_frame_col}: {err_msg}"
                    return DetectedError(
                        category=DetectionCategory.CONFIRMED_ERROR,
                        language=language,
                        error_type=category_label,
                        error_message=err_msg,
                        file_path=last_frame_file,
                        line_number=last_frame_line,
                        column=last_frame_col,
                        relevant_code=code_snippet,
                        full_traceback=raw_context,
                        confidence=confidence,
                        source_application=source_app,
                        raw_context=raw_context,
                    )

        # ------------------------------------------------------------------
        # Stage 4 — Generic confirmed patterns (existing, unchanged)
        # ------------------------------------------------------------------
        for line in reversed(lines):
            match = GENERIC_ERROR_REGEX.search(line)
            if match:
                msg = match.group("msg").strip()
                err_type = line.split(":", 1)[0].strip()
                effective_lang = language if language != "General" else ("JavaScript" if "npm" in line.lower() else "General")
                return DetectedError(
                    category=DetectionCategory.CONFIRMED_ERROR,
                    language=effective_lang,
                    error_type=err_type,
                    error_message=msg,
                    file_path=last_frame_file,
                    line_number=last_frame_line,
                    relevant_code=code_snippet,
                    full_traceback=raw_context,
                    confidence=0.85,
                    source_application=source_app,
                    raw_context=raw_context,
                )

        # ------------------------------------------------------------------
        # Stage 5 — Warning / non-zero exit (POSSIBLE ERROR, existing)
        # ------------------------------------------------------------------
        for line in reversed(lines):
            match = WARNING_REGEX.search(line)
            if match:
                return DetectedError(
                    category=DetectionCategory.POSSIBLE_ERROR,
                    language=language,
                    error_type="Warning / Non-zero Exit",
                    error_message=line,
                    confidence=0.60,
                    source_application=source_app,
                    raw_context=raw_context,
                )

        # ------------------------------------------------------------------
        # Stage 6 — No recognized error found
        # ------------------------------------------------------------------
        return DetectedError(
            category=DetectionCategory.GENERAL_CONTEXT,
            language=language,
            confidence=0.0,
            source_application=source_app,
            raw_context=raw_context,
        )


_detector: ErrorDetector | None = None


def get_error_detector() -> ErrorDetector:
    global _detector
    if _detector is None:
        _detector = ErrorDetector()
    return _detector
