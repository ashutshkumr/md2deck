#!/usr/bin/env python3
"""md2deck: stitch Markdown and images into one self-contained HTML slide deck.

    python3 md2deck.py deck.md               writes deck.html next to deck.md
    python3 md2deck.py deck.md -o out.html   writes out.html
    python3 md2deck.py --format              prints the Markdown format reference

One file, standard library only, Python 3.8 or newer.

Why the tool exists and the rules for changing it are in AGENTS.md in the repository:
https://github.com/ashutshkumr/md2deck
"""
import argparse
import base64
import html
import math
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_UP

__version__ = "1.0.0"
__url__ = "https://github.com/ashutshkumr/md2deck"


class DeckError(Exception):
    """A problem in the Markdown source, reported with its line number."""

    def __init__(self, line, msg):
        Exception.__init__(self, msg)
        self.line = line
        self.msg = msg


class Node(object):
    def __init__(self, kind, line, **fields):
        self.kind = kind
        self.line = line
        self.__dict__.update(fields)


# ---------------------------------------------------------------- block parser

ROW_BOXES = ("tiles", "stat", "facts", "summary", "steps", "legend")
FLOW_BOXES = ("cols", "cards", "card")
COLORS = {"accent": "var(--accent)", "warm": "var(--warm)", "muted": "var(--bar-muted)", "faint": "var(--hair)"}
FILL = {"accent": "b1", "warm": "b2", "muted": "bm", "faint": "bo"}

RE_FENCE = re.compile(r"^(`{3,})\s*(.*)$")
RE_OPEN = re.compile(r"^:::\s*([A-Za-z]+)\s*(.*)$")
RE_CLOSE = re.compile(r"^:::\s*$")
RE_SEP = re.compile(r"^\+\+\+\s*$")
RE_RULE = re.compile(r"^(-{3,}|\*{3,}|_{3,})\s*$")
RE_HEAD = re.compile(r"^(#{1,6})\s+(.+)$")
RE_SMALL = re.compile(r"^-#\s+(.+)$")
RE_IMG = re.compile(r'^!\[([^\]]*)\]\(\s*([^\s)]+)(?:\s+"([^"]*)")?\s*\)$')
RE_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
RE_TSEP = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def starts_block(s):
    """True when the stripped line s begins something other than paragraph text."""
    return bool(
        RE_FENCE.match(s) or s.startswith(":::") or RE_SEP.match(s) or RE_RULE.match(s) or RE_HEAD.match(s)
        or RE_SMALL.match(s) or s.startswith(">") or s.startswith("|") or RE_IMG.match(s) or RE_ITEM.match(s)
        or s.startswith("<!--")
    )


def take_text(L, i, first):
    """Join `first` with the plain continuation lines that follow line i."""
    parts = [first]
    i += 1
    while i < len(L):
        s = L[i][1].strip()
        if not s or starts_block(s):
            break
        parts.append(s)
        i += 1
    return " ".join(parts), i


def parse_blocks(L, i=0, opener=None):
    """Parse the numbered lines L[i:] into nodes. Inside a container, stop at its closing ':::'."""
    out = []
    while i < len(L):
        ln, raw = L[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s.startswith("<!--"):
            while i < len(L) and "-->" not in L[i][1]:
                i += 1
            i += 1
            continue
        m = RE_FENCE.match(s)
        if m:
            close = re.compile(r"^\s*`{%d,}\s*$" % len(m.group(1)))
            j = i + 1
            while j < len(L) and not close.match(L[j][1]):
                j += 1
            if j == len(L):
                raise DeckError(ln, "this ``` block is never closed")
            out.append(Node("fence", ln, info=m.group(2).strip(), body=L[i + 1:j]))
            i = j + 1
            continue
        if RE_CLOSE.match(s):
            if opener is None:
                raise DeckError(ln, "':::' closes a container, but none is open here")
            return out, i + 1
        m = RE_OPEN.match(s)
        if m:
            name, args = m.group(1).lower(), m.group(2).split()
            if name in ROW_BOXES:
                j = i + 1
                while j < len(L) and not RE_CLOSE.match(L[j][1].strip()):
                    j += 1
                if j == len(L):
                    raise DeckError(ln, "'::: %s' is never closed with ':::'" % name)
                rows = [(a, b.strip()) for a, b in L[i + 1:j] if b.strip()]
                out.append(Node("box", ln, name=name, args=args, rows=rows))
                i = j + 1
            elif name in FLOW_BOXES:
                kids, i = parse_blocks(L, i + 1, opener=(ln, name))
                out.append(Node("flow", ln, name=name, args=args, kids=kids))
            else:
                raise DeckError(ln, "unknown container '::: %s' (use one of: %s)" % (name, ", ".join(FLOW_BOXES + ROW_BOXES)))
            continue
        if RE_SEP.match(s):
            out.append(Node("sep", ln))
            i += 1
            continue
        if RE_RULE.match(s):
            out.append(Node("break" if opener is None else "rule", ln))
            i += 1
            continue
        m = RE_HEAD.match(s)
        if m:
            out.append(Node("h", ln, level=len(m.group(1)), text=m.group(2).strip()))
            i += 1
            continue
        m = RE_IMG.match(s)
        if m:
            out.append(Node("img", ln, alt=m.group(1), src=m.group(2), cap=m.group(3) or ""))
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(L) and "-" in L[i + 1][1] and RE_TSEP.match(L[i + 1][1].strip()):
            j = i
            while j < len(L) and L[j][1].strip().startswith("|"):
                j += 1
            out.append(Node("table", ln, rows=[(a, b.strip()) for a, b in L[i:j]]))
            i = j
            continue
        m = RE_SMALL.match(s)
        if m:
            text, i = take_text(L, i, m.group(1))
            out.append(Node("small", ln, text=text))
            continue
        if s.startswith(">"):
            parts = []
            while i < len(L) and L[i][1].strip().startswith(">"):
                parts.append(L[i][1].strip()[1:].strip())
                i += 1
            out.append(Node("quote", ln, text=" ".join(p for p in parts if p)))
            continue
        m = RE_ITEM.match(raw)
        if m:
            numbered = m.group(2)[0].isdigit()
            j = i
            while j < len(L):
                r = L[j][1]
                if not r.strip():
                    # a blank line ends the list unless another item of the same kind follows it
                    nxt = RE_ITEM.match(L[j + 1][1]) if j + 1 < len(L) else None
                    if nxt and nxt.group(2)[0].isdigit() == numbered:
                        j += 1
                        continue
                    break
                if j > i and not RE_ITEM.match(r) and not r.startswith((" ", "\t")) and starts_block(r.strip()):
                    break
                j += 1
            out.append(Node("list", ln, lines=[b for _, b in L[i:j] if b.strip()]))
            i = j
            continue
        text, i = take_text(L, i, s)
        out.append(Node("p", ln, text=text))
    if opener is not None:
        raise DeckError(opener[0], "'::: %s' is never closed with ':::'" % opener[1])
    return out, i


def build_list(lines):
    """Turn list lines into (tag, items). An item is (text, nested list or None)."""
    first = RE_ITEM.match(lines[0])
    base = len(first.group(1).expandtabs(4))
    tag = "ol" if first.group(2)[0].isdigit() else "ul"
    items = []
    for line in lines:
        m = RE_ITEM.match(line)
        indent = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())
        if m and indent <= base + 1:
            items.append([m.group(3).strip(), []])
        elif not items:
            continue
        elif m or items[-1][1]:
            items[-1][1].append(line)
        else:
            items[-1][0] += " " + line.strip()
    return tag, [(t, build_list(sub) if sub else None) for t, sub in items]


def split_cells(row):
    """Split a 'a | b | c' row on pipes. Write \\| for a literal pipe."""
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


# ---------------------------------------------------------------- inline text

_INLINE = re.compile(
    r"\\([\\`*_{}\[\]()#+\-.!|>~=<])"                          # 1 backslash escape
    r"|(`+)(.+?)\2"                                             # 2,3 code
    r"|\*\*(?=\S)(.+?)(?<=\S)\*\*"                              # 4 bold
    r"|(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])"       # 5 italic with *
    r"|(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)"                       # 6 italic with _
    r"|\[([^\]]+)\]\(([^)\s]+)\)"                               # 7,8 link
    r"|(<br\s*/?>)"                                             # 9 line break
)


def esc(s):
    return html.escape(s, quote=True)


def inline(s):
    """Render inline Markdown to HTML. Everything else is escaped."""
    out = []
    pos = 0
    for m in _INLINE.finditer(s):
        out.append(html.escape(s[pos:m.start()], quote=False))
        if m.group(1):
            out.append(html.escape(m.group(1)))
        elif m.group(2):
            out.append("<code>%s</code>" % html.escape(m.group(3)))
        elif m.group(4) is not None:
            out.append("<b>%s</b>" % inline(m.group(4)))
        elif m.group(5) is not None:
            out.append("<em>%s</em>" % inline(m.group(5)))
        elif m.group(6) is not None:
            out.append("<em>%s</em>" % inline(m.group(6)))
        elif m.group(7):
            out.append('<a href="%s">%s</a>' % (esc(m.group(8)), inline(m.group(7))))
        else:
            out.append("<br>")
        pos = m.end()
    out.append(html.escape(s[pos:], quote=False))
    return "".join(out)


def plain(s):
    """Inline Markdown reduced to bare text, for chart labels, tooltips and aria labels."""
    return html.unescape(re.sub(r"<[^>]+>", "", inline(s)))


# ---------------------------------------------------------------- charts

RE_NUM = re.compile(r"^[-+]?(\d[\d,]*)?(\.\d+)?%?$")

