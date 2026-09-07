"""Tests for the Skill Sync Status Reporter (sync_skills.py)."""

import json
import time
from pathlib import Path

import pytest

from sync_skills import (
    build_inventory,
    compare_file_hashes,
    compare_inventory,
    detect_tools,
    directory_file_hashes,
    directory_hash,
    extract_frontmatter,
    is_payload_file,
    file_hash,
    format_human,
    format_json,
    inventory_tool,
    latest_mtime,
    parse_simple_yaml,
    resolve_tool_path,
    TOOLS,
)


# ============================================================================
# Helpers
# ============================================================================

SKILL_MD_CONTENT = """\
---
name: test-skill
description: "A test skill"
version: "1.0"
---

# Test Skill

This is a test skill.
"""

SKILL_MD_V2 = """\
---
name: test-skill
description: "A test skill v2"
version: "2.0"
---

# Test Skill v2

This is the updated version.
"""

SKILL_MD_MINIMAL = """\
---
name: minimal-skill
description: "Minimal"
---

# Minimal
"""


def make_skill(base: Path, tool_subpath: str, skill_name: str, content: str = SKILL_MD_CONTENT):
    """Create a skill directory under base/tool_subpath/skill_name/SKILL.md."""
    skill_dir = base / tool_subpath / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def make_tool_dir(base: Path, tool_subpath: str):
    """Create an empty tool skills directory."""
    d = base / tool_subpath
    d.mkdir(parents=True, exist_ok=True)
    return d


# ============================================================================
# Hashing Utilities
# ============================================================================


def test_file_hash_consistent(tmp_path):
    """Same content always produces the same hash."""
    f = tmp_path / "test.txt"
    f.write_text("hello world", encoding="utf-8")
    h1 = file_hash(f)
    h2 = file_hash(f)
    assert h1 == h2
    assert len(h1) == 32  # MD5 hex length


