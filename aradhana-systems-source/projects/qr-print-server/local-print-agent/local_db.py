import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "agent_state.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS local_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT, -- 'PENDING', 'PRINTED', 'FAILED'
                pdf_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

def get_job_status(job_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT status FROM local_jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return row[0] if row else None

def set_job_status(job_id, status, pdf_path=""):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO local_jobs (job_id, status, pdf_path) 
            VALUES (?, ?, ?) 
            ON CONFLICT(job_id) DO UPDATE SET 
                status=excluded.status, 
                pdf_path=CASE WHEN excluded.pdf_path != '' THEN excluded.pdf_path ELSE local_jobs.pdf_path END
        ''', (job_id, status, pdf_path))
