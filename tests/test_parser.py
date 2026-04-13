"""
Unit tests for the Ren'Py parser and reinserter.
Run: python -m pytest tests/ -v   (from renpy_translator/ directory)
"""

import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parser import RenpyParser, Segment
from core.reinserter import _rebuild_line


# ── Test data ──────────────────────────────────────────────────────────────

SAMPLE_RPY = """\
label start:
    e "Hello, world!"
    "This is narration."
    m "What do you want?"

    menu:
        "Go left":
            pass
        "Go right":
            pass

screen main_menu:
    text "Start Game"
    textbutton "Load" action ShowMenu('load')
    label "Options"

translate spanish start_0:
    # e "Hello, world!"
    e "Hola, mundo!"

translate spanish start_1:
    # "This is narration."
    "Esta es la narración."
"""


@pytest.fixture
def sample_file(tmp_path):
    f = tmp_path / "sample.rpy"
    f.write_text(SAMPLE_RPY, encoding="utf-8")
    return str(f)


def parse(content: str):
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.rpy', encoding='utf-8', delete=False
    ) as f:
        f.write(content)
        fname = f.name
    try:
        parser = RenpyParser()
        return parser.parse_file(fname)
    finally:
        os.unlink(fname)


# ── Tests ─────────────────────────────────────────────────────────────────

class TestDialogue:
    def test_basic_dialogue(self):
        segs = parse('    e "Hello, world!"')
        assert any(s.seg_type == 'dialogue' and s.text == "Hello, world!" for s in segs)

    def test_dialogue_with_char_id(self):
        segs = parse('    mcth "Thinking..."')
        assert any(s.char_id == 'mcth' and s.text == "Thinking..." for s in segs)

    def test_single_quote_dialogue(self):
        segs = parse("    e 'Single quoted'")
        assert any(s.text == "Single quoted" and s.quote_char == "'" for s in segs)

    def test_dollar_line_skipped(self):
        segs = parse('    $ variable = "not a dialogue"')
        assert not segs

    def test_keyword_not_char(self):
        # 'menu' is a keyword, not a char_id
        segs = parse('    menu "should not match"')
        assert not any(s.seg_type == 'dialogue' for s in segs)


class TestNarration:
    def test_basic_narration(self):
        segs = parse('    "This is narration."')
        assert any(s.seg_type == 'narration' and s.text == "This is narration." for s in segs)

    def test_narration_preserves_indent(self):
        segs = parse('        "Deep indent narration"')
        segs = [s for s in segs if s.seg_type == 'narration']
        assert segs and segs[0].indent == "        "


class TestMenu:
    def test_menu_choices(self):
        content = """\
    menu:
        "Yes":
            pass
        "No":
            pass
"""
        segs = parse(content)
        menu_segs = [s for s in segs if s.seg_type == 'menu']
        texts = [s.text for s in menu_segs]
        assert "Yes" in texts
        assert "No" in texts

    def test_menu_choices_not_narration(self):
        content = """\
    menu:
        "Option A":
            pass
"""
        segs = parse(content)
        assert all(s.seg_type == 'menu' for s in segs if s.text == "Option A")


class TestUI:
    def test_text_statement(self):
        segs = parse('    text "Start Game"')
        assert any(s.seg_type == 'ui' and s.text == "Start Game" for s in segs)

    def test_textbutton(self):
        segs = parse('    textbutton "Play" action Start()')
        assert any(s.seg_type == 'ui' and s.text == "Play" for s in segs)

    def test_label_statement(self):
        segs = parse('    label "Settings"')
        assert any(s.seg_type == 'ui' and s.text == "Settings" for s in segs)


class TestTranslateBlock:
    def test_translate_block_detected(self):
        content = """\
translate spanish start_0:
    # e "Hello"
    e "Hola"
"""
        segs = parse(content)
        tb = [s for s in segs if s.seg_type == 'translate_block']
        assert len(tb) == 1
        assert tb[0].text == "Hola"
        assert tb[0].translate_lang == "spanish"
        assert tb[0].translate_label == "start_0"

    def test_comment_line_not_extracted(self):
        content = """\
translate spanish start_0:
    # e "Do not translate this"
    e "Translated text"
"""
        segs = parse(content)
        texts = [s.text for s in segs]
        assert "Do not translate this" not in texts
        assert "Translated text" in texts

    def test_context_preserved(self):
        content = """\
translate spanish start_0:
    # "Original narration"
    "Translated narration"
"""
        segs = parse(content)
        tb = [s for s in segs if s.seg_type == 'translate_block']
        assert tb and tb[0].context == "Original narration"


class TestRebuildLine:
    def test_basic_rebuild(self):
        seg = Segment(
            text="Hello", file="", line=1, seg_type='dialogue',
            indent="    ", raw_line='    e "Hello"', quote_char='"'
        )
        result = _rebuild_line('    e "Hello"', seg, "Hola")
        assert result == '    e "Hola"'

    def test_rebuild_preserves_action(self):
        seg = Segment(
            text="Play", file="", line=1, seg_type='ui',
            indent="    ", raw_line='    textbutton "Play" action Start()',
            quote_char='"'
        )
        result = _rebuild_line('    textbutton "Play" action Start()', seg, "Spielen")
        assert result == '    textbutton "Spielen" action Start()'


class TestFullParse:
    def test_all_types_found(self, sample_file):
        parser = RenpyParser()
        segs = parser.parse_file(sample_file)
        types = {s.seg_type for s in segs}
        assert 'dialogue' in types
        assert 'narration' in types
        assert 'menu' in types
        assert 'ui' in types
        assert 'translate_block' in types

    def test_count_reasonable(self, sample_file):
        parser = RenpyParser()
        segs = parser.parse_file(sample_file)
        # We expect at least: 2 dialogue, 1 narration, 2 menu, 3 ui, 2 translate_block
        assert len(segs) >= 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
