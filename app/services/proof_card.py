from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import AviationFlight, AviationSignal

BACKGROUND = "#05070A"
SIGNAL_GREEN = "#00E5A0"
FLIGHT_WHITE = (239, 245, 240)
MUTED_ROUTE = "#5a7060"
TIMESTAMP_GREEN = "#006B4F"
CONFIDENCE_MUTED = "#3a4a3e"
LOW_CONTRAST = "#1a2a1e"
CARD_SIZE = 1080
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
IMAGE_DIR = Path(__file__).resolve().parents[1] / "assets" / "images"
EXO2_BOLD_PATH = FONT_DIR / "Exo2-Bold.ttf"
DMMONO_REGULAR_PATH = FONT_DIR / "DMMono-Regular.ttf"
ZH_MARK_PATH = IMAGE_DIR / "zh_mark.png"
ZH_MARK_SIZE = 48
ZH_MARK_PADDING = 24


def render_proof_card_png(signal: "AviationSignal", flight: "AviationFlight") -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (CARD_SIZE, CARD_SIZE), BACKGROUND)
    draw = ImageDraw.Draw(image)

    exo_bold_10 = _font(EXO2_BOLD_PATH, 10)
    exo_bold_48 = _font(EXO2_BOLD_PATH, 48)
    exo_bold_64 = _font(EXO2_BOLD_PATH, 64)
    dm_9 = _font(DMMONO_REGULAR_PATH, 9)
    dm_11 = _font(DMMONO_REGULAR_PATH, 11)
    dm_12 = _font(DMMONO_REGULAR_PATH, 12)
    dm_14 = _font(DMMONO_REGULAR_PATH, 14)

    draw.rectangle((0, 0, CARD_SIZE, 3), fill=SIGNAL_GREEN)

    _draw_tracking_text(
        draw,
        (64, 72),
        "ZEROHOUR SIGNAL CONFIRMED",
        exo_bold_10,
        SIGNAL_GREEN,
        tracking=2,
    )

    _draw_centered_tracking_text(
        draw,
        y=174,
        text=flight.flight_number.upper(),
        font=exo_bold_48,
        fill=FLIGHT_WHITE,
        tracking=2,
    )

    route_separator = " \u2192 " if _font_supports_text(dm_14, "\u2192") else " to "
    route = (
        f"{flight.origin.upper()}{route_separator}{flight.destination.upper()} "
        f"\u00b7 {_format_date(flight.departure_date)}"
    )
    _draw_centered_text(draw, 240, route, dm_14, MUTED_ROUTE)

    draw.line((64, 326, 1016, 326), fill=(0, 229, 160, 51), width=1)

    fired = f"ZeroHour signal fired \u00b7 {_format_time(signal.fired_at)}"
    announced = f"Airline announced \u00b7 {_format_time(signal.airline_announced_at)}"
    draw.text((64, 394), fired, font=dm_12, fill=TIMESTAMP_GREEN)
    draw.text((64, 442), announced, font=dm_12, fill=TIMESTAMP_GREEN)

    draw.line((64, 520, 1016, 520), fill=SIGNAL_GREEN, width=2)

    head_start_text = _format_head_start(signal.head_start_minutes or 0)
    head_start_y = 632
    _draw_centered_text(
        draw,
        head_start_y,
        head_start_text,
        exo_bold_64,
        SIGNAL_GREEN,
    )
    _, _, _, head_start_bottom = draw.textbbox((0, head_start_y), head_start_text, font=exo_bold_64)
    _draw_centered_text(
        draw,
        head_start_bottom + 20,
        f"ZeroHour confidence \u00b7 {signal.score}%",
        dm_11,
        CONFIDENCE_MUTED,
    )

    _paste_zerohour_mark(image)
    _draw_centered_text(draw, 997, "flyzerohour.com", dm_9, SIGNAL_GREEN)

    signal_label = f"Signal #{str(signal.id).split('-')[0].upper()}"
    signal_width = _text_width(draw, signal_label, dm_9)
    draw.text((1016 - signal_width, 997), signal_label, font=dm_9, fill=LOW_CONTRAST)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _font(font_path: Path, size: int):
    from PIL import ImageFont

    if font_path.exists():
        return ImageFont.truetype(str(font_path), size=size)
    for path in _fallback_font_candidates(font_path):
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def _fallback_font_candidates(font_path: Path) -> list[Path]:
    if font_path.name == "Exo2-Bold.ttf":
        return [
            Path("/Library/Fonts/Exo2-Bold.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ]
    return [
        Path("/Library/Fonts/DMMono-Regular.ttf"),
        Path("/System/Library/Fonts/Menlo.ttc"),
        Path("/Library/Fonts/Menlo.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ]


def _draw_centered_text(draw, y: int, text: str, font, fill: str) -> None:
    width = _text_width(draw, text, font)
    draw.text(((CARD_SIZE - width) / 2, y), text, font=font, fill=fill)


def _draw_centered_tracking_text(draw, *, y: int, text: str, font, fill: str, tracking: int) -> None:
    width = _tracking_width(draw, text, font, tracking)
    _draw_tracking_text(draw, ((CARD_SIZE - width) / 2, y), text, font, fill, tracking)


def _draw_tracking_text(draw, xy: tuple[float, float], text: str, font, fill: str, tracking: int) -> None:
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += _text_width(draw, char, font) + tracking


def _tracking_width(draw, text: str, font, tracking: int) -> float:
    if not text:
        return 0
    return sum(_text_width(draw, char, font) for char in text) + tracking * (len(text) - 1)


def _text_width(draw, text: str, font) -> float:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def _font_supports_text(font, text: str) -> bool:
    for char in text:
        try:
            glyph_mask = font.getmask(char)
            missing_mask = font.getmask("\ue000")
        except Exception:
            return False
        if glyph_mask.size == missing_mask.size and bytes(glyph_mask) == bytes(missing_mask):
            return False
    return True


def _paste_zerohour_mark(image) -> None:
    from PIL import Image, ImageOps

    if not ZH_MARK_PATH.exists():
        return
    source = Image.open(ZH_MARK_PATH).convert("RGBA")
    alpha = ImageOps.grayscale(source)
    bbox = alpha.getbbox()
    if bbox:
        source = source.crop(bbox)
    alpha = ImageOps.grayscale(source)
    mark = Image.new("RGBA", source.size, SIGNAL_GREEN)
    mark.putalpha(alpha)
    canvas = mark.resize((ZH_MARK_SIZE, ZH_MARK_SIZE), Image.Resampling.LANCZOS)
    image.paste(
        canvas,
        (ZH_MARK_PADDING, CARD_SIZE - ZH_MARK_PADDING - ZH_MARK_SIZE),
        canvas,
    )


def _format_date(value: datetime) -> str:
    return value.strftime("%b %d, %Y").upper()


def _format_time(value: datetime | None) -> str:
    if not value:
        return "PENDING"
    return value.strftime("%I:%M %p").lstrip("0")


def _format_head_start(minutes: int) -> str:
    hours = minutes // 60
    remainder = minutes % 60
    return f"{hours}h {remainder}m ahead"
