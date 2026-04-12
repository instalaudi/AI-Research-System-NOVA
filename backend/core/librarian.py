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
from core.knowledge_base import knowledge_base
from core.vector_db import vector_db
from core.database import SessionLocal, KnowledgeEntry

class Librarian:
    def __init__(self, chunk_size: int = 2000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = True
        self.html_converter.ignore_images = True

    def parse_pdf(self, file_path: str) -> str:
        """Extracts text from a PDF file."""
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        return text

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
        """Splits text into overlapping chunks recursively."""
        if not text:
            return []
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += (self.chunk_size - self.overlap)
        
        return chunks

    async def ingest_book(self, file_path: str, title: str, user_id: int = None):
        """Processes a book and stores it in the knowledge base and vector DB."""
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == ".pdf":
                full_text = self.parse_pdf(file_path)
            elif ext == ".epub":
                full_text = self.parse_epub(file_path)
            elif ext == ".txt":
                full_text = self.parse_txt(file_path)
            else:
                raise ValueError(f"Formato no soportado: {ext}")

            if not full_text.strip():
                raise ValueError("No se pudo extraer texto del archivo.")

            chunks = self.chunk_text(full_text)
            print(f"[Librarian] Book '{title}' parsed into {len(chunks)} chunks.")

            # Create a main entry for the book in KnowledgeBase
            book_metadata = {
                "title": title,
                "category": "Library",
                "content": f"Libro completo: {title}. Este registro contiene el índice y metadatos. El contenido real está indexado semánticamente.",
                "confidence_score": 1.0,
                "url": f"local://library/{title}",
                "concepts": ["Libro", "Biblioteca", title],
                "quality_flag": "book_ingestion"
            }
            await knowledge_base.add_entry(book_metadata, user_id=user_id)

            # Index chunks in VectorDB
            for i, chunk in enumerate(chunks):
                chunk_id = f"book_{title}_{i}"
                chunk_metadata = {
                    "book_title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "category": "Library",
                    "user_id": user_id
                }
                # We use a slightly different method name for chunking if we decide to refactor vector_db
                # For now, index_article works as it uses upsert with ID
                vector_db.index_article(chunk_id, chunk, chunk_metadata)
            
            print(f"[Librarian] Book '{title}' successfully ingested.")
            return True
        except Exception as e:
            print(f"[Librarian] Error ingesting book '{title}': {e}")
            return False

# Global instance
librarian = Librarian()
