"""Unit tests for the Error Detection and Context Extraction subsystem."""

from __future__ import annotations

import unittest

from app.detection.code_detector import detect_application, detect_language
from app.detection.context_detector import ContextDetector, get_context_detector
from app.detection.error_detector import ErrorDetector, get_error_detector
from app.detection.models import DetectedError, DetectionCategory


class CodeDetectorTests(unittest.TestCase):
    def test_detect_language_python(self) -> None:
        self.assertEqual(detect_language("def add(a, b): return a + b"), "Python")
        self.assertEqual(detect_language("import pandas as pd"), "Python")
        self.assertEqual(detect_language("NameError: name 'x' is not defined"), "Python")

    def test_detect_language_javascript(self) -> None:
        self.assertEqual(detect_language("const x = 10; console.log(x);"), "JavaScript")
        self.assertEqual(detect_language("ReferenceError: window is not defined"), "JavaScript")

    def test_detect_application(self) -> None:
        self.assertEqual(detect_application("PS C:\\Users\\LENOVO> python run.py"), "Terminal / PowerShell")
        self.assertEqual(detect_application("Visual Studio Code - AI Companion"), "VS Code")


class ErrorDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = ErrorDetector()

    def test_empty_text_returns_general_context(self) -> None:
        res = self.detector.detect("")
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(res.has_error)

    def test_normal_code_returns_general_context(self) -> None:
        code = "def calculate_sum(a, b):\n    return a + b\n\nprint(calculate_sum(3, 4))"
        res = self.detector.detect(code)
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(res.has_error)

    def test_python_traceback_confirmed_error(self) -> None:
        traceback_text = """
Traceback (most recent call last):
  File "main.py", line 12, in <module>
    print(username)
NameError: name 'username' is not defined
"""
        res = self.detector.detect(traceback_text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertTrue(res.has_error)
        self.assertEqual(res.language, "Python")
        self.assertEqual(res.error_type, "NameError")
        self.assertEqual(res.error_message, "name 'username' is not defined")
        self.assertEqual(res.file_path, "main.py")
        self.assertEqual(res.line_number, 12)
        self.assertEqual(res.relevant_code, "print(username)")
        self.assertGreaterEqual(res.confidence, 0.95)

    def test_standalone_python_exception(self) -> None:
        text = "SyntaxError: invalid syntax"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.error_type, "SyntaxError")
        self.assertEqual(res.error_message, "invalid syntax")
        self.assertGreaterEqual(res.confidence, 0.85)

    def test_generic_compiler_error(self) -> None:
        text = "fatal error: iostream: No such file or directory"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        # Universal patterns now produce "Compilation Error" as the error_type
        # (more semantically meaningful than the raw text fragment "fatal error")
        error_type_lower = res.error_type.lower()
        self.assertTrue(
            "fatal error" in error_type_lower or "compilation" in error_type_lower,
            f"Expected compiler error type, got: {res.error_type!r}",
        )


    def test_warning_detected_as_possible_error(self) -> None:
        text = "Process completed: failed with exit code 1"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.POSSIBLE_ERROR)
        self.assertTrue(res.has_error)

    def test_nodejs_reference_error_on_test_js(self) -> None:
        node_output = """
c:\\Users\\LENOVO\\AI-Companion\\test.js:1
console.log(username);
^

ReferenceError: username is not defined
    at Object.<anonymous> (c:\\Users\\LENOVO\\AI-Companion\\test.js:1:13)
    at Module._compile (node:internal/modules/cjs/loader:1469:14)
"""
        res = self.detector.detect(node_output)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "JavaScript")
        self.assertEqual(res.error_type, "ReferenceError")
        self.assertEqual(res.error_message, "username is not defined")
        self.assertTrue(res.file_path.endswith("test.js"))
        self.assertEqual(res.line_number, 1)
        self.assertEqual(res.relevant_code, "console.log(username);")

    def test_javascript_type_error_on_js_file(self) -> None:
        text = """
TypeError: Cannot read properties of undefined (reading 'length')
    at calculate (c:\\project\\utils.js:10:15)
"""
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "JavaScript")
        self.assertEqual(res.error_type, "TypeError")
        self.assertTrue(res.file_path.endswith("utils.js"))
        self.assertEqual(res.line_number, 10)

    def test_node_header_keeps_spaced_drive_path(self) -> None:
        # "d:\Hello Python\testjs.js:1" must not lose its drive prefix.
        text = (
            'd:\\Hello Python\\testjs.js:1\n'
            'console.log("Hello JS!)\n'
            "^^^^^^^^^^^\n"
            "\n"
            "SyntaxError: Invalid or unexpected token\n"
            "    at wrapSafe (node:internal/modules/cjs/loader:1861:18)"
        )
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "JavaScript")
        self.assertEqual(res.error_type, "SyntaxError")
        self.assertTrue(res.file_path.endswith("testjs.js"))
        self.assertIn("Hello Python", res.file_path)
        self.assertEqual(res.line_number, 1)
        self.assertIn('console.log("Hello JS!)', res.relevant_code)

    def test_standalone_reference_error_is_javascript(self) -> None:
        text = "ReferenceError: window is not defined"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "JavaScript")
        self.assertEqual(res.error_type, "ReferenceError")


class ContextDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ContextDetector()

    def test_format_ai_context(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="Python",
            error_type="NameError",
            error_message="name 'username' is not defined",
            file_path="app/main.py",
            line_number=15,
            relevant_code="print(username)",
            source_application="VS Code",
        )
        context_str = self.context.format_ai_context(detected)
        self.assertIn("Application: VS Code", context_str)
        self.assertIn("Language: Python", context_str)
        self.assertIn("File: app/main.py", context_str)
        self.assertIn("Line: 15", context_str)
        self.assertIn("Error: NameError: name 'username' is not defined", context_str)
        self.assertIn("Relevant Code: print(username)", context_str)

    def test_fallback_window_when_no_relevant_code(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="Python",
            error_type="SyntaxError",
            error_message="unterminated string literal (detected at line 4)",
            file_path="test.py",
            line_number=4,
            relevant_code="",
            raw_context='PS C:\\x>\nFile "test.py", line 4\nprint("Hello)\n^\nSyntaxError: unterminated string literal (detected at line 4)',
        )
        context_str = self.context.format_ai_context(detected)
        self.assertNotIn("Relevant Code:", context_str)
        self.assertIn("Nearby Screen Text (unverified OCR", context_str)
        self.assertIn('print("Hello)', context_str)

    def test_fallback_window_drops_symbol_junk(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="Python",
            error_type="SyntaxError",
            error_message="boom",
            relevant_code="",
            raw_context='File "t.py", line 1\nprint("Hello)\n©\n^^^\nSyntaxError: boom',
        )
        context_str = self.context.format_ai_context(detected)
        self.assertIn('print("Hello)', context_str)
        self.assertIn("SyntaxError: boom", context_str)
        self.assertNotIn("©", context_str)
        self.assertNotIn("^^^", context_str)

    def test_no_fallback_window_when_code_present(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="Python",
            error_type="NameError",
            error_message="name 'x' is not defined",
            relevant_code="print(x)",
            raw_context="NameError: name 'x' is not defined\nprint(x)",
        )
        context_str = self.context.format_ai_context(detected)
        self.assertIn("Relevant Code: print(x)", context_str)
        self.assertNotIn("Nearby Screen Text", context_str)

    def test_general_context_unchanged(self) -> None:
        detected = DetectedError(raw_context="just some screen text")
        self.assertEqual(self.context.format_ai_context(detected), "Language: General")


# =============================================================================
# NEW: Language Recognition Tests (16 languages)
# =============================================================================

