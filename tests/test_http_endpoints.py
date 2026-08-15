"""
Tests for /get_data and /save_data.

These are black-box HTTP tests: we write real .rpy files to a real temp
directory and drive the app only through its public HTTP surface (the test
client), asserting on the JSON responses a browser would actually receive.
No internal function is mocked or inspected, so these tests stay valid
even if the extraction/saving logic is refactored internally.
"""
import json


def write_rpy(project_dir, filename, content):
    path = project_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


class TestGetData:
    def test_returns_dialogue_text_for_lines_without_character_id(self, client, project_dir):
        write_rpy(project_dir, "scene.rpy", '"Just narration."\n')

        response = client.get("/get_data?file=scene.rpy")

        assert response.status_code == 200
        data = response.get_json()
        assert data["text"] == "Just narration."
        assert data["count"] == 1

    def test_returns_spoken_text_not_character_id_for_tagged_lines(self, client, project_dir):
        """Regression test for the reported bug."""
        write_rpy(project_dir, "scene.rpy", 'cs "Actual spoken words."\n')

        response = client.get("/get_data?file=scene.rpy")

        data = response.get_json()
        assert data["text"] == "Actual spoken words."
        assert data["count"] == 1

    def test_handles_a_realistic_scene_with_mixed_narration_and_characters(
        self, client, project_dir, sample_rpy_text
    ):
        write_rpy(project_dir, "scene.rpy", sample_rpy_text)

        response = client.get("/get_data?file=scene.rpy")

        data = response.get_json()
        assert data["count"] == 33
        lines = data["text"].split("\n")
        assert "Ты такой милый, когда дрыхнешь!" in lines
        assert "Дай сигаретку, что ли..." in lines

    def test_nonexistent_file_returns_empty_result_rather_than_error(self, client, project_dir):
        response = client.get("/get_data?file=missing.rpy")

        assert response.status_code == 200
        assert response.get_json() == {"text": "", "count": 0, "meta": []}

    def test_file_with_no_dialogue_returns_zero_count(self, client, project_dir):
        write_rpy(project_dir, "scene.rpy", "label start:\n    scene bg room\n    window hide\n")

        response = client.get("/get_data?file=scene.rpy")

        assert response.get_json() == {"text": "", "count": 0, "meta": []}


class TestGetDataMetadata:
    """
    Coverage for the per-line 'meta' field: the original 1-based line
    number in the source file, and the character id given explicitly on
    that line (empty string if the line has none).

    This is purely display metadata for the editor's gutter - it must line
    up index-for-index with the lines in 'text', but must never change the
    content of 'text' itself.
    """

    def test_line_with_no_character_id_has_empty_char(self, client, project_dir):
        write_rpy(project_dir, "scene.rpy", '"Narration only."\n')

        data = client.get("/get_data?file=scene.rpy").get_json()

        assert data["meta"] == [{"line": 1, "char": ""}]

    def test_character_line_reports_its_explicit_character_id(self, client, project_dir):
        write_rpy(project_dir, "scene.rpy", 'dv "Hello."\n')

        data = client.get("/get_data?file=scene.rpy").get_json()

        assert data["meta"] == [{"line": 1, "char": "dv"}]

    def test_untagged_lines_are_always_empty_regardless_of_neighboring_tags(self, client, project_dir):
        raw = 'dv "Tagged."\n"Untagged."\ncs "Tagged again."\n'
        write_rpy(project_dir, "scene.rpy", raw)

        data = client.get("/get_data?file=scene.rpy").get_json()

        assert [m["char"] for m in data["meta"]] == ["dv", "", "cs"]

    def test_line_numbers_reflect_position_in_the_original_file_not_in_the_pure_text(
        self, client, project_dir
    ):
        raw = (
            'label start:\n'          # line 1, not dialogue
            '    scene bg room\n'     # line 2, not dialogue
            '    cs "First line."\n'  # line 3
            '    window hide\n'       # line 4, not dialogue
            '    me "Second line."\n' # line 5
        )
        write_rpy(project_dir, "scene.rpy", raw)

        data = client.get("/get_data?file=scene.rpy").get_json()

        assert data["meta"] == [
            {"line": 3, "char": "cs"},
            {"line": 5, "char": "me"},
        ]

    def test_meta_is_index_aligned_with_the_text_lines(self, client, project_dir, sample_rpy_text):
        write_rpy(project_dir, "scene.rpy", sample_rpy_text)

        data = client.get("/get_data?file=scene.rpy").get_json()
        lines = data["text"].split("\n")

        assert len(data["meta"]) == len(lines) == data["count"]
        # Unattributed narration has no character id.
        assert data["meta"][0]["char"] == ""
        # `dv "Проснулась, ...` is an explicit tag.
        idx = lines.index("Проснулась, спящая красавица моя?")
        assert data["meta"][idx]["char"] == "dv"
        # The very next line is untagged narration, so it has no id - even
        # though dv was the line right before it.
        assert data["meta"][idx + 1]["char"] == ""


