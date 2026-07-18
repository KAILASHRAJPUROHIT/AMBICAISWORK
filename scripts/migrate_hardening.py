from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('bills')]
    
    with engine.connect() as conn:
        # Bill columns
        if 'is_delivered' not in columns:
            print("Adding is_delivered column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN is_delivered BOOLEAN DEFAULT 0'))
        
        if 'delivered_at' not in columns:
            print("Adding delivered_at column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN delivered_at DATETIME'))
            
        if 'delivery_approved_by' not in columns:
            print("Adding delivery_approved_by column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN delivery_approved_by VARCHAR'))

        if 'reversal_date' not in columns:
            print("Adding reversal_date column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN reversal_date DATETIME'))

        if 'reversal_reason' not in columns:
            print("Adding reversal_reason column...")
            conn.execute(text('ALTER TABLE bills ADD COLUMN reversal_reason VARCHAR'))

        # Cheque columns
        cheque_columns = [c['name'] for c in inspector.get_columns('cheques')]
        if 'expected_clearance_date' not in cheque_columns:
            print("Adding expected_clearance_date column to cheques...")
            conn.execute(text('ALTER TABLE cheques ADD COLUMN expected_clearance_date DATETIME'))
        
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
