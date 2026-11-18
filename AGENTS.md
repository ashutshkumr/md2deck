# md2deck: notes for coding agents

This file is the project's memory for coding agents. `CLAUDE.md` imports it, so Claude Code and the agents that read `AGENTS.md` get the same text.
People should start with [README.md](README.md).

Read the part that matches your task:

- You were asked to **make or change a slide deck**, in this repository or in any other project: read "What it is", "Why it exists" and "Making a deck".
- You were asked to **change the tool**: read the whole file.

## What it is

One Python file, `md2deck.py`, that turns one Markdown file and its images into one HTML slide deck.

The Markdown holds the content: text, numbers and image paths.
The tool supplies what is the same in every deck: layout, chart drawing, light and dark colours, and the Back and Next buttons.

## Why it exists

Coding agents were writing slide decks directly as HTML. That was expensive:

- Every deck repeated about 16 KB of styling and script.
- Every chart was drawn by hand as SVG or JavaScript.
- To change one number, the agent read the whole HTML file and rewrote the drawing code.

The deck that started this tool had 20 slides and 17 charts. Written by hand it was 84 KB of HTML. The same content is 38 KB of Markdown.

So the work is split. An agent or a person writes only the content. The tool turns it into the same look every time.

Two more goals shape the design:

- **No setup.** Anyone fetches one file with `curl` and runs it with the Python already on the machine.
- **Easy to pass on.** The output is one HTML file that can be emailed, attached, or published as a Claude artifact.

Each rule under "Rules that must hold" protects one of these goals.

## Making a deck

These steps work in any project. Only `md2deck.py` is needed there.

1. **Get the tool** if the project does not have it:

   ```sh
   curl -fsSLO https://raw.githubusercontent.com/ashutshkumr/md2deck/main/md2deck.py
   ```

2. **Read the format**: `python3 md2deck.py --format`. Read it each time; do not write from memory.
   The format is strict. An unknown setting, container, chart type or chart option stops the build.

3. **Write `deck.md`.**
   - A line holding only `---` starts the next slide.
   - Put numbers in `chart` blocks or tables. Do not draw charts yourself.
   - Save anything else that has to be drawn as an SVG or PNG under `images/`, and reference it on a line of its own.

4. **Build**: `python3 md2deck.py deck.md` writes `deck.html` next to the Markdown.
   An error names the file, the line and the fix:

   ```text
   deck.md:41: error: 'colour' is not an option of chart bars (options: max, unit, decimals, color, tip)
   ```

   Fix that line and build again.

