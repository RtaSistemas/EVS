"""
Coleta de métricas por step: tempo, throughput, compressão.

Sem dependência de biblioteca externa — stdlib apenas.
Exporta JSON para análise posterior ou integração com Prometheus/Grafana.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StepMetrics:
    step_name:       str
    start_time:      float = field(default_factory=time.monotonic)
    end_time:        float = 0.0
    files_total:     int   = 0
    files_processed: int   = 0
    files_skipped:   int   = 0
    files_error:     int   = 0
    bytes_in:        int   = 0
    bytes_out:       int   = 0
    extra:           dict[str, Any] = field(default_factory=dict)

    def finish(self) -> None:
        self.end_time = time.monotonic()

    @property
    def duration_s(self) -> float:
        return (self.end_time or time.monotonic()) - self.start_time

    @property
    def throughput_fps(self) -> float:
        return self.files_processed / self.duration_s if self.duration_s > 0 else 0.0

    @property
    def compression_ratio(self) -> float:
        """< 1.0 significa que o arquivo ficou menor."""
        return self.bytes_out / self.bytes_in if self.bytes_in > 0 else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step":              self.step_name,
            "duration_s":        round(self.duration_s, 3),
            "files_total":       self.files_total,
            "files_processed":   self.files_processed,
            "files_skipped":     self.files_skipped,
            "files_error":       self.files_error,
            "throughput_fps":    round(self.throughput_fps, 2),
            "bytes_in":          self.bytes_in,
            "bytes_out":         self.bytes_out,
            "compression_ratio": round(self.compression_ratio, 4),
            **self.extra,
        }


class MetricsCollector:
    """Agrega métricas de todos os steps de uma execução."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or f"run_{int(time.time())}"
        self._steps: list[StepMetrics] = []

    def start_step(self, name: str) -> StepMetrics:
        m = StepMetrics(step_name=name)
        self._steps.append(m)
        return m

    def export_json(self, output_path: Path) -> None:
        report = {
            "run_id":             self.run_id,
            "pipeline_duration_s": round(sum(s.duration_s for s in self._steps), 3),
            "steps":              [s.to_dict() for s in self._steps],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def print_summary(self) -> None:
        print(f"\n{'='*65}")
        print(f"MÉTRICAS — {self.run_id}")
        print(f"{'='*65}")
        print(f"  {'Step':<28} {'Tempo':>8}  {'arq/s':>7}  {'Compressão':>10}")
        print(f"  {'─'*28} {'─'*8}  {'─'*7}  {'─'*10}")
        for s in self._steps:
            ratio = f"{s.compression_ratio:.1%}" if s.bytes_in > 0 else "—"
            print(f"  {s.step_name:<28} {s.duration_s:>7.1f}s  {s.throughput_fps:>7.1f}  {ratio:>10}")
        total = sum(s.duration_s for s in self._steps)
        print(f"  {'─'*28} {'─'*8}")
        print(f"  {'TOTAL':<28} {total:>7.1f}s")