CHART_OPTIONS = {
    "bars": ("max", "unit", "decimals", "color", "tip"),
    "rows": ("max", "unit", "decimals", "color"),
    "columns": ("max", "step", "unit", "decimals", "color", "colors", "tip", "x", "axis", "height", "legend"),
    "line": ("max", "step", "unit", "decimals", "tip", "every", "height"),
    "range": ("max", "step", "unit", "decimals", "x"),
    "share": ("colors", "legend"),
}


def to_num(s):
    s = s.strip()
    if not RE_NUM.match(s) or not re.search(r"\d", s):
        return None
    return float(s.rstrip("%").replace(",", ""))


def n(x):
    """Format a coordinate compactly."""
    return ("%.1f" % x).rstrip("0").rstrip(".")


def tick(v):
    return "{:,.0f}".format(v) if abs(v - round(v)) < 1e-9 else "{:,g}".format(v)


def nice_step(top, target=4):
    raw = float(top) / target
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * mag + 1e-12:
            return mult * mag
    return 10 * mag


def even_step(top):
    """A round step that divides `top` exactly into 4, 5, 3 or 6 parts, else the nearest nice step."""
    for parts in (4, 5, 3, 6):
        step = float(top) / parts
        lead = step / 10 ** math.floor(math.log10(step)) if step > 0 else 0
        if any(abs(lead - m) < 1e-9 for m in (1, 2, 2.5, 4, 5)):
            return step
    return nice_step(top)


class Row(object):
    def __init__(self, line, label):
        self.line = line
        self.label = label
        self.raws = []
        self.vals = []
        self.color = None
        self.text = ""
        self.star = False


