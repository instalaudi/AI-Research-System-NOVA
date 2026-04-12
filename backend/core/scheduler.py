import asyncio
from core.orchestrator import orchestrator
from core.task_queue import task_queue
from core.config import POLLING_INTERVAL_SECONDS

class Scheduler:
    def __init__(self):
        self.running = False

    async def start(self):
        self.running = True
        print(f"Scheduler: Starting daily research automation (Interval: {POLLING_INTERVAL_SECONDS}s)")
        while self.running:
            # Trigger a general research cycle based on a default set of topics or curiosity
            await task_queue.add_task("start_research", {"interest_areas": ["Tecnología", "Ciencia", "Programación"]})
            await asyncio.sleep(POLLING_INTERVAL_SECONDS)

    def stop(self):
        self.running = False

# Global instance
scheduler = Scheduler()
