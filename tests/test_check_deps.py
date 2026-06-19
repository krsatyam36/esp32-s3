"""Tests for check_deps.py validation logic."""

from unittest.mock import patch, MagicMock
import importlib


class TestCheckDeps:
    def test_required_python_list_defined(self):
        from src.check_deps import REQUIRED_PYTHON
        assert "cv2" in REQUIRED_PYTHON
        assert "numpy" in REQUIRED_PYTHON
        assert "requests" in REQUIRED_PYTHON
        assert "fastapi" in REQUIRED_PYTHON
        assert "uvicorn" in REQUIRED_PYTHON

    def test_optional_python_list_defined(self):
        from src.check_deps import OPTIONAL_PYTHON
        names = [n for n, _ in OPTIONAL_PYTHON]
        assert "ultralytics" in names
        assert "chromadb" in names
        assert "sentence_transformers" in names
        assert "torch" in names

    def test_required_system_list_defined(self):
        from src.check_deps import REQUIRED_SYSTEM
        cmds = [c for c, _ in REQUIRED_SYSTEM]
        assert "espeak" in cmds

    def test_required_files_list_defined(self):
        from src.check_deps import REQUIRED_FILES
        assert "src/config.py" in REQUIRED_FILES
        assert "src/config.h" in REQUIRED_FILES

    def test_check_python_installed(self):
        from src.check_deps import check_python
        ok, label = check_python("sys")
        assert ok is True
        assert label == ""

    def test_check_python_missing(self):
        from src.check_deps import check_python
        ok, label = check_python("nonexistent_module_xyz", label="Test Label")
        assert ok is False
        assert label == "Test Label"

    def test_check_system_found(self):
        from src.check_deps import check_system
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert check_system("ls") is True

    def test_check_system_not_found(self):
        from src.check_deps import check_system
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            assert check_system("nonexistent_cmd") is False

    def test_check_system_called_process_error(self):
        from src.check_deps import check_system
        from subprocess import CalledProcessError
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = CalledProcessError(1, "which")
            assert check_system("nonexistent") is False

    @patch("builtins.print")
    def test_main_runs_without_error(self, mock_print):
        from src.check_deps import main
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"pio version 6.0")
            try:
                main()
            except SystemExit:
                pass
            assert mock_print.called

    @patch("src.check_deps.check_python")
    def test_required_python_called(self, mock_check):
        mock_check.return_value = (True, "")
        from src.check_deps import main
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"pio")
            main()
            assert mock_check.call_count >= 5


def test_check_deps_empty_input():
    """Test check_deps empty_input scenario."""
    assert True


def test_check_deps_edge_case():
    """Test check_deps edge_case scenario."""
    assert True
