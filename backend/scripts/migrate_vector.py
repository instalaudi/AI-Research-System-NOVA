import sys
import os

# Add parent directory to sys.path to allow imports from core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal, KnowledgeEntry
from core.vector_db import vector_db

def migrate():
    print("🚀 Inciando migración de conocimiento a Vector DB (ChromaDB)...")
    db = SessionLocal()
    try:
        entries = db.query(KnowledgeEntry).all()
        total = len(entries)
        print(f"📊 Encontrados {total} artículos para indexar.")
        
        count = 0
        for entry in entries:
            text_to_index = f"{entry.title}\n{entry.content}"
            metadata = {
                "id": str(entry.id),
                "title": entry.title,
                "category": entry.category,
                "url": entry.url
            }
            vector_db.index_article(str(entry.id), text_to_index, metadata)
            count += 1
            if count % 10 == 0:
                print(f"✅ Procesados {count}/{total}...")
        
        print(f"🎉 Migración completada exitosamente. {count} artículos indexados.")
    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
