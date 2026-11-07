"""The look of this business's bills: its details, wording, footer, layout and logo."""

import base64
import io
import re
from typing import Any

from django.db import transaction
from PIL import Image, UnidentifiedImageError

from apps.accounting.models import NumberSeries
from apps.accounts.models import User
from apps.core.colours import ColourError, readable_on_white
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import BillSettings

INVOICE_SERIES = ("INV", "INV-")
PREFIX = re.compile(r"[A-Z0-9][A-Z0-9/-]{0,9}")
MAX_LOGO_BYTES = 1024 * 1024
# Checked before decoding, so a small file that claims a huge picture can't eat the memory.
MAX_LOGO_PIXELS = 25_000_000
LOGO_BOX = (600, 600)
LOGO_FORMATS = {"PNG", "JPEG", "WEBP"}
FIELDS = (
    "address",
    "phone",
    "email",
    "tax_label",
    "tax_number",
    "title",
    "thanks",
    "payment_terms",
    "bank_details",
    "return_policy",
    "accent",
    "show_tax",
    "show_discount",
    "show_sku",
    "counter_paper",
)
Action = AuditEvent.Action


class BillingError(Exception):
    message = "Those bill settings can't be saved."


class UnreadableAccentError(BillingError):
    message = "That colour is too light to read on white paper. Pick a darker one."


class BadPrefixError(BillingError):
    message = "Use up to 10 capital letters, digits, - or /, starting with a letter or digit."


class BadLogoError(BillingError):
    message = "Upload a PNG, JPEG or WebP picture under 1 MB."


def current() -> BillSettings:
    """The saved settings, or the defaults when nothing has been saved yet."""
    return BillSettings.objects.first() or BillSettings()


def logo_data_uri(settings: BillSettings) -> str | None:
    if not settings.logo:
        return None
    return "data:image/png;base64," + base64.b64encode(bytes(settings.logo)).decode()


@transaction.atomic
def save(actor: User, data: dict[str, Any]) -> BillSettings:
    target = BillSettings.objects.select_for_update().first() or BillSettings()
    created = target.pk is None
    before = {field: getattr(target, field) for field in FIELDS}
    accent = data.get("accent", target.accent)
    try:
        readable = readable_on_white(accent)
    except ColourError as exc:
        raise UnreadableAccentError from exc
    if not readable:
        raise UnreadableAccentError
    for field in FIELDS:
        if field in data:
            setattr(target, field, data[field])
    target.save()
    changes = {
        field: [before[field], getattr(target, field)]
        for field in FIELDS
        if before[field] != getattr(target, field)
    }
    if "invoice_prefix" in data:
        changes.update(_set_prefix(data["invoice_prefix"]))
    audit.record(Action.CREATE if created else Action.UPDATE, target, actor, changes)
    return target


def _set_prefix(prefix: str) -> dict[str, list[str]]:
    """Only bills posted from now on take the new prefix; numbers already given keep theirs, and
    the counter carries on, so no number is given twice."""
    if not PREFIX.fullmatch(prefix):
        raise BadPrefixError
    series = NumberSeries.objects.select_for_update().filter(key=INVOICE_SERIES[0]).first()
    if series is None:
        series = NumberSeries(key=INVOICE_SERIES[0], prefix=INVOICE_SERIES[1])
    if series.prefix == prefix:
        return {}
    old, series.prefix = series.prefix, prefix
    series.save()
    return {"invoice_prefix": [old, prefix]}


def _clean_logo(upload: bytes) -> bytes:
    """Decode the picture and write a fresh PNG of it. Whatever else was in the file, such as
    metadata or a second hidden format, is left behind."""
    if not upload or len(upload) > MAX_LOGO_BYTES:
        raise BadLogoError
    try:
        with Image.open(io.BytesIO(upload)) as picture:
            if picture.format not in LOGO_FORMATS:
                raise BadLogoError
            width, height = picture.size
            if width * height > MAX_LOGO_PIXELS:
                raise BadLogoError
            picture.load()
            clean = picture.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise BadLogoError from exc
    clean.thumbnail(LOGO_BOX)
    out = io.BytesIO()
    clean.save(out, format="PNG", optimize=True)
    return out.getvalue()


@transaction.atomic
def set_logo(actor: User, upload: bytes | None) -> BillSettings:
    """`None` takes the logo off."""
    logo = None if upload is None else _clean_logo(upload)
    target = BillSettings.objects.select_for_update().first() or BillSettings()
    created = target.pk is None
    had = bool(target.logo)
    target.logo = logo
    target.save()
    audit.record(
        Action.CREATE if created else Action.UPDATE, target, actor, {"logo": [had, bool(logo)]}
    )
    return target
