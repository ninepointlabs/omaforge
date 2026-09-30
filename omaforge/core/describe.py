"""Addon descriptions from each source, made safe for the UI's rich text.

CurseForge sends HTML, WoWInterface BBCode or Markdown, GitHub a Markdown
README. Everything comes out as either a small HTML subset or Markdown, with
images, scripts and embeds removed: Qt's rich text would otherwise fetch
every image inline. Pictures are shown separately as screenshots. The UI
turns Markdown into HTML with Qt's own parser and passes it through
clean_html() again.
"""

import html
import re
import urllib.parse
from html.parser import HTMLParser

MAX_LENGTH = 200_000

# Tags Qt's rich text understands and that are safe to keep, without attributes.
KEEP = {
    "a", "b", "strong", "i", "em", "u", "s", "del", "strike", "code", "pre", "kbd", "tt", "blockquote",
    "p", "br", "hr", "ul", "ol", "li", "dl", "dt", "dd", "table", "thead", "tbody", "tr", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6", "sub", "sup", "small", "big",
}
VOID = {"br", "hr"}
BLOCK = {"div", "section", "article", "header", "footer", "center", "figure", "figcaption", "details", "summary"}
# Dropped with everything inside them.
DROP = {"script", "style", "iframe", "object", "embed", "noscript", "svg", "video", "audio", "picture", "template",
        "head", "title", "form", "button", "select", "textarea"}
HEADING_SHIFT = 2  # a README's "# Name" should not be the size of the window title


def _link(href: str | None) -> str | None:
    """An absolute http(s) URL, with CurseForge's linkout redirect removed."""
    if not href:
        return None
    href = href.strip()
    parsed = urllib.parse.urlparse(href)
    if parsed.path.endswith("/linkout"):
        target = urllib.parse.parse_qs(parsed.query).get("remoteUrl")
        if target:
            href = urllib.parse.unquote(target[0])
            parsed = urllib.parse.urlparse(href)
    return href if parsed.scheme in ("http", "https") and parsed.netloc else None


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.dropping = 0
        self.open: list[str] = []

    def _tag(self, tag: str) -> str | None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return f"h{min(6, int(tag[1]) + HEADING_SHIFT)}"
        return tag if tag in KEEP else None

    def handle_starttag(self, tag, attrs):
        if tag in DROP:
            self.dropping += 1
            return
        if self.dropping:
            return
        if tag in BLOCK:
            self.out.append("<p>")
            return
        name = self._tag(tag)
        if name is None:
            return
        if name == "a":
            href = _link(dict(attrs).get("href"))
            if href is None:
                self.open.append("")  # keep the text, drop the link
                return
            self.out.append(f'<a href="{html.escape(href)}">')
        else:
            if name in ("li", "p") and self.open and self.open[-1] == name:
                self.out.append(f"</{self.open.pop()}>")  # a new item ends the one before
            self.out.append(f"<{name}>")
        if name not in VOID:
            self.open.append(name)

    def handle_startendtag(self, tag, attrs):
        if tag in DROP or self.dropping:
            return
        name = self._tag(tag)
        if name in VOID:
            self.out.append(f"<{name}>")

    def handle_endtag(self, tag):
        if tag in DROP:
            self.dropping = max(0, self.dropping - 1)
            return
        if self.dropping:
            return
        if tag in BLOCK:
            self.out.append("</p>")
            return
        name = self._tag(tag)
        if name == "a" and "" in self.open and (
                "a" not in self.open or self.open[::-1].index("") < self.open[::-1].index("a")):
            del self.open[len(self.open) - 1 - self.open[::-1].index("")]
            return
        if name is None or name in VOID or name not in self.open:
            return
        # Close anything left open inside this element first.
        while self.open:
            top = self.open.pop()
            if top:
                self.out.append(f"</{top}>")
            if top == name:
                break

    def handle_data(self, data):
        if not self.dropping:
            self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        self.close()
        tail = [f"</{t}>" for t in reversed(self.open) if t]
        text = "".join(self.out + tail)
        text = re.sub(r"(<p>(\s|<br>)*</p>\s*)+", "", text)
        return text.strip()


def clean_html(text: str) -> str:
    cleaner = _Cleaner()
    cleaner.feed(text[:MAX_LENGTH])
    return cleaner.result()


