"""
Tests for extract_pure_lines(), the function that turns raw .rpy source into
the flat list of "pure" spoken lines shown in the editor textarea.

Design notes (Khorikov-style):
- We test through extract_pure_lines(), the public entry point, rather than
  reaching into TEXT_PATTERN's match groups directly. The regex is an
  implementation detail; what matters is the observable input -> output
  behavior. This keeps the tests resistant to refactoring (e.g. if the
  regex is ever rewritten or replaced with a small parser).
- Cases are parametrized with one behavior per case and a descriptive id,
  so a failure immediately tells you *which* .rpy construct broke, without
  needing to read the assertion.
"""
import pytest


class TestSingleLineExtraction:
    """One input line in, zero-or-one pure line out."""

    @pytest.mark.parametrize(
        "raw_line, expected",
        [
            pytest.param('"Hello there."\n', ["Hello there."], id="narrator_line_no_character_id"),
            pytest.param('cs "Hello there."\n', ["Hello there."], id="character_id_two_letters"),
            pytest.param('me "Hello there."\n', ["Hello there."], id="character_id_me"),
            pytest.param('dv "Hello there."\n', ["Hello there."], id="character_id_dv"),
            pytest.param(
                'narrator_alex "Hello there."\n',
                ["Hello there."],
                id="character_id_long_identifier",
            ),
            pytest.param(
                '    me "Indented dialogue."\n',
                ["Indented dialogue."],
                id="leading_indentation_is_stripped_from_text",
            ),
            pytest.param(
                'me "Trailing spaces after quote."   \n',
                ["Trailing spaces after quote."],
                id="trailing_whitespace_after_closing_quote_is_allowed",
            ),
            pytest.param(
                r'me "He said \"hi\" to me."' + "\n",
                ['He said "hi" to me.'],
                id="escaped_quotes_inside_dialogue_are_unescaped",
            ),
            pytest.param("", [], id="empty_line_is_ignored"),
            pytest.param("label day_1zv:\n", [], id="label_line_is_ignored"),
            pytest.param("    stop music fadeout 1\n", [], id="statement_without_quotes_is_ignored"),
            pytest.param("    scene zv_prolog_2 with dissolve\n", [], id="scene_statement_is_ignored"),
            pytest.param(
                '    $ save_name = "Not dialogue, an assignment."\n',
                [],
                id="python_assignment_with_a_quoted_string_is_not_treated_as_dialogue",
            ),
            pytest.param(
                '    show dv smile pioneer close with dissolve\n',
                [],
                id="show_statement_is_ignored",
            ),
        ],
    )
    def test_extracts_expected_pure_lines(self, editor, raw_line, expected):
        assert editor.extract_pure_lines(raw_line) == expected


class TestCharacterTagRegression:
    """
    Direct regression coverage for the reported bug: lines that start with a
    character id (e.g. `cs "text"`, `me "text"`) must yield the *spoken
    text*, not the character id itself.
    """

    @pytest.mark.parametrize("character_id", ["cs", "me", "dv", "sam", "MC"])
    def test_character_prefixed_line_yields_dialogue_not_the_character_id(self, editor, character_id):
        raw = f'{character_id} "This is what was actually said."\n'

        result = editor.extract_pure_lines(raw)

        assert result == ["This is what was actually said."]
        assert character_id not in result


class TestMultiLineExtraction:
    """Behavior across a whole block of source, not just a single line."""

    def test_only_dialogue_lines_are_extracted_in_order(self, editor):
        raw = (
            'label start:\n'
            '    scene bg room with dissolve\n'
            '    "Line one."\n'
            '    cs "Line two, said by cs."\n'
            '    $ some_var = "not dialogue"\n'
            '    me "Line three, said by me."\n'
            '    window hide\n'
        )

        result = editor.extract_pure_lines(raw)

        assert result == [
            "Line one.",
            "Line two, said by cs.",
            "Line three, said by me.",
        ]

    def test_mixed_tagged_and_untagged_lines_preserve_relative_order(self, editor):
        raw = 'cs "First."\n"Second."\nme "Third."\n'

        result = editor.extract_pure_lines(raw)

        assert result == ["First.", "Second.", "Third."]

    def test_file_with_no_dialogue_yields_empty_list(self, editor):
        raw = 'label start:\n    scene bg room\n    window hide\n    pause 1\n'

        assert editor.extract_pure_lines(raw) == []

    def test_realistic_scene_file_end_to_end(self, editor, sample_rpy_text):
        """
        Exercises the extractor against the full, realistic scene supplied
        by the user, mixing narration and several different character ids.
        """
        result = editor.extract_pure_lines(sample_rpy_text)

        assert len(result) == 33
        # Spot-check narration (no character id)
        assert result[0] == (
            "До сих пор не знаю... В самом ли деле Лена любит меня? "
            "Или же ищет во мне утешение?"
        )
        # Spot-check a `dv "..."` line: must contain the spoken text, not "dv"
        assert "Ты такой милый, когда дрыхнешь!" in result
        assert "dv" not in result
        # Spot-check a `me "..."` line: must contain the spoken text, not "me"
        assert "Дай сигаретку, что ли..." in result
        assert "me" not in result
        # Last line of the scene
        assert result[-1] == (
            "Да вроде бы ничего ребята, на самом деле. "
            "С Анькой мы вот сразу общий язык нашли."
        )