def test_file_hash_differs_on_content(tmp_path):
    """Different content produces different hashes."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("hello", encoding="utf-8")
    f2.write_text("world", encoding="utf-8")
    assert file_hash(f1) != file_hash(f2)


def test_directory_hash_consistent(tmp_path):
    """Same directory tree always produces the same hash."""
    d = tmp_path / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text("content", encoding="utf-8")
    h1 = directory_hash(d)
    h2 = directory_hash(d)
    assert h1 == h2


def test_directory_hash_differs_on_content(tmp_path):
    """Different file content produces different directory hashes."""
    d1 = tmp_path / "s1"
    d2 = tmp_path / "s2"
    d1.mkdir()
    d2.mkdir()
    (d1 / "SKILL.md").write_text("version 1", encoding="utf-8")
    (d2 / "SKILL.md").write_text("version 2", encoding="utf-8")
    assert directory_hash(d1) != directory_hash(d2)


def test_directory_hash_ignores_symlinks(tmp_path):
    """Symlinks should not affect the directory hash."""
    d = tmp_path / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text("content", encoding="utf-8")
    h_before = directory_hash(d)
    (d / "link.md").symlink_to(d / "SKILL.md")
    h_after = directory_hash(d)
    assert h_before == h_after


def test_directory_hash_ignores_ds_store(tmp_path):
    """A macOS .DS_Store must not make two identical skills look different."""
    d1 = tmp_path / "s1"
    d2 = tmp_path / "s2"
    d1.mkdir()
    d2.mkdir()
    (d1 / "SKILL.md").write_text("same", encoding="utf-8")
    (d2 / "SKILL.md").write_text("same", encoding="utf-8")
    (d2 / ".DS_Store").write_bytes(b"\x00\x01mac junk")
    assert directory_hash(d1) == directory_hash(d2)


def test_directory_hash_ignores_git_directory(tmp_path):
    """A skill kept as a git checkout must still match its deployed copy.

    Without this, a canonical copy tracked in git can never report in sync with
    any deployment, because the deployment has no .git tree to hash.
    """
    canonical = tmp_path / "canonical"
    deployed = tmp_path / "deployed"
    canonical.mkdir()
    deployed.mkdir()
    (canonical / "SKILL.md").write_text("same", encoding="utf-8")
    (deployed / "SKILL.md").write_text("same", encoding="utf-8")
    git = canonical / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "config").write_text("[core]\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text("abc123\n", encoding="utf-8")
    assert directory_hash(canonical) == directory_hash(deployed)


def test_directory_hash_still_detects_real_content_change(tmp_path):
    """The ignore list must not mask an actual difference in skill payload."""
    d1 = tmp_path / "s1"
    d2 = tmp_path / "s2"
    d1.mkdir()
    d2.mkdir()
    (d1 / "SKILL.md").write_text("same", encoding="utf-8")
    (d2 / "SKILL.md").write_text("same", encoding="utf-8")
    (d1 / ".DS_Store").write_bytes(b"junk")
    (d2 / "data").mkdir()
    (d2 / "data" / "extra.md").write_text("real payload", encoding="utf-8")
    assert directory_hash(d1) != directory_hash(d2)


def test_is_payload_file_classification():
    """Payload vs non-payload, including nested ignored directories."""
    assert is_payload_file(Path("SKILL.md"))
    assert is_payload_file(Path("data/notes.md"))
    assert is_payload_file(Path("scripts/run.sh"))
    assert not is_payload_file(Path(".DS_Store"))
    assert not is_payload_file(Path(".git/config"))
    assert not is_payload_file(Path(".git/refs/heads/main"))
    assert not is_payload_file(Path("__pycache__/mod.pyc"))
    assert not is_payload_file(Path(".claude/settings.local.json"))


def test_latest_mtime_ignores_non_payload_files(tmp_path):
    """Touching .git must not make a skill look newer than a real edit.

    latest_mtime decides which copy is reported as "newest", and "newest" is the
    copy users are told to sync FROM. A git fetch touching .git/FETCH_HEAD must
    not be able to win that comparison.
    """
    d = tmp_path / "skill"
    (d / ".git").mkdir(parents=True)
    (d / "SKILL.md").write_text("content", encoding="utf-8")
    payload_mtime = latest_mtime(d)

    fetch_head = d / ".git" / "FETCH_HEAD"
    fetch_head.write_text("abc123\n", encoding="utf-8")
    import os
    future = payload_mtime + 10_000
    os.utime(fetch_head, (future, future))

    assert latest_mtime(d) == payload_mtime


# ============================================================================
# Frontmatter Parsing
# ============================================================================


def test_parse_simple_yaml_basic():
    """Parse basic key: value pairs."""
    result = parse_simple_yaml('name: my-skill\ndescription: "A skill"')
    assert result["name"] == "my-skill"
    assert result["description"] == "A skill"


def test_parse_simple_yaml_ignores_comments():
    """Comments and blank lines are skipped."""
    result = parse_simple_yaml('# comment\n\nname: foo')
    assert result == {"name": "foo"}


def test_extract_frontmatter_valid(tmp_path):
    """Extracts frontmatter from a valid SKILL.md."""
    f = tmp_path / "SKILL.md"
    f.write_text(SKILL_MD_CONTENT, encoding="utf-8")
    fm = extract_frontmatter(f)
    assert fm["name"] == "test-skill"
    assert fm["version"] == "1.0"


def test_extract_frontmatter_missing_delimiters(tmp_path):
    """Returns empty dict when frontmatter delimiters are missing."""
    f = tmp_path / "SKILL.md"
    f.write_text("# No frontmatter here", encoding="utf-8")
    assert extract_frontmatter(f) == {}


def test_extract_frontmatter_nonexistent(tmp_path):
    """Returns empty dict for a file that doesn't exist."""
    assert extract_frontmatter(tmp_path / "nope.md") == {}


# ============================================================================
# Tool Detection
# ============================================================================


def test_detect_tools_finds_existing(tmp_path):
    """Detects tools whose skills directories exist."""
    make_tool_dir(tmp_path, ".claude/skills")
    make_tool_dir(tmp_path, ".agents/skills")
    detected = detect_tools(home=tmp_path)
    ids = [t["id"] for t in detected]
    assert "claude-code" in ids
    assert "gemini-cli" in ids
    assert all(t["scope"] == "user" for t in detected)


def test_detect_tools_ignores_missing(tmp_path):
    """Tools without skills directories are not detected."""
    detected = detect_tools(home=tmp_path)
    assert detected == []


