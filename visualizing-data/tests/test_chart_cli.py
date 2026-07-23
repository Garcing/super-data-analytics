from __future__ import annotations

import json
import re
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


def run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        capture_output=True,
        check=False,
        input=stdin,
    )


def parse_stdout(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def run_spec(spec: dict, tmp_path: Path, *, output_name: str = "out.png", stdin: str | None = None,
             extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    if stdin is not None:
        return run_cli("--data", "-", "--output", str(tmp_path / output_name), *extra, stdin=stdin)
    return run_cli("--data", json.dumps(spec, ensure_ascii=False),
                   "--output", str(tmp_path / output_name), *extra)


def run_fixture(name: str, tmp_path: Path, *, output_name: str = "out.png",
                extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    return run_cli("--data", f"@{FIXTURES / name}", "--output", str(tmp_path / output_name), *extra)


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


def test_fixtures_cover_every_supported_chart_type() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from chart_renderer.contract import SUPPORTED_TYPES

        fixture_types = {load_fixture(path.name)["type"] for path in FIXTURES.glob("*.json")}
        assert fixture_types == SUPPORTED_TYPES
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_all_fixtures_render_png(tmp_path: Path) -> None:
    for fixture in FIXTURES.glob("*.json"):
        result = run_fixture(fixture.name, tmp_path, output_name=f"{fixture.stem}.png")
        payload = parse_stdout(result)
        assert result.returncode == 0, f"{fixture.name}: {result.stderr}"
        assert_readable_image(Path(payload["path"]))


def test_renderer_colors_are_defined_only_in_theme() -> None:
    renderer_root = SCRIPTS_DIR / "chart_renderer"
    color_literal = re.compile(r"[\"']#[0-9A-Fa-f]{6}[\"']")
    offenders = [
        path.relative_to(renderer_root).as_posix()
        for path in renderer_root.rglob("*.py")
        if path.name != "theme.py" and color_literal.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


# --- 三态输入 -----------------------------------------------------------------

def test_data_at_file_renders_png(tmp_path: Path) -> None:
    fixture = load_fixture("bar_cn.json")
    assert any("华" in row["region"] for row in fixture["data"])
    assert any(row["sales"] < 0 for row in fixture["data"])
    result = run_fixture("bar_cn.json", tmp_path)
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


def test_data_inline_renders_png(tmp_path: Path) -> None:
    result = run_spec(load_fixture("heatmap.json"), tmp_path)
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


def test_data_stdin_renders_svg(tmp_path: Path) -> None:
    spec = load_fixture("line.json")
    result = run_spec(spec, tmp_path, output_name="out.svg", stdin=json.dumps(spec, ensure_ascii=False))
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert output.suffix == ".svg"
    assert "<svg" in output.read_text(encoding="utf-8")
    assert payload["format"] == "svg"


def test_data_stdin_empty_returns_json_error(tmp_path: Path) -> None:
    # 不传 --data 且 stdin 关闭为空 → 报错（模拟非交互下 stdin 没数据）
    result = run_cli("--output", str(tmp_path / "out.png"), stdin="")
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "stdin" in payload["error"] or "为空" in payload["error"]


# --- 格式推断 -----------------------------------------------------------------

def test_output_suffix_png_yields_png(tmp_path: Path) -> None:
    result = run_fixture("bar_cn.json", tmp_path, output_name="chart.png")
    payload = parse_stdout(result)
    assert result.returncode == 0
    assert payload["format"] == "png"
    assert Path(payload["path"]).suffix == ".png"


def test_output_suffix_svg_yields_svg(tmp_path: Path) -> None:
    result = run_fixture("bar_cn.json", tmp_path, output_name="chart.svg")
    payload = parse_stdout(result)
    assert result.returncode == 0
    assert payload["format"] == "svg"
    assert Path(payload["path"]).suffix == ".svg"


def test_output_unknown_suffix_returns_json_error(tmp_path: Path) -> None:
    result = run_fixture("bar_cn.json", tmp_path, output_name="chart.pdf")
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["ok"] is False
    assert "png" in payload["error"] and "svg" in payload["error"]


def test_output_missing_suffix_returns_json_error(tmp_path: Path) -> None:
    result = run_fixture("bar_cn.json", tmp_path, output_name="chart")
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "png" in payload["error"] and "svg" in payload["error"]


# --output 必填 ------------------------------------------------------------------

def test_missing_output_returns_json_error() -> None:
    result = run_cli("--data", f"@{FIXTURES / 'bar_cn.json'}")
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["ok"] is False
    assert "--output" in payload["error"]


# --data 必填（与 stdin 二选一）------------------------------------------------

def test_missing_data_with_closed_stdin_returns_json_error(tmp_path: Path) -> None:
    result = run_cli("--output", str(tmp_path / "out.png"), stdin="")
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False


# --- 图表类型回归 -------------------------------------------------------------

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


def test_cli_renders_stacked_series_bar_png(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "bar",
            "title": "Sales by region",
            "subtitle": "Product contribution",
            "data": [
                {"region": "East", "product": "A", "sales": 12},
                {"region": "East", "product": "B", "sales": 8},
                {"region": "South", "product": "A", "sales": 10},
                {"region": "South", "product": "B", "sales": 11},
            ],
            "encoding": {"x": "region", "y": "sales", "series": "product"},
            "options": {"series_mode": "stacked"},
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
            options={"data_labels": True},
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
            options={"data_labels": True},
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


def test_bar_renderer_groups_series_and_draws_legend() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import bar

        spec = ChartSpec(
            chart_type="bar",
            title="Sales by region",
            subtitle="Grouped series should share each category",
            data=[
                {"region": "East", "product": "A", "sales": 10},
                {"region": "East", "product": "B", "sales": 20},
                {"region": "West", "product": "A", "sales": 15},
                {"region": "West", "product": "B", "sales": 5},
            ],
            encoding={"x": "region", "y": "sales", "series": "product"},
            options={},
        )

        fig = bar.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            assert [patch.get_height() for patch in ax.patches] == pytest.approx([10, 15, 20, 5])
            legend = ax.get_legend()
            assert legend is not None
            assert [text.get_text() for text in legend.get_texts()] == ["A", "B"]
            assert legend.get_bbox_to_anchor().transformed(ax.transAxes.inverted()).x0 > 1
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_bar_renderer_stacks_series_values() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import bar

        spec = ChartSpec(
            chart_type="bar",
            title="Sales by region",
            subtitle="Stacked series should accumulate within each category",
            data=[
                {"region": "East", "product": "A", "sales": 10},
                {"region": "East", "product": "B", "sales": 20},
                {"region": "West", "product": "A", "sales": 15},
                {"region": "West", "product": "B", "sales": 5},
            ],
            encoding={"x": "region", "y": "sales", "series": "product"},
            options={"series_mode": "stacked"},
        )

        fig = bar.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            assert [patch.get_height() for patch in ax.patches] == pytest.approx([10, 15, 20, 5])
            assert [patch.get_y() for patch in ax.patches] == pytest.approx([0, 0, 10, 15])
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_bar_renderer_normalizes_series_to_percent_stacks() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import bar

        spec = ChartSpec(
            chart_type="bar",
            title="Sales mix by region",
            subtitle="Percent stacks should total one hundred per category",
            data=[
                {"region": "East", "product": "A", "sales": 10},
                {"region": "East", "product": "B", "sales": 20},
                {"region": "West", "product": "A", "sales": 15},
                {"region": "West", "product": "B", "sales": 5},
            ],
            encoding={"x": "region", "y": "sales", "series": "product"},
            options={"series_mode": "percent_stacked"},
        )

        fig = bar.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            assert [patch.get_height() for patch in ax.patches] == pytest.approx([100 / 3, 75, 200 / 3, 25])
            assert [patch.get_y() for patch in ax.patches] == pytest.approx([0, 0, 100 / 3, 75])
            assert ax.get_ylabel() == "sales (%)"
            assert [text.get_text() for text in ax.texts] == ["33.3%", "75.0%", "66.7%", "25.0%"]
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_stacked_bar_type_is_not_supported(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "stacked_bar",
            "title": "Legacy stacked bar",
            "subtitle": "Only the bar entry point is supported",
            "data": [{"region": "East", "product": "A", "sales": 10}],
            "encoding": {"x": "region", "series": "product", "value": "sales"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "stacked_bar" not in payload["error"]


def test_percent_stacked_bar_rejects_negative_values(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "bar",
            "title": "Sales mix",
            "subtitle": "Percent stacks require non-negative values",
            "data": [
                {"region": "East", "product": "A", "sales": 10},
                {"region": "East", "product": "B", "sales": -5},
            ],
            "encoding": {"x": "region", "y": "sales", "series": "product"},
            "options": {"series_mode": "percent_stacked"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "percent_stacked" in payload["error"]


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


def test_line_renderer_groups_by_series_and_draws_legend() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import line

        spec = ChartSpec(
            chart_type="line",
            title="Revenue by segment",
            subtitle="Series should render as separate lines with a legend",
            data=[
                {"month": "Jan", "segment": "Enterprise", "revenue": 10},
                {"month": "Feb", "segment": "Enterprise", "revenue": 14},
                {"month": "Jan", "segment": "SMB", "revenue": 6},
                {"month": "Feb", "segment": "SMB", "revenue": 9},
            ],
            encoding={"x": "month", "y": "revenue", "series": "segment"},
            options={},
        )

        fig = line.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            assert len(ax.lines) == 2
            assert [line_object.get_label() for line_object in ax.lines] == ["Enterprise", "SMB"]
            assert [list(line_object.get_ydata()) for line_object in ax.lines] == [
                pytest.approx([10, 14]),
                pytest.approx([6, 9]),
            ]
            legend = ax.get_legend()
            assert legend is not None
            assert [text.get_text() for text in legend.get_texts()] == ["Enterprise", "SMB"]
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_line_renderer_smooths_each_series_and_can_hide_markers() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import line

        spec = ChartSpec(
            chart_type="line",
            title="Revenue by segment",
            subtitle="Smooth lines should retain the original observations separately",
            data=[
                {"month": "Jan", "segment": "Enterprise", "revenue": 10},
                {"month": "Feb", "segment": "Enterprise", "revenue": 14},
                {"month": "Mar", "segment": "Enterprise", "revenue": 12},
                {"month": "Jan", "segment": "SMB", "revenue": 6},
                {"month": "Feb", "segment": "SMB", "revenue": 9},
                {"month": "Mar", "segment": "SMB", "revenue": 8},
            ],
            encoding={"x": "month", "y": "revenue", "series": "segment"},
            options={"markers": False, "smooth": True},
        )

        fig = line.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            assert len(ax.lines) == 2
            assert [line_object.get_label() for line_object in ax.lines] == ["Enterprise", "SMB"]
            assert all(len(line_object.get_xdata()) > 3 for line_object in ax.lines)
            assert all(line_object.get_marker() == "None" for line_object in ax.lines)
            assert not ax.collections
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_line_options_reject_non_boolean_marker_flag(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "line",
            "title": "DAU trend",
            "subtitle": "Boolean line options only",
            "data": [{"week": "W1", "dau": 12}, {"week": "W2", "dau": 18}],
            "encoding": {"x": "week", "y": "dau"},
            "options": {"markers": "yes"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "options.markers" in payload["error"]


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


def test_combo_renderer_uses_left_axis_for_bars_and_right_axis_for_line() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import combo

        spec = ChartSpec(
            chart_type="combo",
            title="Revenue and conversion",
            subtitle="Bars use the left axis and the line uses the right axis",
            data=[
                {"month": "Jan", "revenue": 120, "conversion": 0.12},
                {"month": "Feb", "revenue": 150, "conversion": 0.16},
                {"month": "Mar", "revenue": 135, "conversion": 0.14},
            ],
            encoding={"x": "month", "bar": "revenue", "line": "conversion"},
            options={"data_labels": True},
        )

        fig = combo.render(spec, dpi=144)
        left, right = fig.axes
        try:
            assert [patch.get_height() for patch in left.patches] == pytest.approx([120, 150, 135])
            assert left.get_ylabel() == "revenue"
            assert list(right.lines[0].get_ydata()) == pytest.approx([0.12, 0.16, 0.14])
            assert right.get_ylabel() == "conversion"
            assert left.get_legend() is None
            assert len(fig.legends) == 1
            legend = fig.legends[0]
            assert legend is not None
            assert [text.get_text() for text in legend.get_texts()] == ["revenue", "conversion"]
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            legend_box = legend.get_window_extent(renderer)
            right_axis_box = right.get_tightbbox(renderer)
            assert not legend_box.overlaps(right_axis_box)
            assert {text.get_text() for text in left.texts} == {"120", "150", "135"}
            assert {text.get_text() for text in right.texts} == {"0.12", "0.16", "0.14"}
            assert all(text.get_position()[0] < index for index, text in enumerate(left.texts))
            assert all(text.xy[0] > index for index, text in enumerate(right.texts))
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_header_layout_keeps_multiline_title_above_subtitle() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.theme import prepare_axes

        spec = ChartSpec(
            chart_type="bar",
            title="Revenue performance across strategic accounts\nand priority market segments",
            subtitle="Monthly view with the latest booked revenue and forecast context",
            data=[{"month": "Jan", "revenue": 120}],
            encoding={"x": "month", "y": "revenue"},
            options={},
        )
        fig, ax = prepare_axes(spec, dpi=144)
        try:
            title, subtitle = fig.texts[:2]
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            title_box = title.get_window_extent(renderer).transformed(fig.transFigure.inverted())
            subtitle_box = subtitle.get_window_extent(renderer).transformed(fig.transFigure.inverted())
            assert title_box.y0 > subtitle_box.y1
            assert ax.get_position().y1 < subtitle_box.y0
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_combo_renderer_uses_axis_label_overrides() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import combo

        spec = ChartSpec(
            chart_type="combo",
            title="Revenue and conversion",
            subtitle="Display labels should not expose field names",
            data=[{"week": "W1", "revenue": 120, "conversion": 12}, {"week": "W2", "revenue": 138, "conversion": 15}],
            encoding={"x": "week", "bar": "revenue", "line": "conversion"},
            options={"axis_labels": {"x": "周", "bar": "收入（万元）", "line": "转化率（%）"}},
        )
        fig = combo.render(spec, dpi=144)
        left, right = fig.axes
        try:
            assert left.get_xlabel() == "周"
            assert left.get_ylabel() == "收入（万元）"
            assert right.get_ylabel() == "转化率（%）"
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_line_renderer_adds_raw_point_labels_when_enabled() -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from matplotlib import pyplot as plt

        from chart_renderer.contract import ChartSpec
        from chart_renderer.renderers import line

        spec = ChartSpec(
            chart_type="line",
            title="DAU trend",
            subtitle="Labels should use raw values",
            data=[{"week": "W1", "dau": 12}, {"week": "W2", "dau": 18}],
            encoding={"x": "week", "y": "dau"},
            options={"data_labels": True},
        )
        fig = line.render(spec, dpi=144)
        ax = fig.axes[0]
        try:
            assert [text.get_text() for text in ax.texts] == ["12", "18"]
        finally:
            plt.close(fig)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def test_cli_renders_waterfall_png(tmp_path: Path) -> None:
    result = run_fixture("waterfall.json", tmp_path)
    payload = parse_stdout(result)
    assert result.returncode == 0, result.stderr
    output = Path(payload["path"])
    assert output.exists()
    assert_output_under_directory(output, tmp_path)
    assert_readable_image(output)


# --- 契约 / 参数错误 ----------------------------------------------------------

def test_missing_title_returns_json_error(tmp_path: Path) -> None:
    result = run_spec(
        {"type": "bar", "subtitle": "x", "data": [], "encoding": {}},
        tmp_path,
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
    result = run_spec(
        {
            "type": "bar",
            "title": "Bad",
            "subtitle": "Missing field",
            "data": [{"name": "A", "value": 1}],
            "encoding": {"x": "name", "y": "missing"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "missing" in payload["error"]


def test_non_numeric_encoding_field_returns_json_error(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "bar",
            "title": "Bad numeric",
            "subtitle": "One row is not numeric",
            "data": [{"name": "A", "value": 1}, {"name": "B", "value": "oops"}],
            "encoding": {"x": "name", "y": "value"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "numeric" in payload["error"]


def test_null_numeric_encoding_field_returns_json_error(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "bar",
            "title": "Bad numeric",
            "subtitle": "One row is null",
            "data": [{"name": "A", "value": 1}, {"name": "B", "value": None}],
            "encoding": {"x": "name", "y": "value"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "numeric" in payload["error"]
    assert "row 1" in payload["error"]


def test_optional_encoding_field_missing_returns_json_error(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "bar",
            "title": "Bad optional",
            "subtitle": "Missing optional encoded field",
            "data": [{"month": "Jan", "value": 10}, {"month": "Feb", "value": 20}],
            "encoding": {"x": "month", "y": "value", "color": "segment"},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "segment" in payload["error"]


def test_invalid_dpi_returns_json_error(tmp_path: Path) -> None:
    result = run_fixture("bar_cn.json", tmp_path, extra=("--dpi", "not-a-number"))
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["ok"] is False
    assert "dpi" in payload["error"]


def test_value_labels_option_is_rejected(tmp_path: Path) -> None:
    result = run_spec(
        {
            "type": "bar",
            "title": "Legacy option",
            "subtitle": "Only data_labels is supported",
            "data": [{"category": "A", "value": 10}],
            "encoding": {"x": "category", "y": "value"},
            "options": {"value_labels": True},
        },
        tmp_path,
    )
    payload = parse_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert "data_labels" in payload["error"]


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


def test_cli_threads_dpi_and_fmt_into_render_chart(monkeypatch, tmp_path: Path) -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from chart_renderer import cli as cli_module
        from chart_renderer.contract import ChartSpec

        captured: dict[str, object] = {}

        def fake_read_data_source(options: dict) -> dict:
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

        def fake_render_chart(spec: ChartSpec, output_path: Path, fmt: str, dpi: int) -> list[str]:
            captured["dpi"] = dpi
            captured["fmt"] = fmt
            captured["path"] = output_path
            # 触发 ensure_output_parent 已建好目录，render_chart 跳过真实渲染
            output_path.write_bytes(b"")
            return []

        monkeypatch.setattr(cli_module, "read_data_source", fake_read_data_source)
        monkeypatch.setattr(cli_module, "validate", fake_validate)
        monkeypatch.setattr(cli_module, "render_chart", fake_render_chart)
        monkeypatch.setattr(cli_module, "ensure_output_exists", lambda path: None)
        monkeypatch.setattr(cli_module, "ensure_png_nonblank", lambda path: None)

        output_path = tmp_path / "deep" / "out.svg"
        result = cli_module.main(
            ["--data", f"@{FIXTURES / 'bar_cn.json'}", "--output", str(output_path), "--dpi", "288"]
        )
        assert result == 0
        assert captured["dpi"] == 288
        assert captured["fmt"] == "svg"
        assert captured["path"] == output_path
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
