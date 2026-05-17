import os
import sys
import unicodedata

# Add project paths to import core modules dynamically
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.database import SessionLocal, KnowledgeEntry

def normalize_text(text: str) -> str:
    if not text: return ""
    text = text.lower()
    return "".join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

MAPPING = {
    "astronomia": ["galaxia", "estrella", "planeta", "tierra", "astro", "cosmos", "universo", "reionizacion", "telescopio", "marte", "espectrometro"],
    "computacion cuantica": ["cuantica", "quantum", "qbit", "qubit", "entrelazamiento", "ibm", "google sycamore"],
    "inteligencia artificial": ["ia", "ai", "aprendizaje", "neuronal", "redes", "deep learning", "machine learning", "clasificacion", "convolucional"],
    "software": ["prueba", "estudiante", "github", "repositorio", "codigo", "programacion"],
    "medicina": ["cerebral", "imagenes", "medica", "especies", "peces", "estudio"]
}

def run_hotfix():
    db = SessionLocal()
    try:
        entries = db.query(KnowledgeEntry).all()
        updated_count = 0
        
        for entry in entries:
            norm_title = normalize_text(entry.title or "")
            norm_content = normalize_text((entry.content or "")[:5000])
            norm_concepts = normalize_text(entry.concepts or "")
            
            full_text = f"{norm_title} {norm_content} {norm_concepts}"
            
            current_tags = set(entry.concepts.split(",")) if entry.concepts else set()
            new_tags = set()
            
            for parent_tag, keywords in MAPPING.items():
                if parent_tag in current_tags: continue
                
                for kw in keywords:
                    if kw in full_text:
                        new_tags.add(parent_tag)
                        break
            
            if new_tags:
                merged = current_tags | new_tags
                entry.concepts = ",".join(list(merged))
                updated_count += 1
                tags_str = ", ".join(new_tags)
                print(f"Propagado [{tags_str}] a: {entry.title[:50]}...")
        
        db.commit()
        print(f"\nHotfix completado. {updated_count} entradas actualizadas.")
    except Exception as e:
        db.rollback()
        print(f"Error en hotfix: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_hotfix()
