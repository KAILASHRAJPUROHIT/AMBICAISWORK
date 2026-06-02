import sys
import os
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database import engine
from sqlalchemy import text, inspect

def migrate():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('bills')]
    
    if 'order_date' not in columns:
        print("Adding order_date column to bills table...")
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE bills ADD COLUMN order_date DATETIME'))
            conn.commit()
        print("Done.")
    else:
        print("order_date column already exists.")

if __name__ == "__main__":
    migrate()