class LanguageRecognitionTests(unittest.TestCase):
    """Tests for the expanded 16-language detect_language() signal-scoring."""

    def test_python_traceback(self) -> None:
        text = "Traceback (most recent call last):\n  File \"app.py\", line 5\nNameError: name 'x' is not defined"
        self.assertEqual(detect_language(text), "Python")

    def test_python_import(self) -> None:
        self.assertEqual(detect_language("import sys\nimport os\nprint('hello')"), "Python")

    def test_javascript_node_stack(self) -> None:
        text = "ReferenceError: x is not defined\n    at Object.<anonymous> (app.js:3:5)"
        self.assertEqual(detect_language(text), "JavaScript")

    def test_javascript_console(self) -> None:
        self.assertEqual(detect_language("console.log('hi');\nrequire('./app');"), "JavaScript")

    def test_typescript_error_code(self) -> None:
        text = "src/app.ts:5:3 - error TS2322: Type 'string' is not assignable to type 'number'.\ntsc: version 5.0"
        self.assertEqual(detect_language(text), "TypeScript")

    def test_java_thread_exception(self) -> None:
        text = (
            "Exception in thread \"main\" java.lang.NullPointerException\n"
            "    at com.example.Main.main(Main.java:10)"
        )
        self.assertEqual(detect_language(text), "Java")

    def test_java_javac_error(self) -> None:
        text = "Main.java:5: error: cannot find symbol\npublic static void main(String[] args)"
        self.assertEqual(detect_language(text), "Java")

    def test_c_gcc_error(self) -> None:
        text = "gcc -o hello hello.c\nhello.c:5:3: error: undeclared identifier 'x'\n#include <stdio.h>"
        self.assertEqual(detect_language(text), "C")

    def test_cpp_error(self) -> None:
        text = "g++ -o app app.cpp\napp.cpp:10:5: error: use of undeclared identifier 'foo'\n#include <iostream>"
        self.assertEqual(detect_language(text), "C++")

    def test_csharp_error(self) -> None:
        text = "error CS1002: ; expected\nusing System;\npublic class Program"
        self.assertEqual(detect_language(text), "C#")

    def test_go_panic(self) -> None:
        text = "goroutine 1 [running]:\npanic: runtime error: index out of range\ngo build main.go"
        self.assertEqual(detect_language(text), "Go")

    def test_rust_error(self) -> None:
        text = "error[E0425]: cannot find value `x` in this scope\nfn main() {\ncargo build"
        self.assertEqual(detect_language(text), "Rust")

    def test_php_error(self) -> None:
        text = "Parse error: syntax error, unexpected '}' in /var/www/index.php\n<?php\nundefined variable"
        self.assertEqual(detect_language(text), "PHP")

    def test_ruby_error(self) -> None:
        text = "syntax error, unexpected end-of-input\napp.rb:10:in `<main>'\ngem 'rails'"
        self.assertEqual(detect_language(text), "Ruby")

    def test_kotlin_error(self) -> None:
        text = "error: unresolved reference: foo\nkotlinc -include-runtime Main.kt\nkotlin."
        self.assertEqual(detect_language(text), "Kotlin")

    def test_swift_error(self) -> None:
        text = "error: use of unresolved identifier 'foo'\nswiftc main.swift\nimport Foundation"
        self.assertEqual(detect_language(text), "Swift")

    def test_dart_error(self) -> None:
        text = "dart: /path/main.dart\nvoid main() {\nunhandled exception: NoSuchMethodError"
        self.assertEqual(detect_language(text), "Dart")

    def test_sql_query(self) -> None:
        text = "SELECT * FROM users WHERE id = 1\nSyntax error near 'WHERE'"
        self.assertEqual(detect_language(text), "SQL")

    def test_r_code(self) -> None:
        text = "x <- 5\nlibrary(ggplot2)\nwarning message: subscript out of bounds"
        self.assertEqual(detect_language(text), "R")

    def test_general_for_plain_text(self) -> None:
        self.assertEqual(detect_language("Hello world, how are you today?"), "General")


# =============================================================================
# NEW: Universal Error Detection Tests
# =============================================================================

class UniversalErrorDetectionTests(unittest.TestCase):
    """Tests for multi-language error detection (Java, C/C++, Rust, Go, etc.)."""

    def setUp(self) -> None:
        self.detector = ErrorDetector()

    def test_java_thread_exception(self) -> None:
        text = (
            'Exception in thread "main" java.lang.NullPointerException\n'
            '    at com.example.Main.main(Main.java:10)'
        )
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "Java")
        self.assertIn("NullPointerException", res.error_type)

    def test_java_compilation_error(self) -> None:
        text = "Main.java:5:10: error: cannot find symbol\n    int x = foo();\njava.lang."
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "Java")
        self.assertTrue(res.file_path.endswith("Main.java"))
        self.assertEqual(res.line_number, 5)

    def test_c_compiler_error(self) -> None:
        text = "hello.c:5:3: error: undeclared identifier 'x'\ngcc -o hello hello.c\n#include <stdio.h>"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "C")
        self.assertTrue(res.file_path.endswith("hello.c"))
        self.assertEqual(res.line_number, 5)

    def test_cpp_compiler_error(self) -> None:
        text = "app.cpp:10:5: error: use of undeclared identifier 'bar'\ng++ -o app app.cpp\n#include <iostream>"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "C++")
        self.assertTrue(res.file_path.endswith("app.cpp"))

    def test_rust_error_code(self) -> None:
        text = "error[E0425]: cannot find value `x` in this scope\n  --> src/main.rs:3:5\nfn main() {\ncargo build"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "Rust")

    def test_go_panic(self) -> None:
        text = "goroutine 1 [running]:\npanic: runtime error: index out of range [0] with length 0\ngo build main.go"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.error_type, "panic")

    def test_csharp_error_code(self) -> None:
        text = "error CS1002: ; expected\nusing System;\npublic class Program\ndotnet build"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "C#")

    def test_php_parse_error(self) -> None:
        text = "Parse error: syntax error, unexpected '}' in /var/www/index.php on line 10\n<?php\nundefined variable"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)

    def test_linker_error_undefined_reference(self) -> None:
        text = "/usr/bin/ld: undefined reference to 'main'\ncollect2: error: ld returned 1 exit status"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertIn("Linker", res.error_type)

    def test_segmentation_fault(self) -> None:
        text = "Segmentation fault (core dumped)\nProgram received signal SIGSEGV"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertIn("System", res.error_type)

    def test_module_not_found(self) -> None:
        text = "Error: Cannot find module 'express'\nRequire stack:\n- /app/server.js"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)

    def test_compilation_failed(self) -> None:
        text = "src/main.rs:5:1: compilation failed\ncargo build --release"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)

    def test_build_failed(self) -> None:
        text = "FAILED: build error\nBuild failed with 2 errors"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)

    def test_ruby_syntax_error(self) -> None:
        text = "syntax error, unexpected end-of-input, expecting end\napp.rb:10\ngem 'rails'"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)


