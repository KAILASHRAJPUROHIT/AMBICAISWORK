ARADHANA QR PRINT SERVER - FINAL

1. Copy this folder to:
   C:\aradhana_qr_print_server_final

2. Install packages:
   pip install -r requirements.txt

3. Run:
   python app.py

4. Open on phone:
   http://YOUR-PC-IP:5000

5. Generate QR poster:
   python make_qr.py

6. Admin log:
   http://YOUR-PC-IP:5000/admin

7. Auto-start:
   Press Win + R
   Type: shell:startup
   Copy start_aradhana_print_server.bat into that folder.

Print rules:
- JPG/JPEG/PNG only
- Maximum 12 files per upload
- 1 file = 1 PAN-card-size slot
- 6 files = 1 A4 page
- 7-12 files = 2 A4 pages
