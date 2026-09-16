"""HTML sanitization utility for email signatures, templates, and messages.

Uses Python's standard library html.parser.HTMLParser to parse tokens safely
without regex-based parsing vulnerabilities.
"""

from html import escape
from html.parser import HTMLParser
import re
from typing import List, Optional, Set, Tuple
import urllib.parse


class _HTMLSanitizerParser(HTMLParser):
    """Event-driven HTML parser that strips unsafe tags, scripts, dangerous attributes,
    and executable URI schemes while preserving standard formatting elements.
    """

    ALLOWED_TAGS: Set[str] = {
        "p", "div", "span", "br", "hr",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "strong", "b", "em", "i", "u", "s", "strike",
        "a", "ul", "ol", "li",
        "blockquote", "pre", "code",
        "table", "thead", "tbody", "tfoot", "tr", "th", "td",
        "img", "font", "small", "sub", "sup",
    }

    VOID_TAGS: Set[str] = {"br", "hr", "img"}

    DISALLOWED_CONTENT_TAGS: Set[str] = {
        "script", "style", "iframe", "object", "embed", "applet",
        "meta", "link", "form", "input", "button", "textarea", "select",
    }

    ALLOWED_SCHEMES: Set[str] = {"http", "https", "mailto", "tel"}

    # Allowed safe attributes per tag, and universal attributes
    GLOBAL_ALLOWED_ATTRS: Set[str] = {"class", "id", "style", "title", "dir", "align", "valign", "color"}
    TAG_SPECIFIC_ATTRS: dict = {
        "a": {"href", "title", "target", "rel"},
        "img": {"src", "alt", "title", "width", "height"},
        "font": {"color", "size", "face"},
        "td": {"colspan", "rowspan", "width", "height", "align", "valign"},
        "th": {"colspan", "rowspan", "width", "height", "align", "valign"},
        "table": {"border", "cellpadding", "cellspacing", "width"},
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output: List[str] = []
        self._suppress_content_depth: int = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_lower = tag.lower()

        if tag_lower in self.DISALLOWED_CONTENT_TAGS:
            self._suppress_content_depth += 1
            return

        if self._suppress_content_depth > 0:
            return

        if tag_lower not in self.ALLOWED_TAGS:
            # Drop tag, but allow its inner text
            return

        # Filter attributes
        cleaned_attrs: List[Tuple[str, str]] = []
        allowed_for_tag = self.TAG_SPECIFIC_ATTRS.get(tag_lower, set()).union(self.GLOBAL_ALLOWED_ATTRS)

        for attr_name, attr_val in attrs:
            attr_lower = attr_name.lower().strip()
            val_str = (attr_val or "").strip()

            # 1. Block any event handlers (e.g. onclick, onerror, onload)
            if attr_lower.startswith("on"):
                continue

            # 2. Must be an allowed attribute for this tag or globally
            if attr_lower not in allowed_for_tag:
                continue

            # 3. URL attribute security check (href, src)
            if attr_lower in {"href", "src"}:
                if not self._is_safe_url(val_str):
                    continue

            # 4. Style attribute security check (disallow javascript: or expression())
            if attr_lower == "style":
                val_lower = val_str.lower().replace(" ", "").replace("\t", "").replace("\r", "").replace("\n", "")
                if "expression(" in val_lower or "javascript:" in val_lower or "vbscript:" in val_lower:
                    continue

            cleaned_attrs.append((attr_lower, val_str))

        # Format tag
        attrs_str = ""
        if cleaned_attrs:
            formatted = [f'{k}="{escape(v, quote=True)}"' for k, v in cleaned_attrs]
            attrs_str = " " + " ".join(formatted)

        if tag_lower in {"br", "hr"}:
            self.output.append(f"<{tag_lower}{attrs_str}>")
        elif tag_lower in self.VOID_TAGS:
            self.output.append(f"<{tag_lower}{attrs_str} />")
        else:
            self.output.append(f"<{tag_lower}{attrs_str}>")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()

        if tag_lower in self.DISALLOWED_CONTENT_TAGS:
            self._suppress_content_depth = max(0, self._suppress_content_depth - 1)
            return

        if self._suppress_content_depth > 0:
            return

        if tag_lower in self.ALLOWED_TAGS and tag_lower not in self.VOID_TAGS:
            self.output.append(f"</{tag_lower}>")

    def handle_data(self, data: str) -> None:
        if self._suppress_content_depth == 0:
            self.output.append(escape(data, quote=False))

    def _is_safe_url(self, url_str: str) -> bool:
        """Validate URL to ensure it does not use executable schemes like javascript:."""
        # Strip ASCII control characters and whitespace
        clean_url = "".join(c for c in url_str if c.isprintable()).strip()
        # Collapse whitespace/tabs that attackers use to bypass scheme checks: "java\nscript:"
        collapsed = re.sub(r"\s+", "", clean_url).lower()
        if collapsed.startswith(("javascript:", "vbscript:", "data:")):
            return False

        parsed = urllib.parse.urlparse(clean_url)
        if parsed.scheme:
            return parsed.scheme.lower() in self.ALLOWED_SCHEMES
        # Relative URLs (like anchors or relative paths) are allowed
        return True


def sanitize_html(raw_html: Optional[str]) -> Optional[str]:
    """Sanitize HTML content using Python's standard library HTMLParser.
    
    Removes script tags and their contents, event-handler attributes (onclick,
    onerror, onload), javascript: URLs, and unsafe tags, while preserving
    email formatting markup (p, div, br, b, strong, i, em, a, table, lists).
    """
    if raw_html is None:
        return None
    if not raw_html.strip():
        return ""

    parser = _HTMLSanitizerParser()
    try:
        parser.feed(raw_html)
        parser.close()
        return "".join(parser.output)
    except Exception:
        # Fallback to escaped plain text if parsing fails completely
        return escape(raw_html)
