import time
import logging
from pathlib import Path
from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Prevent Decompression Bomb DOS attacks
Image.MAX_IMAGE_PIXELS = 50000000 # ~50 MP limit

def classify_image(img_path):
    # Future OCR classification stub
    # ocr_keywords = ["invoice", "bill", "certificate", "application", "government form"]
    # ocr_text = extract_text_with_ocr(img_path).lower()
    # if any(kw in ocr_text for kw in ocr_keywords):
    #     logging.info(f"AUTO-DETECT OCR: {Path(img_path).name} | classification: FULL_PAGE")
    #     return "FULL_PAGE"

    img = Image.open(img_path)
    w, h = img.width, img.height
    filename = Path(img_path).name
    classification = "ID_CARD" # Default

    if h > w:
        ratio = h / w
        if 1.25 <= ratio <= 1.60:
            classification = "FULL_PAGE"
    elif w > h:
        ratio = w / h
        if 1.45 <= ratio <= 1.75:
            classification = "ID_CARD"

    logging.info(f"AUTO-DETECT: {filename} | dimensions: {w}x{h} | classification: {classification}")
    return classification

def create_full_page_layout(image_paths, output_pdf, temp_dir):
    c = canvas.Canvas(str(output_pdf), pagesize=A4)
    page_w, page_h = A4
    
    for idx, img_path in enumerate(image_paths):
        if idx > 0:
            c.showPage()
            
        img = Image.open(img_path)
        img = ImageOps.exif_transpose(img).convert("RGB")
        
        # Auto-rotate to fill the portrait A4 page
        if img.width > img.height:
            img = img.rotate(90, expand=True)
            
        ratio = img.width / img.height
        page_ratio = page_w / page_h
        
        if ratio > page_ratio:
            draw_w = page_w
            draw_h = page_w / ratio
        else:
            draw_h = page_h
            draw_w = page_h * ratio
            
        draw_x = (page_w - draw_w) / 2
        draw_y = (page_h - draw_h) / 2
        
        tmp_path = Path(temp_dir) / f"full_{int(time.time()*1000)}.jpg"
        img.save(tmp_path, "JPEG", quality=95)
        c.drawImage(str(tmp_path), draw_x, draw_y, width=draw_w, height=draw_h)
        
    c.save()

def prepare_image(path):
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    
    # Auto-rotate portrait to landscape
    if img.height > img.width:
        img = img.rotate(90, expand=True)
    return img

def create_id_layout(image_paths, output_pdf, temp_dir, pair_front_back=False):
    c = canvas.Canvas(str(output_pdf), pagesize=A4)
    page_w, page_h = A4
    
    # 6 Slots: 2 cols, 3 rows
    margin_x, margin_y = 35, 45
    gap_x, gap_y = 35, 40
    slot_w = 243 # PAN card width approx points
    slot_h = 153
    
    positions = []
    for row in range(3):
        for col in range(2):
            x = margin_x + col * (slot_w + gap_x)
            y = page_h - margin_y - slot_h - row * (slot_h + gap_y)
            positions.append((x, y))
            
    # Group images
    items = []
    if pair_front_back:
        for i in range(0, len(image_paths), 2):
            front = image_paths[i]
            back = image_paths[i+1] if i+1 < len(image_paths) else None
            items.append((front, back))
    else:
        for img in image_paths:
            items.append((img, None))
            
    # Draw items
    for idx, (front_img, back_img) in enumerate(items):
        if idx > 0 and idx % 6 == 0:
            c.showPage()
        
        x, y = positions[idx % 6]
        c.rect(x, y, slot_w, slot_h) # Border
        
        if back_img:
            # Split slot horizontally
            half_h = slot_h / 2
            # Front on top (higher Y), back on bottom (lower Y)
            draw_fitted_image(c, front_img, x, y + half_h, slot_w, half_h, temp_dir)
            draw_fitted_image(c, back_img, x, y, slot_w, half_h, temp_dir)
        else:
            # Full slot
            draw_fitted_image(c, front_img, x, y, slot_w, slot_h, temp_dir)
            
    c.save()

def draw_fitted_image(c, img_path, x, y, bounds_w, bounds_h, temp_dir):
    img = prepare_image(img_path)
    ratio = img.width / img.height
    bounds_ratio = bounds_w / bounds_h
    
    if ratio > bounds_ratio:
        draw_w = bounds_w
        draw_h = bounds_w / ratio
    else:
        draw_h = bounds_h
        draw_w = bounds_h * ratio
        
    draw_x = x + (bounds_w - draw_w) / 2
    draw_y = y + (bounds_h - draw_h) / 2
    
    tmp_path = Path(temp_dir) / f"render_{int(time.time()*1000)}.jpg"
    img.save(tmp_path, "JPEG", quality=95)
    c.drawImage(str(tmp_path), draw_x, draw_y, width=draw_w, height=draw_h)
