import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.distillation import NOVADistillationEngine

async def test_robustness():
    engine = NOVADistillationEngine()
    
    # 1. Test query with a string (normal)
    print("Testing with string...")
    # Mocking llm_client.chat to avoid hitting Ollama if not needed, but here we just check if it fails before the call
    try:
        # Line 221 happens BEFORE the chat call
        await engine._query_single_master("Hola master, cuéntame algo técnico", "llama3.1:8b")
        print("Result 1: Succesfully reached LLM section (Expected)")
    except Exception as e:
        if "AttributeError" in str(e):
            print(f"Result 1 FAILED with AttributeError: {e}")
        else:
            print(f"Result 1 reached LLM call: {type(e).__name__}")

    # 2. Test query with a dict (The BUG)
    print("\nTesting with dict (The Bug fix: {'question': '...'} )...")
    malformed_question = {"question": "Explicame arquitectura software"}
    try:
        await engine._query_single_master(malformed_question, "llama3.1:8b")
        print(f"Result 2 success! Handled dict without crash BEFORE LLM call.")
    except Exception as e:
        if "AttributeError" in str(e):
            print(f"Result 2 FAILED: {e}")
        else:
            print(f"Result 2 handled type check and reached LLM call: {type(e).__name__}")

    # 3. Test query with a different dict structure
    print("\nTesting with alternate dict ( {'text': '...'} )...")
    malformed_question2 = {"text": "Dime sobre Python"}
    try:
        await engine._query_single_master(malformed_question2, "llama3.1:8b")
        print(f"Result 3 success! Handled 'text' key BEFORE LLM call.")
    except Exception as e:
         if "AttributeError" in str(e):
            print(f"Result 3 FAILED: {e}")
         else:
            print(f"Result 3 handled type check and reached LLM call: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_robustness())
