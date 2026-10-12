from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse


ALLOWED_TAGS = {
    "p", "br", "strong", "em", "u", "s",
    "h2", "h3", "h4",
    "ul", "ol", "li",
    "blockquote", "a",
}
TAG_ALIASES = {"b":"strong", "i":"em", "strike":"s", "del":"s", "div":"p"}


class BlogHTMLSanitizer(HTMLParser):
    """Permite formato editorial sencillo y elimina elementos/scripts peligrosos."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "svg", "math"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        tag = TAG_ALIASES.get(tag, tag)
        if tag not in ALLOWED_TAGS:
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag == "a":
            allowed = []
            for name, value in attrs:
                if name.lower() == "href" and value:
                    parsed = urlparse(value.strip())
                    if parsed.scheme in ("http", "https", "mailto") or value.startswith("/"):
                        allowed.append(f'href="{escape(value, quote=True)}"')
                elif name.lower() == "title" and value:
                    allowed.append(f'title="{escape(value, quote=True)}"')
            self.parts.append("<a" + (" " + " ".join(allowed) if allowed else "") + ">")
        else:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "svg", "math"}:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        tag = TAG_ALIASES.get(tag, tag)
        if tag in ALLOWED_TAGS and tag != "br":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(escape(data))

    def handle_entityref(self, name):
        if not self.skip_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip_depth:
            self.parts.append(f"&#{name};")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in {"br"}:
            self.handle_endtag(tag)

    def get_html(self):
        return "".join(self.parts)


def sanitize_blog_html(value):
    parser = BlogHTMLSanitizer()
    parser.feed(value or "")
    parser.close()
    return parser.get_html()
