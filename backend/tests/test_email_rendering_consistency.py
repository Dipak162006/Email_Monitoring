"""Focused regression tests for email rendering consistency across Gmail, Yahoo Mail, and Zoho Mail.

Verifies:
1. Preservation of named HTML entities (&copy;, &amp;, &nbsp;) and numeric entities (&#160;, &#xA0;).
2. Proper link wrapping: CTA buttons and normal links retain normal word breaking, while long unbroken URLs receive aggressive word-break.
3. Accurate container detection across single/double/unquoted width attributes (580/600/640px) and CSS width/max-width.
4. Idempotence and prevention of duplicate reset styles or outer wrapper tables upon repeated normalization.
5. Email-client-compatible table-based layout with a centered maximum width of 600px.
6. Outlook (MSO) conditional comments for desktop clients.
7. End-to-end MIME generation via EmailService.build_mime_message.
"""

from email.message import EmailMessage
import pytest

from app.core.email_layout import prepare_email_html_for_delivery
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.schemas import EmailSendRequest
from app.modules.emails.service import EmailService


def test_prepare_email_html_wraps_fragment_in_600px_centered_table():
    """Verify that a raw HTML fragment is wrapped in a 600px max-width centered table
    with MSO conditional comments, table-layout: fixed, and standard email document shell.
    """
    fragment = """
    <div style="background-color: #0f172a; color: #ffffff; padding: 32px 24px; text-align: center;">
      <h1 style="margin: 0; font-size: 28px; font-weight: 700;">Dipak</h1>
    </div>
    <h2 style="font-size: 20px; text-align: center;">Discover Our Newest Product!</h2>
    <p style="text-align: center;">Upgrade your daily routine with our newly released item.</p>
    """

    result = prepare_email_html_for_delivery(fragment)

    # 1. XHTML Document Shell and Metas
    assert '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"' in result
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0"' in result
    assert '<meta http-equiv="X-UA-Compatible" content="IE=edge"' in result
    assert '<meta name="x-apple-disable-message-reformatting"' in result

    # 2. Outer 100% full-width centering table
    assert 'width="100%"' in result
    assert 'align="center"' in result
    assert 'border-collapse: collapse' in result

    # 3. Outlook MSO conditional wrapper
    assert "<!--[if (gte mso 9)|(IE)]>" in result
    assert 'width="600"' in result
    assert "<![endif]-->" in result

    # 4. Inner container with max-width: 600px, margin: 0 auto, and table-layout: fixed
    assert 'class="email-container"' in result
    assert "max-width: 600px" in result
    assert "margin: 0 auto" in result
    assert "table-layout: fixed" in result

    # 5. Preservation of original content and styles
    assert "background-color: #0f172a" in result
    assert "color: #ffffff" in result
    assert "Dipak" in result
    assert "Discover Our Newest Product!" in result


def test_preserve_html_entities_and_charrefs():
    """Defect 1 regression: Verify named HTML entities (&copy;, &amp;, &nbsp;) and numeric/hex
    entities (&#160;, &#xA0;, &#8212;) survive normalization unchanged without being dropped or stripped.
    """
    raw_html = (
        "<p>&copy; 2026 PulseMail Technologies &amp; Affiliates.&nbsp;"
        "All rights reserved. Price: &#36;100 &#8212; Non-breaking: &#160; Hex: &#xA0;</p>"
    )

    result = prepare_email_html_for_delivery(raw_html)

    assert "&copy;" in result
    assert "&amp;" in result
    assert "&nbsp;" in result
    assert "&#36;" in result
    assert "&#8212;" in result
    assert "&#160;" in result
    assert "&#xA0;" in result


def test_cta_button_text_preserves_normal_word_breaking():
    """Defect 2 regression: Verify CTA buttons do NOT receive word-break: break-all.
    Button text must retain normal word breaking while receiving safe overflow-wrap
    and max-width/box-sizing constraints.
    """
    raw_html = """
    <div style="text-align: center; margin: 24px 0;">
      <a href="https://example.com/shop"
         style="display: inline-block; background-color: #0284c7; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 600;">
        Shop Our New Collection Now
      </a>
    </div>
    """

    result = prepare_email_html_for_delivery(raw_html)

    assert "Shop Our New Collection Now" in result
    assert "word-break: normal" in result
    assert "word-break: break-all" not in result
    assert "overflow-wrap: break-word" in result
    assert "max-width: 100%" in result
    assert "box-sizing: border-box" in result
    assert "background-color: #0284c7" in result