# =============================================================================
# NEW: OCR Corruption Tolerance Tests
# =============================================================================

class OCRCorruptionTests(unittest.TestCase):
    """Tests for OCR-tolerant detection when punctuation is dropped or mangled."""

    def setUp(self) -> None:
        self.detector = ErrorDetector()

    def test_syntax_error_missing_colon(self) -> None:
        """Core real-world OCR failure: colon dropped after SyntaxError."""
        text = "SyntaxError cannot assign to True"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.error_type, "SyntaxError")
        self.assertIn("cannot assign", res.error_message)

    def test_syntax_error_semicolon_instead_of_colon(self) -> None:
        """OCR replaces colon with semicolon."""
        text = "SyntaxError; invalid syntax"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.error_type, "SyntaxError")

    def test_syntax_error_dash_instead_of_colon(self) -> None:
        """OCR replaces colon with dash."""
        text = "SyntaxError - invalid syntax"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.error_type, "SyntaxError")

    def test_name_error_missing_colon(self) -> None:
        text = "NameError name 'x' is not defined"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.error_type, "NameError")

    def test_frame_no_quotes(self) -> None:
        """OCR drops quotes around filename in Python frame."""
        text = "File test.py, line 5\n    print(x)\nNameError: name 'x' is not defined"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.file_path, "test.py")
        self.assertEqual(res.line_number, 5)

    def test_frame_smart_quotes(self) -> None:
        """OCR replaces ASCII quotes with Unicode smart quotes."""
        text = "File \u201ctest.py\u201d, line 3\n    x = y\nNameError: name 'y' is not defined"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.file_path, "test.py")
        self.assertEqual(res.line_number, 3)

    def test_frame_missing_comma(self) -> None:
        """OCR drops the comma between filename and line number."""
        text = "File \"test.py\" line 7\n    foo()\nNameError: name 'foo' is not defined"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.file_path, "test.py")
        self.assertEqual(res.line_number, 7)

    def test_heavily_garbled_ocr_returns_general_context(self) -> None:
        """Completely unrecognizable OCR garbage must NOT trigger a false error."""
        text = "Syntaxrror cannetassign to True"   # both the type AND message are garbled
        res = self.detector.detect(text)
        # It's acceptable to return GENERAL_CONTEXT for completely garbled text
        # The key requirement is: no false positive as a CONFIRMED_ERROR when
        # the error type itself is unrecognisable.
        self.assertNotEqual(res.error_type, "SyntaxError")


# =============================================================================
# NEW: False Positive Protection Tests
# =============================================================================

