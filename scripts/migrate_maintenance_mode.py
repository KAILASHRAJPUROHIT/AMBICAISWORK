from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    with engine.connect() as conn:
        if 'maintenance_sessions' not in tables:
            print("Creating maintenance_sessions table...")
            conn.execute(text("""
                CREATE TABLE maintenance_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    developer_id VARCHAR NOT NULL,
                    start_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    end_at DATETIME,
                    reason VARCHAR NOT NULL,
                    actions_performed TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