BBCODE = re.compile(r"\[(?:(?:b|i|u|s|url|img|list|color|size|font|center|quote|code|highlight|indent)\b[^\]]*|\*)\]",
                    re.I)
MARKDOWN = re.compile(r"^\s{0,3}(#{1,6}\s|[*-]\s|\d+\.\s|```)|\]\(https?://|\*\*\S", re.M)


def _lists(text: str) -> str:
    """[list] and [list=1] to <ul>/<ol>, closing each with the tag it opened."""
    stack: list[str] = []

    def repl(m):
        if m.group(1):
            return f"</{stack.pop()}>" if stack else ""
        stack.append("ol" if m.group(2) else "ul")
        return f"<{stack[-1]}>"

    return re.sub(r"\[(/?)list(=1)?[^\]]*\]", repl, text, flags=re.I)


def bbcode_to_html(text: str) -> str:
    text = html.escape(text[:MAX_LENGTH].replace("\r\n", "\n"), quote=False)
    text = re.sub(r"\[img[^\]]*\].*?\[/img\]", "", text, flags=re.I | re.S)
    text = re.sub(r"\[url\](.*?)\[/url\]", r'<a href="\1">\1</a>', text, flags=re.I | re.S)
    text = re.sub(r'\[url="?([^"\]]*)"?\](.*?)\[/url\]', r'<a href="\1">\2</a>', text, flags=re.I | re.S)
    for bb, tag in (("b", "b"), ("i", "i"), ("u", "u"), ("s", "s"), ("quote", "blockquote"), ("code", "pre")):
        text = re.sub(rf"\[{bb}(=[^\]]*)?\]", f"<{tag}>", text, flags=re.I)
        text = re.sub(rf"\[/{bb}\]", f"</{tag}>", text, flags=re.I)
    text = _lists(text)
    text = re.sub(r"\[\*\]\s*", "<li>", text)
    # Formatting Qt can't show from here: keep the text, drop the tags.
    text = re.sub(r"\[/?(color|size|font|center|left|right|highlight|indent|email|spoiler)(=[^\]]*)?\]", "", text,
                  flags=re.I)
    text = re.sub(r"\n*(</?(ul|ol|li|blockquote|pre)>)\n*", r"\1", text)
    return clean_html(text.replace("\n", "<br>"))


MD_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.I)


def clean_markdown(text: str) -> str:
    text = text[:MAX_LENGTH].replace("\r\n", "\n")
    for tag in DROP:
        text = re.sub(rf"<{tag}\b.*?</{tag}\s*>", "", text, flags=re.I | re.S)
    text = re.sub(r"<(img|source|br)\b[^>]*>", lambda m: "\n" if m.group(1).lower() == "br" else "", text, flags=re.I)
    text = re.sub(r"\[\s*" + MD_IMAGE.pattern + r"\s*\]\([^)]*\)", "", text)  # linked badges
    text = MD_IMAGE.sub("", text)
    text = re.sub(r"\[\s*\]\([^)]*\)", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


NOT_SCREENSHOTS = ("shields.io", "badge", "travis-ci", "/workflows/", "donate", "paypal", "patreon", "ko-fi", "discord")


def markdown_images(text: str, base: str) -> list[str]:
    """Image URLs in a Markdown document, badges and icons left out, resolved against `base`."""
    out = []
    for m in sorted([*MD_IMAGE.finditer(text), *HTML_IMAGE.finditer(text)], key=lambda m: m.start()):
        url = urllib.parse.urljoin(base, html.unescape(m.group(1)))
        low = url.lower()
        if not low.startswith(("https://", "http://")) or url in out:
            continue
        if low.split("?")[0].endswith(".svg") or any(s in low for s in NOT_SCREENSHOTS):
            continue
        out.append(url)
    return out


def describe(text: str, kind: str) -> tuple[str, str]:
    """(format, text) for the UI: format is "html" or "markdown". `kind` is html, markdown, bbcode or text."""
    text = (text or "").strip()
    if not text:
        return "html", ""
    if kind == "html":
        return "html", clean_html(text)
    if kind == "markdown" or (kind == "bbcode" and not BBCODE.search(text) and MARKDOWN.search(text)):
        return "markdown", clean_markdown(text)
    return "html", bbcode_to_html(text)
