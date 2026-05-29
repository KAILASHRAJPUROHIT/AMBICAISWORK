import socket
from pathlib import Path
import qrcode
from PIL import Image, ImageDraw, ImageFont

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "192.168.0.7"

ip = get_local_ip()
url = f"http://{ip}:5000"

out_dir = Path(r"C:\WhatsappAutoPrint")
out_dir.mkdir(parents=True, exist_ok=True)

qr = qrcode.QRCode(box_size=12, border=3)
qr.add_data(url)
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

poster_w, poster_h = 900, 1250
poster = Image.new("RGB", (poster_w, poster_h), "#f7f1e5")
draw = ImageDraw.Draw(poster)

try:
    title_font = ImageFont.truetype("arialbd.ttf", 54)
    text_font = ImageFont.truetype("arial.ttf", 34)
    small_font = ImageFont.truetype("arial.ttf", 26)
except:
    title_font = text_font = small_font = None

draw.text((poster_w//2, 90), "ARADHANA JEWELLERS", anchor="mm", fill="#06142E", font=title_font)
draw.text((poster_w//2, 160), "Scan to Upload & Print", anchor="mm", fill="#9a741c", font=text_font)

qr_size = 620
img = img.resize((qr_size, qr_size))
poster.paste(img, ((poster_w-qr_size)//2, 230))

draw.text((poster_w//2, 910), url, anchor="mm", fill="#06142E", font=small_font)
draw.text((poster_w//2, 980), "Upload JPG / PNG documents", anchor="mm", fill="#333333", font=small_font)
draw.text((poster_w//2, 1030), "Up to 6 files print on one A4 page", anchor="mm", fill="#333333", font=small_font)
draw.text((poster_w//2, 1080), "Collect print from counter", anchor="mm", fill="#333333", font=small_font)

poster_path = out_dir / "Aradhana_Print_QR_Poster.png"
poster.save(poster_path)

print("QR URL:", url)
print("Saved poster:", poster_path)
