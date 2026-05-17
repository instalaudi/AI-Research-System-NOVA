import json
from typing import Dict, Any, List
from agents.base_agent import BaseAgent # type: ignore
from core.llm_gateway import llm_gateway # type: ignore
from core.utils import parse_llm_json # type: ignore

class AnalyzerAgent(BaseAgent):
    def __init__(self):
        super().__init__("Analyzer") # type: ignore

    async def execute(self, article: Dict[str, Any], **kwargs):
        """
        Analyzes the article using heuristics (no LLM).
        """
        context = kwargs.get("context", None)
        print(f"[{self.name}] Analyzing article using heuristics: {article.get('title')}")
        
        title = article.get('title', 'Sin título')
        raw_content = article.get('full_content') or article.get('summary') or "Sin contenido disponible"
        
        # Heuristic analysis
        content_length = len(raw_content)
        word_count = len(raw_content.split())
        
        # Extract concepts using simple keyword extraction
        keywords = self._extract_keywords(raw_content)
        
        # Generate triplets using rule-based approach
        triplets = self._generate_triplets(title, keywords)
        
        # Categorize based on keywords
        category = self._categorize_article(keywords)
        
        # Generate summary using extractive summarization
        summary = self._extractive_summary(raw_content)
        
        # Calculate confidence based on content quality
        confidence = min(0.9, word_count / 500)  # Higher confidence for longer articles
        
        data = {
            "title": title,
            "content": summary,
            "concepts": keywords[:5],  # Top 5 concepts
            "triplets": triplets,
            "category": category,
            "original_url": article.get("url"),
            "research_topic": article.get("research_topic"),
            "is_fallback": False,
            "quality_flag": "heuristic_analysis",
            "relevance_score": float(article.get("relevance_score", 1.0)),
            "confidence_score": round(confidence, 3),
            "review_score": 0.7
        }
        
        return data
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Simple keyword extraction using frequency and position."""
        import re
        from collections import Counter
        
        # Clean text
        text = re.sub(r'[^\w\s]', '', text.lower())
        words = text.split()
        
        # Remove stop words (basic list)
        stop_words = {'el', 'la', 'los', 'las', 'de', 'del', 'y', 'a', 'en', 'que', 'un', 'una', 'es', 'se', 'no', 'por', 'con', 'para', 'como', 'su', 'al', 'lo', 'ha', 'si', 'pero', 'más', 'o', 'este', 'esta', 'estos', 'estas'}
        words = [w for w in words if w not in stop_words and len(w) > 3]
        
        # Count frequency
        word_freq = Counter(words)
        
        # Get top keywords
        keywords = [word for word, _ in word_freq.most_common(10)]
        return keywords
    
    def _generate_triplets(self, title: str, keywords: List[str]) -> List[List[str]]:
        """Generate basic triplets using rule-based patterns."""
        triplets = []
        
        # Basic patterns
        for keyword in keywords[:3]:  # Limit to top 3
            triplets.append([keyword, "es_un_concepto_de", title.split()[0] if title.split() else "Tema"])
            triplets.append([title.split()[0] if title.split() else "Tema", "relacionado_con", keyword])
        
        return triplets[:5]  # Max 5 triplets
    
    def _categorize_article(self, keywords: List[str]) -> str:
        """Categorize based on keyword patterns."""
        tech_keywords = {'tecnología', 'software', 'inteligencia', 'artificial', 'algoritmo', 'sistema', 'computadora', 'programa'}
        science_keywords = {'investigación', 'científico', 'estudio', 'experimento', 'descubrimiento', 'teoría'}
        
        tech_count = sum(1 for k in keywords if k in tech_keywords)
        science_count = sum(1 for k in keywords if k in science_keywords)
        
        if tech_count > science_count:
            return "Tecnología"
        elif science_count > 0:
            return "Ciencia"
        else:
            return "General"
    
    def _extractive_summary(self, text: str) -> str:
        """Simple extractive summarization using first and last sentences."""
        import re
        
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return text[:300] + "..." if len(text) > 300 else text
        
        # Take first sentence and last sentence
        summary = sentences[0]
        if len(sentences) > 1:
            summary += ". " + sentences[-1]
        
        return summary[:500] + "..." if len(summary) > 500 else summary