class Chart(object):
    """One ```chart block: its type, options, optional header row and data rows."""

    def __init__(self, node):
        info = node.info.split()
        self.line = node.line
        self.kind = info[1] if len(info) > 1 else ""
        if self.kind not in CHART_OPTIONS:
            raise DeckError(node.line, "write the chart type after 'chart': one of %s" % ", ".join(sorted(CHART_OPTIONS)))
        self.opts = {}
        self.header = None
        self.rows = []
        for ln, raw in node.body:
            s = raw.strip()
            if not s:
                continue
            if "|" not in s:
                m = re.match(r"^([a-z]+)\s*:\s*(.+)$", s)
                if not m:
                    raise DeckError(ln, "expected 'option: value' or a data row like 'Label | 12'")
                if m.group(1) not in CHART_OPTIONS[self.kind]:
                    raise DeckError(ln, "'%s' is not an option of chart %s (options: %s)" % (
                        m.group(1), self.kind, ", ".join(CHART_OPTIONS[self.kind])))
                self.opts[m.group(1)] = m.group(2).strip()
                continue
            star = bool(re.search(r"(^|\s)\*$", s))
            if star:
                s = s[:-1].rstrip()
            cells = split_cells(s)
            if cells[0] == "" and not self.rows and self.header is None:
                self.header = [c for c in cells[1:]]
                continue
            row = Row(ln, plain(cells[0]))
            row.star = star
            k = 1
            while k < len(cells) and to_num(cells[k]) is not None:
                row.raws.append(cells[k].rstrip("%"))
                row.vals.append(to_num(cells[k]))
                k += 1
            if not row.vals:
                raise DeckError(ln, "this row has no number after its label: write 'Label | 12'")
            for extra in cells[k:]:
                if extra in COLORS and row.color is None and not row.text:
                    row.color = extra
                elif extra:
                    row.text = extra
            self.rows.append(row)
        if not self.rows:
            raise DeckError(node.line, "this chart has no data rows: add lines like 'Label | 12'")

    def num(self, key, default=None):
        if key not in self.opts:
            return default
        v = to_num(self.opts[key])
        if v is None:
            raise DeckError(self.line, "option '%s' must be a number, not '%s'" % (key, self.opts[key]))
        return v

    def color(self, key="color", default="accent"):
        c = self.opts.get(key, default)
        if c not in COLORS:
            raise DeckError(self.line, "'%s' is not a colour (use: %s)" % (c, ", ".join(COLORS)))
        return c

    def series_colors(self, count):
        names = [c.strip() for c in self.opts["colors"].split(",")] if "colors" in self.opts else list(COLORS)
        for c in names:
            if c not in COLORS:
                raise DeckError(self.line, "'%s' is not a colour (use: %s)" % (c, ", ".join(COLORS)))
        if count > len(names):
            raise DeckError(self.line, "%d series but only %d colours: a chart takes at most four series, "
                                       "so fold the smallest into 'Other'" % (count, len(names)))
        return names

    def unit(self):
        u = self.opts.get("unit", "")
        return (" " + u if u[:1].isalnum() else u) if u else ""

    def show(self, raw, val, unit=True):
        """The value as printed on the chart."""
        if "decimals" in self.opts:
            d = int(self.num("decimals"))
            q = Decimal(repr(val)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
            raw = "{:,}".format(q)
        return raw + (self.unit() if unit else "")

    def exact(self, raw):
        """The value as written by the author, for tooltips."""
        return raw + self.unit()

    def scale(self, top, headroom=True):
        if "max" in self.opts:
            mx = self.num("max")
            return mx, self.num("step", even_step(mx))
        step = self.num("step", nice_step(top or 1))
        mx = math.ceil((top or 1) / step - 1e-9) * step
        if headroom and top > 0.93 * mx:
            mx += step
        return mx, step

    def fills(self):
        """Colour of each row: its own, else the chart colour; unmarked rows go muted once any row is marked."""
        base = self.color()
        marked = any(r.star or r.color for r in self.rows)
        return [r.color or (base if (r.star or not marked) else "muted") for r in self.rows]

    def tip_tail(self):
        t = self.opts.get("tip", "")
        return (t if t[:1] in ",.;:" else " " + t) if t else ""


def _text(x, y, cls, s, anchor=None):
    a = ' text-anchor="%s"' % anchor if anchor else ""
    return '<text x="%s" y="%s" class="%s"%s>%s</text>' % (n(x), n(y), cls, a, html.escape(s, quote=False))


def _line(x1, x2, y1, y2, cls):
    return '<line x1="%s" x2="%s" y1="%s" y2="%s" class="%s"/>' % (n(x1), n(x2), n(y1), n(y2), cls)


def _hit(x, y, w, h, tip):
    return '<rect x="%s" y="%s" width="%s" height="%s" class="hit" data-tip="%s"/>' % (n(x), n(y), n(w), n(h), esc(tip))


def _round_top(x, y, w, h, r=4):
    r = min(r, w / 2.0, h)
    return "M%s %sV%sQ%s %s %s %sH%sQ%s %s %s %sV%sZ" % tuple(
        n(v) for v in (x, y + h, y + r, x, y, x + r, y, x + w - r, x + w, y, x + w, y + r, y + h))


def _round_right(x, y, w, h, r=4):
    r = min(r, h / 2.0, w)
    return "M%s %sH%sQ%s %s %s %sV%sQ%s %s %s %sH%sZ" % tuple(
        n(v) for v in (x, y, x + w - r, x + w, y, x + w, y + r, y + h - r, x + w, y + h, x + w - r, y + h, x))


def _svg(W, H, parts, label):
    return '<svg viewBox="0 0 %s %s" role="img" aria-label="%s">%s</svg>' % (n(W), n(H), esc(label), "".join(parts))


def _tip(label, lines):
    return "<b>%s</b><br>%s" % (html.escape(label), "<br>".join(html.escape(x) for x in lines if x))


def _legend(pairs):
    return '<div class="legend">%s</div>' % "".join(
        '<span style="--sw:%s">%s</span>' % (COLORS[c], inline(name)) for c, name in pairs)


def chart_bars(c, W, label):
    """Horizontal bars: label above each bar, value at its end."""
    rows = c.rows
    big = len(rows) <= 4
    row_h, bar_h, bar_y, lab_y, val_y = (46, 14, 20, 13, 32) if big else (34, 10, 17, 12, 26)
    left, top = 4, 6
    shown = [c.show(r.raws[0], r.vals[0]) for r in rows]
    mx = c.num("max", max(r.vals[0] for r in rows)) or 1
    plot = W - left - 14 - 7.3 * max(len(x) for x in shown)
    parts = []
    for i, (r, fill) in enumerate(zip(rows, c.fills())):
        y = top + i * row_h
        w = max(0.0, min(1.0, r.vals[0] / mx)) * plot
        parts.append(_text(left, y + lab_y, "lbl", r.label))
        if w > 0:
            parts.append('<path d="%s" class="%s"/>' % (_round_right(left, y + bar_y, w, bar_h), FILL[fill]))
        parts.append(_text(left + w + 8, y + val_y, "val", shown[i]))
        parts.append(_hit(0, y, W, row_h, _tip(r.label, [c.exact(r.raws[0]) + c.tip_tail(), plain(r.text)])))
    return _svg(W, top + row_h * len(rows) + (0 if big else 4), parts, label)


def chart_rows(c, W, label):
    """HTML rows: label on the left, bar in the middle, value on the right."""
    shown = [c.show(r.raws[0], r.vals[0]) for r in c.rows]
    mx = c.num("max", max(r.vals[0] for r in c.rows)) or 1
    out = ['<div class="funnel" style="--nw:%dpx" role="img" aria-label="%s">' % (
        max(40, 9 * max(len(x) for x in shown) + 14), esc(label))]
    for r, fill, val in zip(c.rows, c.fills(), shown):
        sub = "<small>%s</small>" % inline(r.text) if r.text else ""
        out.append('<div class="frow"><div class="k">%s%s</div><div class="bar" style="width:%s%%;background:%s"></div>'
                   '<div class="n num">%s</div></div>' % (
                       html.escape(r.label, quote=False), sub, n(100 * max(0.0, min(1.0, r.vals[0] / mx))),
                       COLORS[fill], html.escape(val)))
    out.append("</div>")
    return "".join(out)


def chart_columns(c, W, label):
    """Vertical bars. Several values per row are stacked and need a header row naming the series."""
    rows = c.rows
    series = max(len(r.vals) for r in rows)
    stacked = series > 1
    if stacked and (not c.header or len(c.header) < series):
        raise DeckError(c.line, "rows with several values are stacked, so name the series in a header row first: "
                                "'| First | Second'")
    cols = c.series_colors(series) if stacked else None
    fills = None if stacked else c.fills()
    mx, step = c.scale(max(sum(r.vals) for r in rows))
    axis = c.opts.get("axis", "on") != "off"
    x_cap = c.opts.get("x")
    ticks = []
    if axis:
        H = int(c.num("height", 220))
        v = 0.0
        while v <= mx + 1e-9:
            ticks.append((v, tick(v) + (c.unit() if not c.unit().startswith(" ") else "")))
            v += step
        left, right, top, bottom = 14 + 6.7 * max(len(t) for _, t in ticks), 12, 18, 44 if x_cap else 28
    else:
        H = int(c.num("height", 130))
        left, right, top, bottom = 0, 0, 20, 22
    pw, ph = W - left - right, H - top - bottom
    slot = pw / float(len(rows))
    bw = min(34.0 if len(rows) <= 4 else 26.0, slot * 0.5)
    parts = []
    for v, t in ticks:
        y = top + ph - v / mx * ph
        parts.append(_line(left, W - right, y, y, "base" if v == 0 else "grid"))
        parts.append(_text(left - 8, y + 4, "ax", t, "end"))
    if not axis:
        parts.append(_line(0, W, top + ph, top + ph, "base"))
    for i, r in enumerate(rows):
        x = left + slot * i + (slot - bw) / 2
        y = top + ph
        segs = [(k, v) for k, v in enumerate(r.vals) if v > 0]
        for j, (k, v) in enumerate(segs):
            h = v / mx * ph
            y -= h
            cls = FILL[cols[k]] if stacked else FILL[fills[i]]
            if j == len(segs) - 1:
                parts.append('<path d="%s" class="%s"/>' % (_round_top(x, y, bw, h), cls))
            else:
                parts.append('<rect x="%s" y="%s" width="%s" height="%s" class="%s"/>' % (n(x), n(y), n(bw), n(h), cls))
                y -= 2
        total = sum(r.vals)
        shown = plain(r.text) if r.text else (tick(total) + c.unit() if stacked else c.show(r.raws[0], r.vals[0]))
        parts.append(_text(x + bw / 2, y - 6, "val", shown, "middle"))
        parts.append(_text(x + bw / 2, top + ph + (18 if axis else 15), "lbl" if axis else "cap", r.label, "middle"))
        if stacked:
            lines = ["%s %s" % (plain(c.header[k]), c.exact(r.raws[k])) for k in range(len(r.vals))]
        else:
            lines = [c.exact(r.raws[0]) + c.tip_tail()]
        parts.append(_hit(left + slot * i, top, slot, ph + bottom, _tip(r.label, lines)))
    if axis and x_cap:
        parts.append(_text(W - right, top + ph + 36, "ax", x_cap, "end"))
    out = _svg(W, H, parts, label)
    if stacked and c.opts.get("legend", "on") != "off":
        out += _legend(zip(cols, c.header[:series]))
    return out


def chart_line(c, W, label):
    """One line over ordered rows. Starred rows get a dot and a value; with no star, the last row does."""
    rows = c.rows
    H = int(c.num("height", 240))
    mx, step = c.scale(max(r.vals[0] for r in rows))
    ticks = []
    v = 0.0
    while v <= mx + 1e-9:
        ticks.append((v, tick(v) + (c.unit() if not c.unit().startswith(" ") else "")))
        v += step
    count = len(rows)
    marks = [i for i, r in enumerate(rows) if r.star] or [count - 1]
    last = c.show(rows[-1].raws[0], rows[-1].vals[0]) if count - 1 in marks else ""
    left, right, top, bottom = 14 + 6.7 * max(len(t) for _, t in ticks), 16 + 7.4 * len(last), 16, 34
    pw, ph = W - left - right, H - top - bottom

    def X(i):
        return left + pw * i / float(max(1, count - 1))

    def Y(v):
        return top + ph - v / mx * ph

    parts = []
    for v, t in ticks:
        parts.append(_line(left, W - right, Y(v), Y(v), "base" if v == 0 else "grid"))
        parts.append(_text(left - 8, Y(v) + 4, "ax", t, "end"))
    parts.append('<path d="%s" class="ln"/>' % "".join(
        ("L" if i else "M") + n(X(i)) + " " + n(Y(r.vals[0])) for i, r in enumerate(rows)))
    every = int(c.num("every", max(1, math.ceil(count / 6.0))))
    for i, r in enumerate(rows):
        if i % every == 0:
            parts.append(_text(X(i), top + ph + 18, "ax", r.label, "middle"))
        if i in marks:
            shown = c.show(r.raws[0], r.vals[0])
            parts.append('<circle cx="%s" cy="%s" r="5" class="dot"/>' % (n(X(i)), n(Y(r.vals[0]))))
            if i == count - 1:
                parts.append(_text(X(i) + 9, Y(r.vals[0]) + 4, "val", shown))
            else:
                parts.append(_text(X(i), Y(r.vals[0]) - 10, "val", shown, "middle"))
    w = pw / float(max(1, count - 1))
    for i, r in enumerate(rows):
        parts.append(_hit(X(i) - w / 2, top, w, ph + bottom, _tip(r.label, [c.exact(r.raws[0]) + c.tip_tail()])))
    return _svg(W, H, parts, label)


def chart_range(c, W, label):
    """One row per item with a dot for each value and a line from the lowest to the highest."""
    rows = c.rows
    left, right, top, bottom, row_h = 12, 22, 10, 30, 62
    H = top + row_h * len(rows) + bottom
    pw = W - left - right
    mx, step = c.scale(max(max(r.vals) for r in rows), headroom=False)

    def X(v):
        return left + v / mx * pw

    parts = []
    v = 0.0
    while v <= mx + 1e-9:
        parts.append(_line(X(v), X(v), top, H - bottom, "base" if v == 0 else "grid"))
        parts.append(_text(X(v), H - bottom + 16, "ax", tick(v), "middle"))
        v += step
    if "x" in c.opts:
        parts.append(_text(W - right, H - 2, "ax", c.opts["x"], "end"))
    names = c.header or []
    for i, r in enumerate(rows):
        y0 = top + i * row_h
        y = y0 + row_h * 0.62
        parts.append(_text(left + 6, y0 + 16, "lblb", r.label))
        parts.append(_line(X(min(r.vals)), X(max(r.vals)), y, y, "rng"))
        for k, v in enumerate(r.vals):
            parts.append('<circle cx="%s" cy="%s" r="5" class="pdot"/>' % (n(X(v)), n(y)))
            parts.append(_text(X(v), y + 18 if k == 0 else y - 10, "val", c.show(r.raws[k], v, unit=False), "middle"))
        lines = [((plain(names[k]) + " ") if k < len(names) else "") + c.exact(r.raws[k]) for k in range(len(r.vals))]
        parts.append(_hit(0, y0, W, row_h, _tip(r.label, lines)))
    return _svg(W, H, parts, label)


def chart_share(c, W, label):
    """One bar per row, split into each series' share of the row total. Needs a header row."""
    rows = c.rows
    series = max(len(r.vals) for r in rows)
    if not c.header or len(c.header) < series:
        raise DeckError(c.line, "a share chart needs a header row naming the series first: '| First | Second'")
    cols = c.series_colors(series)
    left, top, row_h = 4, 4, 70
    pw = W - 2 * left
    parts = []
    for i, r in enumerate(rows):
        y0 = top + i * row_h
        total = sum(r.vals) or 1.0
        x = left
        parts.append(_text(left, y0 + 16, "lblb", r.label))
        for k, v in enumerate(r.vals):
            w = v / total * pw
            if w <= 0:
                continue
            gap = 1 if k else 0
            parts.append('<rect x="%s" y="%s" width="%s" height="16" rx="3" class="%s"/>' % (
                n(x + gap), n(y0 + 24), n(max(0.0, w - gap - 1)), FILL[cols[k]]))
            x += w
        pct = ["%s %d%%" % (plain(c.header[k]), int(round(v / total * 100))) for k, v in enumerate(r.vals)]
        cap = plain(r.text) if r.text else " · ".join(p for p, v in zip(pct, r.vals) if v > 0)
        parts.append(_text(left, y0 + 58, "cap", cap))
        parts.append(_hit(0, y0, W, row_h, _tip(r.label, pct)))
    out = _svg(W, top + row_h * len(rows) - 6, parts, label)
    if c.opts.get("legend", "on") != "off":
        out += _legend(zip(cols, c.header[:series]))
    return out


CHART_RENDER = {"bars": chart_bars, "rows": chart_rows, "columns": chart_columns, "line": chart_line,
                "range": chart_range, "share": chart_share}


# ---------------------------------------------------------------- renderer

SETTINGS = ("title", "lang", "theme", "webfonts")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
        ".webp": "image/webp", ".avif": "image/avif"}


class Ctx(object):
    """Where a block is being rendered: the width available to it and whether it sits in a card."""

    def __init__(self, width=1040.0, card=False):
        self.width = width
        self.card = card


