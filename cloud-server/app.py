import os
import json
import random
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# Configuration
BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

app = Flask(__name__, template_folder='app/templates')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{BASE_DIR}/jobs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Max 50MB total upload size
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 

db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf'}
MAX_FILES = 12

# Database Model
class PrintJob(db.Model):
    __tablename__ = 'print_jobs'
    id = db.Column(db.String(32), primary_key=True)
    status = db.Column(db.String(20), default='pending') # pending, printing, completed, failed
    print_mode = db.Column(db.String(20), default='auto')
    copies = db.Column(db.Integer, default=1)
    front_back_pairing = db.Column(db.Boolean, default=False)
    file_paths = db.Column(db.Text) # JSON string of paths relative to UPLOADS_DIR
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def generate_queue_id():
    now = datetime.now()
    date_str = now.strftime('%Y%m%d')
    rnd_str = f"{random.randint(1, 999):03d}"
    return f"AR-{date_str}-{rnd_str}"

def is_allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

# Setup Database
with app.app_context():
    db.create_app() if hasattr(db, 'create_app') else db.create_all()

@app.route('/', methods=['GET'])
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    files = request.files.getlist('files[]')
    
    if not files or len(files) == 0:
        return jsonify({"error": "No files uploaded"}), 400
    
    if len(files) > MAX_FILES:
        return jsonify({"error": f"Maximum {MAX_FILES} files allowed."}), 400
        
    print_mode = request.form.get('print_mode', 'auto')
    copies = int(request.form.get('copies', 1))
    front_back_pairing = request.form.get('front_back_pairing', 'false').lower() == 'true'
    
    job_id = generate_queue_id()
    
    # Create job directory
    job_dir = UPLOADS_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    
    saved_paths = []
    
    for file in files:
        if file.filename == '':
            continue
            
        if not is_allowed_file(file.filename):
            return jsonify({"error": f"File type not allowed: {file.filename}"}), 400
            
        filename = secure_filename(file.filename)
        # Add timestamp to prevent overwriting files with the same name
        timestamp = int(time.time() * 1000)
        unique_filename = f"{timestamp}_{filename}"
        
        file_path = job_dir / unique_filename
        file.save(str(file_path))
        saved_paths.append(f"{job_id}/{unique_filename}")
        
    if not saved_paths:
        return jsonify({"error": "No valid files were processed."}), 400
        
    # Save to database
    new_job = PrintJob(
        id=job_id,
        print_mode=print_mode,
        copies=copies,
        front_back_pairing=front_back_pairing,
        file_paths=json.dumps(saved_paths)
    )
    
    db.session.add(new_job)
    db.session.commit()
    
    return jsonify({"success": True, "queue_id": job_id}), 201

@app.route('/media/<job_id>/<filename>', methods=['GET'])
def serve_media(job_id, filename):
    # Basic security check
    job_dir = UPLOADS_DIR / secure_filename(job_id)
    return send_from_directory(job_dir, secure_filename(filename))

@app.route('/api/agent/jobs/pending', methods=['GET'])
def get_pending_jobs():
    # Note: Authentication logic would go here in production
    
    pending_jobs = PrintJob.query.filter_by(status='pending').all()
    jobs_response = []
    
    base_url = request.host_url.rstrip('/')
    
    for job in pending_jobs:
        paths = json.loads(job.file_paths) if job.file_paths else []
        image_urls = [f"{base_url}/media/{path}" for path in paths]
        
        # We pass image_urls. If it's a PDF mode and exactly one file, maybe we pass it as pdf_url.
        # But our local agent layout.py accepts image_urls for compilation.
        # For simplicity and agent compatibility, we'll assign pdf_url if the only file is a PDF,
        # otherwise provide image_urls.
        
        job_data = {
            "id": job.id,
            "print_mode": job.print_mode,
            "copies": job.copies,
            "front_back_pairing": job.front_back_pairing,
        }
        
        if len(paths) == 1 and paths[0].lower().endswith('.pdf'):
            job_data["pdf_url"] = image_urls[0]
        else:
            job_data["image_urls"] = image_urls
            
        jobs_response.append(job_data)
        
    return jsonify({"jobs": jobs_response})

@app.route('/api/agent/jobs/<job_id>/status', methods=['PATCH'])
def update_job_status(job_id):
    # Note: Authentication logic would go here in production
    
    job = PrintJob.query.filter_by(id=job_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
        
    data = request.json
    if not data or 'status' not in data:
        return jsonify({"error": "Missing status"}), 400
        
    new_status = data['status']
    
    job.status = new_status
    if 'error' in data and data['error']:
        # Could log this or store in a separate error column
        print(f"Job {job_id} reported error: {data['error']}")
        
    db.session.commit()
    
    return jsonify({"success": True, "status": job.status})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)