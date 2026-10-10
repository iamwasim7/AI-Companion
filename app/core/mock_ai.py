"""Deterministic mock replies for UI development. No network calls."""

from __future__ import annotations

import json


class MockAIError(Exception):
    """Raised to exercise chat error UI without calling a real API."""


def generate_reply(user_text: str) -> str:
    text = user_text.strip()
    if not text:
        raise MockAIError("Enter a message before sending.")
    lowered = text.lower()
    if lowered == "fail":
        raise MockAIError("The AI service is unavailable. Check your connection and try again.")

    if "nameerror" in lowered or "username" in lowered:
        return (
            "Possible Python error: `username` is used before it exists.\n\n"
            "Cause:\n"
            "Python cannot find a variable called `username` in the current scope.\n\n"
            "Suggested solution:\n"
            "Define the variable before printing it.\n\n"
            "Example:\n"
            "```python\n"
            'username = "Wasim"\n'
            "print(username)\n"
            "```\n\n"
            "This is a mock explanation for UI testing. Switch to live mode in Settings to use OpenAI."
        )

    return (
        "I can help explain that in simple terms.\n\n"
        f"You asked: {text}\n\n"
        "In mock mode I do not call OpenAI. Live mode uses this conversation as follow-up context.\n\n"
        "Example of a code suggestion:\n"
        "```python\n"
        "def greet(name: str) -> None:\n"
        '    print(f"Hello, {name}")\n'
        "```"
    )


# ── Structured error analysis mock ────────────────────────────────────────────

_MOCK_ANALYSES: dict[str, dict] = {
    "ReferenceError": {
        "problem": "A variable is referenced before it was declared or defined in JavaScript.",
        "error_type": "ReferenceError",
        "explanation": (
            "JavaScript raised a ReferenceError because you tried to use a variable that does "
            "not exist in the current scope. In JavaScript, variables must be declared with "
            "`let`, `const`, or `var` before you access them."
        ),
        "cause": "The variable name is not declared in the local, enclosing, or global scope.",
        "solution": (
            "1. Check the spelling of the variable name.\n"
            "2. Declare the variable using 'let' or 'const' before using it.\n"
            "3. Ensure the variable was not declared in a different inner block or module."
        ),
        "corrected_code": 'const username = "Wasim";\nconsole.log(username);',
        "confidence": 0.95,
    },
    "NameError": {
        "problem": "A variable is referenced before it was defined.",
        "error_type": "NameError",
        "explanation": (
            "Python raised a NameError because it could not find a variable with that name "
            "in the current scope. This usually means you either forgot to define it, "
            "misspelled it, or defined it inside a block (like an if or for) and tried "
            "to use it outside."
        ),
        "cause": "The variable name does not exist in the local or global scope at the point it is used.",
        "solution": (
            "1. Check the spelling of the variable name.\n"
            "2. Make sure you assign a value to it before using it.\n"
            "3. If it is defined inside a block, move the assignment to an outer scope."
        ),
        "corrected_code": 'username = "Wasim"\nprint(username)',
        "confidence": 0.95,
    },
    "TypeError": {
        "problem": "An operation was applied to a value of the wrong data type.",
        "error_type": "TypeError",
        "explanation": (
            "Python raised a TypeError because you tried to perform an operation on a "
            "type that does not support it — for example adding a string and a number, "
            "or calling a non-callable object."
        ),
        "cause": "Incompatible data types used together in an expression or function call.",
        "solution": (
            "1. Convert the value to the correct type (e.g. int(), str()).\n"
            "2. Check the function signature to see what types it expects.\n"
            "3. Use type() or print statements to inspect the actual types at runtime."
        ),
        "corrected_code": 'age = 20\nprint("Age: " + str(age))',
        "confidence": 0.90,
    },
    "SyntaxError": {
        "problem": "Python could not parse the code due to a syntax mistake.",
        "error_type": "SyntaxError",
        "explanation": (
            "The Python interpreter found code that does not follow the language rules. "
            "Common causes are missing colons, mismatched brackets, or invalid indentation."
        ),
        "cause": "A syntax rule was broken — often a missing colon after if/for/def, or unmatched brackets.",
        "solution": (
            "1. Read the error message: it shows the line number and a caret (^) pointing at the problem.\n"
            "2. Check for missing colons at the end of if, for, while, def, or class lines.\n"
            "3. Ensure all opening brackets ( [ { have matching closing ones."
        ),
        "corrected_code": "for i in range(5):\n    print(i)",
        "confidence": 0.93,
    },
    "IndexError": {
        "problem": "A list or sequence was accessed at an index that does not exist.",
        "error_type": "IndexError",
        "explanation": (
            "Python raised an IndexError because you tried to access an element using "
            "an index that is outside the valid range. List indices start at 0 and end "
            "at len(list) - 1."
        ),
        "cause": "The index used is greater than or equal to the length of the sequence, or negative past its start.",
        "solution": (
            "1. Check the length of the list with len() before indexing.\n"
            "2. Use a for loop or enumerate() to iterate safely.\n"
            "3. Validate user input that becomes an index."
        ),
        "corrected_code": "items = [10, 20, 30]\nif len(items) > 3:\n    print(items[3])",
        "confidence": 0.92,
    },
    "General": {
        "problem": "Screen context captured — no specific error identified.",
        "error_type": "General",
        "explanation": (
            "The AI Companion captured text from your screen but did not detect a "
            "specific error pattern. The content may be normal program output, "
            "log messages, or general code."
        ),
        "cause": "No error pattern was matched in the captured text.",
        "solution": "No action required. Continue monitoring, or ask a question in the Chat tab.",
        "corrected_code": "",
        "confidence": 0.30,
    },
}


