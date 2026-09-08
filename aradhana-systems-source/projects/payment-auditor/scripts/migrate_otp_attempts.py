from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('otps')]
    
    with engine.connect() as conn:
        if 'attempts' not in columns:
            print("Adding attempts column to otps...")
            conn.execute(text('ALTER TABLE otps ADD COLUMN attempts INTEGER DEFAULT 0'))
            conn.commit()
        else:
            print("attempts column already exists.")
            
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