def test_detect_tools_project_scope(tmp_path):
    """Detects project-level tool directories when project_dir is provided."""
    project = tmp_path / "my-project"
    make_tool_dir(project, ".claude/skills")
    detected = detect_tools(home=tmp_path, project_dir=project)
    proj_tools = [t for t in detected if t["scope"] == "project"]
    assert len(proj_tools) == 1
    assert proj_tools[0]["id"] == "claude-code"


def test_detect_tools_both_scopes(tmp_path):
    """A tool can appear in both user and project scope."""
    make_tool_dir(tmp_path, ".claude/skills")
    project = tmp_path / "proj"
    make_tool_dir(project, ".claude/skills")
    detected = detect_tools(home=tmp_path, project_dir=project)
    claude_entries = [t for t in detected if t["id"] == "claude-code"]
    assert len(claude_entries) == 2
    scopes = {t["scope"] for t in claude_entries}
    assert scopes == {"user", "project"}


def test_detect_tools_all_tools(tmp_path):
    """All 10 tools are detected when their directories exist."""
    for tool in TOOLS:
        path = tool["user_path"].replace("~/", "")
        make_tool_dir(tmp_path, path)
    detected = detect_tools(home=tmp_path)
    assert len(detected) == len(TOOLS)


def test_detect_alef_agent(tmp_path):
    """Alef Agent is detected via its workspace/skills directory."""
    make_tool_dir(tmp_path, ".alef-agent/workspace/skills")
    detected = detect_tools(home=tmp_path)
    ids = [t["id"] for t in detected]
    assert "alef-agent" in ids
    assert all(t["scope"] == "user" for t in detected)


def test_alef_agent_no_project_scope(tmp_path):
    """Alef Agent (daemon) has no project scope and should not appear in project detection."""
    project = tmp_path / "my-project"
    project.mkdir()
    detected = detect_tools(home=tmp_path, project_dir=project)
    alef_agent_entries = [t for t in detected if t["id"] == "alef-agent"]
    assert len(alef_agent_entries) == 0


def test_resolve_tool_path_with_home(tmp_path):
    """resolve_tool_path replaces ~ with the provided home."""
    result = resolve_tool_path("~/.claude/skills", home=tmp_path)
    assert result == tmp_path / ".claude/skills"


def test_resolve_tool_path_without_home():
    """resolve_tool_path uses expanduser when home is None."""
    result = resolve_tool_path("~/.claude/skills", home=None)
    assert str(result).startswith("/")
    assert ".claude/skills" in str(result)


# ============================================================================
# Skill Inventory
# ============================================================================


def test_inventory_tool_finds_skills(tmp_path):
    """Inventories skills within a tool's directory."""
    make_skill(tmp_path, ".claude/skills", "my-skill")
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": tmp_path / ".claude/skills"}
    inv = inventory_tool(tool_entry)
    assert "my-skill" in inv
    assert inv["my-skill"]["hash"]
    assert inv["my-skill"]["name"] == "test-skill"
    assert inv["my-skill"]["version"] == "1.0"


def test_inventory_tool_skips_non_skill_dirs(tmp_path):
    """Directories without SKILL.md are not inventoried."""
    skills_dir = tmp_path / ".claude/skills"
    (skills_dir / "not-a-skill").mkdir(parents=True)
    (skills_dir / "not-a-skill" / "readme.txt").write_text("nope", encoding="utf-8")
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": skills_dir}
    inv = inventory_tool(tool_entry)
    assert inv == {}


def test_inventory_tool_empty_dir(tmp_path):
    """Empty skills directory produces empty inventory."""
    skills_dir = tmp_path / ".claude/skills"
    skills_dir.mkdir(parents=True)
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": skills_dir}
    inv = inventory_tool(tool_entry)
    assert inv == {}


def test_inventory_tool_multiple_skills(tmp_path):
    """Multiple skills are all inventoried."""
    make_skill(tmp_path, ".claude/skills", "skill-a", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".claude/skills", "skill-b", SKILL_MD_MINIMAL)
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": tmp_path / ".claude/skills"}
    inv = inventory_tool(tool_entry)
    assert "skill-a" in inv
    assert "skill-b" in inv


