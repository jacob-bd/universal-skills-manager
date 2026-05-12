# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.13.0] - 2026-05-11

### Added
- **Hermes Agent support**: Added Hermes Agent (NousResearch) as the 11th supported AI tool. User scope: `~/.hermes/skills/`. Project scope: `.hermes/skills/`.
- Hermes detection in `install.sh` one-liner installer (`--tools hermes`).
- Hermes included in Skill Matrix Report tool detection and skill collection.

### Fixed
- **Windows Unicode encoding**: All four Python CLI scripts (`sync_skills.py`, `install_skill.py`, `validate_frontmatter.py`, `scan_skill.py`) now force UTF-8 stdout/stderr on Windows, fixing `UnicodeEncodeError` crashes caused by cp1252 console encoding when outputting Unicode characters (✓, ✗, ⚠, etc.).

### Changed
- Tool count updated from 10 to 11 across all documentation.

### Updated files
- `sync_skills.py`: Added Hermes Agent entry, Windows UTF-8 fix.
- `install_skill.py`: Windows UTF-8 fix.
- `validate_frontmatter.py`: Windows UTF-8 fix.
- `scan_skill.py`: Windows UTF-8 fix.
- `SKILL.md`: Updated ecosystem table, matrix report detection, find command.
- `CLAUDE.md`: Updated ecosystem table, tool count.
- `README.md`: Updated version header, `--tools` help text, supported tools table, tool count.
- `docs/TECHNICAL.md`: Updated tool count.
- `install.sh`: Added Hermes detection, help text, and `--tools hermes` filter.

## [1.12.0] - 2026-04-22

### Added
- **Alef Agent frontmatter injection**: During installation to the Alef Agent workspace (`~/.alef-agent/workspace/skills/`), `install_skill.py` now dynamically injects `type: tool` and `status: approved` into the YAML frontmatter of `SKILL.md`.
- **Alef tool definition configuration**: `sync_skills.py` now includes a `frontmatter_extras` dict in the Alef Agent tool definition to centrally manage agent-specific metadata requirements.
- 3 new unit tests in `tests/test_install_skill.py` validating path-based frontmatter injection and existing-field overwrites.

### Changed
- Bumped `install_skill.py` to v1.4.0.
- Bumped `sync_skills.py` to v1.3.0.

## [1.11.0] - 2026-04-14

### Changed
- **CC-Claw renamed to Alef Agent**: Updated all references from CC-Claw to Alef Agent. New user-scope path: `~/.alef-agent/workspace/skills/`. Daemon tool with no project scope (unchanged).
- `--tools` flag value updated from `cc-claw` to `alef-agent` in `install.sh`.

### Updated files
- `sync_skills.py`: Updated tool entry (`id`, `name`, `user_path`).
- `SKILL.md`: Updated ecosystem table, matrix detection command, `find` path.
- `CLAUDE.md`: Updated ecosystem table.
- `README.md`: Updated `--tools` help text, supported tools table.
- `install.sh`: Updated detection line, help text, and `case` match.
- `tests/test_sync_skills.py`: Renamed `test_detect_cc_claw` → `test_detect_alef_agent` and `test_cc_claw_no_project_scope` → `test_alef_agent_no_project_scope`.

## [1.10.0] - 2026-03-14

### Added
- **CC-Claw support**: Added CC-Claw as the 10th supported AI tool. User scope: `~/.cc-claw/workspace/skills/`. CC-Claw is a daemon-based tool with no project scope.
- CC-Claw detection in `install.sh` one-liner installer (`--tools cc-claw`).
- CC-Claw included in Skill Matrix Report tool detection and skill collection.
- 2 new tests: CC-Claw detection and daemon no-project-scope verification. Total sync tests: 65.

### Changed
- `sync_skills.py`: Added guard for empty `project_path` to support daemon-only tools (no project scope). This prevents false project-scope matches for tools like CC-Claw.
- Tool count updated from 9 to 10 across all documentation.

