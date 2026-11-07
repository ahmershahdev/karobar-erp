"""WhatsApp click-to-chat links. Nothing is sent from here: the link opens WhatsApp with the
message ready, and a person presses send."""

from urllib.parse import quote

# A local number starts with 0, and the shop's currency says which country it is in.
CALLING_CODES = {
    "PKR": "92",
    "AED": "971",
    "SAR": "966",
    "QAR": "974",
    "OMR": "968",
    "KWD": "965",
    "BHD": "973",
}
SHORTEST = 8
LONGEST = 15


def whatsapp_number(phone: str, currency: str) -> str:
    """The digits wa.me wants, or nothing when the number can't be trusted to reach them."""
    digits = "".join(character for character in phone if character in "0123456789")
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and not phone.strip().startswith("+"):
        code = CALLING_CODES.get(currency)
        digits = code + digits[1:] if code else ""
    # No calling code starts with 0, so a 0 left here is a mistyped number.
    if digits.startswith("0"):
        return ""
    return digits if SHORTEST <= len(digits) <= LONGEST else ""


def whatsapp_link(number: str, message: str) -> str:
    """Without a number WhatsApp lets the person pick who to send it to."""
    return f"https://wa.me/{number}?text={quote(message, safe='')}"
