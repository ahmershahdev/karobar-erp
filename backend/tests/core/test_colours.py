import pytest

from apps.core.colours import ColourError, contrast, luminance, readable_on_white


def test_black_on_white_is_the_most_contrast_there_is() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21)
    assert contrast("#ffffff", "#000000") == pytest.approx(21)
    assert contrast("#777777", "#777777") == pytest.approx(1)


def test_luminance_weighs_green_most() -> None:
    assert luminance("#00ff00") > luminance("#ff0000") > luminance("#0000ff")
    # Very dark channels sit on the straight part of the sRGB curve.
    assert luminance("#010101") == pytest.approx(0.000304, rel=0.01)


def test_dark_colours_read_on_white_and_light_ones_do_not() -> None:
    assert readable_on_white("#0b1a3c")
    assert readable_on_white("#767676")  # about 4.54 to 1, just enough
    assert not readable_on_white("#777777")  # about 4.48 to 1
    assert not readable_on_white("#ffcc00")


@pytest.mark.parametrize("colour", ["red", "#fff", "#12345g", "1a2b3c", "#1a2b3c0"])
def test_only_six_digit_hex_colours_are_accepted(colour: str) -> None:
    with pytest.raises(ColourError):
        luminance(colour)
