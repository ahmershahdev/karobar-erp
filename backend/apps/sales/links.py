"""Signed links that let a customer open one posted bill without an account.

The token is signed with the site's secret, so nobody can change the bill it names or guess one for
another bill, and it stops working after BILL_LINK_DAYS. It names the business too, because this
request has no signed-in user to take the tenant from. Signing does not hide the contents, so
the business goes in as its public_id.
"""

from decimal import Decimal

from django.conf import settings
from django.core import signing

from apps.core.whatsapp import whatsapp_link, whatsapp_number
from apps.tenancy.context import get_current_tenant
from apps.tenancy.models import Tenant

from .models import Customer, Invoice

SALT = "sales.bill-link"
BILL_LINK_DAYS = 30


def bill_token(invoice: Invoice) -> str:
    return signing.dumps({"t": str(invoice.tenant.public_id), "i": invoice.pk}, salt=SALT)


def read_bill_token(token: str) -> tuple[Tenant, int] | None:
    try:
        data = signing.loads(token, salt=SALT, max_age=BILL_LINK_DAYS * 24 * 60 * 60)
    except signing.BadSignature:
        return None
    tenant = Tenant.objects.filter(public_id=data["t"]).first()
    return (tenant, data["i"]) if tenant else None


def bill_url(invoice: Invoice) -> str:
    return f"{settings.SITE_URL.rstrip('/')}/api/public/bills/{bill_token(invoice)}/"


def _amount(value: Decimal) -> str:
    return f"{get_current_tenant().base_currency} {value:,.2f}"


def _chat(customer: Customer, message: str) -> str:
    number = whatsapp_number(customer.phone, get_current_tenant().base_currency)
    return whatsapp_link(number, message)


def bill_message(invoice: Invoice) -> str:
    """The link to open WhatsApp with this bill ready to send to its customer."""
    return _chat(
        invoice.customer,
        f"Hello {invoice.customer.name}, here is your bill {invoice.number} from "
        f"{get_current_tenant().name} for {_amount(invoice.total)}: {bill_url(invoice)}",
    )


def reminder_message(customer: Customer, owed: Decimal) -> str:
    """A polite reminder. It only opens WhatsApp: someone still reads it and presses send.
    Nothing comes back when they owe nothing, as a customer in credit has nothing to pay."""
    if owed <= 0:
        return ""
    return _chat(
        customer,
        f"Hello {customer.name}, a friendly reminder from {get_current_tenant().name}: "
        f"your balance is {_amount(owed)}. Thank you.",
    )
