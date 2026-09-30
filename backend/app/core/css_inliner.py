"""CSS inlining utility for HTML emails.

Parses CSS <style> blocks and safely inlines styling rules directly onto matching
HTML element 'style' attributes for universal email client compatibility (Gmail,
Outlook, Apple Mail, Yahoo), while preserving original <style> blocks (for @media
queries and responsive layouts).
"""

import re
from typing import Dict, List, Optional, Tuple


def extract_style_blocks(html: str) -> str:
    """Extract and combine the inner CSS contents of all <style> blocks in an HTML document."""
    if not html:
        return ""
    style_contents = []
    for match in re.finditer(r"<style[^>]*>([\s\S]*?)<\/style>", html, re.IGNORECASE):
        style_contents.append(match.group(1))
    return "\n".join(style_contents)


def remove_at_rules(css_text: str) -> str:
    """Remove @media, @supports, @keyframes, @font-face and other at-rules using brace matching.
    
    These at-rules should stay in the <style> block and should not be inlined into
    individual element style attributes.
    """
    out = []
    i = 0
    n = len(css_text)
    while i < n:
        if css_text[i] == "@":
            j = i
            while j < n and css_text[j] not in "{;":
                j += 1
            if j < n and css_text[j] == ";":
                i = j + 1
                continue
            elif j < n and css_text[j] == "{":
                brace_count = 1
                k = j + 1
                while k < n and brace_count > 0:
                    if css_text[k] == "{":
                        brace_count += 1
                    elif css_text[k] == "}":
                        brace_count -= 1
                    k += 1
                i = k
                continue
            else:
                i = j
                continue
        else:
            out.append(css_text[i])
            i += 1
    return "".join(out)


def parse_css_declarations(decl_str: str) -> Dict[str, str]:
    """Parse a CSS declaration block into a dictionary of property -> value."""
    decls: Dict[str, str] = {}
    for part in decl_str.split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        prop, val = part.split(":", 1)
        prop = prop.strip().lower()
        val = val.strip()
        if prop and val:
            decls[prop] = val
    return decls


def parse_css_rules(css_text: str) -> List[Tuple[str, Dict[str, str], int, int]]:
    """Parse CSS rules from a CSS block into (selector, declarations, specificity, order).
    
    Media queries, keyframes, and pseudo-classes (:hover, :focus) are excluded from inlining.
    """
    cleaned = re.sub(r"/\*[\s\S]*?\*/", "", css_text)
    cleaned = remove_at_rules(cleaned)

    rules: List[Tuple[str, Dict[str, str], int, int]] = []
    order = 0
    for match in re.finditer(r"([^{}]+)\{([^{}]+)\}", cleaned):
        raw_selectors = match.group(1).strip()
        decl_str = match.group(2).strip()
        decls = parse_css_declarations(decl_str)
        if not decls:
            continue
        for sel in raw_selectors.split(","):
            sel = sel.strip()
            # Ignore empty, at-rules, or pseudo-classes (:hover, :active, etc.)
            if not sel or sel.startswith("@") or ":" in sel:
                continue
            # Calculate simple specificity:
            # ID (#) = 100, Class (.) = 10, Tag = 1, Descendant = +1 per segment
            spec = 0
            if "#" in sel:
                spec += 100 * sel.count("#")
            if "." in sel:
                spec += 10 * sel.count(".")
            parts = sel.split()
            spec += len(parts)
            rules.append((sel, decls, spec, order))
            order += 1
    return rules


def _single_part_matches(part: str, tag: str, classes: List[str], elem_id: Optional[str]) -> bool:
    """Check if a single selector part matches a specific element's tag, classes, and ID."""
    part = part.strip()
    if not part:
        return False
    if part == "*":
        return True

    # Strip attribute selectors like [attr] or [attr=val] if present
    base_part = re.sub(r"\[.*?\]", "", part)
    if not base_part:
        return True

    tokens = re.findall(r"([.#]?[a-zA-Z0-9_-]+)", base_part)
    if not tokens:
        return False

    match_tag = None
    required_id = None
    required_classes = []

    for tok in tokens:
        if tok.startswith("#"):
            required_id = tok[1:]
        elif tok.startswith("."):
            required_classes.append(tok[1:])
        else:
            match_tag = tok.lower()

    if match_tag is not None and match_tag != tag.lower():
        return False
    if required_id is not None and required_id != elem_id:
        return False
    for req_cls in required_classes:
        if req_cls not in classes:
            return False

    return True


def selector_matches(
    selector: str,
    tag: str,
    classes: List[str],
    elem_id: Optional[str],
    ancestor_stack: List[Tuple[str, List[str], Optional[str]]],
) -> bool:
    """Check if a CSS selector (simple, descendant, or child combinator) matches the current element."""
    sel = re.sub(r"\s*>\s*", " > ", selector.strip())
    parts = sel.split()
    if not parts:
        return False

    target_part = parts[-1]
    if not _single_part_matches(target_part, tag, classes, elem_id):
        return False

    if len(parts) == 1:
        return True

    ancestor_idx = len(ancestor_stack) - 1
    i = len(parts) - 2
    require_direct_parent = False

    while i >= 0:
        part = parts[i]
        if part == ">":
            require_direct_parent = True
            i -= 1
            continue

        if ancestor_idx < 0:
            return False

        if require_direct_parent:
            anc_tag, anc_classes, anc_id = ancestor_stack[ancestor_idx]
            if not _single_part_matches(part, anc_tag, anc_classes, anc_id):
                return False
            ancestor_idx -= 1
            require_direct_parent = False
        else:
            matched = False
            while ancestor_idx >= 0:
                anc_tag, anc_classes, anc_id = ancestor_stack[ancestor_idx]
                ancestor_idx -= 1
                if _single_part_matches(part, anc_tag, anc_classes, anc_id):
                    matched = True
                    break
            if not matched:
                return False

        i -= 1

    return True
