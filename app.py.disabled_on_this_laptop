import csv
import os
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, request, render_template_string, redirect, url_for
from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)

# =========================
# CONFIG
# =========================

BASE = Path(r"C:\WhatsappAutoPrint")
UPLOADS = BASE / "Uploads"
OUTPUT = BASE / "Output"
PRINTED = BASE / "Printed"
ERROR = BASE / "Error"
TEMP = BASE / "Temp"
LOG_FILE = BASE / "print_log.csv"

PRINTER_NAME = "HPF8EDFC0532A7(HP Laser MFP 330)"
SUMATRA_PATH = r"C:\Users\kaila\AppData\Local\SumatraPDF\SumatraPDF.exe"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_FILES = 12

# PAN card size approx 85.6mm x 54mm in points
PAN_W = 243
PAN_H = 153

# 6 PAN slots per A4 page: 2 columns x 3 rows
MARGIN_X = 35
MARGIN_Y = 45
GAP_X = 35
GAP_Y = 40

for folder in [BASE, UPLOADS, OUTPUT, PRINTED, ERROR, TEMP]:
    folder.mkdir(parents=True, exist_ok=True)

if not LOG_FILE.exists():
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "status", "file_count", "output_pdf", "message"])


# =========================
# HTML
# =========================

UPLOAD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Aradhana Print Upload</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f5f1e8;
            padding: 30px;
            text-align: center;
        }
        .box {
            background: white;
            padding: 25px;
            border-radius: 18px;
            max-width: 440px;
            margin: auto;
            box-shadow: 0 8px 25px rgba(0,0,0,0.12);
        }
        h2 { color: #06142E; margin-bottom: 8px; }
        p { color: #333; line-height: 1.4; }
        input {
            margin: 20px 0;
            width: 100%;
        }
        button {
            background: #06142E;
            color: white;
            padding: 14px 22px;
            border: 0;
            border-radius: 10px;
            font-size: 18px;
            width: 100%;
        }
        .note {
            font-size: 13px;
            color: #666;
            margin-top: 16px;
        }
    </style>
</head>
<body>
    <div class="box">
        <h2>Aradhana Print Upload</h2>
        <p>Select JPG/PNG files. Up to 6 files print on one A4 sheet in PAN-card size.</p>
        <p>7 to 12 files will continue on page 2.</p>

        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="files" multiple accept=".jpg,.jpeg,.png" required>
            <button type="submit">Upload & Print</button>
        </form>

        <div class="note">
            Maximum {{ max_files }} files per upload.<br>
            Please wait after pressing Upload & Print.
        </div>
    </div>
</body>
</html>
"""

SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Print Sent</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f5f1e8;
            text-align: center;
            padding: 40px;
        }
        .box {
            background: white;
            padding: 30px;
            border-radius: 18px;
            max-width: 420px;
            margin: auto;
            box-shadow: 0 8px 25px rgba(0,0,0,0.12);
        }
        h2 { color: #06142E; }
        a {
            display: inline-block;
            margin-top: 20px;
            background: #06142E;
            color: white;
            padding: 12px 20px;
            border-radius: 10px;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="box">
        <h2>Print Sent Successfully</h2>
        <p>{{ count }} file(s) sent to printer.</p>
        <p>Please collect from counter.</p>
        <a href="/">Upload More</a>
    </div>
</body>
</html>
"""

ERROR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Print Error</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background:#f5f1e8; text-align:center; padding:40px; }
        .box { background:white; padding:30px; border-radius:18px; max-width:520px; margin:auto; box-shadow:0 8px 25px rgba(0,0,0,0.12); }
        h2 { color:#8B0000; }
        a { display:inline-block; margin-top:20px; background:#06142E; color:white; padding:12px 20px; border-radius:10px; text-decoration:none; }
        pre { white-space:pre-wrap; text-align:left; background:#f7f7f7; padding:12px; border-radius:8px; font-size:12px; }
    </style>
</head>
<body>
    <div class="box">
        <h2>Print Error</h2>
        <p>{{ message }}</p>
        <a href="/">Try Again</a>
    </div>
</body>
</html>
"""


# =========================
# HELPERS
# =========================

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "YOUR-PC-IP"


def log_event(status, file_count, output_pdf="", message=""):
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status,
            file_count,
            output_pdf,
            message
        ])


def safe_filename(name):
    keep = []
    for ch in name:
        if ch.isalnum() or ch in (" ", ".", "_", "-"):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep).strip() or f"upload_{int(time.time())}"


def prepare_image(path):
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")

    # PAN slot is landscape. Rotate portrait uploads into landscape.
    if img.height > img.width:
        img = img.rotate(90, expand=True)

    return img


def draw_image_in_slot(c, image_path, x, y):
    img = prepare_image(image_path)

    img_ratio = img.width / img.height
    slot_ratio = PAN_W / PAN_H

    if img_ratio > slot_ratio:
        draw_w = PAN_W
        draw_h = PAN_W / img_ratio
    else:
        draw_h = PAN_H
        draw_w = PAN_H * img_ratio

    draw_x = x + (PAN_W - draw_w) / 2
    draw_y = y + (PAN_H - draw_h) / 2

    temp_img = TEMP / f"{Path(image_path).stem}_{int(time.time() * 1000)}.jpg"
    img.save(temp_img, "JPEG", quality=95)

    c.drawImage(str(temp_img), draw_x, draw_y, width=draw_w, height=draw_h)

    # Cutting/alignment border
    c.rect(x, y, PAN_W, PAN_H)


def create_layout_pdf(files):
    output_pdf = OUTPUT / f"print_layout_{int(time.time())}.pdf"
    c = canvas.Canvas(str(output_pdf), pagesize=A4)

    page_w, page_h = A4

    positions = []
    for row in range(3):
        for col in range(2):
            x = MARGIN_X + col * (PAN_W + GAP_X)
            y = page_h - MARGIN_Y - PAN_H - row * (PAN_H + GAP_Y)
            positions.append((x, y))

    for index, file_path in enumerate(files):
        if index > 0 and index % 6 == 0:
            c.showPage()

        x, y = positions[index % 6]
        draw_image_in_slot(c, file_path, x, y)

    c.save()
    return output_pdf


def print_pdf(pdf_path):
    if not Path(SUMATRA_PATH).exists():
        raise FileNotFoundError(f"SumatraPDF not found at: {SUMATRA_PATH}")

    subprocess.run([
        SUMATRA_PATH,
        "-print-to",
        PRINTER_NAME,
        "-silent",
        str(pdf_path)
    ], check=True)


# =========================
# ROUTES
# =========================

@app.route("/", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template_string(UPLOAD_HTML, max_files=MAX_FILES)

    uploaded_files = request.files.getlist("files")

    if not uploaded_files or all(not f.filename for f in uploaded_files):
        return render_template_string(ERROR_HTML, message="No files selected.")

    if len(uploaded_files) > MAX_FILES:
        return render_template_string(
            ERROR_HTML,
            message=f"Too many files selected. Maximum allowed is {MAX_FILES} files."
        )

    saved_files = []

    try:
        batch_id = int(time.time() * 1000)

        for file in uploaded_files:
            if not file.filename:
                continue

            ext = Path(file.filename).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue

            clean_name = safe_filename(file.filename)
            save_path = UPLOADS / f"{batch_id}_{clean_name}"
            file.save(save_path)
            saved_files.append(save_path)

        if not saved_files:
            return render_template_string(
                ERROR_HTML,
                message="No valid files uploaded. Please upload JPG or PNG only."
            )

        pdf = create_layout_pdf(saved_files)
        print_pdf(pdf)

        log_event("printed", len(saved_files), str(pdf), "Sent to printer")

        # Important: redirect after POST prevents refresh from reprinting.
        return redirect(url_for("success", count=len(saved_files)))

    except Exception as e:
        log_event("error", len(saved_files), "", str(e))
        return render_template_string(ERROR_HTML, message=str(e))


@app.route("/success")
def success():
    count = request.args.get("count", "0")
    return render_template_string(SUCCESS_HTML, count=count)


@app.route("/admin")
def admin():
    rows = []
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))

    table_rows = ""
    for row in rows[-100:]:
        table_rows += "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Aradhana Print Log</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; background:#f5f1e8; padding:25px; }}
            h2 {{ color:#06142E; }}
            table {{ border-collapse: collapse; width: 100%; background:white; }}
            td, th {{ border:1px solid #ccc; padding:8px; font-size:13px; }}
            tr:first-child {{ font-weight:bold; background:#06142E; color:white; }}
            a {{ color:#06142E; }}
        </style>
    </head>
    <body>
        <h2>Aradhana Print Log</h2>
        <p><a href="/">Back to Upload Page</a></p>
        <table>{table_rows}</table>
    </body>
    </html>
    """


if __name__ == "__main__":
    ip = get_local_ip()
    print("Starting Aradhana QR Print Server...")
    print("Open on this PC: http://127.0.0.1:5000")
    print(f"Open on phone: http://{ip}:5000")
    print(f"Admin log: http://{ip}:5000/admin")
    app.run(host="0.0.0.0", port=5000)

import logging

logging.basicConfig(
    filename="server.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)