"""Le squelette d'un HTML et d'un CSS — sélecteurs, sans le contenu."""

from html import escape
from html.parser import HTMLParser


class _HTMLSelectorSkeleton(HTMLParser):
    """Conserve la structure HTML et les attributs utiles aux sélecteurs."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []

    def _tag(self, tag, attrs, closing):
        useful = []
        for name, value in attrs:
            if name == "class" or name == "id" or name.startswith("data-"):
                rendered = name
                if value is not None:
                    rendered += f'="{escape(value, quote=True)}"'
                useful.append(rendered)
        attributes = (" " + " ".join(useful)) if useful else ""
        suffix = " />" if closing else ">"
        self.parts.append(f"<{tag}{attributes}{suffix}")

    def handle_decl(self, decl):
        self.parts.append(f"<!{decl}>")

    def handle_starttag(self, tag, attrs):
        self._tag(tag, attrs, closing=False)

    def handle_startendtag(self, tag, attrs):
        self._tag(tag, attrs, closing=True)

    def handle_endtag(self, tag):
        self.parts.append(f"</{tag}>")

def _html_selector_skeleton(content):
    parser = _HTMLSelectorSkeleton()
    parser.feed(content)
    parser.close()
    return "".join(parser.parts)

def _css_without_comments(content):
    """Supprime les commentaires CSS sans toucher aux chaînes de caractères."""
    result = []
    index = 0
    quote = None
    while index < len(content):
        char = content[index]
        if quote:
            result.append(char)
            if char == "\\" and index + 1 < len(content):
                index += 1
                result.append(content[index])
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            result.append(char)
        elif char == "/" and index + 1 < len(content) and content[index + 1] == "*":
            end = content.find("*/", index + 2)
            index = len(content) if end == -1 else end + 1
        else:
            result.append(char)
        index += 1
    return "".join(result)

def _css_selector_skeleton(content):
    """Retourne les sélecteurs CSS, sans recopier les déclarations."""
    source = _css_without_comments(content)
    selectors = []
    stack = []
    segment_start = 0
    quote = None
    index = 0
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "{":
            prelude = source[segment_start:index].strip()
            in_keyframes = any(
                rule.startswith(("@keyframes", "@-webkit-keyframes"))
                for rule in stack
            )
            if prelude and not prelude.startswith("@") and not in_keyframes:
                selectors.append(prelude)
            stack.append(prelude.lower() if prelude.startswith("@") else "")
            segment_start = index + 1
        elif char == ";":
            segment_start = index + 1
        elif char == "}":
            if stack:
                stack.pop()
            segment_start = index + 1
        index += 1
    return "\n".join(selectors) or "(aucun sélecteur CSS déclaré)"
