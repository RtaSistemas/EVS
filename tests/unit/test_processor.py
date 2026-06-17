"""
Testes para BaseProcessor — thread-safety, stats, scan, ExecutionMode.

Prioridade P1.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor, ExecutorType


class ConcreteProcessor(BaseProcessor):
    """Implementação mínima para testar a engine."""
    def process_file(self, file_path: Path) -> str:
        return "processed"


class SlowProcessor(BaseProcessor):
    """Simula processamento com delay."""
    def process_file(self, file_path: Path) -> str:
        time.sleep(0.005)
        return "processed"


class ErrorProcessor(BaseProcessor):
    """Sempre lança exceção."""
    def process_file(self, file_path: Path) -> str:
        raise ValueError("Erro proposital para teste")


class DryRunAwareProcessor(BaseProcessor):
    """Respeita dry_run no process_file."""
    def process_file(self, file_path: Path) -> str:
        if self.dry_run:
            return "dry_run"
        return "processed"


class AuditAwareProcessor(BaseProcessor):
    def process_file(self, file_path: Path) -> str:
        if self.audit_mode:
            assert self._audit is not None
            self._audit.record(
                step=self.name, action="process",
                source=str(file_path),
            )
            return "audit_recorded"
        return "processed"


class TestBaseProcessorStats:
    def test_stats_accumulate_correctly(self, config_factory, tmp_project):
        config_factory()
        files = []
        for i in range(10):
            f = tmp_project / f"file_{i}.png"
            f.write_text("x")
            files.append(f)

        proc = ConcreteProcessor("test", mode=ExecutionMode.NORMAL)
        proc.run_parallel(files, threads=2)
        assert proc.get_stats()["processed"] == 10

    def test_stats_are_thread_safe(self, config_factory, tmp_project):
        """100 arquivos com 8 threads — stats deve somar exatamente 100."""
        config_factory()
        files = []
        for i in range(100):
            f = tmp_project / f"f_{i}.png"
            f.write_text("x")
            files.append(f)

        proc = SlowProcessor("test", mode=ExecutionMode.NORMAL)
        proc.run_parallel(files, threads=8)
        assert proc.get_stats()["processed"] == 100

    def test_errors_do_not_crash_executor(self, config_factory, tmp_project):
        """Exceções em process_file são capturadas e contadas como 'error'."""
        config_factory()
        files = [tmp_project / f"f_{i}.png" for i in range(5)]
        for f in files:
            f.write_text("x")

        proc = ErrorProcessor("test", mode=ExecutionMode.NORMAL)
        proc.run_parallel(files, threads=2)
        assert proc.get_stats().get("error", 0) == 5

    def test_update_stat_is_atomic(self, config_factory):
        config_factory()
        import threading
        proc = ConcreteProcessor("test")
        results = []

        def bump():
            for _ in range(1000):
                proc.update_stat("counter")
            results.append(True)

        threads = [threading.Thread(target=bump) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert proc.get_stats()["counter"] == 4000


class TestBaseProcessorScan:
    def test_scan_finds_files_by_extension(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "a.png").write_text("x")
        (tmp_project / "b.jpg").write_text("x")
        (tmp_project / "c.txt").write_text("x")

        proc = ConcreteProcessor("test")
        files = proc.scan(tmp_project, extensions={".png", ".jpg"}, recursive=False)
        assert len(files) == 2
        suffixes = {f.suffix for f in files}
        assert ".txt" not in suffixes

    def test_scan_ignores_hidden_files(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / ".hidden_file").write_text("x")
        (tmp_project / "visible.png").write_text("x")

        proc = ConcreteProcessor("test")
        files = proc.scan(tmp_project, recursive=False)
        assert all(not f.name.startswith(".") for f in files)

    def test_scan_nonexistent_directory(self, config_factory, tmp_project):
        config_factory()
        proc = ConcreteProcessor("test")
        files = proc.scan(tmp_project / "nonexistent")
        assert files == []

    def test_scan_recursive(self, config_factory, tmp_project):
        config_factory()
        subdir = tmp_project / "subdir"
        subdir.mkdir()
        (subdir / "deep.png").write_text("x")
        (tmp_project / "top.png").write_text("x")

        proc = ConcreteProcessor("test")
        files = proc.scan(tmp_project, extensions={".png"}, recursive=True)
        assert len(files) == 2


class TestExecutionMode:
    def test_dry_run_property_reads_mode(self, config_factory):
        config_factory()
        proc = ConcreteProcessor("test", mode=ExecutionMode.DRY_RUN)
        assert proc.dry_run is True
        assert proc.audit_mode is False

    def test_audit_mode_property(self, config_factory):
        config_factory()
        audit = AuditReport()
        proc = AuditAwareProcessor("test", mode=ExecutionMode.AUDIT, audit=audit)
        assert proc.audit_mode is True

    def test_dry_run_setter_changes_mode(self, config_factory):
        config_factory()
        proc = ConcreteProcessor("test")
        assert proc.dry_run is False
        proc.dry_run = True
        assert proc.dry_run is True
        assert proc._mode == ExecutionMode.DRY_RUN

    def test_mode_not_shared_between_instances(self, config_factory):
        """O modo de uma instância não afeta outra — sem monkey-patch de classe."""
        config_factory()
        p1 = ConcreteProcessor("p1", mode=ExecutionMode.DRY_RUN)
        p2 = ConcreteProcessor("p2", mode=ExecutionMode.NORMAL)
        assert p1.dry_run is True
        assert p2.dry_run is False

    def test_audit_records_via_report(self, config_factory, tmp_project):
        config_factory()
        audit = AuditReport()
        files = [tmp_project / f"f_{i}.png" for i in range(3)]
        for f in files:
            f.write_text("x")

        proc = AuditAwareProcessor("test", mode=ExecutionMode.AUDIT, audit=audit)
        proc.run_parallel(files, threads=2)
        assert audit.total == 3


class TestExecutorType:
    def test_default_is_thread(self, config_factory):
        config_factory()
        proc = ConcreteProcessor("test")
        assert proc._executor_type == ExecutorType.THREAD

    def test_process_executor_created(self, config_factory):
        from concurrent.futures import ProcessPoolExecutor
        config_factory()

        class ProcessProc(BaseProcessor):
            _executor_type = ExecutorType.PROCESS
            def process_file(self, f: Path) -> str:
                return "processed"

        proc = ProcessProc("test")
        executor = proc._make_executor(2)
        assert isinstance(executor, ProcessPoolExecutor)
        executor.shutdown(wait=False)
