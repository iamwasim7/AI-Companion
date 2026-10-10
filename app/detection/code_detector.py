"""Language and application heuristics for screen context."""

from __future__ import annotations

from app.detection.universal_patterns import LANGUAGE_SIGNALS

# Minimum number of signal hits required to commit to a language.
# A threshold of 2 prevents a single weak marker (e.g. "val " or "<-")
# from producing a false language identification.
_MIN_SIGNAL_SCORE = 2

# Tiebreaker order: when two languages tie on signal count, the language
# listed earlier here wins.  TypeScript before JavaScript so ".ts" files
# are not mis-labelled; C++ before C so ".cpp" wins over ".c" ambiguity.
_PRIORITY_ORDER = [
    "TypeScript", "JavaScript",
    "C++", "C",
    "Kotlin", "Java",
    "Rust", "Go",
    "C#", "Swift", "Dart",
    "PHP", "Ruby",
    "Python",
    "SQL", "R",
]


def detect_language(text: str) -> str:
    """Identify programming language from syntax clues, error types, and file extensions.

    Uses a signal-scoring approach across 16 languages.  Each language has a
    list of lowercase marker strings; the number of markers found in the
    lowercased input is its score.  The language with the highest score wins,
    provided it reaches the minimum threshold (_MIN_SIGNAL_SCORE = 2).

    When no language reaches the threshold, the function falls back to the
    original Python / JavaScript / HTML / CSS / SQL quick-check so that all
    existing behaviour is preserved.

    Performance: O(total signals) string containment checks -- no regex,
    no I/O, no network.  Executes in < 1 ms on typical OCR text.
    """
    lowered = text.lower()

    # --- Phase 1: signal scoring over all 16 languages ---
    scores: dict[str, int] = {}
    for lang, signals in LANGUAGE_SIGNALS.items():
        score = sum(1 for sig in signals if sig in lowered)
        if score >= _MIN_SIGNAL_SCORE:
            scores[lang] = score

    if scores:
        # Sort by (score desc, priority_order asc) for deterministic tiebreaking
        def _rank(lang: str) -> tuple:
            pri = _PRIORITY_ORDER.index(lang) if lang in _PRIORITY_ORDER else 99
            return (-scores[lang], pri)

        winner = min(scores, key=_rank)
        return winner

    # --- Phase 2: fallback quick-checks (original logic, unchanged) ---
    # These fire when no language scored >=2 -- e.g. a single ".py" extension
    # hit or a lone exception name on an otherwise blank screen.

    # Definite JS/TS clues
    js_specific = [
        ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
        "node:internal", "npm err!",
        "referenceerror", "rangeerror", "urierror", "evalerror",
        "uncaught referenceerror", "uncaught typeerror", "uncaught syntaxerror",
        "console.log", "const ", "let ", "function(", "function ",
        "export default", "module.exports", "require(",
    ]
    # Definite Python clues
    python_specific = [
        ".py", "traceback (most recent call last)",
        "nameerror", "valueerror", "indentationerror", "zerodivisionerror",
        "modulenotfounderror", "attributeerror", "filenotfounderror",
        "unboundlocalerror", "import numpy", "import pandas",
        "import os", "import sys", "def ", "def __init__", "if __name__ ==",
    ]

    has_js = any(m in lowered for m in js_specific)
    has_py = any(m in lowered for m in python_specific)

    if has_js and not has_py:
        return "JavaScript"
    if has_py and not has_js:
        return "Python"
    if has_js and has_py:
        has_js_ext = any(ext in lowered for ext in [".js", ".ts", ".jsx", ".tsx"])
        has_py_ext = ".py" in lowered
        if has_js_ext and not has_py_ext:
            return "JavaScript"
        if has_py_ext and not has_js_ext:
            return "Python"
        if "traceback (most recent call last)" in lowered:
            return "Python"
        return "JavaScript" if "node:internal" in lowered or "npm err!" in lowered else "Python"

    # Ambiguous shared errors (TypeError, SyntaxError) without specific markers
    if "typeerror" in lowered or "syntaxerror" in lowered:
        if "    at " in text or "at object." in lowered or "at module." in lowered:
            return "JavaScript"
        return "Python"

    # HTML / CSS
    if "<!doctype html>" in lowered or "<html" in lowered:
        return "HTML"
    if "div {" in lowered or "margin:" in lowered:
        return "CSS"

    # SQL
    if any(m in lowered for m in ["select ", "insert into ", "create table ", "drop table "]):
        return "SQL"

    return "General"



def detect_application(text: str) -> str:
    """Determine the source application (VS Code, terminal, or browser)."""
    lowered = text.lower()

    if any(term in lowered for term in ["ps c:\\", "powershell", "cmd.exe", "c:\\users\\", "bash$", "zsh$"]):
        return "Terminal / PowerShell"
    if any(term in lowered for term in ["visual studio code", "vs code", "workbench.action"]):
        return "VS Code"
    if any(term in lowered for term in ["localhost:", "127.0.0.1:", "http://", "https://"]):
        return "Browser / Web"

    return "Editor / Terminal"
