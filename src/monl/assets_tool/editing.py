"""TEXTUAL editing of the spec, line by line.

Never a parse → regenerate round trip: a real project's spec is more than
half comments, and they are what explains the bricks used."""

import re

from .foundations import STARTS_OF_BLOCK, AssetsToolError


# ------------------------------------------- locating in the TEXT --
def _chaine_ouverte(text, ouvert):
    """Is a string literal still open at the end of this line?

    `STRING_LITERAL` is compiled with the /s flag and its class accepts line
    breaks: a seed value CAN therefore span two lines, and the parser accepts
    it (checked, not assumed). Outside a string, a "#" opens a comment: the
    rest of the line no longer counts."""
    escape = False
    for c in text:
        if ouvert:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                ouvert = False
        elif c == '"':
            ouvert = True
        elif c == "#":
            break
    return ouvert

def _entries_of_block(lines, i_header):
    """[(first line, last line)] per ENTRY of the indented block.

    A range, not a plain index: a seed item whose description runs over two
    lines is ONE entry. Counting lines would have shifted every following
    item, and the tool would have written the photo on the wrong one —
    silently, since the resulting spec would stay compilable.

    Empty lines and comment lines are skipped, exactly as the parser does
    (`_strip_standalone_comment_lines`): that is what lets the file's n-th
    entry match the AST's n-th. A non-indented line ends the block — except
    in the middle of a string, where indentation no longer means anything."""
    ranges, debut, ouvert = [], None, False
    for j in range(i_header + 1, len(lines)):
        brute = lines[j].rstrip("\n")
        if not ouvert:
            if not brute.strip():
                continue
            if not brute[:1].isspace():
                break
            if brute.lstrip().startswith("#"):
                continue
            debut = j
        ouvert = _chaine_ouverte(brute, ouvert)
        if not ouvert:
            ranges.append((debut, j))
    return ranges

def _replace_entry(lines, range_, publisher):
    """Applies an edit to an entry that may span SEVERAL lines."""
    debut, fin = range_
    old = "".join(lines[debut:fin + 1])
    new, previous = publisher(old)
    return (lines[:debut] + new.splitlines(keepends=True) + lines[fin + 1:],
            previous)

def _blocks_seed(lines):
    """[(entity, [line ranges]), …] in file order.

    BRICK 21 (point 100): the header accepts a parent designation (`seed
    Variant for Product.name "Chaise Ligne"`). Without accepting it HERE, this
    tool silently skipped the block while the AST contains it: the file ↔ AST
    match, on which all photo writing rests, no longer held. Any brick that
    changes the SHAPE of a spec line also constrains the tools that read it
    textually — the lesson of points 95 and 96, applied outside the smoke
    test."""
    blocks = []
    for i, line in enumerate(lines):
        m = re.match(
            r"^seed[ \t]+([A-Za-z_]\w*)"
            r"(?:[ \t]+for[ \t]+[A-Za-z_]\w*\.[A-Za-z_]\w*[ \t]+\"(?:[^\"\\]|\\.)*\")?"
            r"[ \t]*(#.*)?$",
            line.rstrip("\n"))
        if m:
            blocks.append((m.group(1), _entries_of_block(lines, i)))
    return blocks

def _block_assets(lines):
    """(header index, [property ranges]) or (None, [])."""
    for i, line in enumerate(lines):
        if re.match(r"^assets[ \t]*(#.*)?$", line.rstrip("\n")):
            return i, _entries_of_block(lines, i)
    return None, []

def _split_comment(body):
    """Isolates an end-of-line comment, respecting quotes.

    The grammar accepts `field: "x"  # note`, and a description can contain a
    "#". Cutting at the first hash met would mutilate the human's text — so
    the "inside a string" state is tracked."""
    in_chain = escape = False
    for i, c in enumerate(body):
        if in_chain:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_chain = False
        elif c == '"':
            in_chain = True
        elif c == "#":
            return body[:i], body[i:]
    return body, ""

def _segments(body):
    """Splits a seed line on the commas OUTSIDE strings.

    A description almost always contains a comma: splitting naively would
    make two fields of it, and one of the two would be free text."""
    parts, current = [], ""
    in_chain = escape = False
    for c in body:
        if in_chain:
            current += c
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_chain = False
            continue
        if c == '"':
            in_chain = True
            current += c
        elif c == ",":
            parts.append(current)
            current = ""
        else:
            current += c
    parts.append(current)
    return parts

def _literal(valeur):
    """An asset path as a monl string literal.

    Characters that would require escaping are REFUSED rather than escaped: a
    file name containing them has no business in a URL, and escaping across
    templating layers is exactly the trap already met (backslash
    over-escaping, see the working method)."""
    if any(c in valeur for c in '"\\\n\r'):
        raise AssetsToolError(
            f"'{valeur}' contains a quote, backslash, or newline: it cannot be "
            f"written to the spec and would be unreadable in a URL.")
    return f'"{valeur}"'

def _write_pair(line, field, valeur):
    """Replaces (or appends) `field: "value"` in a seed line.

    Preserves the indentation, the order of the other fields, the original
    spacing and any end-of-line comment."""
    fin = "\n" if line.endswith("\n") else ""
    body, comment = _split_comment(line.rstrip("\n"))
    blanks = body[len(body.rstrip()):]
    body = body.rstrip()
    literal = _literal(valeur)
    segments = _segments(body)
    previous = None
    for k, segment in enumerate(segments):
        key, sep, val = segment.partition(":")
        if sep and key.strip() == field:
            prefix = key[:len(key) - len(key.lstrip())]
            previous = val.strip().strip('"') or None
            segments[k] = f"{prefix}{field}: {literal}"
            break
    else:
        segments.append(f" {field}: {literal}")
    return ",".join(segments) + blanks + comment + fin, previous

def _ask_prop_assets(lines, key, valeur, folder):
    """Writes `logo:` or `favicon:` in the 'assets' block, whether it exists or
    not.

    Creating the missing block is part of the job: sending the human to write
    four lines by hand before they can place their logo would make the tool
    useless where it serves most (a project that has no assets yet)."""
    lines = list(lines)
    i_header, properties = _block_assets(lines)
    if i_header is None:
        target = next((i for i, line in enumerate(lines)
                      if line[:1] and not line[:1].isspace()
                      and line.strip().split(" ")[0] in STARTS_OF_BLOCK),
                     len(lines))
        lines[target:target] = [
            "# Files supplied by the human (brick 13). Each path declared here\n",
            "# is checked PRESENT at compilation.\n",
            "assets\n",
            f'    dir: "{folder}"\n',
            "\n",
        ]
        i_header, properties = _block_assets(lines)

    literal = _literal(valeur)
    for range_ in properties:
        body, comment = _split_comment(
            "".join(lines[range_[0]:range_[1] + 1]).rstrip("\n"))
        name, sep, val = body.partition(":")
        if sep and name.strip() == key:
            indent = name[:len(name) - len(name.lstrip())]
            previous = val.strip().strip('"') or None
            replacement = (f"{indent}{key}: {literal}"
                            + (f"  {comment}" if comment else "") + "\n")
            lines[range_[0]:range_[1] + 1] = [replacement]
            return lines, range_[0], previous

    # Missing: placed at the end of the block, with its neighbors' indentation.
    last = properties[-1][1] if properties else i_header
    indent = "    "
    if properties:
        brute = lines[properties[-1][0]]
        indent = brute[:len(brute) - len(brute.lstrip())]
    lines.insert(last + 1, f"{indent}{key}: {literal}\n")
    return lines, last + 1, None