_MOCK_JS_ANALYSES: dict[str, dict] = {
    "SyntaxError": {
        "problem": "JavaScript could not parse the code due to invalid syntax or an unclosed token.",
        "error_type": "SyntaxError",
        "explanation": (
            "The V8 JavaScript engine encountered code that violates JavaScript syntax rules. "
            "In Node.js, 'Invalid or unexpected token' typically indicates an unclosed string "
            "quote, mismatched brackets, or a misplaced character."
        ),
        "cause": "Unclosed quote literal or unexpected character on the line indicated by the caret (^).",
        "solution": (
            "1. Look at the code line and the caret (^) pointer in the terminal output.\n"
            "2. Ensure all string literals have matching opening and closing quotes (\" \", ' ', or ` `).\n"
            "3. Ensure all parentheses and curly brackets are properly closed: console.log(\"Hello JS!\");"
        ),
        "corrected_code": 'console.log("Hello JS!");',
        "confidence": 0.95,
    },
    "TypeError": {
        "problem": "An operation was performed on an inappropriate value or non-function in JavaScript.",
        "error_type": "TypeError",
        "explanation": (
            "JavaScript raised a TypeError because an operation was attempted on a value of "
            "the wrong type — such as calling a non-function or reading a property of null/undefined."
        ),
        "cause": "Attempting to access properties of undefined or null, or invoking an uncallable variable.",
        "solution": (
            "1. Use optional chaining (e.g. obj?.prop) to safely read properties.\n"
            "2. Ensure functions are imported or declared before invoking them.\n"
            "3. Check the runtime type using console.log(typeof value)."
        ),
        "corrected_code": 'const message = "Hello";\nconsole.log(message.toUpperCase());',
        "confidence": 0.92,
    },
    "ReferenceError": {
        "problem": "A variable is referenced before it was declared or defined in JavaScript.",
        "error_type": "ReferenceError",
        "explanation": (
            "JavaScript raised a ReferenceError because you tried to use a variable that does "
            "not exist in the current scope. In JavaScript, variables must be declared with "
            "`let`, `const`, or `var` before you access them."
        ),
        "cause": "The variable name is not declared in the local, enclosing, or global scope.",
        "solution": (
            "1. Check the spelling of the variable name.\n"
            "2. Declare the variable using 'let' or 'const' before using it.\n"
            "3. Ensure the variable was not declared in a different inner block or module."
        ),
        "corrected_code": 'const username = "Wasim";\nconsole.log(username);',
        "confidence": 0.95,
    },
}


def generate_error_analysis(error_type: str = "General", language: str = "General") -> str:
    """Return a mock JSON string matching the ErrorAnalysis schema.

    Picks the best-matching template using the error_type and language.
    Always returns valid JSON.
    """
    is_js = language.lower() in {"javascript", "typescript", "js", "ts"} or error_type == "ReferenceError"
    primary_dict = _MOCK_JS_ANALYSES if is_js else _MOCK_ANALYSES
    fallback_dict = _MOCK_ANALYSES if is_js else _MOCK_JS_ANALYSES

    # Try exact match first, then substring search in primary dict
    template = primary_dict.get(error_type)
    if template is None:
        for key in primary_dict:
            if key.lower() in error_type.lower() or error_type.lower() in key.lower():
                template = primary_dict[key]
                break
    # Try fallback dict if not found
    if template is None:
        template = fallback_dict.get(error_type)
        if template is None:
            for key in fallback_dict:
                if key.lower() in error_type.lower() or error_type.lower() in key.lower():
                    template = fallback_dict[key]
                    break
    if template is None:
        template = _MOCK_ANALYSES["General"]

    return json.dumps(template, ensure_ascii=False)

