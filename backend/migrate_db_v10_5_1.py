import sqlite3
import os

DB_PATH = r"c:\Users\ELCHINO\OneDrive\Desktop\AI-Research-System\backend\knowledge.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Checking for 'updated_at' column in 'knowledge_nodes'...")
        cursor.execute("PRAGMA table_info(knowledge_nodes)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'updated_at' not in columns:
            print("Adding 'updated_at' column to 'knowledge_nodes'...")
            cursor.execute("ALTER TABLE knowledge_nodes ADD COLUMN updated_at DATETIME")
            # Initialize with current time
            cursor.execute("UPDATE knowledge_nodes SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
            conn.commit()
            print("Migration successful: Added 'updated_at' to 'knowledge_nodes'.")
        else:
            print("'updated_at' column already exists.")
            
    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
