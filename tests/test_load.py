import asyncio
import time
from backend.core.orchestrator import orchestrator
from backend.core.task_queue import task_queue

async def load_test():
    print("--- Starting Load Test (L8: 10 topics, 20+ articles) ---")
    start_time = time.time()
    
    orchestrator.start()
    
    # Inject multiple research starts
    interest_areas = ["AI", "Nanotech", "Space", "Biology", "Computing"]
    await task_queue.add_task("start_research", {"interest_areas": interest_areas})
    
    # Add more direct topics
    topics = [f"Advanced Topic {i}" for i in range(5)]
    for t in topics:
        await task_queue.add_task("explore_topic", {"topic": t})
        
    print(f"Queue size after injection: {task_queue.get_size()}")
    
    # Wait for completion (since workers run infinitely, wait for size to drop to 0 with timeout)
    start_wait = time.time()
    while task_queue.get_size() > 0 and time.time() - start_wait < 60:
        await asyncio.sleep(1)
    
    end_time = time.time()
    print(f"--- Load Test Complete in {end_time - start_time:.2f}s ---")

if __name__ == "__main__":
    asyncio.run(load_test())