class Deck(object):
    def __init__(self, text, base_dir="."):
        self.base = base_dir
        self.images = 0
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.meta, start = self.front_matter(lines)
        numbered = [(k + 1, line) for k, line in enumerate(lines)][start:]
        nodes, _ = parse_blocks(numbered)
        self.slides = [[]]
        for nd in nodes:
            if nd.kind == "break":
                self.slides.append([])
            else:
                self.slides[-1].append(nd)
        self.slides = [s for s in self.slides if s]
        if not self.slides:
            raise DeckError(1, "the file has no slides")
        self.title = self.meta.get("title") or self.first_title() or "Deck"

    @staticmethod
    def front_matter(lines):
        """Read 'key: value' lines between two '---' lines at the very top of the file."""
        if not lines or lines[0].strip() != "---":
            return {}, 0
        meta = {}
        for k in range(1, len(lines)):
            s = lines[k].strip()
            if s == "---":
                for key, (line, _) in meta.items():
                    if key not in SETTINGS:
                        raise DeckError(line, "'%s' is not a setting (settings: %s)" % (key, ", ".join(SETTINGS)))
                return dict((key, v) for key, (_, v) in meta.items()), k + 1
            if not s:
                continue
            m = re.match(r"^([A-Za-z][\w-]*)\s*:\s*(.*)$", s)
            if not m:
                return {}, 0
            meta[m.group(1).lower()] = (k + 1, m.group(2).strip().strip("\"'"))
        return {}, 0

    def first_title(self):
        for nd in self.slides[0]:
            if nd.kind == "h" and nd.level <= 2:
                return plain(nd.text)
        return ""

    # ---- slides

    def slide(self, nodes):
        i = 0
        eyebrow = title = None
        lead = []
        if nodes[i].kind == "h" and nodes[i].level == 6:
            eyebrow = nodes[i]
            i += 1
        if i < len(nodes) and nodes[i].kind == "h" and nodes[i].level <= 2:
            title = nodes[i]
            i += 1
            while i < len(nodes) and nodes[i].kind == "p":
                lead.append(nodes[i])
                i += 1
        body = nodes[i:]
        hero = title is not None and title.level == 1
        if hero:
            nav = self.title
        elif eyebrow is not None:
            nav = re.sub(r"^\d+\s*·\s*", "", plain(eyebrow.text))
        else:
            nav = plain(title.text) if title is not None else self.title
        head = []
        if eyebrow is not None:
            head.append('<p class="eyebrow">%s</p>' % inline(eyebrow.text))
        if hero:
            head.append("<h1>%s</h1>" % inline(title.text))
            head += ['<p class="lede">%s</p>' % inline(p.text) for p in lead]
            right = '<div class="hero-pair">%s</div>' % self.flow(body, Ctx(440.0)) if body else ""
            inner = '<div class="hero%s"><div>%s</div>%s</div>' % ("" if body else " solo", "".join(head), right)
        else:
            if title is not None:
                head.append("<h2>%s</h2>" % inline(title.text))
            head += ["<p>%s</p>" % inline(p.text) for p in lead]
            inner = ('<div class="sec-head">%s</div>' % "".join(head)) if head else ""
            if body:
                inner += '<div class="flow">%s</div>' % self.flow(body, Ctx())
        return '<section data-nav="%s">\n%s\n</section>' % (esc(nav), inner)

    # ---- block sequences

    def flow(self, nodes, ctx):
        out = []
        i = 0
        while i < len(nodes):
            nd = nodes[i]
            if nd.kind == "h" and nd.level in (4, 5):
                # a figure: title, optional subtitle, then the block it describes
                parts = ['<div class="fig-title">%s</div>' % inline(nd.text)]
                i += 1
                if i < len(nodes) and nodes[i].kind == "small":
                    parts.append('<div class="fig-sub">%s</div>' % inline(nodes[i].text))
                    i += 1
                if i < len(nodes) and nodes[i].kind in ("fence", "box", "table", "img", "flow"):
                    parts.append(self.block(nodes[i], ctx, plain(nd.text)))
                    i += 1
                out.append('<div class="fig">%s</div>' % "".join(parts))
            elif nd.kind == "quote":
                group = []
                while i < len(nodes) and nodes[i].kind == "quote":
                    group.append(nodes[i])
                    i += 1
                out.append(self.quotes(group))
            elif nd.kind == "rule" and ctx.card:
                out.append('<div class="foot">%s</div>' % self.flow(nodes[i + 1:], ctx))
                break
            elif nd.kind == "sep":
                raise DeckError(nd.line, "'+++' separates cells, and only works directly inside '::: cols' or '::: cards'")
            else:
                out.append(self.block(nd, ctx, ""))
                i += 1
        return "\n".join(out)

    def block(self, nd, ctx, label):
        k = nd.kind
        if k == "p":
            return "<p>%s</p>" % inline(nd.text)
        if k == "small":
            return '<p class="note">%s</p>' % inline(nd.text)
        if k == "h":
            if nd.level == 6:
                return '<p class="eyebrow">%s</p>' % inline(nd.text)
            return "<h%d>%s</h%d>" % (max(2, nd.level), inline(nd.text), max(2, nd.level))
        if k == "rule":
            return "<hr>"
        if k == "list":
            return self.list(build_list(nd.lines))
        if k == "table":
            return self.table(nd)
        if k == "img":
            return self.image(nd)
        if k == "fence":
            return self.fence(nd, ctx, label)
        if k == "box":
            return getattr(self, "box_" + nd.name)(nd, ctx)
        if k == "flow":
            return getattr(self, "flow_" + nd.name)(nd, ctx)
        raise DeckError(nd.line, "unexpected %s here" % k)

    def list(self, parsed):
        tag, items = parsed
        return "<%s>%s</%s>" % (tag, "".join(
            "<li>%s%s</li>" % (inline(t), self.list(sub) if sub else "") for t, sub in items), tag)

    def quotes(self, group):
        out = []
        for q in group:
            m = re.match(r"^(.*)\s(?:--|—)\s+(.+)$", q.text)
            text, who = (m.group(1), m.group(2)) if m else (q.text, "")
            who = '<span class="who">%s</span>' % inline(who) if who else ""
            out.append('<blockquote class="q">%s%s</blockquote>' % (inline(text), who))
        return '<div class="quotes" style="--n:%d">%s</div>' % (min(3, len(out)), "".join(out))

    def table(self, nd):
        def cells(row):
            star = re.search(r"\|\s*\*$", row)
            if star:
                row = row[:star.start() + 1]
            if row.startswith("|"):
                row = row[1:]
            if row.endswith("|") and not row.endswith("\\|"):
                row = row[:-1]
            return split_cells(row), bool(star)

        head, _ = cells(nd.rows[0][1])
        align = []
        for c in cells(nd.rows[1][1])[0]:
            align.append(' class="c"' if c.startswith(":") and c.endswith(":") else ' class="r"' if c.endswith(":") else "")
        align += [""] * len(head)
        out = ["<thead><tr>%s</tr></thead><tbody>" % "".join(
            "<th%s>%s</th>" % (align[k], inline(c)) for k, c in enumerate(head))]
        for ln, row in nd.rows[2:]:
            vals, star = cells(row)
            if len(vals) > len(head):
                raise DeckError(ln, "this row has %d cells but the header has %d" % (len(vals), len(head)))
            vals += [""] * (len(head) - len(vals))
            out.append("<tr%s>%s</tr>" % (' class="hl"' if star else "", "".join(
                "<td%s>%s</td>" % (align[k], inline(c)) for k, c in enumerate(vals))))
        return '<div class="tscroll"><table>%s</tbody></table></div>' % "".join(out)

    def image(self, nd):
        cap = "<figcaption>%s</figcaption>" % inline(nd.cap) if nd.cap else ""
        if re.match(r"^(https?:|data:)", nd.src):
            return '<figure class="img"><img src="%s" alt="%s">%s</figure>' % (esc(nd.src), esc(nd.alt), cap)
        path = os.path.join(self.base, nd.src)
        if not os.path.isfile(path):
            raise DeckError(nd.line, "image not found: %s (paths are relative to the Markdown file)" % nd.src)
        stem, ext = os.path.splitext(path)
        ext = ext.lower()
        self.images += 1
        if ext == ".svg":
            return '<figure class="img" role="img" aria-label="%s">%s%s</figure>' % (esc(nd.alt), self.svg_file(path), cap)
        if ext not in MIME:
            raise DeckError(nd.line, "unsupported image type '%s' (use: svg, %s)" % (
                ext, ", ".join(sorted(e[1:] for e in MIME))))
        dark = stem + ".dark" + ext
        if os.path.isfile(dark):
            self.images += 1
            return '<figure class="img duo"><img class="lt" src="%s" alt="%s"><img class="dk" src="%s" alt="%s">%s</figure>' % (
                self.data_uri(path, ext), esc(nd.alt), self.data_uri(dark, ext), esc(nd.alt), cap)
        return '<figure class="img"><img src="%s" alt="%s">%s</figure>' % (self.data_uri(path, ext), esc(nd.alt), cap)

    @staticmethod
    def data_uri(path, ext):
        with open(path, "rb") as f:
            return "data:%s;base64,%s" % (MIME[ext], base64.b64encode(f.read()).decode("ascii"))

    @staticmethod
    def svg_file(path):
        """Inline an SVG file so it can use the deck's fonts and CSS variables."""
        with open(path, encoding="utf-8") as f:
            s = f.read()
        s = re.sub(r"<\?xml.*?\?>|<!DOCTYPE.*?>|<!--.*?-->", "", s, flags=re.S).strip()
        m = re.match(r"<svg\b[^>]*>", s)
        if m and "viewBox" not in m.group(0):
            w = re.search(r'\bwidth="([\d.]+)', m.group(0))
            h = re.search(r'\bheight="([\d.]+)', m.group(0))
            if w and h:
                s = s[:4] + ' viewBox="0 0 %s %s"' % (w.group(1), h.group(1)) + s[4:]
        return s

    def fence(self, nd, ctx, label):
        info = nd.info.split()
        kind = info[0].lower() if info else ""
        if kind == "chart":
            c = Chart(nd)
            width = round(min(1100.0, max(220.0, ctx.width)))
            summary = "; ".join("%s %s" % (r.label, " / ".join(r.raws)) for r in c.rows)
            return CHART_RENDER[c.kind](c, width, ((label + ". ") if label else "") + summary)
        if kind == "calc":
            out = []
            for _, raw in nd.body:
                if raw.strip():
                    out.append('<div class="fx%s">%s</div>' % (" sub" if raw[:1] in (" ", "\t") else "", inline(raw.strip())))
            return '<div class="fxs">%s</div>' % "".join(out)
        if kind == "html":
            return "\n".join(raw for _, raw in nd.body)
        return "<pre><code>%s</code></pre>" % html.escape("\n".join(raw for _, raw in nd.body), quote=False)

    # ---- row containers

    @staticmethod
    def args(nd, allowed):
        for a in nd.args:
            if a not in allowed:
                raise DeckError(nd.line, "'%s' is not an option of '::: %s' (options: %s)" % (a, nd.name, ", ".join(allowed)))
        return nd.args

    @staticmethod
    def cells(nd, lo, hi, shape):
        rows = []
        for ln, row in nd.rows:
            c = split_cells(row)
            if not lo <= len(c) <= hi:
                raise DeckError(ln, "a row of '::: %s' is written as: %s" % (nd.name, shape))
            rows.append(c)
        if not rows:
            raise DeckError(nd.line, "'::: %s' is empty; each row is written as: %s" % (nd.name, shape))
        return rows

    def box_tiles(self, nd, ctx):
        args = self.args(nd, ("accent", "warm", "small"))
        rows = self.cells(nd, 2, 3, "value | label   or   value | unit | label")
        if "small" in args:
            return '<div class="basis" style="--n:%d">%s</div>' % (min(4, len(rows)), "".join(
                '<div><b class="num">%s</b><span>%s</span></div>' % (inline(" ".join(c[:-1])), inline(c[-1])) for c in rows))
        tone = "".join(" " + a for a in args[:1])
        out = []
        for c in rows:
            unit = "<small>%s</small>" % inline(c[1]) if len(c) == 3 and c[1] else ""
            out.append('<div class="tile%s"><div class="v num">%s%s</div><div class="l">%s</div></div>' % (
                tone, inline(c[0]), unit, inline(c[-1])))
        return '<div class="tiles" style="--n:%d">%s</div>' % (min(4, len(rows)), "".join(out))

    def box_stat(self, nd, ctx):
        args = self.args(nd, ("accent", "warm"))
        out = []
        for c in self.cells(nd, 1, 3, "value | unit | caption   (unit and caption are optional)"):
            c += [""] * (3 - len(c))
            unit = "<small>%s</small>" % inline(c[1]) if c[1] else ""
            if ctx.card:
                out.append('<div class="sz num">%s%s</div>%s' % (inline(c[0]), unit, "<p>%s</p>" % inline(c[2]) if c[2] else ""))
            else:
                out.append('<div class="stat%s"><div class="big num">%s%s</div>%s</div>' % (
                    " warm" if "warm" in args else "", inline(c[0]), unit,
                    '<p class="cap">%s</p>' % inline(c[2]) if c[2] else ""))
        return "".join(out)

    def box_facts(self, nd, ctx):
        self.args(nd, ())
        rows = self.cells(nd, 2, 2, "value | text")
        return '<div class="facts" style="--n:%d">%s</div>' % (min(4, len(rows)), "".join(
            '<div><b class="num">%s</b>%s</div>' % (inline(c[0]), inline(c[1])) for c in rows))

    def box_summary(self, nd, ctx):
        self.args(nd, ())
        return '<div class="summary">%s</div>' % "".join(
            '<div><span class="eyebrow">%s</span><p>%s</p></div>' % (inline(c[0]), inline(c[1]))
            for c in self.cells(nd, 2, 2, "label | text"))

    def box_steps(self, nd, ctx):
        self.args(nd, ())
        out = []
        for ln, row in nd.rows:
            if row.startswith(">"):
                out.append('<div class="manual">%s</div>' % inline(row[1:].strip()))
                continue
            c = split_cells(row)
            if not 1 <= len(c) <= 3:
                raise DeckError(ln, "a step is written as: title | detail | value   (a line starting with > joins two steps)")
            c += [""] * (3 - len(c))
            out.append('<div class="step"><div><b>%s</b>%s</div>%s</div>' % (
                inline(c[0]), "<small>%s</small>" % inline(c[1]) if c[1] else "",
                '<div class="t num">%s</div>' % inline(c[2]) if c[2] else ""))
        return '<div class="chain">%s</div>' % "".join(out)

    def box_legend(self, nd, ctx):
        self.args(nd, ())
        pairs = []
        for ln, row in nd.rows:
            c = split_cells(row)
            if len(c) != 2 or c[0] not in COLORS:
                raise DeckError(ln, "a legend row is written as: colour | label   (colours: %s)" % ", ".join(COLORS))
            pairs.append((c[0], c[1]))
        return _legend(pairs)

    # ---- containers that hold other blocks

    @staticmethod
    def split(kids):
        cells = [[]]
        for k in kids:
            if k.kind == "sep":
                cells.append([])
            else:
                cells[-1].append(k)
        return [c for c in cells if c]

    def flow_card(self, nd, ctx):
        args = self.args(nd, ("accent", "warm"))
        return '<div class="card%s">%s</div>' % (
            " " + args[0] if args else "", self.flow(nd.kids, Ctx(ctx.width - 44, card=True)))

    def flow_cols(self, nd, ctx):
        cells = self.split(nd.kids)
        if not cells:
            raise DeckError(nd.line, "'::: cols' is empty")
        count = len(cells)
        for a in nd.args:
            if not a.isdigit() or not 1 <= int(a) <= 4:
                raise DeckError(nd.line, "'::: cols' takes one optional number of columns, 1 to 4")
            count = int(a)
        count = min(4, count)
        gap = 28 if count <= 2 else 16
        inner = Ctx((ctx.width - gap * (count - 1)) / count, ctx.card)
        return '<div class="cols c%d" style="--n:%d">%s</div>' % (count, count, "".join(
            '<div class="cell">%s</div>' % self.flow(c, inner) for c in cells))

    def flow_cards(self, nd, ctx):
        cells = self.split(nd.kids)
        if not cells:
            raise DeckError(nd.line, "'::: cards' is empty")
        count = min(4, len(cells))
        tones = []
        for a in nd.args:
            if a.isdigit() and 1 <= int(a) <= 4:
                count = int(a)
            elif a in ("accent", "warm", "plain"):
                tones.append("" if a == "plain" else " " + a)
            else:
                raise DeckError(nd.line, "'::: cards' takes a number of columns and one colour per card "
                                         "(accent, warm or plain), not '%s'" % a)
        tones += [""] * len(cells)
        inner = Ctx((ctx.width - 16 * (count - 1)) / count - 44, card=True)
        return '<div class="cards" style="--n:%d">%s</div>' % (count, "".join(
            '<div class="card%s">%s</div>' % (tones[k], self.flow(c, inner)) for k, c in enumerate(cells)))

    # ---- page

    def html(self, fragment=False):
        slides = "\n\n".join(self.slide(s) for s in self.slides)
        fonts = "" if self.meta.get("webfonts", "on").lower() in ("off", "no", "false") else FONTS + "\n"
        body = ('<div class="wrap">\n%s\n</div>\n%s\n<script>\n%s\n</script>' % (slides, NAV, JS.strip()))
        style = "<style>\n%s\n</style>" % CSS.strip().replace("__DARK__", DARK)
        title = "<title>%s</title>" % html.escape(self.title)
        if fragment:
            return "%s\n%s\n%s%s\n\n%s\n" % (title, '<meta name="claude:viewport-fit-sides" content="cover">', fonts, style, body)
        theme = self.meta.get("theme", "auto").lower()
        theme = ' data-theme="%s"' % theme if theme in ("light", "dark") else ""
        return ('<!doctype html>\n<html lang="%s"%s>\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n%s\n%s%s\n</head>\n<body>\n%s\n</body>\n</html>\n'
                % (esc(self.meta.get("lang", "en")), theme, title, fonts, style, body))