def test_latest_mtime(tmp_path):
    """Returns the most recent mtime across files."""
    d = tmp_path / "skill"
    d.mkdir()
    f1 = d / "a.md"
    f1.write_text("old", encoding="utf-8")
    time.sleep(0.05)
    f2 = d / "b.md"
    f2.write_text("new", encoding="utf-8")
    mt = latest_mtime(d)
    assert mt is not None
    assert mt >= f2.stat().st_mtime


def test_latest_mtime_empty(tmp_path):
    """Returns None for an empty directory."""
    d = tmp_path / "empty"
    d.mkdir()
    assert latest_mtime(d) is None


# ============================================================================
# Build Inventory (across tools)
# ============================================================================


def test_build_inventory_merges_tools(tmp_path):
    """build_inventory merges the same skill from different tools."""
    make_skill(tmp_path, ".claude/skills", "shared-skill")
    make_skill(tmp_path, ".agents/skills", "shared-skill")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    assert "shared-skill" in inv
    assert len(inv["shared-skill"]) == 2


def test_build_inventory_separate_skills(tmp_path):
    """Skills unique to one tool appear as separate entries."""
    make_skill(tmp_path, ".claude/skills", "only-claude")
    make_skill(tmp_path, ".agents/skills", "only-gemini")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    assert "only-claude" in inv
    assert "only-gemini" in inv
    assert len(inv["only-claude"]) == 1
    assert len(inv["only-gemini"]) == 1


# ============================================================================
# Comparison
# ============================================================================


def test_compare_in_sync(tmp_path):
    """Identical skills across tools are reported as in_sync."""
    make_skill(tmp_path, ".claude/skills", "synced")
    make_skill(tmp_path, ".agents/skills", "synced")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    assert len(results) == 1
    assert results[0]["status"] == "in_sync"


def test_compare_out_of_sync(tmp_path):
    """Different content across tools is reported as out_of_sync."""
    make_skill(tmp_path, ".claude/skills", "diverged", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "diverged", SKILL_MD_V2)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    assert len(results) == 1
    assert results[0]["status"] == "out_of_sync"
    newest = [l for l in results[0]["locations"] if l["is_newest"]]
    assert len(newest) == 1


def test_compare_single_tool(tmp_path):
    """A skill in only one tool is reported as single."""
    make_skill(tmp_path, ".claude/skills", "lonely")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    assert len(results) == 1
    assert results[0]["status"] == "single"


def test_compare_mixed(tmp_path):
    """Mix of in_sync, out_of_sync, and single skills."""
    make_skill(tmp_path, ".claude/skills", "synced")
    make_skill(tmp_path, ".agents/skills", "synced")
    make_skill(tmp_path, ".claude/skills", "diverged", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "diverged", SKILL_MD_V2)
    make_skill(tmp_path, ".claude/skills", "lonely")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    statuses = {r["skill"]: r["status"] for r in results}
    assert statuses["synced"] == "in_sync"
    assert statuses["diverged"] == "out_of_sync"
    assert statuses["lonely"] == "single"


def test_compare_empty_inventory():
    """Empty inventory produces empty results."""
    assert compare_inventory({}) == []


# ============================================================================
# Output Formatting -- Human-readable
# ============================================================================


def test_format_human_no_skills(tmp_path):
    """Human output handles no skills gracefully."""
    make_tool_dir(tmp_path, ".claude/skills")
    detected = detect_tools(home=tmp_path)
    output = format_human([], detected, verbose=False)
    assert "No skills found" in output


def test_format_human_in_sync(tmp_path):
    """Human output shows in-sync marker."""
    make_skill(tmp_path, ".claude/skills", "ok")
    make_skill(tmp_path, ".agents/skills", "ok")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    output = format_human(results, detected, verbose=False)
    assert "\u2713 in sync" in output


def test_format_human_out_of_sync(tmp_path):
    """Human output shows newest/stale markers."""
    make_skill(tmp_path, ".claude/skills", "drift", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "drift", SKILL_MD_V2)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    output = format_human(results, detected, verbose=False)
    assert "newest" in output
    assert "stale" in output


