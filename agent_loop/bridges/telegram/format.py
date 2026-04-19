"""Markdown to Telegram HTML conversion + text splitting."""

from __future__ import annotations

import html as html_mod
import re

from agent_loop.util.text import split_text

# Telegram max message length
MAX_MESSAGE_LENGTH = 4096


def markdown_to_telegram_html(text: str) -> str:
    """Convert GitHub-flavored Markdown to Telegram-compatible HTML.

    Handles: code blocks, inline code, headers, bold, italic,
    strikethrough, links, list bullets, blockquotes.
    """
    placeholders = {}
    counter = [0]

    def placeholder(content):
        key = f"\x00PH{counter[0]}\x00"
        counter[0] += 1
        placeholders[key] = content
        return key

    # 1. Fenced code blocks
    def repl_code_block(m):
        lang = m.group(1) or ""
        code = html_mod.escape(m.group(2).rstrip("\n"))
        if lang:
            return placeholder(
                f'<pre><code class="language-{lang}">{code}</code></pre>'
            )
        return placeholder(f"<pre><code>{code}</code></pre>")

    text = re.sub(r"```(\w*)\n(.*?)```", repl_code_block, text, flags=re.DOTALL)

    # 2. Inline code
    def repl_inline_code(m):
        return placeholder(f"<code>{html_mod.escape(m.group(1))}</code>")

    text = re.sub(r"`([^`]+)`", repl_inline_code, text)

    # 3. Escape remaining HTML special chars
    text = html_mod.escape(text)

    # 4. Headers → bold
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 5. Bold (**text** or __text__)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 6. Italic (*text* or _text_)
    text = re.sub(r"(?<!\w)\*(?!\s)([^*]+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(?!\s)([^_]+?)(?<!\s)_(?!\w)", r"<i>\1</i>", text)

    # 7. Strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 8. Links [text](url)
    def repl_link(m):
        label = m.group(1)
        url = m.group(2).replace("&amp;", "&")
        return f'<a href="{url}">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl_link, text)

    # 9. List bullets: "- " and "* " → "• "
    text = re.sub(r"^[-*]\s+", "\u2022 ", text, flags=re.MULTILINE)

    # 10. Blockquotes
    def repl_blockquote(m):
        lines = m.group(0).split("\n")
        inner = "\n".join(re.sub(r"^&gt;\s?", "", line) for line in lines)
        return f"<blockquote>{inner}</blockquote>"

    text = re.sub(
        r"^&gt;\s?.+(?:\n&gt;\s?.+)*", repl_blockquote, text, flags=re.MULTILINE
    )

    # Restore placeholders
    for key, value in placeholders.items():
        text = text.replace(key, value)

    return text


def format_and_split(text: str) -> list[str]:
    """Convert Markdown to HTML and split into Telegram-sized chunks."""
    formatted = markdown_to_telegram_html(text)
    return split_text(formatted, MAX_MESSAGE_LENGTH)


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities — fallback for send errors."""
    plain = html_mod.unescape(re.sub(r"<[^>]+>", "", text))
    return plain