# ---------------------------------------------------------------- page template

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700'
         '&family=IBM+Plex+Mono:wght@400;500&display=swap">')

NAV = """<nav class="deckbar" aria-label="Presentation controls">
  <div class="prog" id="dkprog"></div>
  <button class="mode" id="dkmode" type="button">Scroll view</button>
  <div class="where" id="dkwhere" aria-live="polite"></div>
  <button class="back" id="dkback" type="button" aria-label="Previous slide">← Back</button>
  <button class="next" id="dknext" type="button" aria-label="Next slide">Next →</button>
</nav>
<div class="tip" id="tip"></div>"""

DARK = ("--bg:#0f1115;--surface:#181b21;--ink:#eef0f3;--ink-2:#b8bec8;--muted:#8a919c;--hair:#272b33;--axis:#3a404a;"
        "--accent:#3987e5;--accent-soft:#1a2c47;--warm:#d95926;--warm-soft:#3d2316;--bar-muted:#3a414d;color-scheme:dark")

# Colours and fonts are the custom properties in :root. Blue (--accent) and orange (--warm) are the two data colours.
CSS = r"""
:root{
  --bg:#f7f8fa;--surface:#ffffff;--ink:#0e1420;--ink-2:#4b5563;--muted:#8a919c;--hair:#e3e6eb;--axis:#c6ccd4;
  --accent:#2a78d6;--accent-soft:#dbe8f9;--warm:#eb6834;--warm-soft:#fbe3d8;--bar-muted:#c9d2de;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --maxw:1040px;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){__DARK__}
  :root:not([data-theme="light"]) .img.duo .lt{display:none}
  :root:not([data-theme="light"]) .img.duo .dk{display:block}
}
:root[data-theme="dark"]{__DARK__}
:root[data-theme="dark"] .img.duo .lt{display:none}
:root[data-theme="dark"] .img.duo .dk{display:block}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.55;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:0 96px}
.wrap{max-width:var(--maxw);margin:0 auto}
h1,h2,h3{text-wrap:balance;margin:0;line-height:1.15}
h1{font-size:clamp(34px,5.2vw,56px);font-weight:600;letter-spacing:-.02em}
h2{font-size:clamp(24px,3vw,32px);font-weight:600;letter-spacing:-.015em}
h3{font-size:17px;font-weight:600}
p{margin:0}
a{color:var(--accent)}
hr{border:0;border-top:1px solid var(--hair);margin:0;width:100%}
ul,ol{margin:0;padding-left:20px;display:grid;gap:6px;color:var(--ink-2)}
li::marker{color:var(--muted)}
li>ul,li>ol{margin-top:6px}
code{font-family:var(--mono);font-size:.9em;background:var(--hair);padding:1px 5px;border-radius:4px}
pre{margin:0;background:var(--surface);border:1px solid var(--hair);border-radius:8px;padding:14px 16px;overflow-x:auto;
  font-family:var(--mono);font-size:13px;line-height:1.5}
pre code{background:none;padding:0;font-size:inherit}
.lede{font-size:clamp(17px,1.6vw,20px);color:var(--ink-2);max-width:60ch}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.note{font-size:13px;color:var(--muted);max-width:70ch}
.note b{color:var(--ink-2);font-weight:600}
.flow:not(:has(> :not(.note)))>.note{max-width:96ch}
.num{font-variant-numeric:tabular-nums}

/* slides */
section{padding-block:56px;border-top:1px solid var(--hair)}
section:first-of-type{border-top:0;padding-top:72px}
.sec-head{display:grid;gap:10px;max-width:68ch;margin-bottom:28px}
.sec-head:last-child{margin-bottom:0}
.sec-head p{color:var(--ink-2)}
.flow,.cell{display:grid;gap:24px;align-content:start;min-width:0}
.cell{gap:18px}
.flow>*,.cell>*{min-width:0}
.flow>.note,.cell>.note{margin-top:-8px}
.flow>.note+.note{margin-top:-14px}
.flow>.eyebrow{margin-bottom:-12px}
.cell>.legend{margin-top:-10px}

/* opening slide */
.hero{display:grid;grid-template-columns:1.1fr .9fr;gap:40px;align-items:end}
.hero.solo{grid-template-columns:1fr}
.hero h1{margin-top:14px}
.hero .lede{margin-top:18px}
.hero-pair{display:grid;gap:18px;min-width:0}
.stat{display:grid;gap:4px;border-left:3px solid var(--accent);padding-left:22px}
.stat.warm{border-left-color:var(--warm)}
.stat .big{font-size:clamp(44px,6vw,68px);font-weight:600;line-height:1;letter-spacing:-.03em}
.stat .big small{font-size:.26em;font-weight:500;color:var(--ink-2);letter-spacing:0;margin-left:6px}
.stat .cap{color:var(--ink-2);font-size:15px;max-width:40ch}

/* columns and cards */
.cols{display:grid;grid-template-columns:repeat(var(--n,2),minmax(0,1fr));gap:28px;align-items:start}
.cols.c3,.cols.c4{gap:16px}
.cols .cols{gap:16px 20px;align-items:end}
.cols .cols .fig-title{font-size:13px}
.cards{display:grid;grid-template-columns:repeat(var(--n,3),minmax(0,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:22px;min-width:0;
  display:grid;gap:12px;align-content:start}
.card>*{min-width:0}
.card.accent{border-top:3px solid var(--accent)}
.card.warm{border-top:3px solid var(--warm)}
.card ul,.card ol{padding-left:18px;font-size:15px}
.card p:not([class]){font-size:14.5px;color:var(--ink-2)}
.card .eyebrow{color:var(--accent);letter-spacing:.08em;margin-bottom:-4px}
.card .sz{font-size:30px;font-weight:600;letter-spacing:-.02em;line-height:1.2}
.card .sz small{font-size:14px;font-weight:500;color:var(--ink-2);letter-spacing:0;margin-left:6px}
.card .foot{margin-top:2px;padding-top:12px;border-top:1px solid var(--hair);display:grid;gap:8px}
.card .foot,.card .foot p:not([class]){font-size:13.5px;color:var(--ink-2)}
.card .foot b{color:var(--ink);font-weight:600}
.card .facts{margin-top:4px}

/* figures: tiles, facts, summary, steps, formulas */
.tiles{display:grid;grid-template-columns:repeat(var(--n,4),minmax(0,1fr));gap:14px}
.tile{background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:18px 18px 16px;display:grid;gap:4px;
  min-width:0}
.tile .v{font-size:34px;font-weight:600;letter-spacing:-.02em;line-height:1.05}
.tile .v small{font-size:15px;font-weight:500;color:var(--ink-2);letter-spacing:0;margin-left:4px}
.tile .l{font-size:13.5px;color:var(--ink-2)}
.tile.warm{border-top:3px solid var(--warm)}
.tile.accent{border-top:3px solid var(--accent)}
.basis{display:grid;grid-template-columns:repeat(var(--n,4),minmax(0,1fr));gap:14px}
.basis>div{border:1px solid var(--hair);border-radius:8px;background:var(--surface);padding:12px 14px;display:grid;gap:2px;
  min-width:0}
.basis b{font-size:19px;font-weight:600}
.basis span{font-size:13px;color:var(--ink-2)}
.facts{display:grid;grid-template-columns:repeat(var(--n,3),minmax(0,1fr));gap:14px}
.facts div{border-top:1px solid var(--hair);padding-top:10px;font-size:14px;color:var(--ink-2)}
.facts b{display:block;font-size:22px;font-weight:600;color:var(--ink);letter-spacing:-.01em}
.summary{border:1px solid var(--hair);border-radius:10px;background:var(--surface);display:grid}
.summary>div{display:grid;grid-template-columns:120px 1fr;gap:16px;padding:14px 20px;border-top:1px solid var(--hair);align-items:baseline}
.summary>div:first-child{border-top:0}
.summary p{color:var(--ink-2);max-width:78ch}
.summary p b{color:var(--ink);font-weight:600}
.chain{display:grid;gap:8px}
.chain .step{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;border:1px solid var(--hair);
  background:var(--surface);border-radius:8px;padding:12px 14px}
.chain .step b{font-weight:600;font-size:15px;display:block}
.chain .step small{font-size:13px;color:var(--ink-2)}
.chain .step .t{font-family:var(--mono);font-size:18px;font-weight:500;white-space:nowrap}
.chain .manual{font-size:13px;color:var(--ink-2);padding:2px 14px 2px 30px;position:relative}
.chain .manual::before{content:"";position:absolute;left:16px;top:-6px;bottom:-6px;border-left:2px dashed var(--warm)}
.chain .manual b{color:var(--ink);font-weight:600}
.fxs{display:grid;gap:10px}
.fx{font-family:var(--mono);font-size:14px;line-height:1.5;overflow-wrap:anywhere}
.fx.sub{color:var(--ink-2);font-size:13.5px}
.fx b{color:var(--ink);font-weight:500}
.quotes{display:grid;grid-template-columns:repeat(var(--n,3),minmax(0,1fr));gap:16px}
.q{margin:0;padding:18px 20px;border-left:3px solid var(--warm);background:var(--surface);border-radius:0 8px 8px 0;
  font-size:15px;color:var(--ink-2)}
.q .who{display:block;margin-top:10px;font-family:var(--mono);font-size:12px;color:var(--muted)}

/* charts and images */
.fig{min-width:0}
.fig-title{font-size:15px;font-weight:600;margin-bottom:2px}
.fig-sub{font-size:13px;color:var(--muted);margin-bottom:12px}
.fig-title+:not(.fig-sub){margin-top:10px}
svg{display:block;width:100%;height:auto;max-width:100%}
svg .ax{font-family:var(--mono);font-size:11px;fill:var(--muted)}
svg .lbl{font-family:var(--sans);font-size:13px;fill:var(--ink-2)}
svg .lblb{font-family:var(--sans);font-size:13px;font-weight:600;fill:var(--ink)}
svg .val{font-family:var(--mono);font-size:12px;fill:var(--ink)}
svg .cap{font-family:var(--sans);font-size:12px;fill:var(--ink-2)}
svg .grid{stroke:var(--hair);stroke-width:1}
svg .base{stroke:var(--axis);stroke-width:1}
svg .b1{fill:var(--accent)} svg .b2{fill:var(--warm)} svg .bm{fill:var(--bar-muted)} svg .bo{fill:var(--hair)}
svg .rng{stroke:var(--warm);stroke-width:2;opacity:.4}
svg .pdot{fill:var(--warm);stroke:var(--bg);stroke-width:2}
svg .ln{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
svg .dot{fill:var(--accent);stroke:var(--surface);stroke-width:2}
svg .hit{fill:transparent;cursor:default}
.legend{display:flex;gap:6px 18px;flex-wrap:wrap;font-size:13px;color:var(--ink-2);margin-top:8px}
.legend span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:7px;
  vertical-align:-1px;background:var(--sw)}
.funnel{display:grid;gap:10px}
.frow{display:grid;grid-template-columns:var(--lw,200px) 1fr var(--nw,48px);gap:14px;align-items:center;font-size:14px}
.frow .bar{height:18px;border-radius:0 4px 4px 0}
.frow .n{font-family:var(--mono);font-size:13px;text-align:right}
.frow .k{color:var(--ink-2)}
.frow .k small{display:block;color:var(--muted);font-size:12px}
.card .frow{--lw:170px;font-size:13.5px}
.tip{position:fixed;z-index:20;pointer-events:none;background:var(--ink);color:var(--bg);font-size:12.5px;padding:7px 10px;
  border-radius:6px;opacity:0;transition:opacity .12s;max-width:260px;line-height:1.35}
.tip b{font-weight:600}
.img{margin:0;min-width:0}
.img img{display:block;max-width:100%;height:auto;margin:0 auto;border-radius:8px}
.img .dk{display:none}
.img figcaption{font-size:13px;color:var(--muted);margin-top:8px}

/* tables */
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--hair);vertical-align:top}
th{font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:500}
td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
td.c,th.c{text-align:center}
tr.hl td{background:var(--accent-soft)}
.tscroll{overflow-x:auto}

@media (max-width:860px){
  .hero,.cols.c2{grid-template-columns:1fr}
  .cols.c3,.cols.c4,.cards,.tiles,.basis,.quotes{grid-template-columns:1fr 1fr}
  .facts{grid-template-columns:1fr}
  .frow{--lw:140px}
}
@media (max-width:560px){
  .cols.c3,.cols.c4,.cards,.tiles,.basis,.quotes{grid-template-columns:1fr}
  section{padding-block:40px}
  .summary>div{grid-template-columns:1fr;gap:4px}
  .frow{--lw:120px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* slide view: one slide per screen, with a bar of controls at the bottom */
body.deck{padding-bottom:64px}
body.deck .wrap>section{display:none}
body.deck .wrap{max-width:1180px}
body.deck .wrap>.on{display:flex;flex-direction:column;justify-content:center;min-height:calc(100vh - 64px);
  min-height:calc(100dvh - 64px);border-top:0;padding-block:22px;margin-top:0;animation:pg .25s ease}
body.deck .sec-head{margin-bottom:22px}
body.deck .sec-head:last-child{margin-bottom:0}
@keyframes pg{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){body.deck .wrap>.on{animation:none}}
.deckbar{position:fixed;left:0;right:0;bottom:0;z-index:50;height:64px;background:var(--surface);border-top:1px solid var(--hair);
  display:flex;align-items:center;gap:10px;padding:0 max(16px,env(safe-area-inset-right,0px)) 0 max(16px,env(safe-area-inset-left,0px))}
.deckbar button{font:inherit;font-size:14px;font-weight:500;height:40px;padding:0 16px;border-radius:8px;border:1px solid var(--hair);
  background:var(--surface);color:var(--ink);cursor:pointer;white-space:nowrap}
.deckbar button:hover{border-color:var(--axis)}
.deckbar button:disabled{opacity:.35;cursor:default}
.deckbar .next{background:var(--ink);border-color:var(--ink);color:var(--bg);font-weight:600;min-width:96px}
.deckbar .where{flex:1;min-width:0;text-align:center;font-family:var(--mono);font-size:12px;letter-spacing:.06em;color:var(--ink-2);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.deckbar .prog{position:absolute;left:0;top:-2px;height:2px;width:0;background:var(--accent);transition:width .25s ease}
body:not(.deck) .deckbar .back,body:not(.deck) .deckbar .next,body:not(.deck) .deckbar .prog{display:none}
@media (max-width:560px){.deckbar .mode{display:none}.deckbar button{padding:0 12px}}
@media print{.deckbar,.tip{display:none}body.deck .wrap>section{display:block;break-inside:avoid}}
"""