5. **Look at the result.** The tool does not check whether a slide fits the screen.
   In slide view the page shrinks a slide that is too tall, down to 80%. Past that, the slide scrolls.
   Open the file in a browser, or take a screenshot of each slide with headless Chrome:

   ```sh
   chrome --headless=new --hide-scrollbars --window-size=1440,900 --virtual-time-budget=4000 \
     --screenshot=slide-3.png "file:///absolute/path/to/deck.html#3"
   ```

   `#3` opens slide 3. On macOS the program is `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
   If a slide scrolls or looks cramped, move part of it to another slide.
   To check dark mode, build once with `theme: dark` in the settings block.

6. **To change the deck**, edit `deck.md` and build again.
   Do not read or edit the HTML. It is generated, and the next build overwrites it.

Three more things to know:

- **Claude artifacts.** Build with `--fragment` and publish that file. It leaves out the page wrapper, which the artifact host adds itself.
- **Something the format cannot express.** For a one-off, such as a slider, use an `html` block. It passes through unchanged and may hold its own `<style>` and `<script>`. Use the deck's colour variables there (`var(--ink)`, `var(--accent)` and the others at the top of `CSS`), so the block follows dark mode. If several decks would need the piece, add it to the tool in this repository.
- **Do not patch a project's copy of `md2deck.py`.** The next download replaces it, and the deck then stops building for everyone else.

To make the agents in another project follow these steps, paste the block under "For every deck in a project" in the README into that project's `AGENTS.md` or `CLAUDE.md`.
The README section "Ask an AI agent to make the deck" also has a prompt a person can paste for a single deck.

## Changing the tool

### Rules that must hold

1. **One file, standard library only, Python 3.8 syntax.**
   People install the tool with one `curl` and run it with the system Python, which is 3.9 on a Mac with the developer tools.
   So: no third-party imports, no `match`, no `X | Y` type hints, no `str.removeprefix`. The tests have been run on 3.9 and 3.15.

2. **The output is one self-contained file.**
   Images are embedded, and the styles and script are inline. The file gets emailed, and Claude artifacts block most outside resources.
   The only outside request is the Google Fonts stylesheet. It has system-font fallbacks, and `webfonts: off` removes it.

3. **Charts are drawn at build time.**
   Each chart is inline SVG that takes its colours from CSS classes. There is no chart library and no chart code in the page.
   This keeps the output testable, lets charts follow light and dark mode through CSS, and makes them print.
   The page script (`JS`) only moves between slides, fits a slide to the screen and shows tooltips.

4. **Colours come from CSS variables.**
   Light values are at the top of `CSS`, and dark values are in `DARK`. A component never uses a literal colour, or it breaks in one of the two modes.

5. **Every problem in the input raises `DeckError(line, message)`.**
   The message says what is wrong and what to write instead. Unknown names are errors and are never skipped.
   An agent can fix an error from one line. A typo that is silently ignored produces a wrong deck that nobody notices.

6. **The format reference lives in the tool.**
   The `FORMAT` string at the bottom of `md2deck.py` is the only source, and `FORMAT.md` is generated from it.
   A downloaded copy must be able to explain itself with `--format`. Any change to what the tool accepts updates `FORMAT` in the same commit.

7. **The same input gives the same bytes.**
   The output has no timestamps, random ids or absolute paths. The tests compare the committed examples byte for byte.

8. **Existing decks keep building.**
   Add to the format. Do not change the meaning of something already documented without raising the major version.

9. **The format stays small.**
   Add a piece when several decks need it. A one-off belongs in an `html` block.

10. **Examples and tests use invented data, and the example slides say so.**
    This repository is public. Do not put real project figures or people's names in it.

### How the file is laid out

`md2deck.py` runs top to bottom in the order the work happens:

- **Block parser.** `parse_blocks` turns the numbered lines into `Node` objects of kind `h`, `p`, `list`, `table`, `img`, `quote`, `small`, `fence`, `box`, `flow`, `sep`, `rule` or `break`. Each node keeps its line number for error messages. `ROW_BOXES` and `FLOW_BOXES` name the `:::` containers.
- **Inline text.** `inline` renders bold, italic, code, links and `<br>`, and escapes everything else. `plain` strips the markup for chart labels and tooltips.
- **Charts.** `Chart` parses a chart block's options, header row and data rows. `CHART_OPTIONS` lists the options each chart type accepts. Each type has one function, `chart_<type>(c, W, label)`, that returns an SVG string. `CHART_RENDER` maps the type names to those functions.
- **Renderer.** `Deck` reads the settings block, splits the nodes into slides at each `break` and renders them through `slide`, `flow` and `block`. `block` sends a `box` node to the method `box_<name>` and a `flow` node to `flow_<name>`. `Ctx` carries the width available to a block, which sets the width of a chart.
- **Page template.** `CSS`, `DARK`, `JS`, `NAV` and `FONTS` are the fixed part of every deck.
- **Command line.** `build(text, base_dir, fragment)` is the function to call from Python. `main` is the command.
- **Format reference.** `FORMAT`.

### Common changes

- **A chart option.** Add its name to `CHART_OPTIONS` for each type that takes it. Read it in the chart function with `c.num("name")` for a number or `c.opts.get("name")` for text.
- **A chart type.** Write `chart_<type>(c, W, label)` and register it in `CHART_RENDER` and `CHART_OPTIONS`. Colour the marks with the classes in `FILL`, and add one `_hit` rectangle per mark for its tooltip. Add the type to `test_every_chart_type_renders` and to `example/deck.md`.
- **A container whose rows are `a | b | c`.** Add the name to `ROW_BOXES` and write `box_<name>(self, nd, ctx)`. Check its options with `self.args` and the shape of each row with `self.cells`.
- **A container that holds other blocks.** Add the name to `FLOW_BOXES` and write `flow_<name>(self, nd, ctx)`.
- **A setting.** Add it to `SETTINGS` and read it from `self.meta`.
- **The look.** Colours and fonts are the variables at the top of `CSS`. Dark values are in `DARK`.

Every one of these also needs a line in `FORMAT` and a test.

### Before you commit

```sh
python3 md2deck.py --format > FORMAT.md
python3 md2deck.py example/minimal.md
python3 md2deck.py example/deck.md
python3 -m unittest discover tests
```

The first three commands regenerate files that are committed. The tests fail if any of them is out of date.

The tests check the HTML text, not how it looks. Open `example/deck.html` and go through every slide in light and dark mode, at 1440×900 and in a narrow window.

Then:

- Raise `__version__` if the format or the output changed.
- Retake the screenshots in `docs/` (1280×720) if the look changed. The README shows them.
- Update this file if a rule, the layout of the code or a limit changed.
- Commit the regenerated files together with the code change.

## Files

| Path | What it is |
|---|---|
| `md2deck.py` | The tool |
| `FORMAT.md` | The format reference, generated from the tool |
| `README.md` | The introduction for people: the purpose, a quick start, how to ask an agent for a deck, token saving |
| `AGENTS.md`, `CLAUDE.md` | This file, and the one line that imports it for Claude Code |
| `example/minimal.md`, `example/deck.md` | Example decks. Their `.html` outputs are committed, so people can open them and the tests can compare them. |
| `example/images/` | An SVG diagram and a PNG with a dark variant, used by `example/deck.md` |
| `docs/` | Screenshots shown in the README |
| `tests/test_md2deck.py` | The tests |

## Known limits

- The tool does not check that a slide fits the screen, and it does not split slides.
- There are no interactive controls. Use an `html` block.
- A chart takes at most four series and has one axis. Fold further series into "Other", or use two charts.
- There are no speaker notes, transitions or PDF export. Scroll view is the form to print.
- The Markdown is a subset: headings, paragraphs, lists, pipe tables, quotes, bold, italic, code, links and `<br>`. There are no footnotes, reference links, inline images or inline HTML.
- Fitting a slide to the screen uses CSS `zoom`. A browser without it scrolls instead.
