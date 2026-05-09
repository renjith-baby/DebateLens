from pathlib import Path

import pytest

from debatelens.analysis.prompts import PromptHeader, load_prompt, render_prompt


def test_load_prompt_parses_frontmatter(fixtures_dir):
    p = load_prompt(fixtures_dir / "example_prompt.md")
    assert isinstance(p.header, PromptHeader)
    assert p.header.name == "example"
    assert p.header.input_variables == ["window_text"]
    assert p.header.model_hint == "gemini-2.0-flash"
    assert p.header.temperature == 0.0
    assert "{{ window_text }}" in p.body


def test_render_prompt_substitutes_variables(fixtures_dir):
    p = load_prompt(fixtures_dir / "example_prompt.md")
    out = render_prompt(p, window_text="hello world")
    assert "You will analyze: hello world." in out


def test_render_prompt_rejects_unknown_variable(fixtures_dir):
    p = load_prompt(fixtures_dir / "example_prompt.md")
    with pytest.raises(KeyError):
        render_prompt(p, wrong_var="x")


def test_load_prompt_missing_frontmatter_fails(tmp_path: Path):
    f = tmp_path / "no_fm.md"
    f.write_text("just a body")
    with pytest.raises(ValueError):
        load_prompt(f)