JS = r"""
(function(){
  // tooltips: any element carrying data-tip
  var tip=document.getElementById('tip'),cur=null;
  document.addEventListener('mousemove',function(e){
    var t=e.target.closest?e.target.closest('[data-tip]'):null;
    if(!t){if(cur){cur=null;tip.style.opacity=0}return}
    if(t!==cur){cur=t;tip.innerHTML=t.getAttribute('data-tip')}
    tip.style.opacity=1;
    var w=tip.offsetWidth,h=tip.offsetHeight,x=e.clientX+14,y=e.clientY+14;
    if(x+w>innerWidth-8)x=e.clientX-w-14;if(y+h>innerHeight-8)y=e.clientY-h-14;
    tip.style.left=x+'px';tip.style.top=y+'px';
  });

  // slide view
  var pages=[].slice.call(document.querySelectorAll('.wrap > section'));
  var $=function(id){return document.getElementById(id)};
  var where=$('dkwhere'),prog=$('dkprog'),back=$('dkback'),next=$('dknext'),mode=$('dkmode');
  var i=0,deck=true;
  function show(k){
    i=Math.max(0,Math.min(pages.length-1,k));
    pages.forEach(function(p,j){p.classList.toggle('on',j===i)});
    where.textContent=(i+1)+' / '+pages.length+' · '+(pages[i].getAttribute('data-nav')||'');
    prog.style.width=((i+1)/pages.length*100)+'%';
    back.disabled=i===0;next.disabled=i===pages.length-1;
    if(deck){fit();window.scrollTo(0,0)}
    try{history.replaceState(null,'','#'+(i+1))}catch(e){}
  }
  // shrink a slide that is slightly too tall so it fits the screen without scrolling
  function fit(){
    var el=pages[i];pages.forEach(function(p){p.style.zoom=''});
    if(!deck||!('zoom' in el.style))return;
    var root=document.documentElement,z=1;
    function over(){return root.scrollHeight>window.innerHeight+1}
    if(!over())return;
    while(over()&&z>0.8){z=Math.round((z-0.03)*100)/100;el.style.zoom=z}
    while(!over()&&z<1){z=Math.round((z+0.01)*100)/100;el.style.zoom=z}
    if(over()){z=Math.round((z-0.01)*100)/100;el.style.zoom=z}
  }
  var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(fit,120)});
  function setMode(d){
    deck=d;document.body.classList.toggle('deck',d);
    mode.textContent=d?'Scroll view':'Slide view';
    if(d){show(i)}else{pages.forEach(function(p){p.style.zoom=''});where.textContent='Scroll view · all '+pages.length+' slides';pages[i].scrollIntoView()}
  }
  back.addEventListener('click',function(){show(i-1)});
  next.addEventListener('click',function(){show(i+1)});
  mode.addEventListener('click',function(){setMode(!deck)});
  document.addEventListener('keydown',function(e){
    if(!deck||e.metaKey||e.ctrlKey||e.altKey)return;
    var t=e.target.tagName;
    if(t==='INPUT'||t==='SELECT'||t==='TEXTAREA')return;
    if(t==='BUTTON'&&(e.key===' '||e.key==='Enter'))return;
    if(['ArrowRight','PageDown',' '].indexOf(e.key)>=0){e.preventDefault();show(i+1)}
    else if(['ArrowLeft','PageUp'].indexOf(e.key)>=0){e.preventDefault();show(i-1)}
    else if(e.key==='Home'){e.preventDefault();show(0)}
    else if(e.key==='End'){e.preventDefault();show(pages.length-1)}
  });
  var h=parseInt(location.hash.slice(1),10);
  if(h>=1&&h<=pages.length)i=h-1;
  setMode(true);
})();
"""


