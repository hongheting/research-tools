"""共享样式与颜色工具。"""
from .style import apply_journal_style, COLORBLIND_SAFE, FIGURE_DPI
from .colors import (
    ColorError,
    PALETTES,
    add_color_arguments,
    colors_from_args,
    darken_color,
    parse_color,
    resolve_series_colors,
)

__all__ = [
    "apply_journal_style",
    "COLORBLIND_SAFE",
    "FIGURE_DPI",
    "ColorError",
    "PALETTES",
    "add_color_arguments",
    "colors_from_args",
    "darken_color",
    "parse_color",
    "resolve_series_colors",
]
