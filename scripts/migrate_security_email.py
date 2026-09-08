from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('users')]
    
    with engine.connect() as conn:
        if 'security_email' not in columns:
            print("Adding security_email column to users...")
            conn.execute(text('ALTER TABLE users ADD COLUMN security_email VARCHAR'))
            conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
