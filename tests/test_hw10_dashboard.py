"""Exercise the Streamlit entry point against saved evidence only."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "scripts/hw10/dashboard.py"
SYNTHETIC = Path(__file__).parent / "fixtures/hw10_dashboard_synthetic"


def metric_values(app):
    assert not app.exception
    return {metric.label: metric.value for metric in app.metric}


@pytest.fixture(autouse=True)
def streamlit_import_path(monkeypatch):
    # Streamlit's server bootstrap adds this path. AppTest skips that bootstrap.
    monkeypatch.syspath_prepend(str(APP.parent))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("HW10_EVIDENCE_ROOT", raising=False)
    return AppTest.from_file(str(APP)).run()


def test_summary_counts_unique_api_completions_and_separates_latencies(app):
    metrics = metric_values(app)
    assert metrics == {
        "Completed requests": "3",
        "Cache hits": "1",
        "Cache misses": "2",
        "Cache hit rate": "33.3%",
        "Request error rate": "33.3%",
        "API latency (p50)": "1,200 ms",
        "API latency (p95)": "2,280 ms",
        "Cache-hit latency (p50)": "40 ms",
        "Cache-hit latency (p95)": "40 ms",
    }
    assert any("Synthetic" in warning.value for warning in app.warning)
    assert any("UTC" in caption.value and "Window" in caption.value for caption in app.caption)
    assert any("tracing/spans.jsonl" in caption.value for caption in app.caption)

    app.selectbox(key="summary_window").select("Latest hour").run()
    assert metric_values(app)["Completed requests"] == "1"

    app.selectbox(key="summary_window").select("Custom UTC dates").run()
    app.date_input[0].set_value((date(2026, 11, 8), date(2026, 11, 8))).run()
    assert metric_values(app)["Completed requests"] == "0"
    assert metric_values(app)["Request error rate"] == "—"
    assert any("No completed requests in this window" in info.value for info in app.info)


def test_evaluation_shows_stages_draft_final_and_judge_validation(app):
    app.radio(key="page").set_value("Evaluation").run()
    metrics = metric_values(app)
    assert metrics["Final − draft"] == "+1"
    assert metrics["Spearman correlation"] == "0.949"
    assert metrics["Mean absolute difference"] == "0.25 pts"
    assert metrics["Cases with score changes"] == "1 / 4 (25.0%)"
    assert metrics["Mean score change"] == "0.25 pts"
    assert metrics["Max score change"] == "1.00 pts"
    table = app.dataframe[0].value
    assert table["Stage"].tolist() == ["Planner", "Writer", "Reviewer"]
    assert table["Score / 5"].tolist() == [4, 3, 4]
    assert any("monthly rent" in text.value for text in app.text)


@pytest.mark.parametrize(
    ("trace_id", "banner_type", "label", "stages"),
    [
        ("synthetic-hit", "success", "Cache hit", ["api_request", "cache_lookup"]),
        (
            "synthetic-miss",
            "info",
            "Successful cache miss",
            [
                "api_request",
                "cache_lookup",
                "inbox",
                "planner",
                "tasks",
                "writer",
                "drafts",
                "reviewer",
                "final",
                "evaluation",
            ],
        ),
        (
            "synthetic-failure",
            "error",
            "Failed request",
            ["api_request", "cache_lookup", "inbox", "planner", "tasks", "writer"],
        ),
    ],
)
def test_trace_lookup_orders_spans_and_distinguishes_outcomes(
    app, trace_id, banner_type, label, stages
):
    app.radio(key="page").set_value("Trace Lookup").run()
    app.text_input(key="trace_id").set_value(trace_id).run()
    assert not app.exception
    assert any(label in banner.value for banner in getattr(app, banner_type))
    spans = app.dataframe[0].value
    assert spans["Stage"].tolist() == stages
    assert {"Start (UTC)", "End (UTC)", "Duration (ms)", "Status", "Error"} <= set(spans)
    if trace_id == "synthetic-failure":
        assert "Synthetic Writer failure" in spans["Error"].tolist()


def test_refresh_reads_new_evidence_and_handles_partial_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HW10_EVIDENCE_ROOT", str(tmp_path))
    app = AppTest.from_file(str(APP)).run()
    assert metric_values(app)["Completed requests"] == "0"
    assert metric_values(app)["Cache hit rate"] == "—"

    spans = tmp_path / "tracing/spans.jsonl"
    spans.parent.mkdir()
    shutil.copyfile(SYNTHETIC / "tracing/spans.jsonl", spans)
    app.button(key="refresh_evidence").click().run()
    assert metric_values(app)["Completed requests"] == "3"

    partial = {
        "trace_id": "partial",
        "stage": "writer",
        "status": "running",
        "start_time": "2026-11-09T18:00:00Z",
    }
    with spans.open("a", encoding="utf-8") as file:
        file.write(json.dumps(partial) + "\n{unfinished")
    app.run()
    assert metric_values(app)["Completed requests"] == "3"
    assert any("malformed" in warning.value for warning in app.warning)

    app.radio(key="page").set_value("Evaluation").run()
    assert not app.exception
    assert any("No saved pipeline scores" in info.value for info in app.info)

    app.radio(key="page").set_value("Trace Lookup").run()
    app.text_input(key="trace_id").set_value("unknown").run()
    assert any("No saved spans" in warning.value for warning in app.warning)
    app.text_input(key="trace_id").set_value("partial").run()
    assert not app.exception
    assert any("Incomplete trace" in warning.value for warning in app.warning)
    assert app.dataframe[0].value["Stage"].tolist() == ["writer"]


def test_evaluation_error_does_not_affect_api_error_rate(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    shutil.copytree(SYNTHETIC, evidence)
    monkeypatch.setenv("HW10_EVIDENCE_ROOT", str(evidence))
    spans = evidence / "evaluation/spans.jsonl"
    original = json.loads(spans.read_text(encoding="utf-8"))
    retry = {
        **original,
        "attempt": 2,
        "status": "error",
        "error": "Synthetic judge timeout",
    }
    with spans.open("a", encoding="utf-8") as file:
        file.write(json.dumps(retry) + "\n")
    app = AppTest.from_file(str(APP)).run()
    assert metric_values(app)["Request error rate"] == "33.3%"

    app.radio(key="page").set_value("Trace Lookup").run()
    next(button for button in app.button if button.label == "Successful miss").click().run()
    assert app.text_input(key="trace_id").value == "synthetic-miss"
    assert any("Successful cache miss" in info.value for info in app.info)
    assert "Synthetic judge timeout" in app.dataframe[0].value["Error"].tolist()


def test_incomplete_judge_passes_have_no_comparison_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("HW10_EVIDENCE_ROOT", str(tmp_path))
    validation = tmp_path / "evaluation/judge_validation.json"
    validation.parent.mkdir()
    validation.write_text(
        json.dumps({"status": "incomplete", "spearman": None, "repeatability": None}),
        encoding="utf-8",
    )
    app = AppTest.from_file(str(APP)).run()
    app.radio(key="page").set_value("Evaluation").run()
    assert metric_values(app) == {}
    assert any("Judge validation is incomplete" in warning.value for warning in app.warning)
