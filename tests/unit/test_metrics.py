"""
Testes para MetricsCollector e StepMetrics.

Cobertura: start_step, register, export_json, print_summary,
StepMetrics properties (duration_s, throughput_fps, compression_ratio).
"""

from __future__ import annotations

import json

import pytest

from emupipeline.core.metrics import MetricsCollector, StepMetrics


class TestStepMetrics:
    def test_finish_sets_end_time(self):
        m = StepMetrics(step_name="test")
        assert m.end_time == 0.0
        m.finish()
        assert m.end_time > 0.0

    def test_duration_positive_after_finish(self):
        m = StepMetrics(step_name="test")
        m.finish()
        assert m.duration_s >= 0.0

    def test_duration_fallback_before_finish(self):
        """Antes de finish(), duration_s usa time.monotonic() internamente."""
        m = StepMetrics(step_name="test")
        # end_time == 0.0 → duration usa monotonic() como fallback
        assert m.duration_s >= 0.0

    def test_throughput_fps_zero_when_no_files(self):
        m = StepMetrics(step_name="test")
        m.finish()
        assert m.throughput_fps == 0.0

    def test_throughput_fps_positive_with_files(self):
        m = StepMetrics(step_name="test")
        m.files_processed = 10
        m.finish()
        assert m.throughput_fps > 0.0

    def test_compression_ratio_default_is_one(self):
        m = StepMetrics(step_name="test")
        assert m.compression_ratio == 1.0

    def test_compression_ratio_with_bytes(self):
        m = StepMetrics(step_name="test", bytes_in=1000, bytes_out=500)
        assert m.compression_ratio == pytest.approx(0.5)

    def test_to_dict_contains_step_name(self):
        m = StepMetrics(step_name="MyStep")
        m.finish()
        d = m.to_dict()
        assert d["step"] == "MyStep"

    def test_to_dict_contains_all_required_keys(self):
        m = StepMetrics(step_name="s")
        m.finish()
        d = m.to_dict()
        for key in ("duration_s", "files_total", "files_processed",
                    "files_skipped", "files_error", "throughput_fps",
                    "bytes_in", "bytes_out", "compression_ratio"):
            assert key in d

    def test_to_dict_includes_extra(self):
        m = StepMetrics(step_name="s", extra={"custom": "value"})
        m.finish()
        d = m.to_dict()
        assert d["custom"] == "value"


class TestMetricsCollector:
    def test_start_step_returns_step_metrics(self):
        collector = MetricsCollector()
        m = collector.start_step("step1")
        assert isinstance(m, StepMetrics)
        assert m.step_name == "step1"

    def test_start_step_appends_to_internal_list(self):
        collector = MetricsCollector()
        collector.start_step("a")
        collector.start_step("b")
        assert len(collector._steps) == 2

    def test_register_appends_existing_metrics(self):
        collector = MetricsCollector()
        m = StepMetrics(step_name="external")
        m.finish()
        collector.register(m)
        assert len(collector._steps) == 1
        assert collector._steps[0] is m

    def test_export_json_creates_file(self, tmp_path):
        collector = MetricsCollector(run_id="test-run")
        m = collector.start_step("step1")
        m.files_processed = 5
        m.finish()
        out = tmp_path / "metrics.json"
        collector.export_json(out)
        assert out.exists()

    def test_export_json_valid_json(self, tmp_path):
        collector = MetricsCollector(run_id="test-run")
        m = collector.start_step("step1")
        m.finish()
        out = tmp_path / "metrics.json"
        collector.export_json(out)
        data = json.loads(out.read_text())
        assert data["run_id"] == "test-run"
        assert "steps" in data
        assert len(data["steps"]) == 1

    def test_export_json_creates_parent_dir(self, tmp_path):
        collector = MetricsCollector()
        out = tmp_path / "subdir" / "metrics.json"
        collector.export_json(out)
        assert out.exists()

    def test_export_json_pipeline_duration_is_sum(self, tmp_path):
        collector = MetricsCollector()
        # Two manually crafted metrics with fixed start/end times
        m1 = StepMetrics(step_name="a", start_time=0.0, end_time=1.0)
        m2 = StepMetrics(step_name="b", start_time=0.0, end_time=2.0)
        collector.register(m1)
        collector.register(m2)
        out = tmp_path / "m.json"
        collector.export_json(out)
        data = json.loads(out.read_text())
        assert data["pipeline_duration_s"] == pytest.approx(3.0, abs=0.01)

    def test_print_summary_does_not_raise(self, capsys):
        collector = MetricsCollector(run_id="pr")
        m = collector.start_step("step1")
        m.files_processed = 3
        m.bytes_in = 300
        m.bytes_out = 150
        m.finish()
        collector.print_summary()
        captured = capsys.readouterr()
        assert "MÉTRICAS" in captured.out
        assert "step1" in captured.out

    def test_print_summary_shows_dash_when_no_bytes(self, capsys):
        collector = MetricsCollector(run_id="pr")
        m = collector.start_step("step1")
        m.finish()
        collector.print_summary()
        captured = capsys.readouterr()
        assert "—" in captured.out

    def test_run_id_auto_generated_when_none(self):
        collector = MetricsCollector()
        assert collector.run_id.startswith("run_")
