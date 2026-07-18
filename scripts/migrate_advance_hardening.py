from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('bills')]
    
    with engine.connect() as conn:
        if 'advance_source' not in columns:
            print("Adding advance_source column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN advance_source VARCHAR'))
        
        if 'advance_verification_status' not in columns:
            print("Adding advance_verification_status column...")
            conn.execute(text("ALTER TABLE bills ADD COLUMN advance_verification_status VARCHAR DEFAULT 'UNVERIFIED'"))
        
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
