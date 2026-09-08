import time
from pathlib import Path
from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4

# Prevent Decompression Bomb DOS attacks
Image.MAX_IMAGE_PIXELS = 50000000 # ~50 MP limit
from reportlab.pdfgen import canvas

# PAN card size approx 85.6mm x 54mm in points
PAN_W = 243
PAN_H = 153

# 6 PAN slots per A4 page: 2 columns x 3 rows
MARGIN_X = 35
MARGIN_Y = 45
GAP_X = 35
GAP_Y = 40

def prepare_image(path):
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    
    # PAN slot is landscape. Rotate portrait uploads into landscape.
    if img.height > img.width:
        img = img.rotate(90, expand=True)
    return img

def draw_image_in_slot(c, image_path, x, y, temp_dir):
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

    temp_img = Path(temp_dir) / f"tmp_{Path(image_path).stem}_{int(time.time() * 1000)}.jpg"
    img.save(temp_img, "JPEG", quality=95)

    c.drawImage(str(temp_img), draw_x, draw_y, width=draw_w, height=draw_h)

    # Cutting/alignment border
    c.rect(x, y, PAN_W, PAN_H)

def create_layout_pdf(image_files, output_pdf_path, temp_dir):
    c = canvas.Canvas(str(output_pdf_path), pagesize=A4)
    page_w, page_h = A4

    positions = []
    for row in range(3):
        for col in range(2):
            x = MARGIN_X + col * (PAN_W + GAP_X)
            y = page_h - MARGIN_Y - PAN_H - row * (PAN_H + GAP_Y)
            positions.append((x, y))

    for index, file_path in enumerate(image_files):
        if index > 0 and index % 6 == 0:
            c.showPage()
        
        x, y = positions[index % 6]
        draw_image_in_slot(c, file_path, x, y, temp_dir)

    c.save()
    return output_pdf_path
