import time
from pathlib import Path
from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Prevent Decompression Bomb DOS attacks
Image.MAX_IMAGE_PIXELS = 50000000 # ~50 MP limit

def is_image(file_path):
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True
    except Exception:
        return False

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

def create_id_layout(image_paths, output_pdf, temp_dir):
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
            
    # Draw items
    for idx, img_path in enumerate(image_paths):
        if idx > 0 and idx % 6 == 0:
            c.showPage()
        
        x, y = positions[idx % 6]
        c.rect(x, y, slot_w, slot_h) # Border
        
        # Full slot
        draw_fitted_image(c, img_path, x, y, slot_w, slot_h, temp_dir)
            
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