def test_normal_links_do_not_receive_break_all():
    """Defect 2 regression: Verify normal descriptive links with spaces (e.g. Terms and Conditions)
    do NOT receive word-break: break-all, preserving natural word boundary wrapping.
    """
    raw_html = """
    <p>Please read our <a href="https://example.com/terms">Terms and Service Agreement</a> or visit our
    <a href="https://example.com/support">Customer Support Help Center</a> for assistance.</p>
    """

    result = prepare_email_html_for_delivery(raw_html)

    assert "Terms and Service Agreement" in result
    assert "Customer Support Help Center" in result
    # Neither normal link should have break-all
    assert "word-break: break-all" not in result
    assert "overflow-wrap: break-word" in result


def test_genuinely_long_unbroken_urls_receive_aggressive_word_break():
    """Defect 2 regression: Verify genuinely long unbroken URLs (like 250+ char JWT unsubscribe links)
    receive word-break: break-all to prevent horizontal blowout across Yahoo Mail and Zoho Mail.
    """
    long_unsub_url = (
        "http://localhost:8000/api/v1/public/unsubscribe/"
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb21wYW55X2lkIjoxLCJlbWFpbCI6ImRpcGFrb2RoYXZhbmlAem9ob21haWwuaW4iLCJleHAiOjE3NjIyMTYxOTN9."
        "abcdef1234567890abcdef1234567890abcdef1234567890"
    )
    raw_html = f"""
    <div>
      <p>Click below to unsubscribe:</p>
      <a href="{long_unsub_url}">{long_unsub_url}</a>
    </div>
    """

    result = prepare_email_html_for_delivery(raw_html)

    assert long_unsub_url in result
    assert "word-break: break-all" in result
    assert "overflow-wrap: break-word" in result


def test_detect_existing_containers_580_600_640_and_styles():
    """Defect 3 regression: Verify container detection recognizes:
    - single-quoted width: width='580'
    - double-quoted width: width="600"
    - unquoted width: width=640
    - CSS width / max-width: style="width: 580px", style="max-width: 640px"
    - MSO conditional table wrappers with 600px width
    Avoids double-wrapping an already constrained email layout.
    """
    # 1. Double-quoted 600px table
    t600 = '<table width="600" align="center"><tr><td><p>600px Table</p></td></tr></table>'
    r600 = prepare_email_html_for_delivery(t600)
    assert r600.count('width="600"') == 1 or r600.count("width='600'") == 1
    assert "600px Table" in r600
    assert r600.count('class="email-container"') == 0  # Not double wrapped

    # 2. Single-quoted 580px table
    t580 = "<table width='580' align='center'><tr><td><p>580px Table</p></td></tr></table>"
    r580 = prepare_email_html_for_delivery(t580)
    assert "580px Table" in r580
    assert r580.count('class="email-container"') == 0

    # 3. Unquoted 640px table
    t640 = "<table width=640 align=center><tr><td><p>640px Table</p></td></tr></table>"
    r640 = prepare_email_html_for_delivery(t640)
    assert "640px Table" in r640
    assert r640.count('class="email-container"') == 0

    # 4. CSS max-width 600px on div
    div600 = '<div style="max-width: 600px; margin: 0 auto;"><p>CSS Container</p></div>'
    rdiv = prepare_email_html_for_delivery(div600)
    assert "CSS Container" in rdiv
    assert rdiv.count('class="email-container"') == 0

    # 5. CSS width 580px on table
    t_css580 = '<table style="width: 580px; margin: 0 auto;"><tr><td><p>CSS Width 580</p></td></tr></table>'
    r_css = prepare_email_html_for_delivery(t_css580)
    assert "CSS Width 580" in r_css
    assert r_css.count('class="email-container"') == 0


