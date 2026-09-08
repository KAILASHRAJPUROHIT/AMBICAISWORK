from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('payments')]
    
    with engine.connect() as conn:
        if 'payment_date' not in columns:
            print("Adding payment_date column to payments table...")
            conn.execute(text('ALTER TABLE payments ADD COLUMN payment_date DATETIME'))
            conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
