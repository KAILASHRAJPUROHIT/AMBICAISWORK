"""Deterministic delivery-image conversion for the catalogue pipeline.

The product decision between ``crop`` and ``pad`` is deliberately not encoded
as a default.  Callers must choose explicitly.  Both strategies preserve the
source file, publish atomically, and produce a 2400x2400 JPEG with an embedded
sRGB profile and 72 DPI metadata. Encoding starts at JPEG quality 95 and only
reduces quality when required to stay at or below the hard 1,000,000-byte cap.
"""

from __future__ import annotations

import argparse
import io
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Sequence

from PIL import Image, ImageCms, ImageFilter, ImageOps, ImageStat


TARGET_SIZE = (2400, 2400)
JPEG_QUALITY = 95
MIN_JPEG_QUALITY = 1
TARGET_DPI = 72
MIN_FILE_BYTES = 800_000
MAX_FILE_BYTES = 1_000_000
AI_SOURCE_TYPE = (
    "http://cv.iptc.org/newscodes/digitalsourcetype/CompositeSynthetic"
)
Strategy = Literal["crop", "pad"]


@dataclass(frozen=True, slots=True)
class ImageSpecResult:
    source: Path
    output: Path
    strategy: Strategy
    width: int
    height: int
    mode: str
    dpi: tuple[float, float]
    has_icc_profile: bool
    has_ai_source_metadata: bool
    file_bytes: int
    within_target_file_size: bool

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["source"] = str(self.source)
        payload["output"] = str(self.output)
        return payload