def test_repeated_normalization_is_idempotent():
    """Defect 4 regression: Verify normalization is strictly idempotent.
    Repeated normalization (pass 1, pass 2, pass 3) must never duplicate the reset
    stylesheet, extra head styles, or outer email container wrappers.
    """
    raw_html = """
    <div style="background-color: #0f172a; padding: 20px;">
      <p>&copy; 2026 PulseMail. <a href="https://example.com/shop" style="display:inline-block; padding:10px 20px; background:#0284c7; color:#fff;">Shop Now</a></p>
    </div>
    """

    pass1 = prepare_email_html_for_delivery(raw_html)
    pass2 = prepare_email_html_for_delivery(pass1)
    pass3 = prepare_email_html_for_delivery(pass2)

    # Identical content across repeated passes
    assert pass1 == pass2
    assert pass2 == pass3

    # Exactly one reset style tag
    assert pass1.count('data-email-layout="reset"') == 1
    assert pass2.count('data-email-layout="reset"') == 1
    assert pass3.count('data-email-layout="reset"') == 1

    # Exactly one email container
    assert pass1.count('class="email-container"') == 1
    assert pass2.count('class="email-container"') == 1
    assert pass3.count('class="email-container"') == 1

    # Entities preserved
    assert "&copy;" in pass3

    # CTA button preserved
    assert "Shop Now" in pass3
    assert "word-break: break-all" not in pass3


def test_images_and_nested_tables_receive_defensive_overflow_constraints():
    """Verify that images and nested tables receive max-width: 100% constraints
    so they cannot force horizontal scrollbars.
    """
    raw_html = """
    <div>
      <img src="https://example.com/banner.png" alt="Promo Banner" />
      <table>
        <tr>
          <td>Column 1</td>
          <td>Column 2</td>
        </tr>
      </table>
      <pre>Some long code block that should not overflow</pre>
    </div>
    """

    result = prepare_email_html_for_delivery(raw_html)

    # <img> tag must have max-width: 100% and height: auto
    assert "max-width: 100%" in result
    assert "height: auto" in result
    assert 'border="0"' in result

    # nested <table> must have max-width: 100% and box-sizing: border-box
    assert "box-sizing: border-box" in result
    assert 'role="presentation"' in result

    # <pre> must have white-space: pre-wrap
    assert "white-space: pre-wrap" in result


def test_mime_generation_end_to_end_in_email_service():
    """Verify that EmailService.build_mime_message produces a MIME message
    whose text/html part contains the normalized 600px centered table structure,
    properly formatted CTA buttons, entities, and unsubscribe links.
    """
    account = EmailAccount(
        id=1,
        company_id=1,
        email_address="dipak@example.com",
        name="Dipak",
        is_active=True,
        smtp_host="smtp.example.com",
        smtp_port=587,
    )

    long_unsub = (
        "http://localhost:8000/api/v1/public/unsubscribe/"
        "eyJhbGciOiJIUzI1NiJ9.eyJjb21wYW55X2lkIjoxfQ.abcdef1234567890abcdef1234567890"
    )

    send_req = EmailSendRequest(
        email_account_id=1,
        to=["recipient@example.com"],
        subject="Campaign_Test 1",
        body_text="Discover Our Newest Product! Upgrade your routine.",
        body_html=f"""
        <div style="background-color: #0f172a; color: #ffffff; padding: 32px 24px; text-align: center;">
          <h1 style="margin: 0; font-size: 28px;">Dipak &amp; Friends</h1>
        </div>
        <div style="text-align: center; margin: 24px 0;">
          <a href="https://example.com/shop" style="display: inline-block; background-color: #0284c7; color: #ffffff; padding: 12px 28px;">Shop Now</a>
        </div>
        <p>&copy; 2026 PulseMail. <a href="{long_unsub}">{long_unsub}</a></p>
        """,
    )

    service = EmailService()
    mime_msg, message_id, recipients, in_reply_to, references = service.build_mime_message(
        account=account,
        send_req=send_req,
    )

    # Extract HTML part from MIME message
    html_parts = [p.get_content() for p in mime_msg.walk() if p.get_content_type() == "text/html"]
    assert len(html_parts) == 1
    delivered_html = html_parts[0]

    # Verify key requirements on delivered HTML:
    assert "<!DOCTYPE html" in delivered_html
    assert 'class="email-container"' in delivered_html
    assert "max-width: 600px" in delivered_html
    assert "table-layout: fixed" in delivered_html
    assert "<!--[if (gte mso 9)|(IE)]>" in delivered_html
    assert "background-color: #0f172a" in delivered_html
    assert "Dipak &amp; Friends" in delivered_html
    assert "PulseMail" in delivered_html
    assert "Shop Now" in delivered_html
    assert "word-break: normal" in delivered_html
    assert "word-break: break-all" in delivered_html  # On the long unsub link
