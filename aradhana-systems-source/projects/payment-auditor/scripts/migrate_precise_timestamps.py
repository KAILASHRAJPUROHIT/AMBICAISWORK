from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('bills')]
    
    with engine.connect() as conn:
        if 'invoice_generated_at' not in columns:
            print("Adding invoice_generated_at column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN invoice_generated_at DATETIME'))
        
        if 'ingested_at' not in columns:
            print("Adding ingested_at column...")
            conn.execute(text("ALTER TABLE bills ADD COLUMN ingested_at DATETIME"))
            # For existing records, set ingested_at = created_at
            conn.execute(text("UPDATE bills SET ingested_at = created_at"))
        
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
