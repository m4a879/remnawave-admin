"""Tests for OutboundMailQueue._build_message noreply handling."""
from web.backend.core.mail.outbound_queue import OutboundMailQueue


def _row(from_email: str, body_html: str | None = None) -> dict:
    return {
        "subject": "Test",
        "from_email": from_email,
        "from_name": None,
        "to_email": "user@example.com",
        "domain": "stijoin.com",
        "body_text": "Hello",
        "body_html": body_html,
    }


def test_noreply_mail_marked_and_gets_notice():
    msg = OutboundMailQueue()._build_message(_row("noreply@stijoin.com"))

    assert msg["Auto-Submitted"] == "auto-generated"
    assert msg["X-Auto-Response-Suppress"] == "All"
    body = msg.get_content()
    assert "ответы не доходят" in body
    assert "do not reply" in body


def test_noreply_notice_inserted_before_body_close():
    html = "<html><body><p>Hi</p></body></html>"
    msg = OutboundMailQueue()._build_message(_row("noreply@stijoin.com", body_html=html))

    html_part = msg.get_body(preferencelist=("html",)).get_content()
    assert "ответы не доходят" in html_part
    # Notice must sit inside the body, before the closing tag.
    assert html_part.index("ответы не доходят") < html_part.rindex("</body>")


def test_relayed_user_mail_is_untouched():
    """Mail relayed from a real user mailbox must not be marked or annotated."""
    msg = OutboundMailQueue()._build_message(_row("ceo@stijoin.com"))

    assert msg["Auto-Submitted"] is None
    assert msg["X-Auto-Response-Suppress"] is None
    assert "do not reply" not in msg.get_content()
