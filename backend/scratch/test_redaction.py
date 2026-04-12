import logging
import re
from typing import Any

_SENSITIVE_PATTERNS = [
    (re.compile(r"bot\d+:[A-Za-z0-9_\-]+"), "bot[REDACTED]"),
]

def _redact(text: str) -> str:
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text

def _redact_val(val: Any) -> Any:
    if val is None:
        return None
    try:
        s_val = str(val)
        redacted = _redact(s_val)
        if redacted != s_val:
            return redacted
        return val
    except Exception:
        return val

# Test cases
test_cases = [
    (200, int), # Should stay int
    ("Hello bot123:abc-def", str), # Should become redacted str
    ("Clean message", str), # Should stay same str
    (123.45, float), # Should stay float
    (["bot123:abc"], list), # Should become redacted str (as str([]) contains the token)
]

print("Starting tests...")
all_passed = True
for val, expected_type in test_cases:
    result = _redact_val(val)
    print(f"Input: {val!r} ({type(val)}) -> Output: {result!r} ({type(result)})")
    if "bot123:abc" in str(val) and "[REDACTED]" not in str(result):
        print("FAILED: Token not redacted")
        all_passed = False
    if "bot123:abc" not in str(val) and not isinstance(result, expected_type):
        print(f"FAILED: Type changed unnecessarily (Expected {expected_type}, got {type(result)})")
        all_passed = False

if all_passed:
    print("SUCCESS: All tests passed!")
else:
    print("FAILURE: Some tests failed.")
