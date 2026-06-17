"""
Testes para ExecutionMode e AuditReport.

Cobertura alvo: 90%
Foco em:
  - AuditReport é thread-safe
  - export_json gera JSON válido
  - export_html gera HTML válido
  - contadores (total, destructive_count) corretos
  - print_summary não lança exceção
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from emupipeline.core.execution_mode import AuditEntry, AuditReport, ExecutionMode


# ---------------------------------------------------------------------------
# ExecutionMode enum
# ---------------------------------------------------------------------------

class TestExecutionMode:
    def test_three_modes_exist(self):
        assert ExecutionMode.NORMAL
        assert ExecutionMode.DRY_RUN
        assert ExecutionMode.AUDIT

    def test_modes_are_distinct(self):
        assert ExecutionMode.NORMAL != ExecutionMode.DRY_RUN
        assert ExecutionMode.DRY_RUN != ExecutionMode.AUDIT


# ---------------------------------------------------------------------------
# AuditReport — registros
# ---------------------------------------------------------------------------

class TestAuditReport:
    def test_empty_on_creation(self):
        report = AuditReport()
        assert report.total == 0
        assert report.destructive_count == 0

    def test_record_adds_entry(self):
        report = AuditReport()
        report.record(step="TestStep", action="copy", source="/a/file.png", dest="/b/file.png")
        assert report.total == 1

    def test_destructive_count_counts_deletions(self):
        report = AuditReport()
        report.record(step="S", action="copy", source="a", would_delete=False)
        report.record(step="S", action="delete_original", source="b", would_delete=True)
        report.record(step="S", action="delete_original", source="c", would_delete=True)
        assert report.destructive_count == 2

    def test_entries_returns_copy(self):
        report = AuditReport()
        report.record(step="S", action="copy", source="a")
        entries1 = report.entries()
        entries2 = report.entries()
        assert entries1 is not entries2  # nova lista a cada chamada

    def test_extra_kwargs_stored(self):
        report = AuditReport()
        report.record(step="S", action="convert", source="a", codec="libx265", crf=28)
        entry = report.entries()[0]
        assert entry.extra.get("codec") == "libx265"
        assert entry.extra.get("crf") == 28


# ---------------------------------------------------------------------------
# Thread-safety
# ---------------------------------------------------------------------------

class TestAuditReportThreadSafety:
    def test_concurrent_records_are_all_captured(self):
        """100 threads registrando ao mesmo tempo → todas as 100 entradas capturadas."""
        report = AuditReport()
        n = 100

        def worker(i: int) -> None:
            report.record(step="Thread", action="op", source=f"file_{i}.png")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert report.total == n

    def test_concurrent_reads_while_writing(self):
        """Leituras concorrentes durante escrita não causam crash."""
        report = AuditReport()
        errors = []

        def writer() -> None:
            for i in range(50):
                try:
                    report.record(step="W", action="op", source=f"f{i}")
                except Exception as e:
                    errors.append(e)

        def reader() -> None:
            for _ in range(50):
                try:
                    _ = report.total
                    _ = report.entries()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer if i < 5 else reader)
                   for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


# ---------------------------------------------------------------------------
# Exportação JSON
# ---------------------------------------------------------------------------

class TestAuditReportExportJson:
    def test_exports_valid_json(self, tmp_path):
        report = AuditReport()
        report.record(step="Convert", action="to_webp", source="/a/sf2.png",
                      dest="/b/sf2.webp", reason="PNG → WebP")

        out = tmp_path / "audit.json"
        report.export_json(out)

        assert out.exists()
        data = json.loads(out.read_text())
        assert data["mode"] == "AUDIT"
        assert data["total_operations"] == 1
        assert len(data["operations"]) == 1

    def test_json_contains_all_fields(self, tmp_path):
        report = AuditReport()
        report.record(
            step="Optimize", action="encode_h265", source="/videos/game.avi",
            dest="/videos/game.mp4", reason="mpeg4 → hevc", would_delete=True
        )
        out = tmp_path / "audit.json"
        report.export_json(out)

        data = json.loads(out.read_text())
        op = data["operations"][0]
        assert op["step"] == "Optimize"
        assert op["would_delete"] is True
        assert op["dest"] == "/videos/game.mp4"

    def test_creates_parent_dirs(self, tmp_path):
        report = AuditReport()
        report.record(step="S", action="a", source="b")
        nested = tmp_path / "deep" / "nested" / "audit.json"
        report.export_json(nested)
        assert nested.exists()

    def test_empty_report_exports_cleanly(self, tmp_path):
        report = AuditReport()
        out = tmp_path / "empty.json"
        report.export_json(out)
        data = json.loads(out.read_text())
        assert data["total_operations"] == 0
        assert data["operations"] == []


# ---------------------------------------------------------------------------
# Exportação HTML
# ---------------------------------------------------------------------------

class TestAuditReportExportHtml:
    def test_exports_html_file(self, tmp_path):
        report = AuditReport()
        report.record(step="S", action="copy", source="/a/sf2.png", dest="/b/sf2.png")
        out = tmp_path / "audit.html"
        report.export_html(out)
        assert out.exists()

    def test_html_contains_step_name(self, tmp_path):
        report = AuditReport()
        report.record(step="WebPConverter", action="convert", source="sf2.png")
        out = tmp_path / "audit.html"
        report.export_html(out)
        content = out.read_text()
        assert "WebPConverter" in content

    def test_html_marks_destructive(self, tmp_path):
        report = AuditReport()
        report.record(step="S", action="delete", source="f.png", would_delete=True)
        out = tmp_path / "audit.html"
        report.export_html(out)
        content = out.read_text()
        assert "destructive" in content or "🗑" in content

    def test_html_is_valid_structure(self, tmp_path):
        report = AuditReport()
        report.record(step="S", action="a", source="b")
        out = tmp_path / "audit.html"
        report.export_html(out)
        content = out.read_text()
        assert "<!DOCTYPE html>" in content
        assert "<table>" in content
        assert "</html>" in content


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------

class TestPrintSummary:
    def test_print_summary_does_not_raise(self, capsys):
        report = AuditReport()
        report.record(step="S1", action="copy", source="a")
        report.record(step="S1", action="copy", source="b")
        report.record(step="S2", action="delete", source="c", would_delete=True)
        report.print_summary()
        captured = capsys.readouterr()
        assert "AUDIT REPORT" in captured.out
        assert "S1" in captured.out