### Updated files
- `sync_skills.py`: Added CC-Claw entry, empty-project-path guard in `detect_tools()`.
- `SKILL.md`: Updated ecosystem table, version, matrix report detection, find command.
- `CLAUDE.md`: Updated ecosystem table, tool count.
- `README.md`: Updated version header, `--tools` help text, supported tools table.
- `docs/TECHNICAL.md`: Updated tool count.
- `install.sh`: Added CC-Claw detection and `--tools cc-claw` filter.
- `tests/test_sync_skills.py`: Added `test_detect_cc_claw` and `test_cc_claw_no_project_scope`.

## [1.9.0] - 2026-03-13

### Changed
- **Gemini CLI and OpenAI Codex merged into single tool entry**: Gemini CLI (v0.30+) now reads both `~/.agents/skills/` and `~/.gemini/skills/`, with `.agents/` taking precedence. OpenAI Codex also uses `~/.agents/skills/`. To avoid duplicate-skill conflicts (Gemini CLI warning that `.agents/` overrides `.gemini/`), both tools are now served by a single `~/.agents/skills/` directory. The separate `~/.gemini/skills/` path is no longer used for skill installation.
- **Tool count reduced from 10 to 9**: Gemini CLI and OpenAI Codex share a single entry ("Gemini CLI / Codex") since they use the same skills directory. The `--tools` flags `gemini` and `codex` both remain valid and install to `~/.agents/skills/`.
- `sync_skills.py` bumped to v1.2.0.

### Fixed
- **Gemini CLI duplicate-skill conflict warnings**: Installing skills to both `~/.gemini/skills/` and `~/.agents/skills/` caused Gemini CLI to detect conflicts and warn that `.agents/` was overriding `.gemini/`. Now only `~/.agents/skills/` is used, eliminating the conflict entirely.

### Updated files
- `sync_skills.py`: Merged Gemini CLI + Codex entries, removed separate OpenAI Codex entry.
- `SKILL.md`: Updated ecosystem table, detection commands, matrix report, sync examples.
- `CLAUDE.md`: Updated ecosystem table, tool counts, shared-path note.
- `README.md`: Updated supported tools table, version, `--tools` help text.
- `docs/TECHNICAL.md`: Updated example install paths, tool counts.
- `install.sh`: Merged Gemini CLI / Codex detection; both `gemini` and `codex` flags map to `~/.agents/skills/`.
- `tests/test_sync_skills.py`: Updated all tests from `.gemini/skills` to `.agents/skills` for Gemini CLI.

## [1.8.1] - 2026-03-11

