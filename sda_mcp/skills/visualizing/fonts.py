from __future__ import annotations

from matplotlib import font_manager, rcParams


CJK_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "PingFang SC",
    "WenQuanYi Micro Hei",
    "Arial Unicode MS",
]

FALLBACK_FONTS = ["DejaVu Sans", "Arial", "sans-serif"]


def _available_font_names() -> set[str]:
    return {font.name for font in font_manager.fontManager.ttflist}


def configure_fonts() -> list[str]:
    available = _available_font_names()
    selected = [font for font in CJK_FONT_CANDIDATES if font in available]
    rcParams["font.sans-serif"] = selected + FALLBACK_FONTS
    rcParams["font.family"] = "sans-serif"
    rcParams["axes.unicode_minus"] = False

    if selected:
        return []
    return [
        "No known CJK font detected; Chinese labels may render with fallback glyphs. "
        "Install Microsoft YaHei, SimHei, Noto Sans CJK SC, Source Han Sans SC, "
        "PingFang SC, WenQuanYi Micro Hei, or Arial Unicode MS for best results."
    ]
