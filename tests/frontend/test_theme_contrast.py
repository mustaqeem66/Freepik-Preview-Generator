"""Colour-contrast regression guard for the studio theme.

The primary button label and every accent-coloured label are read by the user,
so they must clear the WCAG AA 4.5:1 floor for normal text. These checks read
the shipped stylesheets directly, so a colour change cannot quietly drop a
ratio below the floor without failing the suite.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "frontend" / "src"


def _channel(value: int) -> float:
    """The sRGB electro-optical transfer function."""
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    clean = hex_colour.lstrip("#")
    red, green, blue = (int(clean[index:index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _contrast(foreground: str, background: str) -> float:
    first = _luminance(foreground)
    second = _luminance(background)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def _mix(from_colour: str, to_colour: str, amount: float) -> str:
    def channels(colour: str) -> list[int]:
        clean = colour.lstrip("#")
        return [int(clean[index:index + 2], 16) for index in (0, 2, 4)]

    start = channels(from_colour)
    end = channels(to_colour)
    blended = [
        round(start[index] + (end[index] - start[index]) * amount) for index in range(3)
    ]
    return "#" + "".join(f"{value:02x}" for value in blended)


def _tokens(css: str, selector: str) -> dict[str, str]:
    block = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    found: dict[str, str] = {}
    if not block:
        return found
    for name, value in re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{3,8})\s*;", block.group(1)):
        found[name] = value
    return found


@pytest.fixture(scope="module")
def theme_css() -> str:
    return (SRC_DIR / "index.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def light(theme_css: str) -> dict[str, str]:
    return _tokens(theme_css, ":root")


@pytest.fixture(scope="module")
def dark(theme_css: str) -> dict[str, str]:
    return _tokens(theme_css, '[data-theme="dark"]')


def test_accent_text_token_exists(light: dict[str, str], dark: dict[str, str]) -> None:
    """Accent-coloured text needs its own token; the solid accent is a fill."""
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", light.get("accent-text", ""))
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", dark.get("accent-text", ""))


@pytest.mark.parametrize("surface", ["bg", "card-bg", "surface"])
def test_accent_text_is_readable_on_every_surface(
    light: dict[str, str], dark: dict[str, str], surface: str
) -> None:
    for theme, values in (("light", light), ("dark", dark)):
        ratio = _contrast(values["accent-text"], values[surface])
        assert ratio >= 4.5, (
            f"{theme}: --accent-text on --{surface} is {ratio:.2f}:1, below the 4.5:1 floor"
        )


def test_accent_text_is_readable_on_the_selection_surface(dark: dict[str, str]) -> None:
    """--selection is a tinted surface, so the pressed-state label needs its own check."""
    ratio = _contrast(dark["text"], dark["selection"])
    assert ratio >= 4.5, (
        f"dark: --text on --selection is {ratio:.2f}:1, below the 4.5:1 floor"
    )


@pytest.mark.parametrize(
    ("theme", "gradient_top"),
    [("light", "#2676cc"), ("dark", "#1a6fc8")],
)
def test_white_button_label_is_readable_across_the_whole_gradient(
    light: dict[str, str], dark: dict[str, str], theme: str, gradient_top: str
) -> None:
    """The label sits on every point of the gradient, so the worst point must pass."""
    values = light if theme == "light" else dark
    for step in range(21):
        shade = _mix(gradient_top, values["accent"], step / 20)
        ratio = _contrast("#ffffff", shade)
        assert ratio >= 4.5, (
            f"{theme}: white on {shade} is {ratio:.2f}:1, below the 4.5:1 floor"
        )


@pytest.mark.parametrize("token", ["text-sec", "text-muted"])
def test_secondary_text_is_readable_on_the_page_background(
    light: dict[str, str], dark: dict[str, str], token: str
) -> None:
    for theme, values in (("light", light), ("dark", dark)):
        ratio = _contrast(values[token], values["bg"])
        assert ratio >= 4.5, (
            f"{theme}: --{token} on --bg is {ratio:.2f}:1, below the 4.5:1 floor"
        )


@pytest.mark.parametrize("token", ["success", "error"])
def test_status_colours_are_readable_on_surfaces(
    light: dict[str, str], dark: dict[str, str], token: str
) -> None:
    for theme, values in (("light", light), ("dark", dark)):
        ratio = _contrast(values[token], values["surface"])
        assert ratio >= 4.5, (
            f"{theme}: --{token} on --surface is {ratio:.2f}:1, below the 4.5:1 floor"
        )
