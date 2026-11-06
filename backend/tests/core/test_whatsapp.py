import pytest

from apps.core.whatsapp import whatsapp_link, whatsapp_number


@pytest.mark.parametrize(
    ("phone", "currency", "number"),
    [
        ("0300 1234567", "PKR", "923001234567"),
        ("0300-1234567", "PKR", "923001234567"),
        ("+92 300 1234567", "PKR", "923001234567"),
        ("0092 300 1234567", "PKR", "923001234567"),
        ("050 123 4567", "AED", "971501234567"),
        ("+0300 1234567", "PKR", "03001234567"),
        ("0300 1234567", "USD", ""),
        ("12345", "PKR", ""),
        ("1234567890123456", "PKR", ""),
        ("not a phone", "PKR", ""),
        ("", "PKR", ""),
    ],
)
def test_a_phone_becomes_the_number_whatsapp_wants(phone: str, currency: str, number: str) -> None:
    assert whatsapp_number(phone, currency) == number


def test_the_message_is_safe_inside_the_link() -> None:
    link = whatsapp_link("923001234567", "Bill & total: 5/5?")
    assert link == "https://wa.me/923001234567?text=Bill%20%26%20total%3A%205%2F5%3F"


def test_no_number_lets_the_person_choose() -> None:
    assert whatsapp_link("", "Hello") == "https://wa.me/?text=Hello"