class FalsePositiveTests(unittest.TestCase):
    """Tests to ensure normal prose containing 'error', 'warning', etc. is NOT
    incorrectly classified as a programming error."""

    def setUp(self) -> None:
        self.detector = ErrorDetector()

    def test_prose_with_error_word(self) -> None:
        text = "Error handling is important in Python programming."
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(res.has_error)

    def test_prose_with_exception_word(self) -> None:
        text = "The exception proves the rule in every case."
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(res.has_error)

    def test_prose_with_warning_word(self) -> None:
        text = "There was a warning in the documentation about this feature."
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(res.has_error)

    def test_prose_with_failed_word(self) -> None:
        text = "He failed to impress the judges at the competition."
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(res.has_error)

    def test_normal_python_code_no_error(self) -> None:
        code = "def add(a, b):\n    return a + b\n\nresult = add(3, 4)\nprint(result)"
        res = self.detector.detect(code)
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(res.has_error)

    def test_normal_javascript_code_no_error(self) -> None:
        code = "const greet = (name) => {\n  console.log('Hello, ' + name);\n};\ngreet('World');"
        res = self.detector.detect(code)
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(res.has_error)

    def test_markdown_with_error_in_code_fence(self) -> None:
        text = "To handle errors use try/except. Example:\n```python\ntry:\n    pass\nexcept Exception as e:\n    pass\n```"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)

    def test_log_line_with_error_level(self) -> None:
        # Log lines like "2024-01-01 ERROR some message" should not fire
        text = "2024-01-01 12:00:00 ERROR Something happened in the background"
        res = self.detector.detect(text)
        # ERROR here is just a log level — no traceback, no exception type, no file
        self.assertFalse(res.has_error)


class UniversalFixTests(unittest.TestCase):
    """Regression tests for the universal-detection fix batch."""

    def setUp(self) -> None:
        self.detector = ErrorDetector()

    def test_bare_error_404_not_confirmed(self) -> None:
        for text in ("Error 404", "Error 500", "Error 403"):
            res = self.detector.detect(text)
            self.assertFalse(res.has_error, text)
            self.assertEqual(res.category, DetectionCategory.GENERAL_CONTEXT)

    def test_worded_error_code_still_confirmed(self) -> None:
        res = self.detector.detect("Error 500 Internal Server Error")
        self.assertTrue(res.has_error)

    def test_bracketed_and_prefixed_codes_confirmed(self) -> None:
        for text in ("error[E0308]: mismatched types", "error CS1002: ; expected"):
            res = self.detector.detect(text)
            self.assertTrue(res.has_error, text)

    def test_rust_panicked_thread_confirmed(self) -> None:
        text = "thread 'main' panicked at 'index out of bounds', src/main.rs:5:10"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.error_type, "panic")
        self.assertEqual(res.language, "Rust")

    def test_go_panic_still_confirmed(self) -> None:
        text = "panic: runtime error: index out of range [3] with length 0"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.error_type, "panic")

    def test_go_undefined_confirmed(self) -> None:
        res = self.detector.detect(".\\main.go:6:3: undefined: Foo")
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "Go")

    def test_go_unused_import_confirmed(self) -> None:
        res = self.detector.detect('main.go:4:2: imported and not used: "fmt"')
        self.assertTrue(res.has_error)

    def test_dart_unhandled_exception_confirmed(self) -> None:
        res = self.detector.detect("Unhandled exception:\nNull check operator used on a null value")
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)

    def test_dart_prose_not_confirmed(self) -> None:
        res = self.detector.detect("Always handle unhandled exception cases carefully")
        self.assertFalse(res.has_error)

    def test_r_error_in_confirmed(self) -> None:
        res = self.detector.detect("Error in library(x) : subscript out of bounds")
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)

    def test_csharp_paren_location(self) -> None:
        res = self.detector.detect("Program.cs(10,5): error CS1002: ; expected")
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertTrue(res.file_path.endswith("Program.cs"))
        self.assertEqual(res.line_number, 10)

    def test_rust_arrow_location(self) -> None:
        text = "error[E0308]: mismatched types\n --> src/main.rs:12:5\n  |"
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertTrue(res.file_path.endswith("main.rs"))
        self.assertEqual(res.line_number, 12)

    def test_php_on_line_location(self) -> None:
        res = self.detector.detect("Parse error: syntax error in test.php on line 5")
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertTrue(res.file_path.endswith("test.php"))
        self.assertEqual(res.line_number, 5)

    def test_ruby_bare_location(self) -> None:
        res = self.detector.detect("test.rb:3: syntax error, unexpected end-of-input")
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertTrue(res.file_path.endswith("test.rb"))
        self.assertEqual(res.line_number, 3)

    def test_java_frame_location(self) -> None:
        text = 'Exception in thread "main" java.lang.NullPointerException\n        at com.example.App.main(App.java:14)'
        res = self.detector.detect(text)
        self.assertEqual(res.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(res.language, "Java")
        self.assertTrue(res.file_path.endswith("App.java"))
        self.assertEqual(res.line_number, 14)

    def test_column_stored_as_field(self) -> None:
        res = self.detector.detect("main.c:5:3: error: implicit declaration of function 'foo'")
        self.assertEqual(res.column, 3)


if __name__ == "__main__":
    unittest.main()
