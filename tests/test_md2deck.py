"""Tests for md2deck. Run from the repository root: python3 -m unittest discover tests"""
import io
import os
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import md2deck as ds  # noqa: E402


def png():
    """A valid 1x1 white PNG."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b""))


def chart(kind, body):
    return ds.build("## T\n\n```chart %s\n%s\n```\n" % (kind, body))


class Slides(unittest.TestCase):
    def test_slides_split_on_rule_and_take_their_name_from_the_eyebrow(self):
        out = ds.build("###### 01 · First\n## One\n\nLead.\n\n---\n\n## Two\n\nBody.\n")
        self.assertEqual(out.count("<section "), 2)
        self.assertIn('data-nav="First"', out)
        self.assertIn('data-nav="Two"', out)
        self.assertIn('<p class="eyebrow">01 · First</p><h2>One</h2><p>Lead.</p>', out)

    def test_settings_block_sets_the_title(self):
        out = ds.build("---\ntitle: My deck\ntheme: dark\n---\n\n## One\n")
        self.assertIn("<title>My deck</title>", out)
        self.assertIn('<html lang="en" data-theme="dark">', out)

    def test_title_defaults_to_the_first_slide(self):
        self.assertIn("<title>One</title>", ds.build("## One\n"))

    def test_a_leading_rule_without_settings_is_a_slide_break(self):
        out = ds.build("---\n## One\n---\n## Two\n")
        self.assertEqual(out.count("<section "), 2)

    def test_unknown_setting_is_reported(self):
        with self.assertRaises(ds.DeckError) as e:
            ds.build("---\ntittle: x\n---\n## One\n")
        self.assertEqual(e.exception.line, 2)

    def test_opening_slide_puts_blocks_beside_the_title(self):
        out = ds.build("# Big\n\nLead.\n\n::: stat warm\n4.5 | hours | lost\n:::\n")
        self.assertIn("<h1>Big</h1>", out)
        self.assertIn('<p class="lede">Lead.</p>', out)
        self.assertIn('<div class="hero-pair"><div class="stat warm"><div class="big num">4.5<small>hours</small></div>', out)

    def test_fragment_has_no_page_wrapper(self):
        out = ds.build("## One\n", fragment=True)
        self.assertTrue(out.startswith("<title>One</title>"))
        self.assertNotIn("<html", out)
        self.assertNotIn("<body", out)

    def test_comments_are_dropped(self):
        self.assertNotIn("secret", ds.build("## One\n\n<!-- secret\nnote -->\n\nShown.\n"))


class Text(unittest.TestCase):
    def test_inline_markup(self):
        self.assertEqual(ds.inline("**b** *i* `c<d` [t](https://x.y)"),
                         '<b>b</b> <em>i</em> <code>c&lt;d</code> <a href="https://x.y">t</a>')

    def test_html_is_escaped_and_escapes_are_literal(self):
        self.assertEqual(ds.inline(r"<b>x</b> 2 \* 3 a_b_c"), "&lt;b&gt;x&lt;/b&gt; 2 * 3 a_b_c")

    def test_lists_nest(self):
        out = ds.build("## T\n\n- a\n  - b\n- c\n\n1. one\n2. two\n")
        self.assertIn("<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>", out)
        self.assertIn("<ol><li>one</li><li>two</li></ol>", out)

    def test_small_print_and_figure_subtitle(self):
        out = ds.build("## T\n\n#### Title\n-# Sub\n| a |\n|---|\n| 1 |\n\n-# Note\n")
        self.assertIn('<div class="fig-title">Title</div><div class="fig-sub">Sub</div><div class="tscroll">', out)
        self.assertIn('<p class="note">Note</p>', out)

    def test_quotes_group_and_split_attribution(self):
        out = ds.build('## T\n\n> "One." -- Ann\n\n> "Two."\n')
        self.assertIn('<div class="quotes" style="--n:2"><blockquote class="q">"One."<span class="who">Ann</span></blockquote>', out)

    def test_table_alignment_and_highlight(self):
        out = ds.build("## T\n\n| A | B |\n|---|---:|\n| x | 1 |\n| y | 2 | *\n")
        self.assertIn('<th class="r">B</th>', out)
        self.assertIn('<tr class="hl"><td>y</td><td class="r">2</td></tr>', out)

    def test_formula_lines(self):
        out = ds.build("## T\n\n```calc\na = b + c\n  = **5**\n```\n")
        self.assertIn('<div class="fx">a = b + c</div><div class="fx sub">= <b>5</b></div>', out)

    def test_raw_html_passes_through_and_code_is_escaped(self):
        out = ds.build("## T\n\n```html\n<div id=\"raw\"></div>\n```\n\n```python\nif a < b: pass\n```\n")
        self.assertIn('<div id="raw"></div>', out)
        self.assertIn("<pre><code>if a &lt; b: pass</code></pre>", out)


class Containers(unittest.TestCase):
    def test_cols_split_on_plus_lines(self):
        out = ds.build("## T\n\n::: cols\nLeft\n+++\nRight\n+++\nThird\n:::\n")
        self.assertIn('<div class="cols c3" style="--n:3">', out)
        self.assertEqual(out.count('<div class="cell">'), 3)

    def test_cards_take_colours_in_order_and_a_footer_after_a_rule(self):
        out = ds.build("## T\n\n::: cards accent warm\n### A\n- x\n---\nFoot **b**\n+++\n### B\n+++\n### C\n:::\n")
        self.assertIn('<div class="card accent"><h3>A</h3>', out)
        self.assertIn('<div class="foot"><p>Foot <b>b</b></p></div>', out)
        self.assertIn('<div class="card warm"><h3>B</h3></div><div class="card"><h3>C</h3></div>', out)

    def test_containers_nest(self):
        out = ds.build("## T\n\n::: cols\n::: card\n### In\n::: facts\n34% | of time\n:::\n:::\n+++\nRight\n:::\n")
        self.assertIn('<div class="card"><h3>In</h3>\n<div class="facts" style="--n:1"><div><b class="num">34%</b>of time</div></div></div>', out)

    def test_row_containers(self):
        out = ds.build("## T\n\n::: tiles warm\n8.6 | h / mo | hands-on\n1 in 3 | fixers\n:::\n\n::: summary\nAsk | Two people\n:::\n\n"
                       "::: steps\nA | first | 1 h\n> **Manual.** wait\nB | second | 2 h\n:::\n\n::: legend\nwarm | Reported\n:::\n")
        self.assertIn('<div class="tile warm"><div class="v num">8.6<small>h / mo</small></div><div class="l">hands-on</div></div>', out)
        self.assertIn('<div class="v num">1 in 3</div>', out)
        self.assertIn('<span class="eyebrow">Ask</span><p>Two people</p>', out)
        self.assertIn('<div class="manual"><b>Manual.</b> wait</div>', out)
        self.assertIn('<span style="--sw:var(--warm)">Reported</span>', out)

    def test_stat_inside_a_card_is_a_plain_number(self):
        out = ds.build("## T\n\n::: card\n::: stat\n2 | engineers\n:::\n:::\n")
        self.assertIn('<div class="sz num">2<small>engineers</small></div>', out)


class Charts(unittest.TestCase):
    def test_bars_mark_rows_and_carry_tooltips(self):
        out = chart("bars", "unit: %\ndecimals: 0\ntip: failed\nHardware | 22.1 | 3,278 of 14,827 runs *\nSoftware | 2.9")
        self.assertIn('class="b1"', out)          # the marked row keeps the chart colour
        self.assertIn('class="bm"', out)          # the unmarked row turns muted
        self.assertIn(">22%</text>", out)         # printed value is rounded
        self.assertIn("22.1% failed&lt;br&gt;3,278 of 14,827 runs", out)   # tooltip keeps the value as written

    def test_columns_stack_with_a_header_and_show_a_legend(self):
        out = chart("columns", "colors: accent, muted\n| Yes | No\n<3 | 2 | 5 | 2/7\n3–6 | 5 | 0")
        self.assertIn(">2/7</text>", out)
        self.assertIn('<div class="legend"><span style="--sw:var(--accent)">Yes</span><span style="--sw:var(--bar-muted)">No</span></div>', out)

    def test_columns_without_header_cannot_stack(self):
        with self.assertRaises(ds.DeckError):
            chart("columns", "a | 1 | 2")

    def test_every_chart_type_renders(self):
        self.assertIn('<path d="M', chart("line", "2024 | 5\n2025 | 9 *\n2026 | 12"))
        self.assertIn('class="pdot"', chart("range", "| low | mid | high\ndpxs | 16 | 25 | 96"))
        self.assertIn("Test 92% · Build 8%", chart("share", "| Test | Build\ndpxs | 92 | 8"))
        self.assertIn('<div class="funnel"', chart("rows", "As reported | 841 | warm\nKept | 245 | accent | after corrections"))
        self.assertIn("<small>after corrections</small>", chart("rows", "Kept | 245 | accent | after corrections"))

    def test_axis_steps_are_round(self):
        self.assertEqual(ds.even_step(25), 5)
        self.assertEqual(ds.even_step(20), 5)
        self.assertEqual(ds.even_step(160), 40)

    def test_chart_errors_name_the_line_and_the_fix(self):
        cases = [("pie", "a | 1", "chart type"), ("bars", "colour: warm\na | 1", "not an option"),
                 ("bars", "a | b", "no number"), ("bars", "max: 5", "no data rows"),
                 ("bars", "color: pink\na | 1", "not a colour")]
        for kind, body, expected in cases:
            with self.assertRaises(ds.DeckError) as e:
                chart(kind, body)
            self.assertIn(expected, e.exception.msg)


class Errors(unittest.TestCase):
    def check(self, md, line, text):
        with self.assertRaises(ds.DeckError) as e:
            ds.build(md)
        self.assertEqual(e.exception.line, line)
        self.assertIn(text, e.exception.msg)

    def test_container_problems(self):
        self.check("## T\n\n::: cols\nLeft\n", 3, "never closed")
        self.check("## T\n\n:::\n", 3, "none is open")
        self.check("## T\n\n::: box\nx\n:::\n", 3, "unknown container")
        self.check("## T\n\n+++\n", 3, "only works directly inside")
        self.check("## T\n\n::: tiles\njust one cell\n:::\n", 4, "value | label")
        self.check("## T\n\n```chart bars\na | 1\n", 3, "never closed")

    def test_empty_file(self):
        self.check("\n\n", 1, "no slides")


class Images(unittest.TestCase):
    def test_images_are_embedded_and_dark_variants_are_paired(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("a.png", "a.dark.png", "b.png"):
                with open(os.path.join(d, name), "wb") as f:
                    f.write(png())
            with open(os.path.join(d, "c.svg"), "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="10" height="5"><rect/></svg>')
            deck = ds.Deck('## T\n\n![Alt a](a.png "Cap")\n\n![Alt b](b.png)\n\n![Alt c](c.svg)\n', d)
            out = deck.html()
        self.assertEqual(deck.images, 4)
        self.assertIn('<figure class="img duo"><img class="lt" src="data:image/png;base64,', out)
        self.assertIn("<figcaption>Cap</figcaption>", out)
        self.assertIn('<svg viewBox="0 0 10 5" xmlns', out)
        self.assertNotIn("<?xml", out)

    def test_missing_image_is_reported(self):
        with self.assertRaises(ds.DeckError) as e:
            ds.build("## T\n\n![x](nope.png)\n")
        self.assertIn("image not found", e.exception.msg)


class CommandLine(unittest.TestCase):
    def run_main(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ds.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_builds_next_to_the_input_and_reports_sizes(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "deck.md")
            with open(src, "w", encoding="utf-8") as f:
                f.write("## One\n")
            code, _, err = self.run_main([src])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(d, "deck.html")))
            self.assertIn("1 slides", err)

    def test_error_goes_to_stderr_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "deck.md")
            with open(src, "w", encoding="utf-8") as f:
                f.write("## One\n\n::: nope\n:::\n")
            code, _, err = self.run_main([src])
            self.assertEqual(code, 1)
            self.assertIn("deck.md:3: error: unknown container", err)
            self.assertFalse(os.path.exists(os.path.join(d, "deck.html")))

    def test_format_reference_matches_the_file_in_the_repository(self):
        code, out, _ = self.run_main(["--format"])
        with open(os.path.join(ROOT, "FORMAT.md"), encoding="utf-8") as f:
            self.assertEqual(out, f.read(), "run: python3 md2deck.py --format > FORMAT.md")
        self.assertEqual(code, 0)

    def test_examples_build_and_match_the_committed_output(self):
        for name in ("deck", "minimal"):
            src = os.path.join(ROOT, "example", name + ".md")
            with open(src, encoding="utf-8") as f:
                built = ds.build(f.read(), os.path.dirname(src))
            with open(os.path.join(ROOT, "example", name + ".html"), encoding="utf-8") as f:
                self.assertEqual(built, f.read(), "run: python3 md2deck.py example/%s.md" % name)


if __name__ == "__main__":
    unittest.main()
