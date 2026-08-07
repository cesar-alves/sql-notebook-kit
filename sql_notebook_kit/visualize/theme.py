"""Theme validation and Plotly template construction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from sql_notebook_kit.errors import VisualizationConfigError

ThemeKind = Literal["light", "dark", "high_contrast"]
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

LIGHT_COLORWAY = (
    "#2563eb",
    "#d97706",
    "#059669",
    "#dc2626",
    "#7c3aed",
    "#0891b2",
    "#db2777",
    "#65a30d",
    "#9333ea",
    "#475569",
)
DARK_COLORWAY = (
    "#60a5fa",
    "#fbbf24",
    "#34d399",
    "#f87171",
    "#a78bfa",
    "#22d3ee",
    "#f472b6",
    "#a3e635",
    "#c084fc",
    "#94a3b8",
)

LIGHT = {
    "background": "#ffffff",
    "surface": "#ffffff",
    "surface_muted": "#f6f8fa",
    "surface_raised": "#ffffff",
    "text": "#1f2328",
    "text_muted": "#57606a",
    "border": "#d0d7de",
    "accent": "#0969da",
    "accent_hover": "#0550ae",
    "focus": "#0550ae",
    "danger": "#cf222e",
    "warning_bg": "#fff8c5",
    "warning_text": "#4d2d00",
    "selection_bg": "#ddf4ff",
    "input_bg": "#f6f8fa",
}
DARK = {
    "background": "#1e1e1e",
    "surface": "#252526",
    "surface_muted": "#313131",
    "surface_raised": "#2d2d30",
    "text": "#f0f0f0",
    "text_muted": "#c4c4c4",
    "border": "#5a5a5a",
    "accent": "#4daafc",
    "accent_hover": "#75beff",
    "focus": "#75beff",
    "danger": "#f48771",
    "warning_bg": "#3b2e00",
    "warning_text": "#ffd866",
    "selection_bg": "#063b49",
    "input_bg": "#313131",
}


@dataclass(frozen=True, slots=True)
class ThemeContext:
    kind: ThemeKind
    tokens: dict[str, str]
    font_family: str = "system-ui, sans-serif"
    colorway: tuple[str, ...] = LIGHT_COLORWAY

    def __post_init__(self) -> None:
        if self.kind not in ("light", "dark", "high_contrast"):
            raise VisualizationConfigError("unsupported theme kind", path="theme.kind")
        required = set(LIGHT)
        missing = required - set(self.tokens)
        if missing:
            raise VisualizationConfigError(
                f"missing token {sorted(missing)[0]!r}", path="theme.tokens"
            )
        for name, value in self.tokens.items():
            if not isinstance(value, str) or not _HEX.fullmatch(value):
                raise VisualizationConfigError(
                    "must be an opaque #rrggbb color", path=f"theme.tokens.{name}"
                )

    @classmethod
    def fallback(cls, kind: ThemeKind = "light") -> ThemeContext:
        dark = kind in ("dark", "high_contrast")
        return cls(
            kind, dict(DARK if dark else LIGHT), colorway=DARK_COLORWAY if dark else LIGHT_COLORWAY
        )


def build_plotly_template(theme: ThemeContext) -> Any:
    """Build an isolated Plotly template without changing process globals."""
    import plotly.graph_objects as go

    t = theme.tokens
    axis = {
        "color": t["text"],
        "linecolor": t["border"],
        "gridcolor": t["border"],
        "zerolinecolor": t["border"],
        "tickcolor": t["border"],
        "showline": True,
    }
    return go.layout.Template(
        layout={
            "paper_bgcolor": t["background"],
            "plot_bgcolor": t["surface"],
            "font": {"color": t["text"], "family": theme.font_family},
            "title": {"font": {"color": t["text"]}},
            "legend": {"font": {"color": t["text"]}, "bgcolor": t["surface"]},
            "hoverlabel": {
                "bgcolor": t["surface_raised"],
                "font": {"color": t["text"]},
                "bordercolor": t["border"],
            },
            "xaxis": axis,
            "yaxis": axis,
            "colorway": list(theme.colorway),
            "modebar": {
                "bgcolor": t["surface"],
                "color": t["text_muted"],
                "activecolor": t["accent"],
            },
            "coloraxis": {
                "colorbar": {"tickfont": {"color": t["text"]}, "outlinecolor": t["border"]}
            },
        },
        data={
            "table": [
                go.Table(
                    header={
                        "fill": {"color": t["surface_muted"]},
                        "font": {"color": t["text"]},
                        "line": {"color": t["border"]},
                    },
                    cells={
                        "fill": {"color": t["surface"]},
                        "font": {"color": t["text"]},
                        "line": {"color": t["border"]},
                    },
                )
            ],
            "indicator": [
                go.Indicator(
                    number={"font": {"color": t["text"]}},
                    delta={"font": {"color": t["text"]}},
                    title={"font": {"color": t["text"]}},
                )
            ],
        },
    )


__all__ = ["ThemeContext", "ThemeKind", "build_plotly_template"]
