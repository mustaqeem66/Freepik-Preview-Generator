"""Colour-contrast regression guard for the studio theme.

The primary button label and every accent-coloured label are read by the user,
so they must clear the WCAG AA 4.5:1 floor for normal text.

The palette is assembled from several ``:root`` blocks spread across the
stylesheet files, and the **last imported file wins**. A token can therefore
be "fixed" in a file that never reaches the browser, which is exactly how the
studio badge, the format notes and the slider hints kept landing between
3.92:1 and 4.41:1 while their token looked correct in isolation.

So these checks resolve the *effective* palette: the stylesheets are read in
the order ``main.tsx`` imports them and every later declaration overrides the
earlier one, exactly as the cascade does. A colour change cannot quietly drop
a ratio below the floor without failing the suite.

``scripts/verify_theme_contrast.py`` proves the same property against the
built bundle in a real engine; this test is the fast layer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "frontend" / "src"

# The order main.tsx imports them. A later file overrides an earlier one.
STYLESHEET_ORDER = (
    "index.css",
    "studioPolish.css",
    "studioPremium.css",
    "studioControls.css",
    "studioMotion.css",
    "desktopTitlebar.css",
    "fileSelection.css",
)


def _channel(value: int) -> float:
    """The sRGB electro-optical transfer function."""
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    clean = hex_colour.lstrip("#")
    red, green, blue = (int(clean[index : index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _contrast(foreground: str, background: str) -> float:
    first = _luminance(foreground)
    second = _luminance(background)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def _mix(from_colour: str, to_colour: str, amount: float) -> str:
    def channels(colour: str) -> list[int]:
        clean = colour.lstrip("#")
        return [int(clean[index : index + 2], 16) for index in (0, 2, 4)]

    start = channels(from_colour)
    end = channels(to_colour)
    blended = [round(start[index] + (end[index] - start[index]) * amount) for index in range(3)]
    return "#" + "".join(f"{value:02x}" for value in blended)


def _declarations(block: str) -> dict[str, str]:
    """Every custom property in a block, with its value.

    The value may be a hex colour, an rgba() colour or a var() reference, so
    it is captured generically rather than as a colour literal.
    """
    found: dict[str, str] = {}
    for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", block):
        found[name] = value.strip()
    return found


def _blocks(css: str, selector: str) -> list[dict[str, str]]:
    """Every declaration block for a selector, in source order."""
    pattern = re.compile(rf"(?:^|[\s,}}]){re.escape(selector)}\s*(?:,[^{{]*)?\{{([^}}]*)\}}", re.MULTILINE)
    return [_declarations(match.group(1)) for match in pattern.finditer(css)]


def _resolve(values: dict[str, str]) -> dict[str, str]:
    """Follow var() references so every token is a concrete colour.

    A token such as --danger: var(--error) inherits the other token's value,
    exactly as the engine resolves it.
    """
    resolved: dict[str, str] = {}
    for name in values:
        seen: set[str] = set()
        value = values[name]
        while True:
            reference = re.fullmatch(r"var\(\s*--([\w-]+)\s*\)", value)
            if not reference or reference.group(1) in seen:
                break
            seen.add(reference.group(1))
            target = values.get(reference.group(1))
            if target is None:
                break
            value = target
        resolved[name] = value
    return resolved


def _effective(theme: str) -> dict[str, str]:
    """Resolve the palette the browser actually computes for a theme.

    Every stylesheet is read in import order and every later declaration wins,
    which is what the cascade does. This is the value the engine sees, not the
    value in whichever file a reader happened to open.
    """
    selector = ":root" if theme == "light" else '[data-theme="dark"]'
    resolved: dict[str, str] = {}
    for name in STYLESHEET_ORDER:
        path = SRC_DIR / name
        if not path.is_file():
            continue
        css = path.read_text(encoding="utf-8")
        for block in _blocks(css, selector):
            resolved.update(block)
    return _resolve(resolved)


@pytest.fixture(scope="module")
def light() -> dict[str, str]:
    return _effective("light")


@pytest.fixture(scope="module")
def dark() -> dict[str, str]:
    return _effective("dark")


def test_accent_text_token_exists(light: dict[str, str], dark: dict[str, str]) -> None:
    """Accent-coloured text needs its own token; the solid accent is a fill."""
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", light.get("accent-text", ""))
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", dark.get("accent-text", ""))


@pytest.mark.parametrize("surface", ["bg", "card-bg", "surface"])
def test_accent_text_is_readable_on_every_surface(light: dict[str, str], dark: dict[str, str], surface: str) -> None:
    for theme, values in (("light", light), ("dark", dark)):
        ratio = _contrast(values["accent-text"], values[surface])
        assert ratio >= 4.5, f"{theme}: --accent-text on --{surface} is {ratio:.2f}:1, below the 4.5:1 floor"


def test_accent_text_is_readable_on_the_selection_surface(dark: dict[str, str]) -> None:
    """--selection is a tinted surface, so the pressed-state label needs its own check."""
    ratio = _contrast(dark["text"], dark["selection"])
    assert ratio >= 4.5, f"dark: --text on --selection is {ratio:.2f}:1, below the 4.5:1 floor"


@pytest.mark.parametrize("surface", ["accent", "accent-hover"])
def test_accent_filled_button_label_is_readable(light: dict[str, str], dark: dict[str, str], surface: str) -> None:
    """The label sits on the accent fill, so the pairing must clear the floor."""
    for theme, values in (("light", light), ("dark", dark)):
        ratio = _contrast(values["accent-label"], values[surface])
        assert ratio >= 4.5, f"{theme}: --accent-label on --{surface} is {ratio:.2f}:1, below the 4.5:1 floor"


@pytest.mark.parametrize("token", ["text-sec", "text-muted"])
@pytest.mark.parametrize("surface", ["bg", "card-bg", "chip-bg"])
def test_secondary_text_is_readable_on_every_surface(
    light: dict[str, str], dark: dict[str, str], token: str, surface: str
) -> None:
    """Secondary text lands on the page, the cards and the tinted chips."""
    for theme, values in (("light", light), ("dark", dark)):
        ratio = _contrast(values[token], values[surface])
        assert ratio >= 4.5, f"{theme}: --{token} on --{surface} is {ratio:.2f}:1, below the 4.5:1 floor"


@pytest.mark.parametrize("token", ["success", "error"])
def test_status_colours_are_readable_on_surfaces(light: dict[str, str], dark: dict[str, str], token: str) -> None:
    for theme, values in (("light", light), ("dark", dark)):
        ratio = _contrast(values[token], values["surface"])
        assert ratio >= 4.5, f"{theme}: --{token} on --surface is {ratio:.2f}:1, below the 4.5:1 floor"


def test_the_palette_has_a_single_authority() -> None:
    """No stylesheet may redefine a token the palette already owns.

    The palette used to be declared in three :root blocks across index.css and
    studioPremium.css. Because studioPremium.css is imported last its values
    silently won, so a token "fixed" in index.css never reached the browser --
    which is how the studio badge and the slider hints kept failing WCAG AA
    while their token looked correct in isolation.

    index.css now owns the palette and the other files contribute only their
    own tokens, so the cascade cannot reorder the colours any more.
    """
    owned = {
        "bg",
        "card-bg",
        "surface",
        "field-bg",
        "preview-bg",
        "card-border",
        "field-border",
        "text",
        "text-main",
        "text-sec",
        "text-muted",
        "accent",
        "accent-hover",
        "accent-label",
        "accent-text",
        "chip-bg",
        "btn-disabled",
        "toolbar-bg",
        "selection",
        "success",
        "error",
        "danger",
        "focus-ring",
    }
    index_css = (SRC_DIR / "index.css").read_text(encoding="utf-8")
    declared = set()
    for selector in (":root", '[data-theme="dark"]'):
        for block in _blocks(index_css, selector):
            declared |= set(block)
    missing = owned - declared
    assert not missing, f"index.css must declare the palette tokens: {sorted(missing)}"

    for name in STYLESHEET_ORDER:
        if name == "index.css":
            continue
        path = SRC_DIR / name
        if not path.is_file():
            continue
        css = path.read_text(encoding="utf-8")
        for selector in (":root", '[data-theme="dark"]'):
            for block in _blocks(css, selector):
                redefined = set(block) & owned
                assert not redefined, (
                    f"{name} redefines palette token(s) {sorted(redefined)}; "
                    "the palette has a single authority in index.css"
                )


def test_the_contrast_gate_measures_settled_colours_not_an_animation_frame() -> None:
    """The packaged gate must not sample a colour mid-transition.

    The studio animates background-color when the theme changes while the
    foreground changed instantly. `getComputedStyle` returns the interpolated
    value during that animation, so the gate once measured the dark theme's
    near-white foreground against the light theme's still-animating white
    background and failed on colours the app never displayed.
    """
    script = (PROJECT_ROOT / "scripts" / "verify_theme_contrast.py").read_text(encoding="utf-8")

    assert "SETTLE_JS" in script, "the gate must disable transitions before measuring"
    assert "transition: none !important" in script, "the settle style must disable transitions"
    # The settle style has to be applied before the theme toggle, otherwise
    # the animation has already started and the frame on screen is sampled.
    assert script.index("SETTLE_JS") < script.index("def apply_theme"), (
        "the settle style must be defined before the theme toggle is driven"
    )
    assert "run_script(view, SETTLE_JS" in script, "the gate must run the settle script before measuring any theme"


def _transitions_colour(rule_body: str) -> bool:
    """True when a rule transitions the `color` property itself.

    `border-color` and `background-color` both contain "color", so a plain
    substring search would accept a background-only transition.
    """
    for declaration in rule_body.split(";"):
        name, separator, value = declaration.partition(":")
        if not separator:
            continue
        if name.strip() != "transition":
            continue
        # The transition shorthand lists the animated properties first and
        # the timing functions last; a bare property name is a property.
        for part in value.split(","):
            token = part.strip().split()[0] if part.strip() else ""
            if token == "color":
                return True
    return False


def test_the_theme_transition_animates_the_foreground_with_the_background() -> None:
    """A theme switch must not leave the text unreadable mid-animation.

    The palette is applied to the root element, so switching the theme
    changes every surface at once. A transition that animated only the
    background moved the foreground to its new value first, which left
    near-white text on a white surface for the length of the animation.
    """
    index_css = (SRC_DIR / "index.css").read_text(encoding="utf-8")

    # Each rule may list several selectors, so match on the selector list that
    # contains the target rather than on an exact selector string.
    rules = re.findall(r"([^{}]+)\{([^}]*)\}", index_css)
    for target in ("button, input, select", ".button, .icon-button"):
        matching = [body for selectors, body in rules if target in selectors and "transition" in body]
        assert matching, f"{target} must declare a transition"
        assert any(_transitions_colour(body) for body in matching), (
            f"{target} must transition `color` together with its background; "
            "a background-only transition leaves the text unreadable while the "
            "theme switch animates"
        )
