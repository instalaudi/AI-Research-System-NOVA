import asyncio
from backend.core.memory import memory

async def test_hierarchical_memory():
    print("--- Testing Hierarchical Memory (L4) ---")
    
    # Short term memory check
    item = {"title": "Quantum Trends", "text": "Recent news..."}
    memory.add_to_short_term(item)
    assert len(memory.short_term) == 1
    print("Short-term: OK")
    
    # Medium term promotion check
    summary = {"title": "Quantum Trends", "summary": "Condensed version"}
    memory.promote_to_medium(summary)
    assert len(memory.medium_term) == 1
    print("Medium-term promotion: OK")
    
    # Long term reference check
    assert memory.long_term_ref == "vector_db"
    print("Long-term reference: OK")

if __name__ == "__main__":
    asyncio.run(test_hierarchical_memory())
