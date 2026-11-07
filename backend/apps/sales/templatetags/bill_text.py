"""Which way text the business typed should run on a printed bill.

WeasyPrint does not support dir="auto", so an English sentence on an Urdu bill would be laid out
right to left and print its full stop at the wrong end. This finds the direction the way
browsers do for dir="auto": from the first letter with a strong direction.
"""

import unicodedata

from django import template

register = template.Library()


@register.filter
def textdir(value: object) -> str:
    for character in str(value or ""):
        kind = unicodedata.bidirectional(character)
        if kind in ("R", "AL"):
            return "rtl"
        if kind == "L":
            return "ltr"
    return "ltr"