def convert_delivery_image(
    source: str | os.PathLike[str],
    output: str | os.PathLike[str],
    *,
    strategy: Strategy,
    overwrite: bool = False,
    target_size: tuple[int, int] = TARGET_SIZE,
    sharpen: bool = False,
    maximum_file_bytes: int = MAX_FILE_BYTES,
    minimum_jpeg_quality: int = MIN_JPEG_QUALITY,
) -> ImageSpecResult:
    """Convert one image without changing or replacing the source.

    ``crop`` uses a centred cover resize and may remove content at the long
    edges. ``pad`` uses a contain resize and fills the unused area with a
    colour sampled from the source border, preserving the complete frame.

    JPEG encoding begins at quality 95. If that exceeds 1,000,000 bytes, the
    highest fitting quality is selected by a bounded search. The complete JPEG
    payload (including ICC and XMP metadata) is measured before publication.
    Low-detail images may still compress below the preferred 800,000-byte floor.
    """

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if strategy not in ("crop", "pad"):
        raise ValueError("strategy must be 'crop' or 'pad'")
    if not source_path.is_file():
        raise FileNotFoundError(f"Source image does not exist: {source_path}")
    if source_path == output_path:
        raise ValueError("Source and output paths must be different")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output image already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as opened:
        oriented = ImageOps.exif_transpose(opened)
        srgb = _to_srgb(oriented)
        if strategy == "crop":
            converted = ImageOps.fit(
                srgb,
                target_size,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
        else:
            contained = ImageOps.contain(
                srgb,
                target_size,
                method=Image.Resampling.LANCZOS,
            )
            converted = Image.new("RGB", target_size, _border_colour(srgb))
            offset = (
                (target_size[0] - contained.width) // 2,
                (target_size[1] - contained.height) // 2,
            )
            converted.paste(contained, offset)
        if sharpen:
            sharpened = converted.filter(
                ImageFilter.UnsharpMask(radius=0.7, percent=70, threshold=2)
            )
            converted.close()
            converted = sharpened

    temporary = _temporary_sibling(output_path)
    try:
        payload = _encode_jpeg_under_cap(
            converted,
            maximum_file_bytes,
            minimum_jpeg_quality,
        )
        if len(payload) > maximum_file_bytes:
            raise ValueError(
                f"Encoded JPEG is {len(payload)} bytes; hard maximum is "
                f"{maximum_file_bytes} bytes"
            )
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        result = inspect_delivery_image(
            temporary,
            source=source_path,
            output=output_path,
            strategy=strategy,
            expected_size=target_size,
            maximum_file_bytes=maximum_file_bytes,
        )
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Output image already exists: {output_path}")
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
        converted.close()

    return ImageSpecResult(
        **{
            **result.as_dict(),
            "source": source_path,
            "output": output_path,
        }
    )


def inspect_delivery_image(
    path: str | os.PathLike[str],
    *,
    source: str | os.PathLike[str] | None = None,
    output: str | os.PathLike[str] | None = None,
    strategy: Strategy = "crop",
    expected_size: tuple[int, int] = TARGET_SIZE,
    maximum_file_bytes: int = MAX_FILE_BYTES,
) -> ImageSpecResult:
    """Inspect delivery metadata without modifying the image."""

    image_path = Path(path).resolve()
    with Image.open(image_path) as image:
        dpi_value = image.info.get("dpi") or (0.0, 0.0)
        dpi = (float(dpi_value[0]), float(dpi_value[1]))
        xmp = image.info.get("xmp") or b""
        if isinstance(xmp, str):
            xmp = xmp.encode("utf-8", errors="replace")
        result = ImageSpecResult(
            source=Path(source).resolve() if source else image_path,
            output=Path(output).resolve() if output else image_path,
            strategy=strategy,
            width=image.width,
            height=image.height,
            mode=image.mode,
            dpi=dpi,
            has_icc_profile=bool(image.info.get("icc_profile")),
            has_ai_source_metadata=AI_SOURCE_TYPE.encode("ascii") in xmp,
            file_bytes=image_path.stat().st_size,
            within_target_file_size=(
                MIN_FILE_BYTES <= image_path.stat().st_size <= maximum_file_bytes
            ),
        )
    if (result.width, result.height) != expected_size:
        raise ValueError(
            f"Output is {result.width}x{result.height}, expected "
            f"{expected_size[0]}x{expected_size[1]}"
        )
    if result.mode != "RGB":
        raise ValueError(f"Output colour mode is {result.mode!r}, expected 'RGB'")
    if not result.has_icc_profile:
        raise ValueError("Output has no embedded ICC profile")
    if not result.has_ai_source_metadata:
        raise ValueError("Output has no IPTC AI/composite source metadata")
    if any(abs(axis - TARGET_DPI) > 0.1 for axis in result.dpi):
        raise ValueError(f"Output DPI is {result.dpi}, expected 72x72")
    if result.file_bytes > maximum_file_bytes:
        raise ValueError(
            f"Output is {result.file_bytes} bytes, exceeding hard maximum "
            f"{maximum_file_bytes} bytes"
        )
    return result


def _to_srgb(image: Image.Image) -> Image.Image:
    embedded_profile = image.info.get("icc_profile")
    if embedded_profile:
        try:
            source_profile = ImageCms.ImageCmsProfile(io.BytesIO(embedded_profile))
            return ImageCms.profileToProfile(
                image,
                source_profile,
                ImageCms.createProfile("sRGB"),
                outputMode="RGB",
            )
        except (ImageCms.PyCMSError, OSError, ValueError):
            # A corrupt embedded profile must not make Pillow retain a
            # non-sRGB mode. The output still receives a valid sRGB profile.
            pass
    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def _border_colour(image: Image.Image) -> tuple[int, int, int]:
    sample = image.copy()
    sample.thumbnail((128, 128), Image.Resampling.LANCZOS)
    width, height = sample.size
    border = max(1, min(width, height) // 16)
    strips = (
        sample.crop((0, 0, width, border)),
        sample.crop((0, height - border, width, height)),
        sample.crop((0, 0, border, height)),
        sample.crop((width - border, 0, width, height)),
    )
    means = [ImageStat.Stat(strip).mean[:3] for strip in strips]
    sample.close()
    return tuple(
        round(sum(mean[channel] for mean in means) / len(means))
        for channel in range(3)
    )


def _srgb_profile_bytes() -> bytes:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    return profile.tobytes()


def _ai_source_xmp() -> bytes:
    """IPTC DigitalSourceType metadata required for AI product imagery."""
    return f'''<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
   Iptc4xmpExt:DigitalSourceType="{AI_SOURCE_TYPE}"/>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''.encode("utf-8")


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=quality,
        subsampling=0,
        optimize=True,
        dpi=(TARGET_DPI, TARGET_DPI),
        icc_profile=_srgb_profile_bytes(),
        xmp=_ai_source_xmp(),
    )
    return buffer.getvalue()


def _encode_jpeg_under_cap(
    image: Image.Image,
    maximum_file_bytes: int = MAX_FILE_BYTES,
    minimum_jpeg_quality: int = MIN_JPEG_QUALITY,
) -> bytes:
    """Return the highest-quality encoded payload within the hard byte cap."""

    preferred = _encode_jpeg(image, JPEG_QUALITY)
    if len(preferred) <= maximum_file_bytes:
        return preferred

    low = minimum_jpeg_quality
    high = JPEG_QUALITY - 1
    best: bytes | None = None
    while low <= high:
        quality = (low + high) // 2
        candidate = _encode_jpeg(image, quality)
        if len(candidate) <= maximum_file_bytes:
            best = candidate
            low = quality + 1
        else:
            high = quality - 1

    if best is None:
        raise ValueError(
            f"{image.width}x{image.height} JPEG cannot fit within "
            f"{maximum_file_bytes} bytes at minimum quality "
            f"{minimum_jpeg_quality}"
        )
    return best


def _temporary_sibling(output: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{output.stem}.",
        suffix=".jpg.tmp",
        dir=output.parent,
    )
    os.close(descriptor)
    return Path(name)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a 2400x2400 delivery JPEG")
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--strategy", choices=("crop", "pad"), required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    result = convert_delivery_image(
        args.source,
        args.output,
        strategy=args.strategy,
        overwrite=args.overwrite,
    )
    import json

    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
