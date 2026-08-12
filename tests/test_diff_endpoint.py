"""
Tests for /get_diff.

This endpoint's behavior is inseparable from git, so we test it against a
real git repository created in a temp directory rather than mocking
subprocess calls. Mocking `subprocess.run` here would mean re-encoding our
assumptions about git's CLI output into the mock, which tells us nothing
about whether the endpoint actually works against real git - exactly the
kind of fragile, false-confidence test Khorikov warns against for code
whose whole job is to talk to a real collaborator.

We keep the number of these git-backed tests small (a handful of key
scenarios) since they're slower and more complex to set up than the pure
extraction tests; the fine-grained line-classification logic is already
covered indirectly by asserting the specific 'type' returned per case.
"""
import subprocess

import pytest


def run_git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture()
def git_project_dir(project_dir):
    run_git("init", "-q", cwd=project_dir)
    run_git("config", "user.email", "test@example.com", cwd=project_dir)
    run_git("config", "user.name", "Test Runner", cwd=project_dir)
    return project_dir


def commit_file(git_project_dir, filename, content, message="commit"):
    path = git_project_dir / filename
    path.write_text(content, encoding="utf-8")
    run_git("add", filename, cwd=git_project_dir)
    run_git("commit", "-q", "-m", message, cwd=git_project_dir)


class TestGetDiffAvailability:
    def test_reports_unavailable_when_project_dir_is_not_a_git_repo(self, client, project_dir):
        (project_dir / "scene.rpy").write_text('cs "Text."\n', encoding="utf-8")

        response = client.get("/get_diff?file=scene.rpy")

        data = response.get_json()
        assert data["available"] is False

    def test_reports_unavailable_for_a_missing_file(self, client, git_project_dir):
        response = client.get("/get_diff?file=missing.rpy")

        assert response.get_json() == {"available": False, "reason": "Файл не найден"}

    def test_reports_available_for_an_unchanged_committed_file(self, client, git_project_dir):
        commit_file(git_project_dir, "scene.rpy", 'cs "Same text."\n')

        response = client.get("/get_diff?file=scene.rpy")

        data = response.get_json()
        assert data["available"] is True
        assert data["count"] == 1


class TestGetDiffClassification:
    def test_unchanged_line_is_not_flagged(self, client, git_project_dir):
        commit_file(git_project_dir, "scene.rpy", 'cs "Same text."\n')

        data = client.get("/get_diff?file=scene.rpy").get_json()

        assert data["diff"] == [None]

    def test_edited_line_is_flagged_changed_with_word_level_segments(self, client, git_project_dir):
        commit_file(git_project_dir, "scene.rpy", 'cs "Old text here."\n')
        (git_project_dir / "scene.rpy").write_text('cs "New text here."\n', encoding="utf-8")

        data = client.get("/get_diff?file=scene.rpy").get_json()

        assert len(data["diff"]) == 1
        assert data["diff"][0]["type"] == "changed"
        segment_texts = {seg["op"]: seg["text"] for seg in data["diff"][0]["segments"]}
        assert segment_texts["delete"] == "Old"
        assert segment_texts["insert"] == "New"

    def test_newly_added_line_is_flagged_new(self, client, git_project_dir):
        commit_file(git_project_dir, "scene.rpy", 'cs "First line."\n')
        (git_project_dir / "scene.rpy").write_text(
            'cs "First line."\nme "Brand new line."\n', encoding="utf-8"
        )

        data = client.get("/get_diff?file=scene.rpy").get_json()

        assert data["diff"] == [None, {"type": "new"}]

    def test_character_tagged_lines_are_compared_by_spoken_text_not_by_tag(
        self, client, git_project_dir
    ):
        """
        Regression guard: since diffing relies on the same extraction as
        /get_data, a line whose only change is its character tag (e.g.
        `cs "text"` -> `me "text"`) must NOT show up as a text change,
        because the *spoken words* are identical.
        """
        commit_file(git_project_dir, "scene.rpy", 'cs "Shared line."\n')
        (git_project_dir / "scene.rpy").write_text('me "Shared line."\n', encoding="utf-8")

        data = client.get("/get_diff?file=scene.rpy").get_json()

        assert data["diff"] == [None]
