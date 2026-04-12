import json
import re
import logging

# BUG-06: Add proper logging for JSON parsing failures
logger = logging.getLogger(__name__)

def parse_llm_json(text: str):
    """
    Cleans and parses JSON from LLM responses, handling markdown code blocks.
    Implements 4 levels of fallback for maximum robustness with LLM output.
    """
    if not text or not text.strip():
        raise ValueError("Empty response from LLM.")

    # 1. Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract content between ```json and ```
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Generic code block ```...```
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 4. Robust extraction: find FIRST { and LAST } to handle trailing text
    first_brace = text.find("{")
    last_brace  = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 5. Final Fail — Log with enough context to diagnose
    snippet = text[:500] + ("..." if len(text) > 500 else "")
    logger.error(
        f"JSON Parse Failure after 4 attempts. "
        f"Text length: {len(text)}. "
        f"Content preview: '{snippet}'"
    )
    raise ValueError("Could not parse JSON from LLM response.")

