import os
import re
import fitz # PyMuPDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import html2text
from typing import List, Dict, Any
import datetime
import json
import asyncio
import hashlib
from core.knowledge_base import knowledge_base
from core.vector_db import vector_db
from core.database import SessionLocal, KnowledgeEntry
from core.lightrag_manager import lightrag_manager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Librarian:
    def __init__(self, chunk_size: int = 2000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = True
        self.html_converter.ignore_images = True
        # v11.4: Bloqueo para asegurar procesamiento secuencial y estabilidad de RAM
        self.ingest_lock = asyncio.Lock()

    def parse_pdf(self, file_path: str) -> str:
        """
        Extracts text from a PDF file with robust error suppression for MuPDF syntax errors.
        """
        # v11.8.1: Silenciar stderr de MuPDF si es posible (emite errores directamente a C/C++ stderr)
        # que Python no siempre captura con try/except.
        import sys
        
        text = ""
        try:
            with fitz.open(file_path) as doc:
                for page in doc:
                    try:
                        text += page.get_text()
                    except Exception as pe:
                        print(f"[Librarian] ⚠️ Error en página de PDF '{file_path}': {pe}")
                        continue
        except Exception as e:
            print(f"[Librarian] ❌ Fallo crítico abriendo PDF '{file_path}': {e}")
            raise
        return text

    def _is_corrupt(self, file_path: str) -> bool:
        """Verifica si el archivo está en la lista negra de corruptos."""
        corrupt_file = os.path.join(BASE_DIR, "data", "corrupt_files.json")
        if not os.path.exists(corrupt_file): return False
        try:
            with open(corrupt_file, 'r') as f:
                data = json.load(f)
                return file_path in data
        except: return False

    def _mark_as_corrupt(self, file_path: str):
        """Añade un archivo a la lista negra para evitar reintentos infinitos."""
        corrupt_file = os.path.join(BASE_DIR, "data", "corrupt_files.json")
        os.makedirs(os.path.dirname(corrupt_file), exist_ok=True)
        data = []
        if os.path.exists(corrupt_file):
            try:
                with open(corrupt_file, 'r') as f: data = json.load(f)
            except: data = []
        if file_path not in data:
            data.append(file_path)
            with open(corrupt_file, 'w') as f: json.dump(data, f)
        print(f"[Librarian] 💀 Archivo marcado como CORRUPTO: {file_path}")


    def parse_epub(self, file_path: str) -> str:
        """Extracts text from an EPUB file."""
        book = epub.read_epub(file_path)
        text = ""
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text += self.html_converter.handle(str(soup))
        return text

    def parse_txt(self, file_path: str) -> str:
        """Reads text from a plain text file."""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def chunk_text(self, text: str) -> List[str]:
        """
        v12.0.0: Chunking semántico — divide por encabezados y párrafos
        en vez de cortes arbitrarios por tamaño fijo.
        Preserva la estructura del documento para mejor retrieval RAG.
        Fallback a chunking fijo si el texto no tiene estructura.
        """
        if not text:
            return []

        from core.chunking_optimizer import chunk_text as smart_chunk
        chunks = smart_chunk(text, max_chunk_size=self.chunk_size, strategy="semantic")

        # Fallback: si el chunking semántico produce chunks muy grandes,
        # subdividir con sentence-based
        final_chunks: List[str] = []
        for c in chunks:
            if len(c) > self.chunk_size * 1.5:
                sub = smart_chunk(c, max_chunk_size=self.chunk_size, strategy="sentence")
                final_chunks.extend(sub)
            else:
                final_chunks.append(c)

        return final_chunks

    def generate_content_hash(self, text: str) -> str:
        """v11.4.2: Generates a unique SHA-256 fingerprint for the document content."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    async def ingest_book(self, file_path: str, title: str, user_id: int = None):
        """Processes a book and stores it in the knowledge base and vector DB."""
        # v11.8.1: Evitar procesar archivos conocidos como corruptos (DDoS de logs)
        if self._is_corrupt(file_path):
            print(f"[Librarian] 🛑 Saltando '{title}': Archivo marcado como corrupto previamente.")
            return {"status": "error", "reason": "corrupt_file"}

        async with self.ingest_lock:
            ext = os.path.splitext(file_path)[1].lower()
            
            try:
                print(f"[Librarian] Iniciando absorción de '{title}'...")
                if ext == ".pdf":
                    try:
                        full_text = self.parse_pdf(file_path)
                    except:
                        self._mark_as_corrupt(file_path)
                        raise

                elif ext == ".epub":
                    full_text = self.parse_epub(file_path)
                elif ext == ".txt":
                    full_text = self.parse_txt(file_path)
                else:
                    raise ValueError(f"Formato no soportado: {ext}")

                if not full_text or not full_text.strip():
                    raise ValueError("No se pudo extraer texto del archivo.")

                # v11.4.2: Generar huella digital y verificar duplicados
                content_hash = self.generate_content_hash(full_text)
                
                db = SessionLocal()
                try:
                    # Verificar por Título exacto o por Huella Digital del contenido
                    existing = db.query(KnowledgeEntry).filter(
                        (KnowledgeEntry.title == title) | (KnowledgeEntry.content_hash == content_hash)
                    ).first()
                    
                    if existing:
                        conflict_type = "Nombre" if existing.title == title else "Contenido"
                        print(f"[Librarian] ⚠️ Duplicado detectado por {conflict_type}. Cancelando.")
                        return {"status": "duplicate", "title": existing.title}
                finally:
                    db.close()

                chunks = self.chunk_text(full_text)
                total_chunks = len(chunks)
                print(f"[Librarian] Libro '{title}' segmentado en {total_chunks} fragmentos (chunking semántico v12).")

                # v12.0.0: Registrar lección de ingesta exitosa
                try:
                    from core.lessons_learned import lessons_db
                    lessons_db.learn(
                        action=f"Ingesta de '{title}' ({total_chunks} chunks, {len(full_text)} chars)",
                        context="book_ingestion",
                        outcome="positive",
                        insight=f"Documento procesado exitosamente con chunking semántico.",
                        source="system"
                    )
                except Exception:
                    pass  # Non-critical

                # Create a main entry for the book in KnowledgeBase
                book_metadata = {
                    "title": title,
                    "category": "Library",
                    "content": f"Libro completo: {title}. Realizado análisis semántico de {total_chunks} fragmentos.",
                    "confidence_score": 1.0,
                    "url": f"local://library/{title}",
                    "concepts": ["Libro", "Biblioteca", title],
                    "quality_flag": "book_ingestion",
                    "content_hash": content_hash
                }
                await knowledge_base.add_entry(book_metadata, user_id=user_id)

                # v12.0.1: Indexación SEGMENTADA en Grafo de Conocimiento (LightRAG)
                # Dividimos en bloques de ~4000 tokens para no saturar el contexto del modelo extractor
                # y procesamos secuencialmente para respetar los límites del Ryzen 7.
                async def index_graph_sequentially(text_chunks):
                    for i, chunk in enumerate(text_chunks):
                        try:
                            # Agrupamos chunks de la librería (que son de 2000 chars) 
                            # en bloques más grandes para LightRAG si es necesario, 
                            # pero por ahora uno por uno es más seguro para la RAM.
                            await lightrag_manager.insert_text(chunk)
                            await asyncio.sleep(0) # Evitar saturar el event loop
                        except Exception as e:
                            print(f"[Librarian] ❌ Error en LightRAG (segmento {i}): {e}")

                task = asyncio.create_task(index_graph_sequentially(chunks))
                task.add_done_callback(
                    lambda t: t.exception() and print(f"[Librarian] 💀 Tarea LightRAG falló: {t.exception()}")
                )

                # v11.4: OPTIMIZACIÓN - Procesamiento por LOTES (Batching) para ChromaDB
                BATCH_SIZE = 25
                for i in range(0, total_chunks, BATCH_SIZE):
                    batch_chunks = chunks[i : i + BATCH_SIZE]
                    
                    ids = []
                    docs = []
                    metas = []
                    
                    for j, chunk in enumerate(batch_chunks):
                        idx = i + j
                        ids.append(f"book_{title}_{idx}")
                        docs.append(chunk)
                        metas.append({
                            "book_title": title,
                            "chunk_index": idx,
                            "total_chunks": total_chunks,
                            "category": "Library",
                            "user_id": user_id
                        })
                    
                    # Inyección masiva en la base de datos vectorial
                    await vector_db.upsert_batch(ids, docs, metas)
                    
                    # Log de progreso para el usuario
                    progress = min(100, int(((i + BATCH_SIZE) / total_chunks) * 100))
                    print(f"[Librarian] Progreso '{title}': {progress}% completo...")

                print(f"[Librarian] ✅ Libro '{title}' absorbido y comprendido corectamente.")
                return True
            except Exception as e:
                print(f"[Librarian] ❌ Error absorbiendo '{title}': {e}")
                return False

# Global instance
librarian = Librarian()
