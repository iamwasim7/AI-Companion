"""Universal patterns and language signal tables for multi-language error detection.

This module is pure data -- no logic, no Qt, no I/O.
Import LANGUAGE_SIGNALS, UNIVERSAL_ERROR_PATTERNS, and the compiled regexes
from here to keep code_detector.py and error_detector.py clean and extensible.

Adding a new language later requires only adding an entry to LANGUAGE_SIGNALS.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Language signal tables
# ---------------------------------------------------------------------------
# Each entry maps a language name to a list of lowercase marker strings.
# Signals are checked with `marker in text.lower()`.
# Higher-specificity signals are listed first (file extensions, unique exception
# names, runtime commands) before weaker context clues.
#
# Scoring: the number of matching signals is counted. The detect_language()
# function in code_detector.py requires >= 2 matches to commit to a language,
# preventing single-marker false positives.

LANGUAGE_SIGNALS: dict[str, list[str]] = {
    "Python": [
        ".py", ".pyw",
        "traceback (most recent call last)",
        "nameerror", "valueerror", "indentationerror", "zerodivisionerror",
        "modulenotfounderror", "attributeerror", "filenotfounderror",
        "unboundlocalerror", "recursionerror",
        "import numpy", "import pandas", "import os", "import sys",
        "def __init__", "if __name__ ==",
        ">>> ",
    ],
    "JavaScript": [
        ".js", ".mjs", ".cjs", ".jsx",
        "node:internal", "npm err!",
        "referenceerror", "rangeerror", "urierror", "evalerror",
        "aggregateerror",
        "console.log", "require(", "module.exports", "export default",
        "unhandledpromiserejection",
    ],
    "TypeScript": [
        ".ts", ".tsx",
        "error ts", "tsc:", "ts-node", "tsconfig.json",
        "type 'undefined'", "type 'null'",
    ],
    "Java": [
        ".java",
        "exception in thread",
        "at java.", "at sun.", "at com.", "at org.",
        "javac", "java.lang.", "java.io.", "java.util.",
        "nullpointerexception", "arrayindexoutofboundsexception",
        "classnotfoundexception", "illegalargumentexception",
        "public static void main",
    ],
    "C": [
        ".c",
        "gcc", "clang",
        "#include <stdio.h>", "#include <stdlib.h>",
        "segmentation fault",
        "undefined reference",
        "implicit declaration of function",
    ],
    "C++": [
        ".cpp", ".cc", ".cxx",
        "g++", "clang++",
        "#include <iostream>", "#include <vector>", "#include <string>",
        "std::", "std::cout", "std::string",
        "unresolved external symbol",
        "no matching function for call",
    ],
    "C#": [
        ".cs",
        "error cs", "dotnet", "csc:",
        "system.nullreferenceexception", "system.exception",
        "using system", "namespace ", "public class",
        "nullreferenceexception",
    ],
    "Go": [
        ".go",
        "goroutine ", "panic:", "go build", "go run",
        "undefined:", "cannot use ",
        "func main()", "package main",
        "imported and not used",
    ],
    "Rust": [
        ".rs",
        "error[e", "rustc", "cargo build", "cargo run",
        "fn main()", "fn main() {",
        "cannot borrow", "mismatched types",
        "use of undeclared", "borrow checker",
    ],
    "PHP": [
        ".php",
        "parse error:", "php parse", "<?php",
        "undefined variable", "call to undefined function",
        "fatal error:", "warning: undefined",
    ],
    "Ruby": [
        ".rb",
        "syntax error, unexpected",
        "nomethoderror",
        "gem ",
    ],
    "Kotlin": [
        ".kt", ".kts",
        "kotlinc",
        "error: unresolved reference",
        "fun main(",
        "kotlin.",
    ],
    "Swift": [
        ".swift",
        "swiftc",
        "error: use of unresolved identifier",
        "import foundation", "import uikit", "import swiftui",
        "could not compile",
    ],
    "Dart": [
        ".dart",
        "dart:", "flutter",
        "void main(", "nosuchmethod", "dartanalyzer",
        "unhandled exception:",
    ],
    "SQL": [
        "select ", "insert into ", "create table ", "drop table ",
        "syntax error near", "alter table ",
        "where ", "group by ", "order by ",
    ],
    "R": [
        "<-",
        "library(",
        "warning message:",
        "subscript out of bounds",
        "error in ",
    ],
}

# ---------------------------------------------------------------------------
# Universal error pattern table
# ---------------------------------------------------------------------------
# A list of (category_label, compiled_regex) tuples.
# Patterns are checked in the order listed -- most specific first.
# The detector iterates this list when the Python/JS-specific passes all fail.
#
# Performance: all regexes are compiled once at module import time.
# At detection time only string matching occurs -- no extra I/O, AI, or OCR.

UNIVERSAL_ERROR_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Compilation errors with error codes (Rust, C#, Java, TS, MSVC).
    # Requires a bracketed ([E0308]), letter-prefixed (CS1002, TS2322),
    # or worded ("Error 500 Internal Server Error") code -- a bare
    # "Error 404" (HTTP status, common on dev screens) must NOT confirm.
    (
        "Compilation Error",
        re.compile(
            r"\berror\s*(?:\[[A-Z]{0,3}\d{3,}\]"
            r"|\d{3}\s+[A-Za-z]"
            r"|(?=[A-Z]{1,3}\d{3,}))",
            re.IGNORECASE,
        ),
    ),
    # Fatal compiler/linker errors
    (
        "Compilation Error",
        re.compile(
            r"\bfatal\s+error\b",
            re.IGNORECASE,
        ),
    ),
    # Compilation failure summary lines
    (
        "Compilation Error",
        re.compile(
            r"\bcompilation\s+(?:failed|terminated)\b",
            re.IGNORECASE,
        ),
    ),
    # Build failure
    (
        "Build Error",
        re.compile(
            r"\bbuild\s+(?:failed|error)\b",
            re.IGNORECASE,
        ),
    ),
    # Linker / reference errors
    (
        "Linker/Reference Error",
        re.compile(
            r"\b(?:undefined\s+reference\s+to|unresolved\s+external\s+symbol)\b",
            re.IGNORECASE,
        ),
    ),
    # Name / identifier not found (incl. Go's "undefined: Foo" form)
    (
        "Name/Reference Error",
        re.compile(
            r"\b(?:cannot\s+find\s+(?:symbol|value|name|type)"
            r"|undeclared\s+(?:identifier|variable)"
            r"|unresolved\s+(?:reference|name|identifier)"
            r"|is\s+not\s+defined"
            r"|undefined\s*:\s*\S+"
            r"|was\s+not\s+declared\s+in\s+this\s+scope)\b",
            re.IGNORECASE,
        ),
    ),
    # Declared/imported but not used (Go: "imported and not used")
    (
        "Unused Import/Variable",
        re.compile(
            r"\b(?:imported\s+and\s+not\s+used"
            r"|declared\s+(?:and\s+|but\s+)not\s+used"
            r"|defined\s+but\s+not\s+used)\b",
            re.IGNORECASE,
        ),
    ),
    # Type mismatch / incompatibility
    (
        "Type Error",
        re.compile(
            r"\b(?:type\s+mismatch"
            r"|incompatible\s+types"
            r"|cannot\s+convert\s+.{1,40}\s+to"
            r"|expected\s+.{1,40}\s+found)\b",
            re.IGNORECASE,
        ),
    ),
    # Import / module / package not found
    (
        "Module/Import Error",
        re.compile(
            r"\b(?:module\s+not\s+found"
            r"|cannot\s+find\s+module"
            r"|package\s+not\s+found"
            r"|no\s+module\s+named"
            r"|no\s+such\s+file\s+or\s+directory"
            r"|could\s+not\s+find\s+package)\b",
            re.IGNORECASE,
        ),
    ),
    # Runtime / system errors
    (
        "Runtime/System Error",
        re.compile(
            r"\b(?:segmentation\s+fault"
            r"|access\s+violation"
            r"|out\s+of\s+memory"
            r"|stack\s+overflow"
            r"|connection\s+refused"
            r"|permission\s+denied"
            r"|killed\s+by\s+signal)\b",
            re.IGNORECASE,
        ),
    ),
    # Syntax errors (multi-language phrasing)
    (
        "Syntax Error",
        re.compile(
            r"\b(?:parse\s+error"
            r"|unexpected\s+token"
            r"|unexpected\s+(?:end\s+of\s+input|identifier|keyword)"
            r"|expected\s+expression"
            r"|invalid\s+syntax"
            r"|syntax\s+error)\b",
            re.IGNORECASE,
        ),
    ),
    # Go / Rust panic (incl. Rust's "panicked at" phrasing)
    (
        "Runtime Exception",
        re.compile(
            r"\bpanic(?:ked)?\b.{0,3}(?:runtime\s+error|interface|nil\s+pointer|index\s+out|out\s+of\s+range)?",
            re.IGNORECASE,
        ),
    ),
    # Dart / Flutter unhandled exception (colon required -- bare prose
    # mentioning "unhandled exception" must not confirm)
    (
        "Runtime Exception",
        re.compile(
            r"\bunhandled\s+exception\s*:",
            re.IGNORECASE,
        ),
    ),
    # R runtime error ("Error in library(x) : ...")
    (
        "Runtime Error",
        re.compile(
            r"\berror\s+in\s+[A-Za-z_][\w.]*\s*\(",
            re.IGNORECASE,
        ),
    ),
    # Java / JVM thread exception header
    (
        "Runtime Exception",
        re.compile(
            r"\bException\s+in\s+thread\b",
            re.IGNORECASE,
        ),
    ),
    # Generic "error: <text>" compiler line -- low specificity, placed last
    (
        "Compiler Error",
        re.compile(
            r"(?:^|\s)error\s*:\s+\S.{4,}",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
]

# ---------------------------------------------------------------------------
# OCR-tolerant Python traceback frame regex
# ---------------------------------------------------------------------------
# Extends the strict FRAME_REGEX to tolerate:
#   - Missing or misread quotes (straight, smart, or absent)
#   - Missing comma before "line"
#   - Smart/curly Unicode quotes

FRAME_REGEX_TOLERANT = re.compile(
    r'File\s+'
    r'[\"\u201c\u2018\']?'
    r'(?P<file>[^\"\u201d\u2019\',\n]+\.(?:py|pyw))'
    r'[\"\u201d\u2019\']?'
    r'\s*,?\s*'
    r'line\s+(?P<line>\d+)',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# OCR-tolerant exception line regex (fallback when colon is missing/garbled)
# ---------------------------------------------------------------------------
# Matches: "SyntaxError cannot assign to True"  (no colon)
#          "SyntaxError; cannot assign"          (semicolon)
#          "SyntaxError - bad input"             (dash)
# Requires capitalized XxxError/Exception/Warning + 3+ char message.

OCR_TOLERANT_EXCEPTION_REGEX = re.compile(
    r'^(?:Uncaught\s+)?'
    r'(?:[A-Za-z_][\w.]*\.)?'
    r'(?P<type>[A-Z][A-Za-z0-9_]*(?:Error|Exception|Warning))'
    r'[\s;:\-\u2013\u2014]+(?P<msg>[^\n]{3,})',
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Compiler file:line[:col]: error  (GCC, Clang, Rust, Go, Java, C#)
# ---------------------------------------------------------------------------

COMPILER_FILE_LINE_REGEX = re.compile(
    r'^(?P<file>[^\s:]+\.(?:c|cpp|cc|cxx|h|hpp|rs|go|java|cs|kt|swift|php|rb|dart|ts|tsx|js|jsx))'
    r':(?P<line>\d+)(?::(?P<col>\d+))?'
    r':\s*(?:error|warning|note)\b',
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Java thread exception header
# ---------------------------------------------------------------------------

JAVA_EXCEPTION_REGEX = re.compile(
    r'Exception\s+in\s+thread\s+["\']?\S+["\']?\s+'
    r'(?P<type>(?:[\w$.]+\.)*[A-Z]\w*(?:Exception|Error))',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Go / Rust panic (incl. Rust's "thread 'main' panicked at ..." phrasing)
# ---------------------------------------------------------------------------

PANIC_REGEX = re.compile(
    r'\bpanic(?:ked)?\b[:\s]+(?P<msg>[^\n]{3,})',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Extra location formats (fill-in only: the detector applies these solely
# when no location was found by the primary scanners above)
# ---------------------------------------------------------------------------

# MSVC / Roslyn "Program.cs(10,5)" paren format
CS_PAREN_REGEX = re.compile(
    r'(?P<file>[^\s():]+\.cs)\((?P<line>\d+)(?:,(?P<col>\d+))?\)',
    re.IGNORECASE,
)

# Rust "--> src/main.rs:12:5" arrow prefix (no error suffix on the line)
RUST_ARROW_REGEX = re.compile(
    r'^\s*-->\s*(?P<file>[^\s:]+\.rs):(?P<line>\d+)(?::(?P<col>\d+))?',
    re.IGNORECASE | re.MULTILINE,
)

# Java stack frame "at com.example.App.main(App.java:14)"
JAVA_FRAME_REGEX = re.compile(
    r'^\s*at\s+(?:[^\s()]*\()?(?P<file>[^\s()]+\.java):(?P<line>\d+)\)?',
    re.IGNORECASE | re.MULTILINE,
)

# Bare "test.php on line 5" / "test.rb:3:" (no ": error" suffix)
BARE_FILE_LINE_REGEX = re.compile(
    r'(?P<file>[^\s():]+\.(?:php|rb)):(?P<line>\d+)',
    re.IGNORECASE,
)
ON_LINE_REGEX = re.compile(
    r'on\s+line\s+(?P<line>\d+)',
    re.IGNORECASE,
)
PHP_RB_FILE_REGEX = re.compile(
    r'(?P<file>[^\s():,;\'"]+\.(?:php|rb))',
    re.IGNORECASE,
)
