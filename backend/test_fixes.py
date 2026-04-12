"""Test script to verify all fixes applied to NOVA backend."""
import asyncio

# Test 1: Imports
print("=== TEST 1: ALL IMPORTS ===")
from services.chat_service import chat_service
from core.llm_client import llm_client, _strip_think_tags
from core.task_queue import task_queue
from routers.chat import router
from core.config import LLM_FAST_MODEL, OLLAMA_NUM_CTX
from core.prompts import RAG_STREAM_PROMPT_BODY, VISION_ANALYSIS_PROMPT_BODY, NOVA_IDENTITY_PROMPT
print("  ✅ All imports successful")

# Test 2: Config values
print("\n=== TEST 2: CONFIG VALUES ===")
print(f"  LLM_FAST_MODEL = {LLM_FAST_MODEL}")
assert LLM_FAST_MODEL == "qwen3:8b", f"FAIL: Expected qwen3:8b, got {LLM_FAST_MODEL}"
print(f"  OLLAMA_NUM_CTX = {OLLAMA_NUM_CTX}")
assert OLLAMA_NUM_CTX == 8192, f"FAIL: Expected 8192, got {OLLAMA_NUM_CTX}"
print(f"  fast_model = {llm_client.fast_model}")
assert llm_client.fast_model == "qwen3:8b"
print("  ✅ Config values correct")

# Test 3: Think tag stripping
print("\n=== TEST 3: THINK TAG STRIPPING ===")
t1 = _strip_think_tags("Hola mundo")
assert t1 == "Hola mundo", f"FAIL: {t1}"
print(f"  Normal text: '{t1}' ✅")

t2 = _strip_think_tags("<think>reasoning here</think>Respuesta final")
assert t2 == "Respuesta final", f"FAIL: {t2}"
print(f"  Think+response: '{t2}' ✅")

t3 = _strip_think_tags("<think>solo pensamiento</think>")
assert t3 == "", f"FAIL: expected empty, got '{t3}'"
print(f"  Only thinking: '{t3}' (empty) ✅")

t4 = _strip_think_tags("<think>first</think>Middle<think>second</think>End")
assert t4 == "MiddleEnd", f"FAIL: {t4}"
print(f"  Multiple thinks: '{t4}' ✅")

t5 = _strip_think_tags("No tags at all")
assert t5 == "No tags at all"
print(f"  No tags: '{t5}' ✅")
print("  ✅ All think tag tests passed")

# Test 4: Async _mark_job_failed
print("\n=== TEST 4: ASYNC SAFETY ===")
assert asyncio.iscoroutinefunction(task_queue._mark_job_failed), "FAIL: _mark_job_failed should be async"
print("  _mark_job_failed is async ✅")

# Test 5: Prompt deduplication
print("\n=== TEST 5: PROMPT DEDUPLICATION ===")
assert "NOVA" not in RAG_STREAM_PROMPT_BODY[:50], "FAIL: RAG_STREAM_PROMPT_BODY should not contain identity"
assert "NOVA" not in VISION_ANALYSIS_PROMPT_BODY[:50], "FAIL: VISION_ANALYSIS should not contain identity"
print(f"  RAG_STREAM_PROMPT_BODY: {len(RAG_STREAM_PROMPT_BODY)} chars (no identity) ✅")
print(f"  VISION_ANALYSIS_PROMPT_BODY: {len(VISION_ANALYSIS_PROMPT_BODY)} chars (no identity) ✅")
print(f"  NOVA_IDENTITY_PROMPT: {len(NOVA_IDENTITY_PROMPT)} chars ✅")

print("\n🎉 ALL TESTS PASSED — System ready to restart!")