# ---------------------------------------------------------------- command line

def build(text, base_dir=".", fragment=False):
    """Markdown text in, HTML text out. Raises DeckError with a line number on bad input."""
    return Deck(text, base_dir).html(fragment)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="md2deck", description="Stitch Markdown and images into one self-contained HTML slide deck.",
        epilog="Read the format before writing a deck: python3 md2deck.py --format. "
               "Source, and AGENTS.md with the reasons behind the tool and the rules for changing it: " + __url__)
    ap.add_argument("input", nargs="?", help="the deck's Markdown file")
    ap.add_argument("-o", "--output", help="where to write the HTML (default: next to the input, with .html; '-' for stdout)")
    ap.add_argument("--fragment", action="store_true",
                    help="leave out the <html>, <head> and <body> wrapper, for hosts that add their own (such as Claude artifacts)")
    ap.add_argument("--format", action="store_true", help="print the Markdown format reference and exit")
    ap.add_argument("--version", action="version", version="md2deck " + __version__)
    a = ap.parse_args(argv)
    if a.format:
        sys.stdout.write(FORMAT.lstrip("\n"))
        return 0
    if not a.input:
        ap.error("give the deck's Markdown file, or --format to read the format reference")
    try:
        with open(a.input, encoding="utf-8") as f:
            text = f.read()
    except (IOError, OSError) as e:
        sys.stderr.write("md2deck: cannot read %s: %s\n" % (a.input, e.strerror or e))
        return 1
    try:
        deck = Deck(text, os.path.dirname(os.path.abspath(a.input)))
        out = deck.html(a.fragment)
    except DeckError as e:
        sys.stderr.write("%s:%d: error: %s\n" % (a.input, e.line, e.msg))
        return 1
    if a.output == "-":
        sys.stdout.write(out)
        return 0
    target = a.output or os.path.splitext(a.input)[0] + ".html"
    with open(target, "w", encoding="utf-8") as f:
        f.write(out)
    sys.stderr.write("%s: %d slides, %d images, %.1f KB of HTML from %.1f KB of Markdown\n" % (
        target, len(deck.slides), deck.images, len(out.encode("utf-8")) / 1024.0, len(text.encode("utf-8")) / 1024.0))
    return 0