### Added
- **Per-file verbose diff**: `--verbose` now shows which specific files are added/removed/modified between the newest copy and each stale location, replacing the old hash-prefix display. Inspired by [sync-skills](https://github.com/viteinfinite/sync-skills) conflict resolution.
- **Conflict detection**: When 3+ tools have 3+ distinct versions of a skill, the status is now `"conflict"` (not just `"out_of_sync"`), with a prominent warning showing how many distinct versions exist.
- **Exit code 2 for drift**: The script now exits with code 2 when out-of-sync or conflicting skills are detected, enabling cron/CI alerting. Inspired by [skills-sync](https://github.com/ryanreh99/skills-sync) drift detection.
- **File count in inventory**: Single-tool skills now display file count (e.g., `(19 files)`) for context about skill complexity.
- **17 new tests** covering per-file diff, conflict detection, file counts, and output formatting. Total test count: 128 (65 scanner + 63 sync).

### Changed
- `sync_skills.py` bumped to v1.1.0.

### Fixed
- **Hardening from code review**: Replaced `lstrip("~/")` with `removeprefix("~/")`, added `OSError` handling in hash/mtime functions, added symlink guard on directory traversal, narrowed exception types in frontmatter parsing.
- **OpenAI Codex path in sync_skills.py**: Aligned with v1.7.1 update (`~/.agents/skills/`).
- **SKILL.md Section D**: Replaced `{slug}` with `{skill-name}` for consistency.
- **Doc fixes**: Updated README repo tree, version header, scanner test counts (62→65), `validate_frontmatter.py` description, added `SECURITY_SCANNING.md` to CLAUDE.md tree.

## [1.8.0] - 2026-03-11

### Added
- **`sync_skills.py` — read-only sync status reporter**: New zero-dependency Python 3 CLI tool that detects installed AI tools, inventories skills across them, compares content using MD5 directory hashes, and reports sync status (in sync / out of sync / single-tool only). Supports `--json` for machine-readable output, `--skill` for single-skill checks, `--project-dir` for project-level scanning, and `--verbose` for per-file details. Addresses [#4](https://github.com/jacob-bd/universal-skills-manager/issues/4).
- **46 new tests** in `tests/test_sync_skills.py` covering tool detection, skill inventory, hash comparison, output formatting (human + JSON), edge cases (broken symlinks, missing frontmatter, single-tool installs), and project-level scanning.

### Changed
- **SKILL.md Section 2 ("Updates & Consistency Check")**: Expanded from a 3-line placeholder to a concrete 5-step procedure that runs `sync_skills.py`, presents the report, asks the user which direction to sync, copies on approval, and verifies.
- **SKILL.md Section D ("Installing from Local Source")**: Expanded from 3 lines to a full confirmation-gated flow with source identification, user approval, copy, verification, and missing-skill handling.
- **New Operational Rule 3 ("Sync Safety")**: The `sync_skills.py` script is read-only — it only reports status. All write operations (copy, overwrite, deploy, delete) are performed by the agent and require explicit user approval. No sync action is ever taken autonomously.
- **docs/TECHNICAL.md**: New "Sync Status Reporter" section with usage, CLI flags, output format, and two-layer architecture explanation.
- **README.md**: Expanded "Cross-Tool Sync" feature description, added sync example to Quick Start, updated "How It Works" step 5.
- **CLAUDE.md**: Expanded "Synchronization Logic" section, added `sync_skills.py` and `test_sync_skills.py` to repo structure and file locations, added sync testing instructions.

## [1.7.1] - 2026-03-08

### Fixed
- **OpenAI Codex skill paths aligned with official documentation**: Updated all Codex skill paths from `~/.codex/skills/` / `./.codex/skills/` to `~/.agents/skills/` / `./.agents/skills/` per the [official Codex skills documentation](https://developers.openai.com/codex/skills/). This was a discrepancy across 5 files: `SKILL.md` (path table, detection command, find command), `README.md`, `CLAUDE.md`, `docs/TECHNICAL.md`, and `install.sh`.

## [1.7.0] - 2026-03-07

### Added
- **ChatGPT cloud upload support**: ChatGPT (chatgpt.com) now supports skills via ZIP upload, following the same Agent Skills specification as claude.ai/Claude Desktop. Added ChatGPT to cloud platforms table, Section 5 packaging flow, upload instructions, and platform limitations.
- **ChatGPT Skills documentation**: Platform-specific upload path (Profile → Skills → New skill → Upload from your computer), plan availability (Business/Enterprise/Edu/Teachers/Healthcare beta), Skills editor, workspace sharing, and OpenAI Skills API reference.
- **ChatGPT Skills limits**: Documented 25 MB uncompressed / 50 MB ZIP / 500 files per skill limits in `docs/TECHNICAL.md`.

### Changed
- **Section 5 generalized to "Package for Cloud Upload"**: Renamed from "Package for claude.ai / Claude Desktop" to cover all three cloud platforms. Upload instructions now branch by platform.
- **`validate_frontmatter.py` messaging updated**: All output messages now reference "cloud platforms" instead of "Claude Desktop" specifically, since claude.ai, Claude Desktop, and ChatGPT all use the same Agent Skills spec validation.
- **Platform limitations expanded**: ChatGPT's sandboxed code execution (like claude.ai) prevents the Universal Skills Manager from making outbound API calls. Documented alongside the existing claude.ai limitation.
- **`docs/TECHNICAL.md` restructured**: Renamed "claude.ai / Claude Desktop" section to "Cloud Platforms" covering all three platforms with upload paths table, ChatGPT-specific notes, and limits.
- **README.md cloud section**: Replaced single-platform section with multi-platform table showing upload paths for all three cloud platforms.

## [1.6.0] - 2026-02-14

### Fixed
- **`install_skill.py` crashes in non-interactive environments (Claude Code)**: Both `input()` calls in `run_security_scan` and `display_skill_diff` threw `EOFError` when run from Claude Code (no TTY/stdin). Now detects non-interactive mode via `sys.stdin.isatty()`, prints all findings/diffs to stdout so the agent can read them, and defaults to safe abort with a message suggesting `--force` to bypass. `install_skill.py` bumped to v1.3.0.
- **API key not available after install in same session**: Installer saved `SKILLSMP_API_KEY` to shell profile (`~/.zshrc`) but not to `config.json`. Since Claude Code's running process doesn't pick up new env vars until restart, the skill would re-prompt for the API key. Installer now also writes the key to `config.json` in every installed location for immediate availability via the config file fallback path.
- **Cloudflare 403 on SkillsMP API calls**: All curl examples lacked a `User-Agent` header. SkillsMP is behind Cloudflare, which blocks bare curl requests as bot traffic. Added `User-Agent: Universal-Skills-Manager` header to all curl examples in SKILL.md and docs/TECHNICAL.md. Added new Operational Rule 3 requiring User-Agent on all API requests.

### Added
- **`q=*` wildcard for SkillsMP**: Documented that `q=*` works as a wildcard query to surface top skills when combined with `sortBy=stars`, useful for "show me popular skills" requests.
- **ClawHub sort options**: Documented `sort=downloads`, `sort=trending`, and `sort=updated` alongside existing `sort=stars`.
- **`mkdir -p` safety**: Added explicit directory creation step to install flow Step 6 (Execute) and Operational Rule 1 (Structure Integrity) to prevent silent failures when target parent directories don't exist.

### Credits
- Thanks to Jackie and the OpenClaw AI agent for field-testing the skill and reporting the Cloudflare 403, wildcard search, sort options, and mkdir safety issues.

## [1.5.9] - 2026-02-14

### Changed
- **README cleanup**: Slimmed from 574 to 194 lines. Moved security scanning details, install script usage, API key options, API reference (curl/JSON for all 3 sources), manual cloud packaging, and frontmatter spec to new `docs/TECHNICAL.md`.
- **Block scalar validation nuanced**: Testing confirmed folded scalars (`>`) work in Claude Desktop. Updated `validate_frontmatter.py`: literal scalars (`|`) with blank lines remain an error, `|` without blank lines is a warning, `>` is a warning only. Previously all block scalars were errors.
- **Claude Desktop install flow (Step 4a)**: Added to SKILL.md install procedure -- when user targets claude.ai/Desktop, the skill validates frontmatter, notifies user of issues, and only fixes + packages as ZIP with explicit user consent.

### Added
- **`docs/TECHNICAL.md`**: New technical reference document with all content moved from README.

## [1.5.8] - 2026-02-14

### Added
- **`validate_frontmatter.py` script**: New zero-dependency Python script that validates SKILL.md YAML frontmatter against the [Agent Skills specification](https://agentskills.io/specification) for claude.ai/Claude Desktop compatibility. Detects unsupported top-level keys, nested metadata, block scalar descriptions, list-format `allowed-tools`, and field length violations. With `--fix`, automatically corrects all issues. Works on both `.md` files and `.zip` archives.

### Changed
- **SKILL.md**: Added `compatibility` field to frontmatter. Updated Operational Rule 5 and Section 5 packaging flow to use `validate_frontmatter.py`. Added block scalar and list-format `allowed-tools` detection to the compatibility spec documentation.

## [1.5.7] - 2026-02-14

### Added
- **claude.ai / Claude Desktop frontmatter compatibility check**: New Operational Rule 5 validates SKILL.md frontmatter against the [Agent Skills specification](https://agentskills.io/specification) before packaging for upload. Checks allowed top-level keys (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`), enforces flat string values in `metadata`, and validates `name`/`description` length limits. Offers auto-fix for non-compliant skills (moves unsupported keys into `metadata`, flattens nested objects, truncates long descriptions).
- **`compatibility` field** added to our own frontmatter declaring runtime requirements (python3, curl, network access to skillsmp.com, skills.palebluedot.live, clawhub.ai, github.com).
- Frontmatter validation step (Step 2) added to Section 5 packaging flow — runs before ZIP creation.

## [1.5.6] - 2026-02-14

### Fixed
- **YAML frontmatter compatibility with Claude Desktop**: Claude Desktop's skill upload validator only accepts flat key-value pairs inside `metadata` — nested objects and arrays cause "malformed YAML frontmatter" errors. Moved `homepage` and `disable-model-invocation` into `metadata` as flat keys, flattened `clawdbot.requires.bins` array to a comma-separated string (`requires-bins`), and quoted the `description` string.
- **API key validation in SKILL.md**: Added `sk_live_skillsmp_` prefix validation to both the runtime search flow (Section 1) and ZIP packaging flow (Section 5). Invalid keys are now rejected with a helpful message.
- **Removed hardcoded skill counts**: Stripped "173k+" and "5,700+" numbers from SKILL.md, README.md, CLAUDE.md, and install.sh — these go stale quickly.

### Changed
- **Documented Claude Desktop network egress bug**: Claude Desktop has a known bug where custom domains added to the network egress whitelist are not included in the JWT token. The skill cannot reach SkillsMP/SkillHub/ClawHub APIs even when whitelisted. Added workaround guidance (use Claude Code CLI) to SKILL.md and README.
- **README**: Added piped one-liner example for single-tool install (`curl ... | sh -s -- --tools codex`).

## [1.5.5] - 2026-02-14

### Fixed
- **`install.sh` API key prompt hangs on Enter**: When run via `curl ... | sh`, the `read` command tried to read from the exhausted pipe instead of the terminal. Now reads from `/dev/tty` explicitly, and the non-interactive detection tests `/dev/tty` availability in a subshell instead of checking `stdin`.
- **`install.sh --tools` flag ignored**: The `--tools claude` filter installed to all detected tools instead of just Claude Code. Root cause: `IFS=','` set for comma-splitting the filter list also prevented the inner loop from splitting newline-separated tool entries, causing the entire tool list to match as one blob. Fixed by splitting the comma list into positional params first, then restoring IFS before iterating tools.
- **`install.sh` tool names with spaces caused bad word-splitting**: Multi-word tool names like "Claude Code", "Gemini CLI", and "OpenAI Codex" were split into separate tokens when iterating the space-separated tool list (e.g., "Claude" and "Code|/path" as two entries). Switched `DETECTED_TOOLS` from space-separated to newline-separated entries, with proper `IFS` management in all loops.

### Changed
- **`install.sh` API key validation**: Added prefix validation — keys must start with `sk_live_skillsmp_`. Invalid keys are rejected with an error message instead of being silently saved.

### Credits
- Thanks to `@GuyJames` on YouTube for reporting the API key prompt and `--tools` flag bugs.

## [1.5.4] - 2026-02-13

### Changed
- **Hardened credential safety in ZIP packaging (Section 5):** API key embedding is now explicitly optional — SkillHub and ClawHub search work without a key. Added prominent credential safety warning with guidance on scoped keys, key rotation, and distribution risks. Updated security reminders to differentiate key-included vs key-free ZIPs. Addresses ClawHub security review feedback.

## [1.5.3] - 2026-02-13

### Added
- **Cline support**: Added Cline as the 10th supported AI tool. User scope: `~/.cline/skills/`, Project scope: `./.cline/skills/`. Cline uses the same `SKILL.md` format with `name` and `description` frontmatter — no manifest generation required.
- Cline detection in `install.sh` one-liner installer (`--tools cline`).
- Cline included in Skill Matrix Report tool detection and skill collection.
- Cross-Platform Adaptation note: Cline also reads `.claude/skills/` at the project level, so Claude Code project skills work in Cline automatically.

## [1.5.2] - 2026-02-10

### Fixed
- **Cursor path correction**: Fixed Cursor skills path from `.cursor/extensions/` to `.cursor/skills/` in the ecosystem table, Skill Matrix Report detection, and install script.

## [1.5.1] - 2026-02-10

### Fixed
- **Frontmatter fix**: Moved `disable-model-invocation` from nested `metadata` block to top-level frontmatter for correct parsing.

## [1.5.0] - 2026-02-10

### Added
- **Homoglyph transliteration**: Cyrillic homoglyphs are now transliterated to ASCII before running semantic pattern checks (instruction override, role hijacking, safety bypass, prompt extraction). This closes the M2 evasion gap where attackers could use Cyrillic look-alike characters to bypass denylist detection.
- 3 new tests for homoglyph transliteration (instruction override, safety bypass, and combined detection).
- Empty file edge case test.
- `SECURITY.md` with vulnerability reporting process, full security architecture documentation, and known limitations.

### Changed
- **scan_skill.py bumped to v1.2.0**: Includes homoglyph transliteration, performance fix, and Windows portability.
- `_join_continuation_lines` refactored from quadratic string concatenation (`+=`) to list accumulator (`''.join()`), preventing potential 10-20s stalls on large files with many continuation lines.
- Homoglyph map consolidated: single module-level `_HOMOGLYPH_MAP` dict used by both detection and transliteration (was duplicated as class attribute).
- Tests converted from manual `try/finally` global mutation to pytest `monkeypatch` fixture (safe for parallel test execution).
- Multi-line detection test fixed: `test_multiline_bash_c_detected` now correctly tests continuation-line joining at natural word boundaries (was previously testing single-line matching).
- Homoglyph test strengthened: `test_homoglyph_instruction_override_detected` now asserts BOTH `homoglyph_detected` AND `instruction_override` findings (was previously accepting either, masking the M2 gap).

### Fixed
- **install_skill.py integration bug** (pre-existing): Security scan findings were never displayed to the user. `severity_order` used uppercase (`"CRITICAL"`) but scanner outputs lowercase (`"critical"`), and field name was `"message"` instead of `"description"`. Users saw "Security scan found N issue(s)" with a blank findings section.
- **scan_skill.py Windows portability**: `os.O_NOFOLLOW` caused `AttributeError` crash on Windows where the flag doesn't exist. Now guarded with `hasattr()` check; falls back to `is_symlink()` pre-check.

### Security
- All 20 findings from [@ben-alkov](https://github.com/ben-alkov)'s security analysis are now fully closed, including the M2 homoglyph evasion that was previously only detected but not neutralized.

### Credits
- Massive thanks to **[@ben-alkov](https://github.com/ben-alkov)** (Ben Alkov) for an outstanding security contribution: full Claude Code-driven security analysis of `scan_skill.py`, a detailed remediation work plan, 18 atomic commits addressing 20 security findings across 4 severity levels, comprehensive test suite (62 tests), and a final code review by a separate Claude Code instance. This work transformed the scanner from a baseline pattern matcher into a hardened security tool with defense-in-depth against symlink traversal, resource exhaustion, ANSI injection, scanner evasion via dotfiles/continuations/homoglyphs/unclosed comments, and expanded detection coverage for credentials and dangerous URIs. The collaboration — initiated via a Slack message offering unsolicited security help — exemplifies the best of open-source community contribution.

## [1.4.2] - 2026-02-10

### Fixed
- install_skill.py severity case mismatch and field name mismatch (see v1.5.0 for details).
- scan_skill.py O_NOFOLLOW Windows portability (see v1.5.0 for details).

### Added
- SECURITY.md initial creation.
- Updated README.md, CLAUDE.md with security scanning docs.

## [1.4.1] - 2026-02-10

### Fixed
- Address ClawHub security review: declare runtime requirements (`python3`, `curl`), primary env var (`SKILLSMP_API_KEY`), and `disable-model-invocation` in YAML frontmatter metadata.
- Add `homepage` field to frontmatter.
- Add security note for API key handling in ZIP packaging.
- Remove `save_memory` reference.

## [1.4.0] - 2026-02-09

### Added
- ClawHub integration as third search source (5,700+ versioned skills, semantic search, no API key required).
- Three-source skill discovery: SkillsMP (curated, AI semantic search) + SkillHub (open catalog) + ClawHub (versioned, semantic search).
- ClawHub semantic/vector search via `/api/v1/search` endpoint with similarity scoring.
- ClawHub browse/list via `/api/v1/skills` endpoint with cursor pagination and sorting (stars, downloads, trending).
- Direct file fetch install flow for ClawHub skills (bypasses `install_skill.py`, uses ClawHub's `/file` endpoint + manual `scan_skill.py`).
- ZIP download fallback for multi-file ClawHub skills via `/download` endpoint.
- Onboarding flow expanded from A/B to A/B/C choice (SkillsMP / SkillHub / ClawHub).
- Source labeling extended to include `[ClawHub]` tag in search results.
- ClawHub API documentation in SKILL.md, README.md, and CLAUDE.md.

### Changed
- "Search More Sources" generalized to offer all remaining unsearched sources (was SkillHub-only).
- Cross-source deduplication extended: SkillsMP ↔ SkillHub by ID, ClawHub ↔ others by skill name.
- Installation sections reorganized: A (SkillsMP), B (SkillHub), C (ClawHub), D (Local Source).

## [1.3.0] - 2026-02-10

### Added
- SkillHub integration as secondary search source (173k+ community skills, no API key required).
- Multi-source skill discovery: SkillsMP (curated, AI semantic search) + SkillHub (open catalog).
- New onboarding flow: users without a SkillsMP API key can search SkillHub immediately.
- "Search More Sources" option for SkillsMP users to also query SkillHub.
- Source labeling in search results ([SkillsMP] vs [SkillHub]).
- Deduplication logic across sources by full skill ID.
- SkillHub API documentation in SKILL.md, README.md, and CLAUDE.md.

### Changed
- Rebranded from "Universal Skill Manager" to "Universal Skills Manager".
- Renamed skill folder from `universal-skill-manager/` to `universal-skills-manager/` for consistency with branding and repo name. **Breaking:** existing installations will need to remove the old folder manually.
- Updated repository URL to `https://github.com/jacob-bd/universal-skills-manager`.
- SkillsMP API key is now optional (was previously required for all skill discovery).
- Updated install.sh messaging to reflect dual-source availability.

## [1.1.0] - 2026-02-07

### Added
- Security scanning for skill files at install time (`scan_skill.py`).
- 14 detection categories across 3 severity levels (Critical/Warning/Info).
- Detects invisible Unicode, data exfiltration URLs, shell pipe execution, credential references, command execution patterns, prompt injection, role hijacking, safety bypass attempts, HTML comments, encoded content, delimiter injection, and cross-skill escalation.
- `--skip-scan` flag for `install_skill.py` to bypass security scan.
- `docs/SECURITY_SCANNING.md` reference documentation.

## [1.0.1] - 2026-02-03

### Added
- ZIP packaging capability for claude.ai and Claude Desktop
- Hybrid API key discovery (environment variable → config file → runtime prompt)
- `config.json` template for embedded API key storage
- Documentation for claude.ai and Claude Desktop installation

### Changed
- Updated API key discovery logic to support multiple sources
- Expanded supported platforms to include claude.ai and Claude Desktop

## [1.0.0] - 2026-02-01

### Added
- Initial release of the Universal Skills Manager.
- Skill definition with `SKILL.md`.
- `install_skill.py` script for atomic, safe installation.
- Support for multiple AI ecosystems (Claude Code, Gemini, Anti-Gravity, OpenCode, etc.).
- SkillsMP.com API integration for skill discovery.
