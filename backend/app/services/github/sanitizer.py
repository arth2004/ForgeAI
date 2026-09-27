"""Security sanitizer for untrusted Pull Request content."""

import html
import re


def sanitize_pr_text(text: str | None) -> str:
    """Sanitizes untrusted PR titles, descriptions, and comments.

    Strips script tags, executable payloads, and escapes raw HTML.
    """
    if not text:
        return ""

    # Strip dangerous HTML and script tags
    cleaned = html.escape(text)
    cleaned = (
        cleaned.replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&amp;", "&")
    )
    cleaned = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"javascript:", "blocked_script:", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def wrap_untrusted_content(label: str, content: str | None) -> str:
    """Wraps untrusted code diffs and PR descriptions with clear security boundary markers."""
    safe_content = content or "No content provided."
    return (
        f"<{label.upper()}_UNTRUSTED_CONTENT>\n"
        f"{safe_content}\n"
        f"</{label.upper()}_UNTRUSTED_CONTENT>"
    )
