"""Email layout normalization and client compatibility engine for outgoing HTML emails.

Ensures that HTML emails render consistently across all webmail and desktop clients,
specifically Gmail, Yahoo Mail, Zoho Mail, Outlook (MSO), Apple Mail, and mobile clients.

Key capabilities:
1. Centered maximum width container (~600px) with responsive 100% width on mobile.
2. Standard email table-based wrapper with MSO conditional comments for Outlook.
3. Overflow prevention:
   - table-layout: fixed to prevent unbreakable text/URLs from blowing out tables
   - word-break: break-all / overflow-wrap: break-word on genuinely long, unbroken links/URLs
   - safe overflow-wrap and normal word-break on regular links and CTA buttons
   - defensive max-width: 100% and height: auto on images
   - max-width: 100% on nested tables, pre blocks, and CTA buttons
4. Full XHTML 1.0 Transitional document shell with viewport, MSO resets, and client styles.
5. Preservation of all original styles, inline CSS, colors, backgrounds, CTA buttons, signatures, and HTML entities.
6. Idempotent normalization: repeated calls never duplicate stylesheets or outer containers.
"""

from html import escape
from html.parser import HTMLParser
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class _EmailDefensiveStylingParser(HTMLParser):
    """Event-driven parser that injects defensive styles onto elements (a, img, table, pre)
    to prevent horizontal blowout across Yahoo Mail, Zoho Mail, and Outlook, while
    preserving all existing attributes, inline styles, HTML entities, and safe markup.
    """

    VOID_TAGS: Set[str] = {"br", "hr", "img", "meta", "col"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output: List[str] = []
        self._current_anchor: Optional[Dict[str, Any]] = None

    def handle_decl(self, decl: str) -> None:
        # Ignore input doctype; a normalized standard doctype will be output in the shell
        pass

    def handle_comment(self, comment: str) -> None:
        target = self._current_anchor["buffer"] if self._current_anchor else self.output
        target.append(f"<!--{comment}-->")

    def handle_entityref(self, name: str) -> None:
        """Preserve named HTML entities such as &copy;, &amp;, &nbsp;, &lt;, &gt; unchanged."""
        target = self._current_anchor["buffer"] if self._current_anchor else self.output
        target.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        """Preserve numeric and hexadecimal character references such as &#160;, &#xA0; unchanged."""
        target = self._current_anchor["buffer"] if self._current_anchor else self.output
        target.append(f"&#{name};")

    def handle_data(self, data: str) -> None:
        target = self._current_anchor["buffer"] if self._current_anchor else self.output
        target.append(data)

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_lower = tag.lower()

        # Suppress html, head, title, body tags from inner content as they are handled by shell
        if tag_lower in {"html", "head", "title", "body"}:
            return

        raw_attrs: Dict[str, str] = {}
        ordered_keys: List[str] = []
        for attr_name, attr_val in attrs:
            key_lower = attr_name.lower().strip()
            raw_attrs[key_lower] = (attr_val or "").strip()
            if key_lower not in ordered_keys:
                ordered_keys.append(key_lower)

        existing_style = raw_attrs.get("style", "")
        parsed_styles = self._parse_inline_style(existing_style)

        # 1. Anchor <a> handling: buffer content to distinguish CTA buttons and short links
        # from genuinely long unbroken URLs before applying word-break rules
        if tag_lower == "a":
            if self._current_anchor is not None:
                self._flush_current_anchor()

            is_button = (
                "padding" in existing_style.lower()
                or "background" in existing_style.lower()
                or parsed_styles.get("display") in {"inline-block", "block"}
            )
            self._current_anchor = {
                "tag": tag_lower,
                "raw_attrs": raw_attrs,
                "ordered_keys": ordered_keys,
                "parsed_styles": parsed_styles,
                "is_button": is_button,
                "buffer": [],
            }
            return

        # 2. Defend <img> tags against oversized image overflow
        elif tag_lower == "img":
            if "max-width" not in parsed_styles:
                parsed_styles["max-width"] = "100%"
            if "height" not in parsed_styles:
                parsed_styles["height"] = "auto"
            if "display" not in parsed_styles:
                parsed_styles["display"] = "block"
            if "border" not in raw_attrs:
                raw_attrs["border"] = "0"
                if "border" not in ordered_keys:
                    ordered_keys.append("border")

        # 3. Defend nested <table> elements
        elif tag_lower == "table":
            if "max-width" not in parsed_styles:
                parsed_styles["max-width"] = "100%"
            if "box-sizing" not in parsed_styles:
                parsed_styles["box-sizing"] = "border-box"
            if "role" not in raw_attrs:
                raw_attrs["role"] = "presentation"
                if "role" not in ordered_keys:
                    ordered_keys.append("role")

        # 4. Defend <pre> and <code> elements
        elif tag_lower in {"pre", "code"}:
            if "white-space" not in parsed_styles:
                parsed_styles["white-space"] = "pre-wrap"
            if "word-break" not in parsed_styles:
                parsed_styles["word-break"] = "break-word"
            if "max-width" not in parsed_styles:
                parsed_styles["max-width"] = "100%"

        # Reconstruct style attribute if modified
        new_style_str = "; ".join(f"{k}: {v}" for k, v in parsed_styles.items())
        if new_style_str:
            if not new_style_str.endswith(";"):
                new_style_str += ";"
            raw_attrs["style"] = new_style_str
            if "style" not in ordered_keys:
                ordered_keys.append("style")

        # Format attributes
        formatted_attrs = []
        for key in ordered_keys:
            val = raw_attrs[key]
            formatted_attrs.append(f'{key}="{escape(val, quote=True)}"')

        attrs_str = (" " + " ".join(formatted_attrs)) if formatted_attrs else ""
        target = self._current_anchor["buffer"] if self._current_anchor else self.output

        if tag_lower in {"br", "hr"}:
            target.append(f"<{tag_lower}{attrs_str}>")
        elif tag_lower in self.VOID_TAGS:
            target.append(f"<{tag_lower}{attrs_str} />")
        else:
            target.append(f"<{tag_lower}{attrs_str}>")

    def _flush_current_anchor(self) -> None:
        """Complete the current anchor tag, inspecting inner text to apply word breaking
        appropriately without breaking CTA buttons or short link text.
        """
        if self._current_anchor is None:
            return

        anchor = self._current_anchor
        self._current_anchor = None

        inner_html = "".join(anchor["buffer"])
        # Strip nested tags to examine visible text content
        plain_text = re.sub(r"<[^>]+>", "", inner_html)
        # Identify whether the text contains an unbroken token >= 30 chars (e.g. raw JWT URL)
        has_long_unbroken = bool(re.search(r"\S{30,}", plain_text))

        parsed_styles = anchor["parsed_styles"]
        is_button = anchor["is_button"]

        if is_button:
            # Preserve CTA button text: normal word breaking, safe overflow wrapping, defensive box sizing
            if "word-break" not in parsed_styles or parsed_styles["word-break"] == "break-all":
                parsed_styles["word-break"] = "normal"
            if "overflow-wrap" not in parsed_styles:
                parsed_styles["overflow-wrap"] = "break-word"
            if "word-wrap" not in parsed_styles:
                parsed_styles["word-wrap"] = "break-word"
            if "max-width" not in parsed_styles:
                parsed_styles["max-width"] = "100%"
            if "box-sizing" not in parsed_styles:
                parsed_styles["box-sizing"] = "border-box"
        else:
            # Standard links: safe overflow wrapping
            if "overflow-wrap" not in parsed_styles:
                parsed_styles["overflow-wrap"] = "break-word"
            if "word-wrap" not in parsed_styles:
                parsed_styles["word-wrap"] = "break-word"

            # Apply aggressive breaking ONLY to genuinely long, unbroken URLs or strings
            if has_long_unbroken:
                parsed_styles["word-break"] = "break-all"
            elif parsed_styles.get("word-break") == "break-all":
                parsed_styles["word-break"] = "normal"

        new_style_str = "; ".join(f"{k}: {v}" for k, v in parsed_styles.items())
        if new_style_str:
            if not new_style_str.endswith(";"):
                new_style_str += ";"
            anchor["raw_attrs"]["style"] = new_style_str
            if "style" not in anchor["ordered_keys"]:
                anchor["ordered_keys"].append("style")

        formatted_attrs = []
        for key in anchor["ordered_keys"]:
            val = anchor["raw_attrs"][key]
            formatted_attrs.append(f'{key}="{escape(val, quote=True)}"')

        attrs_str = (" " + " ".join(formatted_attrs)) if formatted_attrs else ""
        self.output.append(f"<a{attrs_str}>{inner_html}</a>")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in {"html", "head", "title", "body"}:
            return
        if tag_lower == "a" and self._current_anchor is not None:
            self._flush_current_anchor()
            return
        target = self._current_anchor["buffer"] if self._current_anchor else self.output
        if tag_lower not in self.VOID_TAGS:
            target.append(f"</{tag_lower}>")

    def close(self) -> None:
        if self._current_anchor is not None:
            self._flush_current_anchor()
        super().close()

    def _parse_inline_style(self, style_str: str) -> Dict[str, str]:
        styles: Dict[str, str] = {}
        if not style_str:
            return styles
        for item in style_str.split(";"):
            item = item.strip()
            if not item or ":" not in item:
                continue
            prop, val = item.split(":", 1)
            prop = prop.strip().lower()
            val = val.strip()
            if prop and val:
                styles[prop] = val
        return styles


def _has_outer_email_container(html: str) -> bool:
    """Check if the HTML content already has an outer container table or div enforcing
    a standard fixed email width (e.g. 580px, 600px, 640px).

    Detects:
    1. Class name 'email-container' (quoted, single-quoted, or unquoted)
    2. HTML width attributes: width="600", width='580', width=640 (480-750px) on <table> or <div>
    3. CSS width or max-width: width: 600px, max-width: 580px, max-width: 640px (480-750px) on <table> or <div>
    4. Outlook MSO conditional wrapper tables with 480-750px width
    """
    if not html:
        return False

    # 1. Class-based container detection
    if re.search(r'class\s*=\s*["\']?[^"\'>]*email-container', html, re.IGNORECASE):
        return True

    # Common fixed email widths: 480-750px (e.g. 500, 580, 600, 640, 700)
    width_num_pattern = r"(?:4[89]\d|[56]\d\d|7[0-5]\d)"

    # 2. Outer table or div with width attribute (quoted or unquoted): width="600", width='580', width=640
    width_attr_regex = rf'<(?:table|div)[^>]+width\s*=\s*["\']?{width_num_pattern}(?:px)?["\']?(?:[\s>/])'
    if re.search(width_attr_regex, html, re.IGNORECASE):
        return True

    # 3. CSS style attribute on table or div with width or max-width:
    # Matches: max-width: 600px, width: 580px (using (?<!-)width to exclude stroke-width, border-width)
    css_width_regex = rf'<(?:table|div)[^>]+style\s*=\s*["\'][^"\']*(?:max-width|(?<!-)width)\s*:\s*{width_num_pattern}px'
    if re.search(css_width_regex, html, re.IGNORECASE):
        return True

    # 4. MSO conditional wrapper comments with fixed width
    mso_regex = rf'<!--\[if\s+[^>]*mso[^>]*>[\s\S]*?width\s*=\s*["\']?{width_num_pattern}'
    if re.search(mso_regex, html, re.IGNORECASE):
        return True

    return False


def _extract_body_and_styles(html: str) -> Tuple[str, str, str]:
    """Extract inner body content, extra head styles, and body background color if present.
    Filters out any existing generated reset stylesheets to ensure idempotence.
    """
    if not html:
        return "", "", "#ffffff"

    # Extract any user <style> blocks from head or whole document, excluding generated reset styles
    style_blocks = []
    for match in re.finditer(r"<style[^>]*>([\s\S]*?)<\/style>", html, re.IGNORECASE):
        style_tag = match.group(0)
        style_content = match.group(1)
        # Skip our generated reset stylesheet so repeated normalization never duplicates it
        if 'data-email-layout="reset"' in style_tag or "#outlook a" in style_content:
            continue
        style_blocks.append(style_tag)
    extra_styles = "\n  ".join(style_blocks)

    # Extract body content and bgcolor
    body_bg = "#ffffff"
    body_match = re.search(r"<body([^>]*)>([\s\S]*?)<\/body>", html, re.IGNORECASE)
    if body_match:
        body_attrs = body_match.group(1)
        body_content = body_match.group(2)
        # Check bgcolor
        bg_match = re.search(r'bgcolor="([^"]+)"', body_attrs, re.IGNORECASE)
        if bg_match:
            body_bg = bg_match.group(1)
        else:
            style_match = re.search(r'background(?:-color)?:\s*([^;"]+)', body_attrs, re.IGNORECASE)
            if style_match:
                body_bg = style_match.group(1).strip()
    else:
        # Document is HTML snippet without body tag; remove any leading <style> blocks
        cleaned = re.sub(r"<style[^>]*>[\s\S]*?<\/style>", "", html, flags=re.IGNORECASE).strip()
        body_content = cleaned

    return body_content, extra_styles, body_bg


def _is_already_normalized(html: str) -> bool:
    """Check if the HTML is already a complete, normalized document produced by this engine."""
    return bool(
        html
        and ("<!DOCTYPE" in html or "<html" in html)
        and 'data-email-layout="reset"' in html
        and 'class="email-container"' in html
    )


def prepare_email_html_for_delivery(html_content: Optional[str]) -> Optional[str]:
    """Transform sanitized email HTML into an email-client-compatible layout with
    a centered 600px container, defensive overflow constraints, and standard MSO table wrappers.

    Works across Gmail, Yahoo Mail, Zoho Mail, Outlook (desktop/web), and Apple Mail.
    Preserves all original styling, colors, dark backgrounds, buttons, and dynamic tokens.
    Guarantees idempotence: repeated calls produce identical results without duplicated styles or wrappers.
    """
    if html_content is None:
        return None
    if not html_content.strip():
        return ""

    # 0. Fast-path idempotence: already normalized document is returned directly
    if _is_already_normalized(html_content):
        return html_content

    body_content, extra_head_styles, bg_color = _extract_body_and_styles(html_content)

    # Apply defensive inline styles to nested elements (selective word-break on long URLs, max-width on <img> and <table>)
    parser = _EmailDefensiveStylingParser()
    try:
        parser.feed(body_content)
        parser.close()
        defended_content = "".join(parser.output).strip()
    except Exception:
        defended_content = body_content.strip()

    # If the content already has an outer fixed-width email layout (e.g. 580/600/640px), do not double-wrap
    already_wrapped = _has_outer_email_container(defended_content)

    if already_wrapped:
        wrapped_body = defended_content
    else:
        # Wrap content in a robust table-based 600px centered layout
        # Outer table: 100% full width, transparent, zero margin/padding
        # MSO conditional comments: enforce 600px width in Outlook 2007-2019
        # Inner table: max-width 600px, 100% responsive, centered with margin: 0 auto, table-layout: fixed
        wrapped_body = (
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" align="center" '
            'style="border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; '
            'width: 100%; min-width: 100%; max-width: 100%; box-sizing: border-box; margin: 0; padding: 0; background-color: transparent;">\n'
            '  <tr>\n'
            '    <td align="center" valign="top" style="padding: 0; margin: 0;">\n'
            '      <!--[if (gte mso 9)|(IE)]>\n'
            '      <table role="presentation" align="center" border="0" cellspacing="0" cellpadding="0" width="600" style="width: 600px;">\n'
            '      <tr>\n'
            '      <td align="center" valign="top">\n'
            '      <![endif]-->\n'
            '      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" align="center" '
            'class="email-container" style="border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; '
            'max-width: 600px; width: 100%; margin: 0 auto; table-layout: fixed; box-sizing: border-box;">\n'
            '        <tr>\n'
            '          <td align="left" valign="top" style="padding: 0; margin: 0; '
            'font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; '
            'font-size: 15px; line-height: 1.6; color: #1e293b; '
            'word-break: break-word; overflow-wrap: break-word; word-wrap: break-word;">\n'
            f'            {defended_content}\n'
            '          </td>\n'
            '        </tr>\n'
            '      </table>\n'
            '      <!--[if (gte mso 9)|(IE)]>\n'
            '      </td>\n'
            '      </tr>\n'
            '      </table>\n'
            '      <![endif]-->\n'
            '    </td>\n'
            '  </tr>\n'
            '</table>'
        )

    # Standard email boilerplate styles
    reset_styles = """
    #outlook a { padding: 0; }
    body, table, td, a { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
    table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
    img { -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; max-width: 100%; }
    table { border-collapse: collapse !important; }
    body { height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; }
    a[x-apple-data-detectors] { color: inherit !important; text-decoration: none !important; font-size: inherit !important; font-family: inherit !important; font-weight: inherit !important; line-height: inherit !important; }
    .email-container { width: 100% !important; max-width: 600px !important; margin: 0 auto !important; }
    @media screen and (max-width: 600px) {
      .email-container { width: 100% !important; max-width: 100% !important; }
      .fluid { max-width: 100% !important; height: auto !important; margin-left: auto !important; margin-right: auto !important; }
    }
    """.strip()

    full_head_styles = f'<style type="text/css" data-email-layout="reset">\n    {reset_styles}\n  </style>'
    if extra_head_styles:
        full_head_styles += f"\n  {extra_head_styles}"

    # Produce complete, standards-compliant HTML document shell
    full_html = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="en">\n'
        '<head>\n'
        '  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        '  <meta http-equiv="X-UA-Compatible" content="IE=edge" />\n'
        '  <meta name="x-apple-disable-message-reformatting" />\n'
        '  <meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no" />\n'
        '  <title></title>\n'
        f'  {full_head_styles}\n'
        '</head>\n'
        f'<body style="margin: 0; padding: 0; width: 100% !important; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; mso-line-height-rule: exactly; background-color: {bg_color};">\n'
        f'  {wrapped_body}\n'
        '</body>\n'
        '</html>'
    )

    return full_html
