"""The look of this business's bills: its details, wording, footer, layout, logo and
signature."""

import base64
import io
import re
from typing import Any

from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.accounting.models import NumberSeries
from apps.accounts.models import User
from apps.core.colours import ColourError, readable_on_white
from apps.tenancy import audit
from apps.tenancy.models import AuditEvent

from .models import BillSettings

INVOICE_SERIES = ("INV", "INV-")
PREFIX = re.compile(r"[A-Z0-9][A-Z0-9/-]{0,9}")
MAX_IMAGE_BYTES = 1024 * 1024
# The whole upload request: the picture plus the multipart wrapping around it.
MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + 64 * 1024
# Checked before decoding, so a small file that claims a huge picture can't eat the memory.
MAX_IMAGE_PIXELS = 25_000_000
MIN_SIDE, MAX_SIDE = 16, 5000
# The largest each picture is stored at. A signature is a wide strip.
BOXES = {"logo": (600, 600), "signature": (600, 200)}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
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
    "template",
    "signature_text",
)
Action = AuditEvent.Action


class BillingError(Exception):
    message = "Those bill settings can't be saved."


class BadAccentError(BillingError):
    message = (
        "Pick a colour from the colour picker, written as # and six digits or letters a to f."
    )


class UnreadableAccentError(BillingError):
    message = "That colour is too light to read on white paper. Pick a darker one."


class BadPrefixError(BillingError):
    message = "Use up to 10 capital letters, digits, - or /, starting with a letter or digit."


class BadImageError(BillingError):
    message = (
        "Upload a PNG, JPEG or WebP picture under 1 MB, between 16 and 5000 pixels on each "
        "side. Moving pictures and damaged files can't be used."
    )


def current() -> BillSettings:
    """The saved settings, or the defaults when nothing has been saved yet."""
    return BillSettings.objects.first() or BillSettings()


def data_uri(picture: bytes | memoryview | None) -> str | None:
    if not picture:
        return None
    return "data:image/png;base64," + base64.b64encode(bytes(picture)).decode()


@transaction.atomic
def save(actor: User, data: dict[str, Any]) -> BillSettings:
    target = BillSettings.objects.select_for_update().first() or BillSettings()
    created = target.pk is None
    before = {field: getattr(target, field) for field in FIELDS}
    accent = data.get("accent", target.accent)
    try:
        readable = readable_on_white(accent)
    except ColourError as exc:
        raise BadAccentError from exc
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


def _sniff(upload: bytes) -> str | None:
    """What the first bytes say the file is. The decoder is then held to that one format, so a
    file can't pass as a PNG and be read by some other, less careful decoder."""
    if upload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if upload.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if upload[:4] == b"RIFF" and upload[8:12] == b"WEBP":
        return "WEBP"
    return None


def clean_image(upload: bytes, box: tuple[int, int]) -> bytes:
    """Check a picture and write a fresh PNG of it.

    Nothing from the upload is kept except the pixels: metadata, scripts or a second file
    hidden after the picture are all left behind, so even a file built to attack a viewer is
    harmless once stored. The checks come before the expensive work: size, what the first bytes
    say, and the claimed picture size, then a structural check, then the full decode, which
    refuses a damaged or cut-off file.
    """
    if not upload or len(upload) > MAX_IMAGE_BYTES:
        raise BadImageError
    kind = _sniff(upload)
    if kind is None:
        raise BadImageError
    try:
        with Image.open(io.BytesIO(upload), formats=[kind]) as picture:
            width, height = picture.size
            frames = getattr(picture, "n_frames", 1)
            if (
                picture.format != kind
                or frames != 1
                or not MIN_SIDE <= width <= MAX_SIDE
                or not MIN_SIDE <= height <= MAX_SIDE
                or width * height > MAX_IMAGE_PIXELS
            ):
                raise BadImageError
            picture.verify()
        # verify() leaves the file unusable, so it is opened again for the real decode.
        with Image.open(io.BytesIO(upload), formats=[kind]) as picture:
            picture.load()
            # Phone photos often keep their rotation only in EXIF, which is dropped below, so
            # the pixels are turned upright first or the picture would print sideways.
            clean = ImageOps.exif_transpose(picture).convert("RGBA")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
    ) as exc:
        raise BadImageError from exc
    clean.thumbnail(box)
    out = io.BytesIO()
    clean.save(out, format="PNG", optimize=True)
    return out.getvalue()


@transaction.atomic
def set_image(actor: User, kind: str, upload: bytes | None) -> BillSettings:
    """Put up or take off (`None`) the logo or the signature picture."""
    picture = None if upload is None else clean_image(upload, BOXES[kind])
    target = BillSettings.objects.select_for_update().first() or BillSettings()
    created = target.pk is None
    had = bool(getattr(target, kind))
    setattr(target, kind, picture)
    target.save()
    audit.record(
        Action.CREATE if created else Action.UPDATE, target, actor, {kind: [had, bool(picture)]}
    )
    return target
