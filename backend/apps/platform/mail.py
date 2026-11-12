from django.template.loader import render_to_string

from apps.demo.guard import is_demo_email

from .tasks import send_email


def send_message(
    to: str,
    subject: str,
    heading: str,
    paragraphs: list[str],
    action: tuple[str, str] | None = None,
    note: str = "",
) -> None:
    """One email in our design, with a plain text copy for clients that won't show HTML.

    `action` is a button label and its link. Django escapes everything here, which matters because
    business and product names are typed by users.
    """
    if is_demo_email(to):
        # The shared demo address belongs to nobody, so nothing is sent to it.
        return
    label, url = action or ("", "")
    html = render_to_string(
        "email/message.html",
        {
            "subject": subject,
            "preview": paragraphs[0] if paragraphs else heading,
            "heading": heading,
            "paragraphs": paragraphs,
            "action_label": label,
            "action_url": url,
            "note": note,
        },
    )
    text = "\n\n".join(part for part in [*paragraphs, url, note] if part)
    # A business name can hold a line break, and Django refuses to send such a header.
    send_email.delay(to, " ".join(subject.split()), text, html)
