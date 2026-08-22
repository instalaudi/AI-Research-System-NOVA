import json
import pytest
from unittest.mock import AsyncMock, patch
from backend.agents.planner import PlannerAgent
from backend.agents.explorer import ExplorerAgent
from backend.agents.analyzer import AnalyzerAgent
from backend.agents.critic import CriticAgent
from backend.agents.verifier import VerifierAgent
from backend.agents.librarian import LibrarianAgent

@pytest.mark.asyncio
async def test_planner():
    agent = PlannerAgent()
    topics = await agent.execute(["cybersecurity"])
    assert len(topics) > 0
    assert "cybersecurity" in topics[0].lower()

@pytest.mark.asyncio
async def test_explorer():
    agent = ExplorerAgent()
    
    with patch.object(agent, '_search_wikipedia', new_callable=AsyncMock) as mock_wiki, \
         patch.object(agent, '_search_arxiv', new_callable=AsyncMock) as mock_arxiv, \
         patch.object(agent, '_search_github', new_callable=AsyncMock) as mock_github, \
         patch.object(agent, '_search_semantic', new_callable=AsyncMock) as mock_semantic, \
         patch.object(agent, '_search_google_scholar', new_callable=AsyncMock) as mock_scholar, \
         patch.object(agent, '_filter_relevance', new_callable=AsyncMock) as mock_filter:
         
         mock_wiki.return_value = [{"title": "Wikipedia Article", "url": "http://wiki.com", "summary": "Wiki"}]
         mock_arxiv.return_value = []
         mock_github.return_value = []
         mock_semantic.return_value = []
         mock_scholar.return_value = []
         mock_filter.return_value = [{"title": "Wikipedia Article", "url": "http://wiki.com", "summary": "Wiki"}]
         
         articles = await agent.execute("machine learning")
         assert len(articles) > 0
         assert "title" in articles[0]

@pytest.mark.asyncio
async def test_analyzer():
    agent = AnalyzerAgent()
    analysis = await agent.execute({"title": "Test", "url": "http://test.com", "summary": "This is a test article content."})
    assert "content" in analysis
    assert len(analysis["concepts"]) > 0

@pytest.mark.asyncio
async def test_critic():
    agent = CriticAgent()
    with patch('backend.agents.critic.llm_gateway.chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = json.dumps({"review_score": 0.8, "critique": "Good analysis"})
        critique = await agent.execute({"title": "Test", "summary": "Good summary", "concepts": ["test"]})
        assert "review_score" in critique
        assert critique["review_score"] == 0.8

@pytest.mark.asyncio
async def test_verifier():
    agent = VerifierAgent()
    # High score should pass
    valid = await agent.execute({"title": "Test", "review_score": 0.9})
    assert valid is True
    # Low score should fail
    invalid = await agent.execute({"title": "Test", "review_score": 0.2})
    assert invalid is False

@pytest.mark.asyncio
async def test_librarian():
    agent = LibrarianAgent()
    with patch('core.llm_gateway.llm_gateway.chat', new_callable=AsyncMock) as mock_chat, \
         patch('core.vector_db.vector_db.search_similar', new_callable=AsyncMock) as mock_vector, \
         patch('core.knowledge_base.knowledge_base.add_entry', new_callable=AsyncMock) as mock_kb:
         
         mock_chat.return_value = json.dumps({"triplets": [["A", "rel", "B"]]})
         mock_vector.return_value = []
         mock_kb.return_value = None
         
         stored = await agent.execute({"title": "New Knowledge", "review_score": 0.85, "concepts": ["test"]})
         assert stored is True
