"""Colour checks for what a business may choose for its printed bill.

The bill prints the accent colour as text on white paper, so it has to stay readable. The
formula is the contrast ratio from WCAG 2.2 (success criterion 1.4.3, "Contrast (Minimum)"),
which asks for at least 4.5 to 1 for normal text: https://www.w3.org/TR/WCAG22/#contrast-minimum
"""

import re

HEX = re.compile(r"#[0-9a-fA-F]{6}")
WHITE = "#ffffff"
READABLE = 4.5


class ColourError(ValueError):
    pass


def _channel(value: int) -> float:
    # Each sRGB channel is made linear before it is weighed, as the WCAG definition says.
    scaled = value / 255
    return scaled / 12.92 if scaled <= 0.04045 else ((scaled + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    if not HEX.fullmatch(colour):
        raise ColourError("a colour is written as # and six hex digits, like #1a2b3c")
    red, green, blue = (int(colour[index : index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast(first: str, second: str) -> float:
    """From 1 (the same colour) to 21 (black on white)."""
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def readable_on_white(colour: str) -> bool:
    return contrast(colour, WHITE) >= READABLE
