# visualizing-data Skill Design

## Goal

Add a reusable `visualizing-data/` skill for deterministic single-chart generation. The skill should let an agent or user pass structured data and a chart specification, then produce a polished chart image. PNG is the default output; SVG is also supported.

This skill sits between analysis and reporting. It is not tied to Feishu, HTML reports, Streamlit reports, or AI image generation, but those workflows can call it whenever they need a reliable standalone chart asset.

## Non-Goals

- Do not generate full infographic reports or posters. Existing `generating-insights-report/scripts/image/` owns AI image reports.
- Do not use Recharts or browser screenshots in the first version.
- Do not create interactive charts.
- Do not require Data Analytics plugin onboarding, MCP widgets, or connector state.

## Architecture

Create a new skill directory:

```text
visualizing-data/
  SKILL.md
  agents/
    openai.yaml
  scripts/
    chart.py
    chart_renderer/
      __init__.py
      cli.py
      contract.py
      fonts.py
      io.py
      render.py
      theme.py
      quality.py
      renderers/
        __init__.py
        area.py
        bar.py
        boxplot.py
        funnel.py
        heatmap.py
        histogram.py
        line.py
        pareto.py
        pie.py
        scatter.py
        stacked_bar.py
        table.py
        waterfall.py
  references/
    input_contract.md
    seaborn_templates.md
  tests/
    test_chart_cli.py
    fixtures/
```

`SKILL.md` stays short. It tells agents when to use the skill, which script to run, and when to read `references/input_contract.md` or `references/seaborn_templates.md`.

`scripts/chart.py` is the stable CLI entry point. It delegates to `chart_renderer.cli`.

`chart_renderer/` is a small Python package so chart-specific logic remains modular. Renderers share validation, theme, export, and image-quality checks.

`chart_renderer/fonts.py` owns Chinese-friendly Matplotlib font setup. It should detect available CJK-capable fonts, configure Matplotlib with a stable fallback chain, disable Unicode minus rendering issues, and report a warning when no known CJK font is available.

## Input Contract

The CLI accepts one JSON file:

```json
{
  "type": "bar",
  "title": "Regional sales",
  "subtitle": "June 2026, CNY 10k",
  "data": [{ "region": "East", "sales": 120 }],
  "encoding": {
    "x": "region",
    "y": "sales",
    "color": null,
    "label": null
  },
  "options": {
    "orientation": "vertical",
    "sort": "desc",
    "value_labels": "auto",
    "width": 1200,
    "height": 720
  }
}
```

Required fields are `type`, `title`, `subtitle`, `data`, and the encoding fields needed by the selected chart type. `title` and `subtitle` must be non-empty for shipped charts.

The first version supports these chart types:

- `bar`
- `horizontal_bar`
- `line`
- `area`
- `pie`
- `scatter`
- `heatmap`
- `histogram`
- `boxplot`
- `stacked_bar`
- `waterfall`
- `funnel`
- `pareto`
- `table`

## CLI

Default PNG:

```bash
python visualizing-data/scripts/chart.py input.json
```

Explicit output and format:

```bash
python visualizing-data/scripts/chart.py input.json --out output/chart.svg --format svg
python visualizing-data/scripts/chart.py input.json --out-dir output
```

The command writes machine-readable JSON to stdout:

```json
{
  "ok": true,
  "path": "output/chart.png",
  "format": "png",
  "width": 1200,
  "height": 720,
  "warnings": []
}
```

Failures return non-zero and write a compact JSON error:

```json
{
  "ok": false,
  "error": "encoding.y field 'sales' is missing from data rows"
}
```

## Rendering Rules

Use Seaborn for marks where it fits naturally, and Matplotlib for layout, axes, annotations, headers, export, and chart-specific custom drawing.

Borrow the useful parts of the Data Analytics plugin's `visualize-data` and `seaborn-templates.md`:

- Choose explicit palettes instead of library defaults.
- Require title and subtitle.
- Keep white or near-white chart backgrounds.
- Use quiet grid lines and visible axis anchors.
- Prefer direct value labels when they improve exact reading.
- Avoid chart forms when the provided data is too sparse or structurally incompatible.
- Export PNG and SVG from the same renderer path.

The default theme should fit the existing project style: warm parchment background compatibility, readable dark ink, restrained blue/gold/orange/olive/pink palette roots, and clean report-ready typography. The generated image itself should remain portable and not assume a specific report shell.

## Chinese Text Support

Chinese labels, titles, subtitles, legends, value labels, and table cells are first-class requirements. Matplotlib often renders Chinese as tofu boxes when no CJK font is configured, so the renderer must configure fonts explicitly instead of relying on library defaults.

The implementation should:

- Prefer installed CJK fonts such as `Microsoft YaHei`, `SimHei`, `Noto Sans CJK SC`, `Source Han Sans SC`, `PingFang SC`, and `WenQuanYi Micro Hei`, with `DejaVu Sans` as the Latin fallback.
- Set `axes.unicode_minus = False` so negative values render correctly with CJK font stacks.
- Keep title, subtitle, axis, legend, annotation, and table text on the same font stack.
- Return a warning in CLI JSON when no known CJK-capable font is detected.
- Include smoke tests that render Chinese text and negative values to PNG without crashing and with a non-blank image.

## Data Flow

1. Agent or user prepares a chart JSON file.
2. `chart.py` reads JSON and validates the selected chart contract.
3. The dispatcher selects the renderer for `type`.
4. The renderer builds a Matplotlib figure with shared theme helpers.
5. Font helpers configure the Matplotlib font stack and collect font warnings.
6. The exporter writes PNG by default or SVG when requested.
7. Quality checks verify that the output exists, is non-empty, and is not visually blank.
8. CLI returns a JSON result for downstream workflows.

## Error Handling

Validation errors should be clear enough for an agent to repair input without reading the script internals:

- Missing required fields.
- Unknown chart type.
- Encoding references a column not present in `data`.
- Numeric encoding points at non-numeric data.
- Chart-specific requirements are missing, such as waterfall deltas or heatmap matrix fields.
- Output format is unsupported.

Rendering errors should include the chart type and suggested next action when possible.

## Testing

Use TDD for the implementation. First tests:

- CLI renders a non-blank PNG for `bar`.
- CLI renders SVG for `line`.
- `heatmap` accepts matrix-style input.
- `waterfall` validates start, deltas, and end output.
- Missing `title` or `subtitle` fails with a clear error.
- Missing encoding field fails with a clear error.
- CLI stdout is valid JSON on success and failure.
- Chinese title, subtitle, labels, and negative values render to a non-blank PNG.

Representative render tests are enough for first release; every renderer should have at least a contract validation test or smoke render test before being considered supported.

## Skill Instructions

The skill should tell agents:

- Use this skill when a user asks for a standalone chart image, chart PNG, chart SVG, static chart asset, report illustration, or deterministic generated chart.
- Prefer `visualizing-data` over AI image generation when exact chart values matter.
- Read `references/input_contract.md` before preparing JSON by hand.
- Read `references/seaborn_templates.md` when changing renderers, adding chart types, or tuning visual style.
- Preserve Chinese text and negative signs; inspect font warnings in the CLI JSON result.
- Run the CLI and inspect the output result before claiming the chart is ready.

## Integration Notes

The root `AGENTS.md` should list `visualizing-data/` as a horizontal service that can be called by analysis and reporting workflows.

`generating-insights-report` may call this skill when it needs chart images for document, slide, PDF, or image-report preparation, but no hard dependency is required in the first version.