# The format reference. FORMAT.md is this text: python3 md2deck.py --format > FORMAT.md
FORMAT = r'''
# md2deck format

A deck is one Markdown file. `python3 md2deck.py deck.md` turns it into one HTML file.
This page lists everything the tool understands. Each section shows what you write and what it becomes.

## 1. The file and its slides

```
---
title: Quarterly review
---

###### Eyebrow label
# Deck title

Opening paragraph.

---

###### 01 · Section name
## Slide title

Lead paragraph.

(blocks)
```

| You write | You get |
|---|---|
| `---` on a line of its own | The next slide starts here. |
| `###### Text` as the first line of a slide | The eyebrow: a small upper-case label above the title. It also names the slide in the bottom bar, where a leading number such as `01 ·` is dropped. |
| `# Text` | The deck title, in large type. Use it on the opening slide only. That slide puts its text on the left and any other blocks on the right. |
| `## Text` | A slide title. |
| Paragraphs directly under the title | The lead: muted text under the title. |
| `<!-- text -->` | Nothing. Use it for notes to yourself. |

The block between the two `---` lines at the top of the file is optional. Its keys:

| Key | Meaning | Default |
|---|---|---|
| `title` | Browser tab title | The first slide's title |
| `lang` | Language of the page | `en` |
| `theme` | `light` or `dark` to force one | Follows the viewer's system |
| `webfonts` | `off` uses system fonts and loads nothing from Google Fonts | `on` |

## 2. Text

| You write | You get |
|---|---|
| A paragraph | Body text |
| `**bold**`, `*italic*`, `` `code` ``, `[text](https://url)` | Bold, italic, inline code, a link |
| `- item` or `1. item` | A bulleted or numbered list. Indent two spaces to nest. |
| `-# Text` | Small print: a muted paragraph in footnote size |
| `### Text` | A heading inside a slide or a card |
| `###### Text` below the first line | A small upper-case label |
| `> Quote text -- Who said it` | A quote card. Quotes that follow each other sit side by side. |
| `<br>` | A line break |
| `\*`, `\_`, `\|` | The character itself |

All other HTML in text is shown as written, not interpreted.

## 3. Figure titles

```
#### Hours lost per month
-# Number of respondents in each band
(chart, table, image or container)
```

`####` is the title of the block that follows it. A `-#` line directly under it becomes the subtitle.

## 4. Tables

```
| Team size | Covered | Break-even |
|---|---:|---:|
| 2 engineers | 101% | 4.5 | *
| 3 engineers | 68% | 6.7 |
```

A standard pipe table. `---:` right-aligns a column and `:---:` centres it. A ` *` after the last pipe highlights that row.

## 5. Containers

A container opens with `::: name` and closes with `:::` on a line of its own.

### Layout: `cols`, `cards`, `card`

```
::: cols
(left cell: any blocks)
+++
(right cell: any blocks)
:::
```

| You write | You get |
|---|---|
| `::: cols` | Columns. `+++` on a line of its own starts the next cell. There are as many columns as cells, up to four. |
| `::: cols 2` | The same, with a fixed number of columns. Extra cells wrap to the next row. |
| `::: cards` | Like `cols`, but every cell is a card: a white box with a border. |
| `::: cards accent warm plain` | Colours for the top edge of the first, second and third card. A number sets the column count, as in `::: cards 2`. |
| `::: card`, `::: card accent`, `::: card warm` | One card. Use it inside `cols` when only some cells are cards. |

Inside a card:

| You write | You get |
|---|---|
| `### Text` | The card heading |
| `###### Text` | A coloured upper-case label |
| `---` | A thin rule. What follows it is the card's footer, in smaller type. |

Containers nest. A card can hold a list, a chart, `::: facts` or `::: stat`. A cell of `cols` can hold another `cols`.

### Figures: `tiles`, `stat`, `facts`, `summary`, `steps`, `legend`

These hold one row per line, with cells separated by `|`.

```
::: tiles warm
8.6 | h / mo | average hands-on time per person
47 | of 51 | were blocked for more than half a day
1 in 3 | acted as the unofficial fixer
:::
```

| Container | A row is | You get |
|---|---|---|
| `::: tiles` | `value \| label` or `value \| unit \| label` | A row of boxes, each with a big value, a small unit and a label. Add `accent` or `warm` for a coloured top edge, or `small` for compact boxes. |
| `::: stat` | `value \| unit \| caption` | A very large number with a coloured bar on its left. Add `warm` for orange. Inside a card it is a plain large number. |
| `::: facts` | `value \| text` | Bold values over one line of text, separated by thin rules |
| `::: summary` | `label \| text` | A boxed list of labelled paragraphs, for an executive summary |
| `::: steps` | `title \| detail \| value` | A vertical sequence of boxes. A line starting with `>` between two steps is drawn as a dashed link with that text. |
| `::: legend` | `colour \| label` | A colour key, for charts that share one |

## 6. Charts

````
```chart bars
max: 54
tip: of 54 picked it
Faster CI | 41 *
Fewer flaky tests | 35 *
Reliable local setup | 11
```
````

A chart is a fenced block whose first line is `chart` and a type. Inside it:

- Options come first, one per line, as `name: value`.
- Every other line is a data row: `Label | number`. Numbers may use thousands commas and a trailing `%`.
- A ` *` at the end of a row marks it.
- After the numbers, a cell holding a colour name sets that row's colour. Any other text cell is the row's note.
- A first row that starts with `|` names the series: `| Test | Build | Other`.

Colours are `accent` (blue), `warm` (orange), `muted` (grey-blue) and `faint` (light grey). A row takes the chart's `color`. Once any row is marked or has its own colour, the unmarked rows turn `muted`.

| Type | A row is | You get |
|---|---|---|
| `bars` | `Label \| value` | Horizontal bars, with the label above each bar and the value at its end. The note shows in the tooltip. |
| `rows` | `Label \| value` | The same data as lines of label, bar and value. The note shows under the label. |
| `columns` | `Label \| value` | Vertical bars on a scale with grid lines. With several values per row the bars are stacked, and a header row must name the series. A note replaces the number printed above the bar. |
| `line` | `Label \| value` | One line across the rows, in order. Marked rows get a dot and their value. With no row marked, the last one does. |
| `range` | `Label \| low \| middle \| high` | One line per row with a dot at each value. A header row names the values in the tooltip. |
| `share` | `Label \| value \| value ...` | One bar per row, split into each series' share of the row's total. Needs a header row. A note replaces the caption under the bar. |

| Option | Meaning | Charts |
|---|---|---|
| `max` | Top of the scale. The default fits the data. | all but `share` |
| `step` | Distance between grid lines | `columns`, `line`, `range` |
| `unit` | Text after each value, such as `%`, `h` or `min` | all but `share` |
| `decimals` | Decimals for printed values. Tooltips keep the value as written. | all but `share` |
| `color` | Colour of the bars | `bars`, `rows`, `columns` |
| `colors` | Colours of the series, in order: `colors: accent, muted` | `columns`, `share` |
| `tip` | Text after the value in the tooltip: `tip: of 54 respondents` | `bars`, `columns`, `line` |
| `x` | Caption under the horizontal axis | `columns`, `range` |
| `axis` | `off` drops the scale and grid, for a small chart | `columns` |
| `height` | Height in pixels | `columns`, `line` |
| `every` | Print the label of every Nth row on the axis | `line` |
| `legend` | `off` hides the colour key | `columns`, `share` |

Charts with several series take at most four. Fold the rest into "Other".

## 7. Images

```
![Build cache flow](images/cache-flow.svg "Optional caption under the image")
```

Write an image on a line of its own. The path is relative to the Markdown file. The tool embeds the file in the HTML, so the deck stays one file.

| File | What happens |
|---|---|
| `.png`, `.jpg`, `.gif`, `.webp`, `.avif` | Embedded as it is |
| `.svg` | Placed inline, so it can use the deck's fonts and colours: `var(--ink)`, `var(--ink-2)`, `var(--muted)`, `var(--hair)`, `var(--surface)`, `var(--accent)`, `var(--warm)` |
| `chart.dark.png` next to `chart.png` | Shown in place of `chart.png` when the viewer uses dark mode |
| `https://...` | Linked, not embedded |

## 8. Formulas, code and raw HTML

````
```calc
per person = hands-on hours + blocked hours
  all 54 = 463.5 + 377.5 = **841 hours a month**
```
````

| You write | You get |
|---|---|
| ```` ```calc ```` | Lines in monospaced type. Indent a line to show it as a worked step, in muted type. `**bold**` picks out results. |
| ```` ```html ```` | The content goes into the page unchanged. Use it for the rare block nothing else covers. It may include `<style>` and `<script>`. |
| ```` ``` ```` with any other name, or none | A code block |

## 9. What the deck does

- It opens in slide view: one slide per screen, a bar with Back and Next at the bottom, and arrow keys, space, Page Up, Page Down, Home and End to move.
- "Scroll view" in the bar shows all slides as one page, which is also what gets printed.
- Adding `#7` to the address opens slide 7.
- A slide that is a little too tall is shrunk to fit, down to 80%. Beyond that it scrolls, so split it.
- Colours follow the viewer's light or dark setting.

## 10. Errors

The tool stops at the first problem and prints the file, the line and what to change:

```
deck.md:42: error: 'colour' is not an option of chart bars (options: max, unit, decimals, color, tip)
```
'''

if __name__ == "__main__":
    sys.exit(main())