def test_format_human_verbose_shows_file_diff(tmp_path):
    """Verbose mode shows per-file diff details for out-of-sync skills."""
    make_skill(tmp_path, ".claude/skills", "drift", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "drift", SKILL_MD_V2)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    output = format_human(results, detected, verbose=True)
    assert "modified" in output
    assert "~ SKILL.md" in output


def test_format_human_summary_counts(tmp_path):
    """Summary line reports correct counts."""
    make_skill(tmp_path, ".claude/skills", "synced")
    make_skill(tmp_path, ".agents/skills", "synced")
    make_skill(tmp_path, ".claude/skills", "lonely")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    output = format_human(results, detected, verbose=False)
    assert "1 in sync" in output
    assert "1 single-tool only" in output


# ============================================================================
# Output Formatting -- JSON
# ============================================================================


def test_format_json_valid(tmp_path):
    """JSON output is valid JSON."""
    make_skill(tmp_path, ".claude/skills", "test-skill")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    output = format_json(results, detected)
    data = json.loads(output)
    assert "version" in data
    assert "detected_tools" in data
    assert "skills" in data
    assert "summary" in data


def test_format_json_structure(tmp_path):
    """JSON output has the expected structure for skills."""
    make_skill(tmp_path, ".claude/skills", "my-skill")
    make_skill(tmp_path, ".agents/skills", "my-skill")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    data = json.loads(format_json(results, detected))
    skill = data["skills"][0]
    assert skill["skill"] == "my-skill"
    assert skill["status"] == "in_sync"
    assert len(skill["locations"]) == 2
    loc = skill["locations"][0]
    assert "tool_key" in loc
    assert "hash" in loc
    assert "mtime_iso" in loc


def test_format_json_summary_counts(tmp_path):
    """JSON summary has correct counts."""
    make_skill(tmp_path, ".claude/skills", "synced")
    make_skill(tmp_path, ".agents/skills", "synced")
    make_skill(tmp_path, ".claude/skills", "diverged", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "diverged", SKILL_MD_V2)
    make_skill(tmp_path, ".claude/skills", "solo")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    data = json.loads(format_json(results, detected))
    assert data["summary"]["total"] == 3
    assert data["summary"]["in_sync"] == 1
    assert data["summary"]["out_of_sync"] == 1
    assert data["summary"]["single"] == 1


def test_format_json_empty():
    """JSON output handles empty results."""
    data = json.loads(format_json([], []))
    assert data["skills"] == []
    assert data["summary"]["total"] == 0


# ============================================================================
# Edge Cases
# ============================================================================


def test_skill_without_frontmatter(tmp_path):
    """A skill with no YAML frontmatter still gets inventoried."""
    skill_dir = tmp_path / ".claude/skills/no-fm"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Just markdown, no frontmatter", encoding="utf-8")
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": tmp_path / ".claude/skills"}
    inv = inventory_tool(tool_entry)
    assert "no-fm" in inv
    assert inv["no-fm"]["version"] is None


def test_skill_with_extra_files(tmp_path):
    """Skills with extra files beyond SKILL.md are hashed correctly."""
    skill_dir = make_skill(tmp_path, ".claude/skills", "rich-skill")
    (skill_dir / "helper.py").write_text("print('hi')", encoding="utf-8")
    (skill_dir / "config.json").write_text("{}", encoding="utf-8")
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": tmp_path / ".claude/skills"}
    inv = inventory_tool(tool_entry)
    assert "rich-skill" in inv
    h1 = inv["rich-skill"]["hash"]

    make_skill(tmp_path, ".agents/skills", "rich-skill")
    tool_entry2 = {"id": "gemini-cli", "name": "Gemini CLI / Codex", "scope": "user",
                   "path": tmp_path / ".agents/skills"}
    inv2 = inventory_tool(tool_entry2)
    assert inv2["rich-skill"]["hash"] != h1


def test_broken_symlink_in_skill(tmp_path):
    """Broken symlinks inside a skill don't crash the inventory."""
    skill_dir = make_skill(tmp_path, ".claude/skills", "broken-link")
    (skill_dir / "bad-link.md").symlink_to(tmp_path / "nonexistent")
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": tmp_path / ".claude/skills"}
    inv = inventory_tool(tool_entry)
    assert "broken-link" in inv


