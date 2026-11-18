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
