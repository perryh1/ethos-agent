"""Ethos constitution layer — load_constitution_md contract tests.

The layer's guarantees (see ETHOS.md):
  * CONSTITUTION.md in the agent home is returned wrapped in the authority
    preamble (composed above identity by agent/system_prompt.py);
  * ETHOS_VANILLA is the explicit vanilla switch — file present or not,
    nothing is injected;
  * a missing file yields None (vanilla, logged) — never an error;
  * ETHOS_CONSTITUTION_PATH overrides the home-relative location;
  * the section-1 ``Key: value`` version block parses;
  * oversized content goes through the shared truncation machinery.
"""

import pytest

from agent.prompt_builder import (
    ETHOS_CONSTITUTION_PREAMBLE,
    _parse_constitution_version,
    load_constitution_md,
)

DEMO_VERSION_BLOCK = (
    "# Company constitution\n\n"
    "## 1. Version & ratification\n\n"
    "```\n"
    "Company: Demo Company (DEMO — not ratified)\n"
    "Profile-Version: 0.1.0\n"
    "Schema-Version: 1.0.0\n"
    "Constitution-Version: v1\n"
    "Variant: full\n"
    "Compiled: 2026-08-26\n"
    "Source-Commit: abc123\n"
    "Ratification-Session: RAT-001\n"
    "```\n\n"
    "## 3. Absolutes\n\n- Never invent figures.\n"
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ETHOS_VANILLA", raising=False)
    monkeypatch.delenv("ETHOS_CONSTITUTION_PATH", raising=False)


def test_missing_file_returns_none(tmp_path):
    assert load_constitution_md(home_override=tmp_path) is None


def test_present_file_is_wrapped_in_preamble(tmp_path):
    (tmp_path / "CONSTITUTION.md").write_text(DEMO_VERSION_BLOCK, encoding="utf-8")
    block = load_constitution_md(home_override=tmp_path)
    assert block is not None
    assert block.startswith(ETHOS_CONSTITUTION_PREAMBLE)
    assert "Never invent figures." in block
    # The authority preamble comes first; the document follows.
    assert block.index(ETHOS_CONSTITUTION_PREAMBLE) < block.index("## 3. Absolutes")


def test_empty_file_returns_none(tmp_path):
    (tmp_path / "CONSTITUTION.md").write_text("   \n", encoding="utf-8")
    assert load_constitution_md(home_override=tmp_path) is None


def test_vanilla_env_suppresses_injection(tmp_path, monkeypatch):
    (tmp_path / "CONSTITUTION.md").write_text(DEMO_VERSION_BLOCK, encoding="utf-8")
    monkeypatch.setenv("ETHOS_VANILLA", "1")
    assert load_constitution_md(home_override=tmp_path) is None


@pytest.mark.parametrize("value", ["true", "YES", "on"])
def test_vanilla_env_truthy_spellings(tmp_path, monkeypatch, value):
    (tmp_path / "CONSTITUTION.md").write_text(DEMO_VERSION_BLOCK, encoding="utf-8")
    monkeypatch.setenv("ETHOS_VANILLA", value)
    assert load_constitution_md(home_override=tmp_path) is None


def test_path_override_wins_over_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "CONSTITUTION.md").write_text("HOME COPY\n" + DEMO_VERSION_BLOCK, encoding="utf-8")
    override = tmp_path / "variant.md"
    override.write_text("OVERRIDE COPY\n" + DEMO_VERSION_BLOCK, encoding="utf-8")
    monkeypatch.setenv("ETHOS_CONSTITUTION_PATH", str(override))
    block = load_constitution_md(home_override=home)
    assert block is not None and "OVERRIDE COPY" in block and "HOME COPY" not in block


def test_version_block_parses():
    info = _parse_constitution_version(DEMO_VERSION_BLOCK)
    assert info["Company"].startswith("Demo Company")
    assert info["Constitution-Version"] == "v1"
    assert info["Variant"] == "full"
    assert info["Profile-Version"] == "0.1.0"
    assert info["Ratification-Session"] == "RAT-001"


def test_oversized_content_is_truncated_with_marker(tmp_path):
    big = DEMO_VERSION_BLOCK + ("filler line for truncation test\n" * 20000)
    (tmp_path / "CONSTITUTION.md").write_text(big, encoding="utf-8")
    block = load_constitution_md(context_length=131072, home_override=tmp_path)
    assert block is not None
    assert len(block) < len(big)
    assert "truncated CONSTITUTION.md" in block


def test_bundled_demo_constitution_parses_and_flags_demo():
    from pathlib import Path

    demo = Path(__file__).resolve().parents[1] / "ethos" / "demo-constitution.md"
    info = _parse_constitution_version(demo.read_text(encoding="utf-8"))
    assert "DEMO" in info["Company"]
    assert "DEMO" in info["Constitution-Version"]
    assert info["Schema-Version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Personal-track constitutions (Owner:) and the one-click write path
# ---------------------------------------------------------------------------

PERSONAL_VERSION_BLOCK = """# Constitution — Sam

## 1. Version

```
Owner: Sam Rivera
Profile-Version: 0.1.0
Schema-Version: 1.0.0
Constitution-Version: v1
Variant: full
Compiled: 2026-09-06
Source-Commit: sittings-web
```

## 3. Absolutes

- Family First.
"""


def test_owner_label_parses_for_personal_constitutions():
    """A personal profile names a person, not a company — both must parse."""
    info = _parse_constitution_version(PERSONAL_VERSION_BLOCK)
    assert info["Owner"] == "Sam Rivera"
    assert info["Constitution-Version"] == "v1"


def test_owner_fills_the_company_display_slot(tmp_path):
    """The dashboard badge reads ``company``; Owner must feed it, or a personal
    constitution shows an unlabelled badge."""
    from agent.prompt_builder import get_constitution_status

    (tmp_path / "CONSTITUTION.md").write_text(PERSONAL_VERSION_BLOCK, encoding="utf-8")
    status = get_constitution_status(home_override=tmp_path)
    assert status["active"] is True
    assert status["company"] == "Sam Rivera"
    assert status["constitution_version"] == "v1"
    assert status["demo"] is False


def test_constitution_write_target_honours_explicit_path(tmp_path, monkeypatch):
    """The write endpoint must target exactly what the loader reads."""
    from hermes_cli.web_server import _ethos_constitution_target

    explicit = tmp_path / "elsewhere" / "MINE.md"
    monkeypatch.setenv("ETHOS_CONSTITUTION_PATH", str(explicit))
    assert _ethos_constitution_target() == explicit

    monkeypatch.delenv("ETHOS_CONSTITUTION_PATH", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert _ethos_constitution_target().name == "CONSTITUTION.md"
