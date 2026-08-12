"""
Shared fixtures.

We import editor.py as a module (rather than relying on package layout)
because it's a single-file script. Importing it is safe: the Flask dev
server only starts under `if __name__ == '__main__'`.
"""
import importlib.util
import pathlib
import sys

import pytest

EDITOR_PATH = pathlib.Path(__file__).parent.parent / "editor.py"


def _load_editor_module():
    spec = importlib.util.spec_from_file_location("editor_under_test", EDITOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def editor():
    """The editor.py module under test."""
    return _load_editor_module()


@pytest.fixture()
def project_dir(tmp_path, editor, monkeypatch):
    """
    Point the app at an isolated temp folder for this test, standing in for
    a real Ren'Py project directory. Using the real filesystem (rather than
    mocking `open`/`os.path.exists`) means the tests exercise the same code
    path production traffic does.
    """
    monkeypatch.setattr(editor, "PROJECT_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def client(editor):
    editor.app.config["TESTING"] = True
    return editor.app.test_client()


@pytest.fixture()
def sample_rpy_text():
    fixture_path = pathlib.Path(__file__).parent / "fixtures" / "sample_scene.rpy"
    return fixture_path.read_text(encoding="utf-8")
