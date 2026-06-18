from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import matplotlib
import pytest
from PIL import Image

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "chart.py"
FIXTURES = ROOT / "tests" / "fixtures"
SCRIPTS_DIR = ROOT / "scripts"
DEFAULT_INPUT_DIR = SCRIPTS_DIR / "input"
DEFAULT_OUTPUT_DIR = SCRIPTS_DIR / "output"


def run_chart(input_name: str, tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), str(FIXTURES / input_name), "--out-dir", str(tmp_path), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def parse_stdout(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def run_spec(spec: dict, tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    input_path = tmp_path / f"{spec['type']}.json"
    input_path.write_text(json.dumps(spec), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(CLI), str(input_path), "--out-dir", str(tmp_path), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def assert_output_under_directory(output: Path, directory: Path) -> None:
    assert output.resolve().is_relative_to(directory.resolve())


def assert_readable_image(path: Path) -> None:
    with Image.open(path) as raw:
        raw.load()
        image = raw.convert("RGB")
    assert image.width > 10
    assert image.height > 10
    extrema = image.getextrema()
    assert any(low < high for low, high in extrema)
    colors = image.getcolors(maxcolors=image.width * image.height + 1)
    assert colors is not None
    assert len(colors) > 1


def test_cli_resolves_bare_filename_from_scripts_input_and_defaults_to_scripts_output() -> None:
    input_name = "bar-20260616-103012-a1B2c3D4e5.json"
    input_path = DEFAULT_INPUT_DIR / input_name
    output_path: Path | None = None
    DEFAULT_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        input_path.write_text(json.dumps(load_fixture("bar_cn.json"), ensure_ascii=False), encoding="utf-8")
        result = run_cli(input_name)
        payload = parse_stdout(result)
        assert result.returncode == 0, result.stderr
        assert payload["ok"] is True
        output_path = Path(payload["path"])
        assert output_path.exists()
        assert_output_under_directory(output_path, DEFAULT_OUTPUT_DIR)
        assert_readable_image(output_path)
    finally:
        if output_path and output_path.exists():
            output_path.unlink()
        if input_path.exists():
            input_path.unlink()


def test_cli_renders_chinese_bar_png_and_returns_json(tmp_path: Path) -> None:
    fixture = load_fixture("bar_cn.json")
    assert any("华" in row["region"] for row in fixture["data"])
    assert any(row["sales"] < 0 for row in fixture["data"])
    result = run_chart("bar_cn.json", tmp_path)
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    assert payload["ok"] is True
    assert payload["format"] == "png"
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert output.suffix == ".png"
    assert_readable_image(output)
    assert isinstance(payload["warnings"], list)


def test_cli_renders_line_svg(tmp_path: Path) -> None:
    result = run_chart("line.json", tmp_path, "--format", "svg")
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert output.suffix == ".svg"
    assert "<svg" in output.read_text(encoding="utf-8")


def test_theme_does_not_overwrite_configured_cjk_fonts(monkeypatch) -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import rcParams

        from chart_renderer import fonts
        from chart_renderer.theme import apply_theme

        monkeypatch.setattr(fonts, "_available_font_names", lambda: {"Microsoft YaHei"})
        warnings = fonts.configure_fonts()
        apply_theme()

        assert warnings == []
        assert rcParams["font.sans-serif"][0] == "Microsoft YaHei"
        assert rcParams["axes.unicode_minus"] is False
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_cli_renders_heatmap_png(tmp_path: Path) -> None:
    result = run_chart("heatmap.json", tmp_path)
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_pie_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "pie",
            "title": "Revenue mix",
            "subtitle": "Sorted by contribution",
            "data": [{"channel": "Direct", "revenue": 40}, {"channel": "Partner", "revenue": 25}],
            "encoding": {"label": "channel", "value": "revenue"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_histogram_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "histogram",
            "title": "Order value distribution",
            "subtitle": "Ten bins by default",
            "data": [{"value": value} for value in [8, 12, 14, 19, 21, 26, 31, 37, 45, 52]],
            "encoding": {"x": "value"},
            "options": {"bins": 5},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_boxplot_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "boxplot",
            "title": "Delivery time by lane",
            "subtitle": "Distribution with strip overlay",
            "data": [
                {"lane": "North", "hours": 20},
                {"lane": "North", "hours": 24},
                {"lane": "South", "hours": 18},
                {"lane": "South", "hours": 29},
            ],
            "encoding": {"x": "lane", "y": "hours"},
            "options": {"strip": True},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_stacked_bar_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "stacked_bar",
            "title": "Sales by region",
            "subtitle": "Product contribution",
            "data": [
                {"region": "East", "product": "A", "sales": 12},
                {"region": "East", "product": "B", "sales": 8},
                {"region": "South", "product": "A", "sales": 10},
                {"region": "South", "product": "B", "sales": 11},
            ],
            "encoding": {"x": "region", "series": "product", "value": "sales"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_horizontal_bar_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "horizontal_bar",
            "title": "Top categories",
            "subtitle": "Long labels should remain readable",
            "data": [
                {"category": "Enterprise subscription renewal", "value": 38},
                {"category": "Self-service expansion", "value": 27},
                {"category": "Partner-assisted onboarding", "value": 19},
            ],
            "encoding": {"x": "category", "y": "value"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_bar_renderer_preserves_duplicate_category_rows() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import bar

        spec = ChartSpec(
            chart_type="bar",
            title="Duplicate categories",
            subtitle="Each source row should render exactly once",
            data=[
                {"category": "A", "value": 10},
                {"category": "A", "value": 30},
                {"category": "B", "value": 40},
            ],
            encoding={"x": "category", "y": "value"},
            options={"value_labels": True},
        )

        fig = bar.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            assert [patch.get_height() for patch in ax.patches] == pytest.approx([10, 30, 40])
            assert [tick.get_text() for tick in ax.get_xticklabels()] == ["A", "A", "B"]
            assert [text.get_text() for text in ax.texts] == ["10", "30", "40"]
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_horizontal_bar_renderer_preserves_duplicate_category_rows() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import bar

        spec = ChartSpec(
            chart_type="horizontal_bar",
            title="Duplicate categories",
            subtitle="Each source row should render exactly once",
            data=[
                {"category": "A", "value": 10},
                {"category": "A", "value": 30},
                {"category": "B", "value": 40},
            ],
            encoding={"x": "category", "y": "value"},
            options={"value_labels": True},
        )

        fig = bar.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            assert [patch.get_width() for patch in ax.patches] == pytest.approx([10, 30, 40])
            assert [tick.get_text() for tick in ax.get_yticklabels()] == ["A", "A", "B"]
            assert [text.get_text() for text in ax.texts] == ["10", "30", "40"]
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_line_renderer_preserves_duplicate_x_rows_in_input_order() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import line

        spec = ChartSpec(
            chart_type="line",
            title="Duplicate x values",
            subtitle="Line should preserve source row order",
            data=[
                {"month": "Jan", "sales": 10},
                {"month": "Jan", "sales": 30},
                {"month": "Feb", "sales": 20},
            ],
            encoding={"x": "month", "y": "sales"},
            options={},
        )

        fig = line.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            rendered_line = ax.lines[0]
            assert list(rendered_line.get_xdata()) == [0, 1, 2]
            assert list(rendered_line.get_ydata()) == pytest.approx([10, 30, 20])
            assert [tick.get_text() for tick in ax.get_xticklabels()] == ["Jan", "Jan", "Feb"]
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_boxplot_strip_overlay_disables_jitter(monkeypatch) -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import boxplot

        captured: dict[str, object] = {}

        def fake_stripplot(*args, **kwargs):
            captured["jitter"] = kwargs.get("jitter")
            return None

        monkeypatch.setattr(boxplot.sns, "stripplot", fake_stripplot)
        spec = ChartSpec(
            chart_type="boxplot",
            title="Delivery time by lane",
            subtitle="Deterministic strip overlay",
            data=[
                {"lane": "North", "hours": 20},
                {"lane": "North", "hours": 24},
                {"lane": "South", "hours": 18},
                {"lane": "South", "hours": 29},
            ],
            encoding={"x": "lane", "y": "hours"},
            options={"strip": True},
        )

        fig = boxplot.render(spec, dpi=144)
        try:
            assert captured["jitter"] is False
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_cli_renders_area_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "area",
            "title": "Revenue trend",
            "subtitle": "Area chart rendering",
            "data": [
                {"month": "Jan", "revenue": 12},
                {"month": "Feb", "revenue": 18},
                {"month": "Mar", "revenue": 15},
            ],
            "encoding": {"x": "month", "y": "revenue"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_table_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "table",
            "title": "Top accounts",
            "subtitle": "Exact rows from source data",
            "data": [
                {"account": "Alpha", "owner": "Lin", "amount": 123},
                {"account": "Beta", "owner": "Chen", "amount": 98},
            ],
            "encoding": {},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_funnel_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "funnel",
            "title": "Signup funnel",
            "subtitle": "Input order is preserved",
            "data": [
                {"stage": "Visit", "users": 1000},
                {"stage": "Signup", "users": 420},
                {"stage": "Activated", "users": 180},
            ],
            "encoding": {"stage": "stage", "value": "users"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_pareto_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "pareto",
            "title": "Issue Pareto",
            "subtitle": "Descending bars with cumulative share",
            "data": [
                {"reason": "Billing", "tickets": 18},
                {"reason": "Login", "tickets": 35},
                {"reason": "Performance", "tickets": 12},
            ],
            "encoding": {"x": "reason", "y": "tickets"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_cli_renders_waterfall_png(tmp_path: Path) -> None:
    result = run_chart("waterfall.json", tmp_path)
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_missing_title_returns_json_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"type": "bar", "subtitle": "x", "data": [], "encoding": {}}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CLI), str(bad), "--out-dir", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "title" in payload["error"]


def test_empty_data_returns_json_validation_error(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "bar",
            "title": "Empty data",
            "subtitle": "Should be rejected before rendering",
            "data": [],
            "encoding": {"x": "name", "y": "value"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "data" in payload["error"]
    assert "non-empty" in payload["error"]


def test_missing_encoding_field_returns_json_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad-field.json"
    bad.write_text(
        json.dumps({
            "type": "bar",
            "title": "Bad",
            "subtitle": "Missing field",
            "data": [{"name": "A", "value": 1}],
            "encoding": {"x": "name", "y": "missing"},
        }),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(CLI), str(bad), "--out-dir", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "missing" in payload["error"]


def test_non_numeric_encoding_field_returns_json_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad-numeric.json"
    bad.write_text(
        json.dumps({
            "type": "bar",
            "title": "Bad numeric",
            "subtitle": "One row is not numeric",
            "data": [{"name": "A", "value": 1}, {"name": "B", "value": "oops"}],
            "encoding": {"x": "name", "y": "value"},
        }),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(CLI), str(bad), "--out-dir", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "numeric" in payload["error"]


def test_null_numeric_encoding_field_returns_json_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad-null-numeric.json"
    bad.write_text(
        json.dumps({
            "type": "bar",
            "title": "Bad numeric",
            "subtitle": "One row is null",
            "data": [{"name": "A", "value": 1}, {"name": "B", "value": None}],
            "encoding": {"x": "name", "y": "value"},
        }),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(CLI), str(bad), "--out-dir", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "numeric" in payload["error"]
    assert "row 1" in payload["error"]


def test_optional_encoding_field_missing_returns_json_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad-optional.json"
    bad.write_text(
        json.dumps({
            "type": "bar",
            "title": "Bad optional",
            "subtitle": "Missing optional encoded field",
            "data": [{"month": "Jan", "value": 10}, {"month": "Feb", "value": 20}],
            "encoding": {"x": "month", "y": "value", "color": "segment"},
        }),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(CLI), str(bad), "--out-dir", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "segment" in payload["error"]


def test_missing_input_returns_json_error() -> None:
    result = run_cli()
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["ok"] is False
    assert "input" in payload["error"]


def test_invalid_format_returns_json_error(tmp_path: Path) -> None:
    result = run_cli(str(FIXTURES / "bar_cn.json"), "--out-dir", str(tmp_path), "--format", "pdf")
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["ok"] is False
    assert "format" in payload["error"]


def test_invalid_dpi_returns_json_error(tmp_path: Path) -> None:
    result = run_cli(str(FIXTURES / "bar_cn.json"), "--out-dir", str(tmp_path), "--dpi", "not-a-number")
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["ok"] is False
    assert "dpi" in payload["error"]


def test_nonnumeric_width_returns_json_validation_error(tmp_path: Path) -> None:
    spec = load_fixture("bar_cn.json")
    spec["options"]["width"] = "wide"
    result = run_spec(spec, tmp_path)
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["ok"] is False
    assert "options.width" in payload["error"]
    assert "positive integer" in payload["error"]


def test_non_positive_height_returns_json_validation_error(tmp_path: Path) -> None:
    spec = load_fixture("bar_cn.json")
    spec["options"]["height"] = 0
    result = run_spec(spec, tmp_path)
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["ok"] is False
    assert "options.height" in payload["error"]
    assert "positive integer" in payload["error"]


def test_cli_threads_dpi_into_render_chart(monkeypatch, tmp_path: Path) -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from chart_renderer import cli as cli_module
        from chart_renderer.contract import ChartSpec

        captured: dict[str, object] = {}

        def fake_load_json(path: Path) -> dict:
            return load_fixture("bar_cn.json")

        def fake_validate(raw: dict) -> ChartSpec:
            return ChartSpec(
                chart_type="bar",
                title="T",
                subtitle="S",
                data=[],
                encoding={},
                options={},
            )

        def fake_resolve_output_path(spec: dict, *, out: str | None, out_dir: str | None, fmt: str) -> Path:
            return tmp_path / f"out.{fmt}"

        def fake_render_chart(spec: ChartSpec, output_path: Path, fmt: str, dpi: int) -> list[str]:
            captured["dpi"] = dpi
            captured["fmt"] = fmt
            captured["path"] = output_path
            raise RuntimeError(f"renderer for {spec.chart_type} is not implemented")

        monkeypatch.setattr(cli_module, "load_json", fake_load_json)
        monkeypatch.setattr(cli_module, "validate", fake_validate)
        monkeypatch.setattr(cli_module, "resolve_output_path", fake_resolve_output_path)
        monkeypatch.setattr(cli_module, "render_chart", fake_render_chart)
        monkeypatch.setattr(cli_module, "ensure_output_exists", lambda path: None)
        monkeypatch.setattr(cli_module, "ensure_png_nonblank", lambda path: None)

        result = cli_module.main([str(FIXTURES / "bar_cn.json"), "--out-dir", str(tmp_path), "--dpi", "288"])
        assert result == 1
        assert captured["dpi"] == 288
        assert captured["fmt"] == "png"
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
