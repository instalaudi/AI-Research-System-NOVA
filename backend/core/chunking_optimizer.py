"""
NOVA Chunking Optimizer — Adaptado de OpenClaw rag-architect skill.
Versión: 12.0.0

Proporciona:
- SemanticChunker: Chunking inteligente por encabezados/párrafos para PDFs y artículos.
- SentenceChunker: Chunking respetando límites de oración.
- ChunkingOptimizer: Herramienta de diagnóstico para evaluar la calidad del corpus.
- chunk_text(): Función de utilidad para chunking inteligente (reemplaza split fijo).

Sin dependencias externas — solo stdlib de Python.
"""

import re
import statistics
from typing import Dict, List, Any, Optional


class SentenceChunker:
    """Chunking basado en oraciones con límite de tamaño."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._sentence_re = re.compile(r'[.!?]+\s+')

    def chunk(self, text: str) -> List[Dict[str, Any]]:
        sentences = self._split_sentences(text)
        chunks: List[Dict[str, Any]] = []
        current: List[str] = []
        current_size = 0
        chunk_id = 0

        for sentence in sentences:
            slen = len(sentence)
            if current_size + slen > self.max_size and current:
                chunk_text = ' '.join(current)
                chunks.append({
                    'id': chunk_id,
                    'text': chunk_text,
                    'size': len(chunk_text),
                    'sentence_count': len(current),
                })
                chunk_id += 1
                current = [sentence]
                current_size = slen
            else:
                current.append(sentence)
                current_size += slen

        if current:
            chunk_text = ' '.join(current)
            chunks.append({
                'id': chunk_id,
                'text': chunk_text,
                'size': len(chunk_text),
                'sentence_count': len(current),
            })
        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        parts = self._sentence_re.split(text)
        endings = list(self._sentence_re.finditer(text))
        sentences: List[str] = []
        for i, part in enumerate(parts[:-1]):
            if i < len(endings):
                sentence = part + endings[i].group().strip()
            else:
                sentence = part
            s = sentence.strip()
            if s:
                sentences.append(s)
        if parts[-1].strip():
            sentences.append(parts[-1].strip())
        return [s for s in sentences if s]


class SemanticChunker:
    """
    Chunking semántico consciente de encabezados (Markdown/Plain Text).
    Preserva la estructura del documento al dividir por secciones.
    """

    def __init__(self, max_size: int = 1500):
        self.max_size = max_size
        self._heading_re = re.compile(r'^#{1,6}\s+(.+)$', re.MULTILINE)

    def chunk(self, text: str) -> List[Dict[str, Any]]:
        sections = self._identify_sections(text)
        chunks: List[Dict[str, Any]] = []
        chunk_id = 0
        for section in sections:
            section_chunks = self._chunk_section(section, chunk_id)
            chunks.extend(section_chunks)
            chunk_id += len(section_chunks)
        return chunks

    def _identify_sections(self, text: str) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        lines = text.split('\n')
        current: Dict[str, Any] = {'heading': '', 'content': '', 'level': 0}

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                level = len(stripped) - len(stripped.lstrip('#'))
                if 1 <= level <= 6:
                    if current['content'].strip():
                        sections.append(current)
                    current = {
                        'heading': stripped.lstrip('#').strip(),
                        'content': '',
                        'level': level,
                    }
                    continue
            current['content'] += line + '\n'

        if current['content'].strip():
            sections.append(current)
        return sections

    def _chunk_section(self, section: Dict[str, Any], start_id: int) -> List[Dict[str, Any]]:
        content = section['content'].strip()
        if not content:
            return []

        heading = section['heading']

        if len(content) <= self.max_size:
            text = f"{heading}\n\n{content}" if heading else content
            return [{
                'id': start_id,
                'text': text,
                'size': len(text),
                'heading': heading,
                'level': section['level'],
            }]

        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        chunks: List[Dict[str, Any]] = []
        current_paras: List[str] = []
        current_size = len(heading) + 2 if heading else 0
        chunk_id = start_id

        for para in paragraphs:
            plen = len(para)
            if current_size + plen > self.max_size and current_paras:
                chunk_text = '\n\n'.join(current_paras)
                if heading and chunk_id == start_id:
                    chunk_text = f"{heading}\n\n{chunk_text}"
                chunks.append({
                    'id': chunk_id,
                    'text': chunk_text,
                    'size': len(chunk_text),
                    'heading': heading if chunk_id == start_id else f"{heading} (cont.)",
                    'level': section['level'],
                })
                chunk_id += 1
                current_paras = [para]
                current_size = plen
            else:
                current_paras.append(para)
                current_size += plen + 2

        if current_paras:
            chunk_text = '\n\n'.join(current_paras)
            if heading and chunk_id == start_id:
                chunk_text = f"{heading}\n\n{chunk_text}"
            elif heading:
                chunk_text = f"{heading} (cont.)\n\n{chunk_text}"
            chunks.append({
                'id': chunk_id,
                'text': chunk_text,
                'size': len(chunk_text),
                'heading': heading if chunk_id == start_id else f"{heading} (cont.)",
                'level': section['level'],
            })
        return chunks


# ═══════════════════════════════════════════════════════
# Función de utilidad para NOVA
# ═══════════════════════════════════════════════════════

def chunk_text(text: str, max_chunk_size: int = 1500, strategy: str = "semantic") -> List[str]:
    """
    Divide un texto largo en chunks inteligentes.
    
    Uso en Librarian/VectorDB:
        from core.chunking_optimizer import chunk_text
        chunks = chunk_text(pdf_content, max_chunk_size=1200)
        for chunk in chunks:
            await vector_db.index_article(...)

    Args:
        text: Texto a dividir.
        max_chunk_size: Tamaño máximo por chunk en caracteres.
        strategy: "semantic" (por encabezados) o "sentence" (por oraciones).
    
    Returns:
        Lista de strings, cada uno un chunk del texto original.
    """
    if not text or not text.strip():
        return []

    if len(text) <= max_chunk_size:
        return [text.strip()]

    if strategy == "semantic":
        chunker = SemanticChunker(max_size=max_chunk_size)
    else:
        chunker = SentenceChunker(max_size=max_chunk_size)

    raw_chunks = chunker.chunk(text)
    return [c['text'] for c in raw_chunks if c['text'].strip()]


# ═══════════════════════════════════════════════════════
# Herramienta de diagnóstico
# ═══════════════════════════════════════════════════════

class ChunkingOptimizer:
    """
    Evalúa la calidad de chunking del corpus actual de NOVA.
    Uso: desde el endpoint /api/diagnostics/chunking
    """

    @staticmethod
    def analyze_chunks(chunks: List[str]) -> Dict[str, Any]:
        """Analiza una lista de chunks y retorna métricas de calidad."""
        if not chunks:
            return {'error': 'No chunks to analyze'}

        sizes = [len(c) for c in chunks]
        sentence_re = re.compile(r'[.!?]\s*$')
        clean_breaks = sum(1 for c in chunks if sentence_re.search(c.strip()))

        # Coherencia semántica (solapamiento de vocabulario entre chunks consecutivos)
        coherence_scores: List[float] = []
        for i in range(len(chunks) - 1):
            words1 = set(re.findall(r'\b\w+\b', chunks[i].lower()))
            words2 = set(re.findall(r'\b\w+\b', chunks[i + 1].lower()))
            if words1 and words2:
                inter = len(words1 & words2)
                union = len(words1 | words2)
                if union > 0:
                    coherence_scores.append(inter / union)

        return {
            'chunk_count': len(chunks),
            'size_mean': round(statistics.mean(sizes), 1),
            'size_std': round(statistics.stdev(sizes), 1) if len(sizes) > 1 else 0,
            'size_min': min(sizes),
            'size_max': max(sizes),
            'boundary_quality': round(clean_breaks / len(chunks), 3) if chunks else 0,
            'semantic_coherence': round(
                statistics.mean(coherence_scores), 3
            ) if coherence_scores else 0.0,
        }

    @staticmethod
    def recommend_strategy(text_sample: str) -> Dict[str, Any]:
        """
        Dado un texto de ejemplo, prueba ambas estrategias y recomienda la mejor.
        """
        results = {}
        for strategy_name in ("semantic", "sentence"):
            chunks = chunk_text(text_sample, max_chunk_size=1200, strategy=strategy_name)
            analysis = ChunkingOptimizer.analyze_chunks(chunks)
            
            # Score compuesto
            if 'error' not in analysis:
                size_consistency = 1.0 - min(
                    analysis['size_std'] / analysis['size_mean'], 1.0
                ) if analysis['size_mean'] > 0 else 0
                score = (
                    size_consistency * 0.3
                    + analysis['boundary_quality'] * 0.4
                    + analysis['semantic_coherence'] * 0.3
                )
            else:
                score = 0.0

            results[strategy_name] = {**analysis, 'score': round(score, 3)}

        best = max(results, key=lambda k: results[k].get('score', 0))
        return {
            'recommended': best,
            'strategies': results,
        }
