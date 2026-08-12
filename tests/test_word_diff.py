"""
Tests for word_diff_segments(), which powers the inline word-highlighting
in the diff pane.

We assert on the reconstructed text per operation type rather than on the
exact token boundaries difflib chooses internally. Concatenating all
'equal'+'delete' segments must reproduce old_text, and all 'equal'+'insert'
segments must reproduce new_text - that's the actual contract the frontend
relies on, and it holds regardless of exactly how tokens are grouped.
"""
import pytest


def old_text_from(segments):
    return "".join(s["text"] for s in segments if s["op"] in ("equal", "delete"))


def new_text_from(segments):
    return "".join(s["text"] for s in segments if s["op"] in ("equal", "insert"))


class TestWordDiffSegments:
    def test_identical_text_is_a_single_equal_segment(self, editor):
        segments = editor.word_diff_segments("Hello world.", "Hello world.")

        assert segments == [{"op": "equal", "text": "Hello world."}]

    def test_completely_different_text_has_no_equal_segment(self, editor):
        segments = editor.word_diff_segments("foo", "bar")

        assert all(s["op"] != "equal" for s in segments)

    @pytest.mark.parametrize(
        "old, new",
        [
            pytest.param("Hello world.", "Hello there world.", id="word_inserted"),
            pytest.param("Hello there world.", "Hello world.", id="word_removed"),
            pytest.param("Hello world.", "Hello Python.", id="word_replaced"),
            pytest.param("", "Something new.", id="empty_old_text"),
            pytest.param("Something old.", "", id="empty_new_text"),
            pytest.param(
                "Проснулась, спящая красавица моя?",
                "Проснулась, милая красавица моя?",
                id="cyrillic_text_word_replaced",
            ),
        ],
    )
    def test_segments_reconstruct_the_original_and_edited_text(self, editor, old, new):
        segments = editor.word_diff_segments(old, new)

        assert old_text_from(segments) == old
        assert new_text_from(segments) == new

    def test_every_segment_has_a_recognized_operation(self, editor):
        segments = editor.word_diff_segments("The quick fox.", "A slow fox jumps.")

        assert all(s["op"] in ("equal", "delete", "insert") for s in segments)
