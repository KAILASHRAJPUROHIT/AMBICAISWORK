from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('bills')]
    
    with engine.connect() as conn:
        if 'is_test_data' not in columns:
            print("Adding is_test_data column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN is_test_data BOOLEAN DEFAULT 0'))
        
        if 'customer_purchase_amount' not in columns:
            print("Adding customer_purchase_amount column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN customer_purchase_amount NUMERIC(12, 2) DEFAULT 0.0'))
            
        if 'advance_amount' not in columns:
            print("Adding advance_amount column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN advance_amount NUMERIC(12, 2) DEFAULT 0.0'))
        
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
