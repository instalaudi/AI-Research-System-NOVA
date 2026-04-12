import asyncio
import sys
import os
import time

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.intent_classifier import classify_intent
from core.llm_client import PrioritySemaphore

async def test_fast_intent():
    print("=== Testing Fast Intent Classification ===")
    queries = [
        "hola",
        "hola nova como estas hoy",
        "buenos dias amigo",
        "investiga sobre computacion cuantica",
        "que es un modelo de lenguaje"
    ]
    
    for q in queries:
        t0 = time.time()
        intent = await classify_intent(q)
        duration = (time.time() - t0) * 1000
        print(f"Query: '{q}' -> Intent: {intent} ({duration:.2f}ms)")

async def test_priority_reservation():
    print("\n=== Testing Priority Semaphore Reservation ===")
    # 1. Test the RESERVATION:
    sem_res = PrioritySemaphore(value=1)
    print("Testing Reservation with value=1 (1 slot total, reserved for priority 0):")
    
    # Task A (Prio 1) SHOULD BE BLOCKED/WAIT because value=1 is reserved
    print("Task A (Prio 1) trying to acquire...")
    try:
        await asyncio.wait_for(sem_res.acquire(priority=1), timeout=0.5)
        print("❌ Error: Task A acquired the ONLY slot (reserved for chat).")
    except (asyncio.TimeoutError, TimeoutError):
        print("✅ Task A blocked/wait correctly. Slot reserved for Priority 0.")
        
    print("Chat (Prio 0) trying to acquire the reserved slot...")
    try:
        await asyncio.wait_for(sem_res.acquire(priority=0), timeout=0.5)
        print("✅ Chat acquired the reserved slot!")
    except Exception as e:
        print(f"❌ Error: Chat could not acquire reserved slot: {e}")

if __name__ == "__main__":
    # Note: Intent classifier might still hit LLM if keywords fail, but greetings should pass.
    # In this test environment, we expect headers missing if it hits LLM.
    # We just want to see if it catches 'hola nova como estas hoy'.
    asyncio.run(test_fast_intent())
    asyncio.run(test_priority_reservation())
