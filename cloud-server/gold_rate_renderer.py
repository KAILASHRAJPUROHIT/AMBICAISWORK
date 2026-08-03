from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont


RATE_INPUT = re.compile(r"^\s*(?:₹|rs\.?|inr)?\s*([0-9][0-9,\s]*)\s*$", re.IGNORECASE)
EXPECTED_SIZE = (941, 1672)
DATE_BOX = (198, 812, 476, 875)
RATE_BOX = (62, 1064, 521, 1171)


def parse_rate(text: str) -> str | None:
    """Return normalized digits for a valid rate message, otherwise None."""
    match = RATE_INPUT.fullmatch(text)
    if not match:
        return None
    digits = re.sub(r"[,\s]", "", match.group(1))
    if not digits or len(digits) > 9:
        return None
    value = int(digits)
    if value < 1:
        return None
    return str(value)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(path),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def _fit_font(
    text: str,
    font_path: str,
    max_size: int,
    min_size: int,
    max_width: int,
) -> ImageFont.FreeTypeFont:
    for size in range(max_size, min_size - 1, -1):
        font = _font(font_path, size)
        left, _top, right, _bottom = font.getbbox(text, stroke_width=1)
        if right - left <= max_width:
            return font
    return _font(font_path, min_size)


def _centered_position(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    stroke_width: int = 0,
) -> tuple[int, int]:
    bounds = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = box[0] + ((box[2] - box[0]) - width) // 2 - bounds[0]
    y = box[1] + ((box[3] - box[1]) - height) // 2 - bounds[1]
    return x, y


def _draw_gold_text(
    image: Image.Image,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
) -> None:
    draw = ImageDraw.Draw(image)
    position = _centered_position(draw, box, text, font, stroke_width=1)

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.text(
        (position[0] + 3, position[1] + 4),
        text,
        font=font,
        fill=(0, 0, 0, 155),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 110),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(2.0))
    image.alpha_composite(shadow)

    # Dark rim followed by a warm vertical gold gradient gives the type the same
    # embossed feeling as the supplied artwork.
    draw = ImageDraw.Draw(image)
    draw.text(
        position,
        text,
        font=font,
        fill=(151, 97, 18, 255),
        stroke_width=2,
        stroke_fill=(104, 65, 10, 255),
    )

    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).text(position, text, font=font, fill=255)
    gradient = Image.new("RGBA", image.size)
    pixels = gradient.load()
    top, bottom = box[1], box[3]
    for y in range(top, bottom + 1):
        t = (y - top) / max(1, bottom - top)
        color = (
            round(250 + (183 - 250) * t),
            round(218 + (128 - 218) * t),
            round(111 + (27 - 111) * t),
            255,
        )
        for x in range(box[0], box[2] + 1):
            pixels[x, y] = color
    image.paste(gradient, (0, 0), mask)


@dataclass(frozen=True)
class RenderResult:
    path: Path
    rate: str
    date_label: str


class RateImageRenderer:
    def __init__(self, template_path: Path, output_dir: Path, timezone: str) -> None:
        self.template_path = template_path
        self.output_dir = output_dir
        self.timezone = ZoneInfo(timezone)

    def render(self, rate: str, now: datetime | None = None) -> RenderResult:
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template image not found: {self.template_path}")

        instant = now or datetime.now(self.timezone)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=self.timezone)
        else:
            instant = instant.astimezone(self.timezone)
        date_label = f"{instant.day} {instant.strftime('%B %Y')}"

        image = Image.open(self.template_path).convert("RGBA")
        if image.size != EXPECTED_SIZE:
            raise ValueError(f"Expected a {EXPECTED_SIZE} template, received {image.size}")

        date_font = _fit_font(
            date_label,
            r"C:\Windows\Fonts\arialbd.ttf",
            max_size=38,
            min_size=28,
            max_width=DATE_BOX[2] - DATE_BOX[0] - 8,
        )
        draw = ImageDraw.Draw(image)
        date_pos = _centered_position(draw, DATE_BOX, date_label, date_font)
        draw.text(
            (date_pos[0] + 1, date_pos[1] + 2),
            date_label,
            font=date_font,
            fill=(0, 0, 0, 105),
        )
        draw.text(date_pos, date_label, font=date_font, fill=(247, 247, 249, 255))

        price_text = f"₹ {rate}"
        price_font = _fit_font(
            price_text,
            r"C:\Windows\Fonts\timesbd.ttf",
            max_size=98,
            min_size=55,
            max_width=RATE_BOX[2] - RATE_BOX[0] - 10,
        )
        _draw_gold_text(image, RATE_BOX, price_text, price_font)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"rate-{instant.strftime('%Y%m%d-%H%M%S')}-{rate}.jpg"
        destination = self.output_dir / filename
        image.convert("RGB").save(destination, "JPEG", quality=94, optimize=True)
        return RenderResult(path=destination, rate=rate, date_label=date_label)