def test_single_tool_install(tmp_path):
    """System with only one tool still produces valid output."""
    make_skill(tmp_path, ".claude/skills", "only-here")
    detected = detect_tools(home=tmp_path)
    assert len(detected) == 1
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    assert len(results) == 1
    assert results[0]["status"] == "single"


# ============================================================================
# Project-level Scanning
# ============================================================================


def test_project_level_detection(tmp_path):
    """Project-level skill directories are detected with --project-dir."""
    project = tmp_path / "my-project"
    make_skill(project, ".claude/skills", "project-skill")
    detected = detect_tools(home=tmp_path, project_dir=project)
    proj = [t for t in detected if t["scope"] == "project"]
    assert len(proj) == 1
    assert proj[0]["id"] == "claude-code"


def test_project_and_user_same_skill(tmp_path):
    """Same skill in user and project scope appears in both."""
    make_skill(tmp_path, ".claude/skills", "dual-scope")
    project = tmp_path / "proj"
    make_skill(project, ".claude/skills", "dual-scope")
    detected = detect_tools(home=tmp_path, project_dir=project)
    inv = build_inventory(detected)
    assert "dual-scope" in inv
    assert len(inv["dual-scope"]) == 2


def test_project_level_no_dir(tmp_path):
    """No project-level tools detected when project_dir has no tool dirs."""
    project = tmp_path / "empty-project"
    project.mkdir()
    detected = detect_tools(home=tmp_path, project_dir=project)
    assert all(t["scope"] == "user" for t in detected)


# ============================================================================
# Per-file Hashing and Diff
# ============================================================================


def test_directory_file_hashes(tmp_path):
    """Returns a map of relative paths to hashes."""
    d = tmp_path / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text("content", encoding="utf-8")
    (d / "helper.py").write_text("print('hi')", encoding="utf-8")
    fh = directory_file_hashes(d)
    assert "SKILL.md" in fh
    assert "helper.py" in fh
    assert len(fh) == 2


def test_compare_file_hashes_identical():
    """Identical file maps produce empty diffs."""
    a = {"SKILL.md": "abc123", "helper.py": "def456"}
    diff = compare_file_hashes(a, a)
    assert diff == {"added": [], "removed": [], "modified": []}


def test_compare_file_hashes_modified():
    """Different hashes for the same file are detected as modified."""
    a = {"SKILL.md": "abc123"}
    b = {"SKILL.md": "xyz789"}
    diff = compare_file_hashes(a, b)
    assert diff["modified"] == ["SKILL.md"]
    assert diff["added"] == []
    assert diff["removed"] == []


def test_compare_file_hashes_added_removed():
    """Files present in one but not the other are detected."""
    a = {"SKILL.md": "abc", "old.txt": "111"}
    b = {"SKILL.md": "abc", "new.txt": "222"}
    diff = compare_file_hashes(a, b)
    assert diff["added"] == ["new.txt"]
    assert diff["removed"] == ["old.txt"]
    assert diff["modified"] == []


# ============================================================================
# File Count in Inventory
# ============================================================================


def test_inventory_includes_file_count(tmp_path):
    """Inventory entries include file_count."""
    skill_dir = make_skill(tmp_path, ".claude/skills", "multi-file")
    (skill_dir / "helper.py").write_text("pass", encoding="utf-8")
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": tmp_path / ".claude/skills"}
    inv = inventory_tool(tool_entry)
    assert inv["multi-file"]["file_count"] == 2


def test_inventory_single_file_count(tmp_path):
    """A skill with only SKILL.md has file_count of 1."""
    make_skill(tmp_path, ".claude/skills", "minimal")
    tool_entry = {"id": "claude-code", "name": "Claude Code", "scope": "user",
                  "path": tmp_path / ".claude/skills"}
    inv = inventory_tool(tool_entry)
    assert inv["minimal"]["file_count"] == 1


# ============================================================================
# Conflict Detection (3+ distinct versions)
# ============================================================================


SKILL_MD_V3 = """\
---
name: test-skill
description: "A test skill v3"
version: "3.0"
---

# Test Skill v3

This is yet another version.
"""


