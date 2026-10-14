"""HTML sanitization and CSS inlining utility for email signatures, templates, and messages.

Uses Python's standard library html.parser.HTMLParser to parse tokens safely
without regex-based parsing vulnerabilities. Inlines CSS rules from <style> blocks
directly onto HTML elements for universal email client compatibility (Gmail, Outlook,
Apple Mail, Yahoo) while preserving security sanitization and responsive <style> blocks.
"""

from html import escape
from html.parser import HTMLParser
import re
from typing import Dict, List, Optional, Set, Tuple
import urllib.parse

from app.core.css_inliner import (
    extract_style_blocks,
    inline_css,
    parse_css_declarations,
    parse_css_rules,
    selector_matches,
)


class _HTMLSanitizerParser(HTMLParser):
    """Event-driven HTML parser that strips unsafe tags, scripts, dangerous attributes,
    and executable URI schemes while preserving standard formatting elements and
    inlining CSS stylesheet rules for email clients.
    """

    ALLOWED_TAGS: Set[str] = {
        "html", "head", "body", "title", "style", "meta",
        "p", "div", "span", "br", "hr", "center",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "strong", "b", "em", "i", "u", "s", "strike",
        "a", "ul", "ol", "li",
        "blockquote", "pre", "code",
        "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
        "img", "font", "small", "sub", "sup",
    }

    VOID_TAGS: Set[str] = {"br", "hr", "img", "meta"}

    # Container tags whose content must be suppressed along with the tag
    DISALLOWED_CONTENT_TAGS: Set[str] = {
        "script", "iframe", "object", "embed", "applet",
        "form", "input", "button", "textarea", "select",
    }

    ALLOWED_SCHEMES: Set[str] = {"http", "https", "mailto", "tel", "cid"}

    # Allowed safe attributes per tag, and universal attributes
    GLOBAL_ALLOWED_ATTRS: Set[str] = {
        "class", "id", "style", "title", "dir", "align", "valign",
        "color", "bgcolor", "width", "height", "lang", "role", "border",
    }
    TAG_SPECIFIC_ATTRS: dict = {
        "a": {"href", "title", "target", "rel", "style"},
        "img": {"src", "alt", "title", "width", "height", "border", "style", "data-media-id"},
        "font": {"color", "size", "face", "style"},
        "tr": {"bgcolor", "align", "valign", "style"},
        "td": {"colspan", "rowspan", "width", "height", "align", "valign", "bgcolor", "style"},
        "th": {"colspan", "rowspan", "width", "height", "align", "valign", "bgcolor", "style"},
        "table": {"border", "cellpadding", "cellspacing", "width", "height", "align", "bgcolor", "role", "style"},
        "meta": {"charset", "name", "content", "http-equiv"},
        "style": {"type", "media"},
        "body": {"bgcolor", "text", "link", "vlink", "alink", "marginwidth", "marginheight", "topmargin", "leftmargin", "style"},
        "html": {"lang", "xmlns"},
    }

    def __init__(self, css_rules: Optional[List[Tuple[str, Dict[str, str], int, int]]] = None):
        super().__init__(convert_charrefs=True)
        self.css_rules = css_rules or []
        self.output: List[str] = []
        self._suppress_content_depth: int = 0
        self._in_style_tag: bool = False
        self.ancestor_stack: List[Tuple[str, List[str], Optional[str]]] = []

    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype"):
            self.output.append(f"<!{decl}>\n")

    def handle_comment(self, comment: str) -> None:
        # Preserve safe conditional comments (e.g. Outlook/MSO styles) while blocking script injection
        if "<script" not in comment.lower() and "javascript:" not in comment.lower():
            self.output.append(f"<!--{comment}-->")

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

        if tag_lower == "style":
            self._in_style_tag = True

        raw_attrs_dict: Dict[str, str] = {}
        for attr_name, attr_val in attrs:
            raw_attrs_dict[attr_name.lower().strip()] = (attr_val or "").strip()

        elem_id = raw_attrs_dict.get("id") or None
        cls_str = raw_attrs_dict.get("class", "")
        classes = cls_str.split() if cls_str else []

        # Find matching CSS stylesheet rules and compute merged styles
        matching_rules = []
        if self.css_rules and tag_lower not in {"html", "head", "title", "style", "meta"}:
            for r in self.css_rules:
                sel, decls, spec, order = r
                if selector_matches(sel, tag_lower, classes, elem_id, self.ancestor_stack):
                    matching_rules.append(r)

        existing_style = raw_attrs_dict.get("style")
        final_style: Optional[str] = None

        if matching_rules:
            matching_rules.sort(key=lambda r: (r[2], r[3]))
            merged_styles: Dict[str, str] = {}
            for sel, decls, spec, order in matching_rules:
                for prop, val in decls.items():
                    is_important = "!important" in val.lower()
                    curr_val = merged_styles.get(prop)
                    if curr_val is None:
                        merged_styles[prop] = val
                    else:
                        curr_important = "!important" in curr_val.lower()
                        if is_important or not curr_important:
                            merged_styles[prop] = val

            if existing_style:
                parsed_inline = parse_css_declarations(existing_style)
                for prop, val in parsed_inline.items():
                    merged_styles[prop] = val

            style_str = "; ".join([f"{k}: {v}" for k, v in merged_styles.items()])
            if style_str and not style_str.endswith(";"):
                style_str += ";"
            final_style = style_str
        elif existing_style:
            final_style = existing_style

        # Filter safe attributes
        cleaned_attrs: List[Tuple[str, str]] = []
        allowed_for_tag = self.TAG_SPECIFIC_ATTRS.get(tag_lower, set()).union(self.GLOBAL_ALLOWED_ATTRS)

        for attr_lower, val_str in raw_attrs_dict.items():
            # 1. Block any event handlers (e.g. onclick, onerror, onload)
            if attr_lower.startswith("on"):
                continue

            # 2. Must be an allowed attribute for this tag or globally
            if attr_lower not in allowed_for_tag:
                continue

            # 3. URL attribute security check (href, src)
            if attr_lower in {"href", "src"}:
                if not self._is_safe_url(val_str, tag_lower=tag_lower, attr_lower=attr_lower):
                    continue

            # 4. Skip style here; we attach validated final_style below
            if attr_lower == "style":
                continue

            cleaned_attrs.append((attr_lower, val_str))

        # Attach merged & sanitized style attribute
        if final_style:
            val_lower = final_style.lower().replace(" ", "").replace("\t", "").replace("\r", "").replace("\n", "")
            if not ("expression(" in val_lower or "javascript:" in val_lower or "vbscript:" in val_lower):
                cleaned_attrs.append(("style", final_style))

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
            self.ancestor_stack.append((tag_lower, classes, elem_id))

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()

        if tag_lower in self.DISALLOWED_CONTENT_TAGS:
            self._suppress_content_depth = max(0, self._suppress_content_depth - 1)
            return

        if self._suppress_content_depth > 0:
            return

        if tag_lower == "style":
            self._in_style_tag = False

        if tag_lower in self.ALLOWED_TAGS and tag_lower not in self.VOID_TAGS:
            self.output.append(f"</{tag_lower}>")
            # Pop matching element from ancestor_stack
            for idx in range(len(self.ancestor_stack) - 1, -1, -1):
                if self.ancestor_stack[idx][0] == tag_lower:
                    self.ancestor_stack.pop(idx)
                    break

    def handle_data(self, data: str) -> None:
        if self._suppress_content_depth == 0:
            if self._in_style_tag:
                # Sanitize CSS content: block expression(...) or javascript: or vbscript: or @import
                cleaned_css = re.sub(r"expression\s*\(", "blocked(", data, flags=re.IGNORECASE)
                cleaned_css = re.sub(r"javascript\s*:", "blocked:", cleaned_css, flags=re.IGNORECASE)
                cleaned_css = re.sub(r"vbscript\s*:", "blocked:", cleaned_css, flags=re.IGNORECASE)
                cleaned_css = re.sub(r"@import\s*", "/* @import blocked */", cleaned_css, flags=re.IGNORECASE)
                self.output.append(cleaned_css)
            else:
                self.output.append(escape(data, quote=False))

    def _is_safe_url(self, url_str: str, tag_lower: str = "", attr_lower: str = "") -> bool:
        """Validate URL to ensure it does not use executable schemes like javascript:."""
        # Strip ASCII control characters and whitespace
        clean_url = "".join(c for c in url_str if c.isprintable()).strip()
        # Reject URLs containing raw quotes, brackets, or backticks (attribute breakout vectors)
        if any(c in clean_url for c in ('"', "'", "<", ">", "`")):
            return False

        # Collapse whitespace/tabs that attackers use to bypass scheme checks: "java\nscript:"
        collapsed = re.sub(r"\s+", "", clean_url).lower()
        if collapsed.startswith(("javascript:", "vbscript:")):
            return False

        if collapsed.startswith("data:"):
            # Only allow safe raster image data URIs in img src attributes
            # Disallow data:text/html, data:image/svg+xml (XSS vectors), and data in href
            if tag_lower == "img" and attr_lower == "src":
                if re.match(r"^data:image\/(png|jpeg|jpg|gif|webp);base64,[a-z0-9+/=]+$", collapsed):
                    return True
            return False

        parsed = urllib.parse.urlparse(clean_url)
        if parsed.scheme:
            return parsed.scheme.lower() in self.ALLOWED_SCHEMES
        # Relative URLs (like anchors or relative paths) are allowed
        return True


def sanitize_html(raw_html: Optional[str]) -> Optional[str]:
    """Sanitize HTML content using Python's standard library HTMLParser and inline CSS rules.
    
    Removes script tags and their contents, event-handler attributes (onclick,
    onerror, onload), javascript: URLs, and unsafe tags, while preserving
    email formatting markup (p, div, br, b, strong, i, em, a, table, lists),
    and inlining CSS rules from <style> blocks into element style="..." attributes.
    """
    if raw_html is None:
        return None
    if not raw_html.strip():
        return ""

    # Pre-inline CSS rules onto element style attributes before sanitization
    if "<style" in raw_html.lower():
        try:
            inlined = inline_css(raw_html)
            if inlined:
                raw_html = inlined
        except Exception:
            pass

    style_content = extract_style_blocks(raw_html)
    css_rules = parse_css_rules(style_content) if style_content else []

    parser = _HTMLSanitizerParser(css_rules=css_rules)
    try:
        parser.feed(raw_html)
        parser.close()
        return "".join(parser.output)
    except Exception:
        # Fallback to escaped plain text if parsing fails completely
        return escape(raw_html)
