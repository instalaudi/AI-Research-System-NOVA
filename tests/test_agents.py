import asyncio
import pytest
from backend.agents.planner import PlannerAgent
from backend.agents.explorer import ExplorerAgent
from backend.agents.analyzer import AnalyzerAgent
from backend.agents.critic import CriticAgent
from backend.agents.verifier import VerifierAgent
from backend.agents.librarian import LibrarianAgent

@pytest.mark.asyncio
async def test_planner():
    agent = PlannerAgent()
    topics = await agent.generate_topics(["cybersecurity"])
    assert len(topics) > 0
    assert "cybersecurity" in topics[0].lower()
    print("Planificador: OK")

@pytest.mark.asyncio
async def test_explorer():
    agent = ExplorerAgent()
    articles = await agent.search("machine learning")
    assert len(articles) > 0
    assert "title" in articles[0]
    print("Explorador: OK")

@pytest.mark.asyncio
async def test_analyzer():
    agent = AnalyzerAgent()
    analysis = await agent.process({"title": "Test", "url": "http://test.com"})
    assert "summary" in analysis
    assert len(analysis["concepts"]) > 0
    print("Analizador: OK")

@pytest.mark.asyncio
async def test_critic():
    agent = CriticAgent()
    critique = await agent.review({"title": "Test", "summary": "Bad summary"})
    assert "review_score" in critique
    print("Critic: OK")

@pytest.mark.asyncio
async def test_verifier():
    agent = VerifierAgent()
    # High score should pass
    valid = await agent.validate({"title": "Test", "review_score": 9.0})
    assert valid is True
    # Low score should fail
    invalid = await agent.validate({"title": "Test", "review_score": 2.0})
    assert invalid is False
    print("Verificador: OK")

@pytest.mark.asyncio
async def test_librarian():
    agent = LibrarianAgent()
    stored = await agent.store({"title": "New Knowledge", "review_score": 8.5})
    assert stored is True
    print("Librarian: OK")

if __name__ == "__main__":
    asyncio.run(test_planner())
    asyncio.run(test_explorer())
    asyncio.run(test_analyzer())
    asyncio.run(test_critic())
    asyncio.run(test_verifier())
    asyncio.run(test_librarian())
