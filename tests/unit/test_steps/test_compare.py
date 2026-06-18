"""
Testes para FolderComparator (step_compare.py).

Foco em: comparação correta de diretórios, stats, cópia de comuns.
"""

from __future__ import annotations

from emupipeline.core.execution_mode import ExecutionMode


class TestFolderComparatorBasic:
    def test_no_dirs_returns_early(self, config_factory, tmp_project):
        """Sem dir_a/dir_b e sem config, retorna sem crash."""
        config_factory()
        from emupipeline.steps.step_compare import FolderComparator

        comparator = FolderComparator()
        comparator.run()  # não deve levantar exceção
        assert comparator.get_stats() == {}

    def test_nonexistent_dirs_returns_early(self, config_factory, tmp_project):
        """Diretórios inexistentes retornam sem crash."""
        config_factory()
        from emupipeline.steps.step_compare import FolderComparator

        comparator = FolderComparator()
        comparator.run(dir_a="/nonexistent/a", dir_b="/nonexistent/b")
        assert comparator.get_stats() == {}

    def test_identical_dirs_all_common(self, config_factory, tmp_project):
        """Dois diretórios com os mesmos arquivos → tudo em common."""
        config_factory({"compare": {"copy_common": False, "output_dir": "output/common"}})
        from emupipeline.steps.step_compare import FolderComparator

        dir_a = tmp_project / "dir_a"
        dir_b = tmp_project / "dir_b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "sf2.png").write_bytes(b"data")
        (dir_b / "sf2.png").write_bytes(b"data")

        comparator = FolderComparator()
        comparator.run(dir_a=str(dir_a), dir_b=str(dir_b))

        stats = comparator.get_stats()
        assert stats["common"] == 1
        assert stats["only_a"] == 0
        assert stats["only_b"] == 0

    def test_exclusive_files_counted(self, config_factory, tmp_project):
        """Arquivos exclusivos de cada diretório são contados corretamente."""
        config_factory({"compare": {"copy_common": False, "output_dir": "output/common"}})
        from emupipeline.steps.step_compare import FolderComparator

        dir_a = tmp_project / "dir_a2"
        dir_b = tmp_project / "dir_b2"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "sf2.png").write_bytes(b"a")
        (dir_a / "kof97.png").write_bytes(b"a")
        (dir_b / "sf2.png").write_bytes(b"b")
        (dir_b / "tekken.png").write_bytes(b"b")

        comparator = FolderComparator()
        comparator.run(dir_a=str(dir_a), dir_b=str(dir_b))

        stats = comparator.get_stats()
        assert stats["common"] == 1   # sf2.png
        assert stats["only_a"] == 1   # kof97.png
        assert stats["only_b"] == 1   # tekken.png

    def test_copy_common_creates_output_files(self, config_factory, tmp_project):
        """Com copy_common=True, arquivos comuns são copiados para output_dir."""
        out_dir = tmp_project / "output" / "common_files"
        config_factory({"compare": {"copy_common": True, "output_dir": "output/common_files"}})
        from emupipeline.steps.step_compare import FolderComparator

        dir_a = tmp_project / "dir_copy_a"
        dir_b = tmp_project / "dir_copy_b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "sf2.png").write_bytes(b"common_content")
        (dir_b / "sf2.png").write_bytes(b"common_content")
        (dir_a / "kof97.png").write_bytes(b"only_in_a")

        comparator = FolderComparator(mode=ExecutionMode.NORMAL)
        comparator.run(dir_a=str(dir_a), dir_b=str(dir_b))

        assert out_dir.exists()
        assert (out_dir / "sf2.png").exists()
        assert (out_dir / "sf2.png").read_bytes() == b"common_content"
        assert not (out_dir / "kof97.png").exists()

    def test_copy_common_dry_run_does_not_copy(self, config_factory, tmp_project):
        """Em DRY_RUN, nenhum arquivo é copiado mesmo com copy_common=True."""
        config_factory({"compare": {"copy_common": True, "output_dir": "output/common_dry"}})
        from emupipeline.steps.step_compare import FolderComparator

        dir_a = tmp_project / "dir_dry_a"
        dir_b = tmp_project / "dir_dry_b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "sf2.png").write_bytes(b"data")
        (dir_b / "sf2.png").write_bytes(b"data")

        comparator = FolderComparator(mode=ExecutionMode.DRY_RUN)
        comparator.run(dir_a=str(dir_a), dir_b=str(dir_b))

        out = tmp_project / "output" / "common_dry"
        assert not out.exists()

    def test_copy_common_removes_existing_output_dir(self, config_factory, tmp_project):
        """Se output_dir já existe, deve ser removido antes de recriar."""
        config_factory({"compare": {"copy_common": True, "output_dir": "output/common_existing"}})
        from emupipeline.steps.step_compare import FolderComparator

        dir_a = tmp_project / "dir_exist_a"
        dir_b = tmp_project / "dir_exist_b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "sf2.png").write_bytes(b"fresh")
        (dir_b / "sf2.png").write_bytes(b"fresh")

        # Cria o output_dir com arquivo antigo antes de rodar
        out_dir = tmp_project / "output" / "common_existing"
        out_dir.mkdir(parents=True)
        (out_dir / "old_file.txt").write_bytes(b"old")

        comparator = FolderComparator(mode=ExecutionMode.NORMAL)
        comparator.run(dir_a=str(dir_a), dir_b=str(dir_b))

        # Arquivo antigo deve ter sido removido, novo copiado
        assert not (out_dir / "old_file.txt").exists()
        assert (out_dir / "sf2.png").exists()

    def test_stats_reset_on_each_run(self, config_factory, tmp_project):
        """Cada chamada a run() produz stats independentes."""
        config_factory({"compare": {"copy_common": False, "output_dir": "output/common"}})
        from emupipeline.steps.step_compare import FolderComparator

        dir_a = tmp_project / "dir_reset_a"
        dir_b = tmp_project / "dir_reset_b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "sf2.png").write_bytes(b"x")

        comparator = FolderComparator()
        comparator.run(dir_a=str(dir_a), dir_b=str(dir_b))

        assert comparator.get_stats()["only_a"] == 1
        assert comparator.get_stats()["common"] == 0
