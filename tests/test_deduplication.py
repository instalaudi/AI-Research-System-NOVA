import pytest
from unittest.mock import AsyncMock, patch
from backend.agents.librarian import LibrarianAgent

@pytest.mark.asyncio
async def test_deduplication():
    agent = LibrarianAgent()
    
    article = {
        "title": "Quantum Supremacy in 2026",
        "summary": "AI systems reaching new heights in quantum error correction.",
        "review_score": 0.92
    }
    
    with patch('core.llm_gateway.llm_gateway.chat', new_callable=AsyncMock) as mock_chat, \
         patch('core.vector_db.vector_db.search_similar', new_callable=AsyncMock) as mock_vector, \
         patch('core.knowledge_base.knowledge_base.add_entry', new_callable=AsyncMock) as mock_kb:
         
         mock_chat.return_value = '{"triplets": []}'
         
         # Test case 1: Not a duplicate
         mock_vector.return_value = []
         result1 = await agent.execute(article)
         assert result1 is True
         
         # Test case 2: Duplicate detected
         mock_vector.return_value = [{"distance": 0.10, "metadata": {"title": "Quantum Supremacy in 2026"}}]
         result2 = await agent.execute(article)
         assert result2 is False