def test_compare_conflict_three_versions(tmp_path):
    """Three distinct versions across three tools are reported as conflict."""
    make_skill(tmp_path, ".claude/skills", "diverged", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "diverged", SKILL_MD_V2)
    make_skill(tmp_path, ".config/opencode/skills", "diverged", SKILL_MD_V3)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    assert len(results) == 1
    assert results[0]["status"] == "conflict"


def test_compare_two_versions_not_conflict(tmp_path):
    """Two distinct versions stay as out_of_sync, not conflict."""
    make_skill(tmp_path, ".claude/skills", "diverged", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "diverged", SKILL_MD_V2)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    assert results[0]["status"] == "out_of_sync"


def test_compare_three_tools_two_versions_is_out_of_sync(tmp_path):
    """Three tools with only 2 distinct versions = out_of_sync, not conflict."""
    make_skill(tmp_path, ".claude/skills", "partial", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "partial", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".config/opencode/skills", "partial", SKILL_MD_V2)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    assert results[0]["status"] == "out_of_sync"


# ============================================================================
# File Diff in Comparison Results
# ============================================================================


def test_compare_includes_file_diff(tmp_path):
    """Out-of-sync results include per-file diff vs newest."""
    make_skill(tmp_path, ".claude/skills", "drift", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "drift", SKILL_MD_V2)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    entry = results[0]
    assert entry["status"] == "out_of_sync"
    assert entry["file_diff"]
    stale_key = [k for k in entry["file_diff"]][0]
    diff = entry["file_diff"][stale_key]
    assert "SKILL.md" in diff["modified"]


def test_compare_in_sync_no_file_diff(tmp_path):
    """In-sync results have empty file_diff."""
    make_skill(tmp_path, ".claude/skills", "ok")
    make_skill(tmp_path, ".agents/skills", "ok")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    assert results[0]["file_diff"] == {}


# ============================================================================
# Output Formatting — Conflict and File Count
# ============================================================================


def test_format_human_conflict(tmp_path):
    """Human output shows CONFLICT marker for 3+ versions."""
    make_skill(tmp_path, ".claude/skills", "mess", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "mess", SKILL_MD_V2)
    make_skill(tmp_path, ".config/opencode/skills", "mess", SKILL_MD_V3)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    output = format_human(results, detected, verbose=False)
    assert "CONFLICT" in output
    assert "3 distinct versions" in output
    assert "1 conflict" in output


def test_format_human_file_count_single(tmp_path):
    """Single-tool skills show file count."""
    skill_dir = make_skill(tmp_path, ".claude/skills", "solo")
    (skill_dir / "extra.py").write_text("pass", encoding="utf-8")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    output = format_human(results, detected, verbose=False)
    assert "(2 files)" in output


def test_format_human_verbose_file_diff(tmp_path):
    """Verbose mode shows per-file diff details."""
    make_skill(tmp_path, ".claude/skills", "drift", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "drift", SKILL_MD_V2)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    output = format_human(results, detected, verbose=True)
    assert "1 modified" in output
    assert "~ SKILL.md" in output


def test_format_json_includes_conflict_count(tmp_path):
    """JSON summary includes conflict count."""
    make_skill(tmp_path, ".claude/skills", "mess", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "mess", SKILL_MD_V2)
    make_skill(tmp_path, ".config/opencode/skills", "mess", SKILL_MD_V3)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    data = json.loads(format_json(results, detected))
    assert data["summary"]["conflict"] == 1
    assert data["skills"][0]["status"] == "conflict"


def test_format_json_includes_file_count(tmp_path):
    """JSON locations include file_count."""
    make_skill(tmp_path, ".claude/skills", "test")
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    data = json.loads(format_json(results, detected))
    assert data["skills"][0]["locations"][0]["file_count"] == 1


def test_format_json_includes_file_diff(tmp_path):
    """JSON includes file_diff for out-of-sync skills."""
    make_skill(tmp_path, ".claude/skills", "drift", SKILL_MD_CONTENT)
    make_skill(tmp_path, ".agents/skills", "drift", SKILL_MD_V2)
    detected = detect_tools(home=tmp_path)
    inv = build_inventory(detected)
    results = compare_inventory(inv)
    data = json.loads(format_json(results, detected))
    skill = data["skills"][0]
    assert "file_diff" in skill
    assert any("SKILL.md" in diff["modified"] for diff in skill["file_diff"].values())