class TestSaveData:
    def test_edited_text_is_written_back_with_original_character_tag_preserved(
        self, client, project_dir
    ):
        write_rpy(project_dir, "scene.rpy", 'cs "Old text."\n')

        response = client.post(
            "/save_data",
            data=json.dumps({"file": "scene.rpy", "text": "New text."}),
            content_type="application/json",
        )

        assert response.status_code == 200
        saved = (project_dir / "scene.rpy").read_text(encoding="utf-8")
        assert saved == 'cs "New text."\n'

    def test_non_dialogue_lines_are_left_untouched(self, client, project_dir):
        original = 'label start:\n    scene bg room with dissolve\n    cs "Old text."\n    window hide\n'
        write_rpy(project_dir, "scene.rpy", original)

        client.post(
            "/save_data",
            data=json.dumps({"file": "scene.rpy", "text": "New text."}),
            content_type="application/json",
        )

        saved = (project_dir / "scene.rpy").read_text(encoding="utf-8")
        assert saved == (
            'label start:\n'
            '    scene bg room with dissolve\n'
            '    cs "New text."\n'
            '    window hide\n'
        )

    def test_quotes_in_edited_text_are_escaped_on_save(self, client, project_dir):
        write_rpy(project_dir, "scene.rpy", 'me "Old text."\n')

        client.post(
            "/save_data",
            data=json.dumps({"file": "scene.rpy", "text": 'He said "hi".'}),
            content_type="application/json",
        )

        saved = (project_dir / "scene.rpy").read_text(encoding="utf-8")
        assert saved == 'me "He said \\"hi\\"."\n'

    def test_round_trip_get_then_save_then_get_returns_the_edit(self, client, project_dir):
        write_rpy(project_dir, "scene.rpy", 'dv "Original line."\n"Second line."\n')

        loaded = client.get("/get_data?file=scene.rpy").get_json()["text"]
        edited = loaded.replace("Original line.", "Edited line.")

        client.post(
            "/save_data",
            data=json.dumps({"file": "scene.rpy", "text": edited}),
            content_type="application/json",
        )

        reloaded = client.get("/get_data?file=scene.rpy").get_json()
        assert reloaded["text"] == "Edited line.\nSecond line."
        assert reloaded["count"] == 2

    def test_mismatched_line_count_is_rejected_and_file_is_left_unchanged(self, client, project_dir):
        original = 'cs "Line one."\nme "Line two."\n'
        write_rpy(project_dir, "scene.rpy", original)

        response = client.post(
            "/save_data",
            data=json.dumps({"file": "scene.rpy", "text": "Only one line."}),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert (project_dir / "scene.rpy").read_text(encoding="utf-8") == original

    def test_saving_to_a_nonexistent_file_returns_404(self, client, project_dir):
        response = client.post(
            "/save_data",
            data=json.dumps({"file": "missing.rpy", "text": "Whatever."}),
            content_type="application/json",
        )

        assert response.status_code == 404
