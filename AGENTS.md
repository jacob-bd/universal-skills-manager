# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

This repository contains the **Universal Skills Manager** skill, which acts as a centralized skill manager for AI capabilities across multiple AI coding tools (Gemini CLI, Google Antigravity, OpenCode, Codex, Cline, Cursor, etc.).

The skill enables:
- **Discovery**: Searching for skills from multiple sources — SkillsMP.com (curated, AI semantic search), SkillHub (community skills, no API key required), and ClawHub (versioned skills, semantic search, no API key required)
- **Installation**: Installing skills from GitHub or ClawHub to User-level (global) or Project-level (local) scopes
- **Synchronization**: Copying/syncing skills across different AI tools
- **Consistency**: Maintaining version consistency across installed locations
- **Cloud Packaging**: Creating ready-to-upload ZIP files for Codex.ai/Codex Desktop/ChatGPT with embedded API keys

## Architecture

This is a **skill definition repository** containing the Universal Skills Manager in the `universal-skills-manager/` subfolder. It is not a traditional codebase with source files.

### Repository Structure

```
universal-skills-manager/
├── README.md                       # Installation & usage documentation
├── AGENTS.md                       # This file - technical context
├── SECURITY.md                     # Security policy and vulnerability reporting
├── specs.md                        # Technical specification for install script
├── docs/
│   ├── TECHNICAL.md                # Technical reference (APIs, scripts, security details)
│   ├── SECURITY_SCANNING.md        # Security scanner reference
│   ├── scan_skill-security-analysis.md  # Full security analysis of scanner
│   └── remediation-final-code-review.md # Code review of security hardening
├── tests/
│   ├── conftest.py                 # Test fixtures (scanner, tmp_skill helpers)
│   ├── test_scan_skill.py          # Scanner test suite (65 tests)
│   └── test_sync_skills.py         # Sync reporter test suite (63 tests)
└── universal-skills-manager/       # The skill folder
    ├── SKILL.md                    # Skill definition and logic
    └── scripts/
        ├── install_skill.py        # Python helper for downloading skills from GitHub
        ├── scan_skill.py           # Security scanner (20+ detection categories)
        ├── sync_skills.py          # Read-only sync status reporter across AI tools
        └── validate_frontmatter.py # Cloud platform YAML frontmatter validator
```

### Skill Structure

The `SKILL.md` file follows this format:
- **Frontmatter**: YAML metadata (name, description, homepage, metadata block with runtime requirements)
- **Documentation**: Markdown content describing when to use the skill, capabilities, operational rules
- **Implementation details**: Instructions for the AI agent on how to execute skill functionality

### Supported Tool Ecosystem

The skill manages skills across these AI tools and their respective paths:

| Tool | User Scope (Global) | Project Scope (Local) |
|------|---------------------|----------------------|
| Gemini CLI / Codex | `~/.agents/skills/` | `./.agents/skills/` |
| Google Antigravity | `~/.gemini/antigravity/skills/` | `./.antigravity/extensions/` |
| Google Antigravity CLI | `~/.gemini/antigravity-cli/skills/` | `./.agents/skills/` |
| OpenCode | `~/.config/opencode/skills/` | `./.opencode/skills/` |
| OpenClaw | `~/.openclaw/workspace/skills/` | `./.openclaw/skills/` |
| Alef Agent | `~/.alef-agent/workspace/skills/` | N/A (daemon, no project scope) |
| Codex | `~/.Codex/skills/` | `./.Codex/skills/` |
| block/goose | `~/.config/goose/skills/` | `./.goose/agents/` |
| Roo Code | `~/.roo/skills/` | `./.roo/skills/` |
| Cursor | `~/.cursor/skills/` | `./.cursor/skills/` |
| Cline | `~/.cline/skills/` | `./.cline/skills/` |
| Hermes Agent | `~/.hermes/skills/` | `./.hermes/skills/` |

*Note: Gemini CLI (v0.30+) and OpenAI Codex both read `~/.agents/skills/`. Gemini CLI also reads `~/.gemini/skills/` but gives `.agents/` higher precedence. We install to `~/.agents/skills/` only to avoid duplicate-skill conflicts.*

### Cloud Platform Support (Codex.ai, Codex Desktop, ChatGPT)

For Codex.ai, Codex Desktop, and ChatGPT, skills must be uploaded as ZIP files through their respective web UIs. The skill includes a "Package for Cloud Upload" capability that:
1. Prompts user for their SkillsMP API key (optional — SkillHub works without one)
2. Creates `config.json` with the embedded key
3. Validates frontmatter against the Agent Skills spec
4. Generates a ZIP file ready for upload

**Upload paths:**
- **Codex.ai / Codex Desktop**: Settings → Capabilities → Upload Skill
- **ChatGPT**: Profile → Skills → New skill → Upload from your computer

ChatGPT Skills are in beta and available on Business, Enterprise, Edu, Teachers, and Healthcare plans. All three platforms follow the same [Agent Skills specification](https://agentskills.io/specification) for SKILL.md frontmatter.

The hybrid API key discovery checks:
1. `$SKILLSMP_API_KEY` environment variable (Codex)
2. `config.json` in skill directory (Codex.ai/Codex Desktop/ChatGPT)
3. Source selection prompt: offer SkillsMP (with key), SkillHub (no key needed), or ClawHub (no key needed) as fallback

## Key Concepts

### Multi-Source Skill Discovery

The skill discovers skills from three sources:

#### SkillsMP API (Primary, Curated)

**API Endpoints:**
- **Keyword Search**: `/api/v1/skills/search?q={query}&limit=20&sortBy=recent|stars`
- **AI Semantic Search**: `/api/v1/skills/ai-search?q={query}`

**Authentication:**
- Bearer token required via `SKILLSMP_API_KEY` environment variable
- Header format: `Authorization: Bearer $SKILLSMP_API_KEY`
- Configuration options:
  - Shell profile: `export SKILLSMP_API_KEY="your_key"` in `~/.zshrc` or `~/.bashrc`
  - Home directory .env: Create `~/.env` with the API key, then `source ~/.env`
  - Session-based: `export SKILLSMP_API_KEY="your_key"` (temporary)

**Response Fields:**
- `id`, `name`, `author`, `description`
- `githubUrl` (for fetching skill content)
- `skillUrl` (web page URL)
- `stars`, `updatedAt`

**Content Fetching:**
Skills are stored in GitHub repositories. To get the actual SKILL.md content:
1. Extract from `githubUrl`: `https://github.com/{user}/{repo}/tree/{branch}/{path}`
2. Convert to raw URL: `https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}/SKILL.md`
3. Fetch using curl or web_fetch

#### SkillHub API (Secondary, Community)

**Base URL:** `https://skills.palebluedot.live/api`

**Authentication:** None required (open API)

**API Endpoints:**
- **Search**: `GET /api/skills?q={query}&limit=20` — keyword search
- **Detail**: `GET /api/skills/{id}` — full skill details with `skillPath`, `branch`, `rawContent`
- **Categories**: `GET /api/categories` — list skill categories

**Response Fields (Search):**
- `id` (e.g., `wshobson/agents/debugging-strategies`), `name`, `description`
- `githubOwner`, `githubRepo`, `githubStars`
- `downloadCount`, `securityScore`, `rating`

**Content Fetching:**
1. Fetch skill detail: `GET /api/skills/{id}` to get `skillPath` and `branch`
2. Construct GitHub tree URL: `https://github.com/{githubOwner}/{githubRepo}/tree/{branch}/{skillPath}`
3. Pass to `install_skill.py` for download

**IMPORTANT:** The `id` field does NOT map to the file path within the repo. Always use the detail endpoint to get the correct `skillPath`.

#### ClawHub API (Tertiary, Versioned)

**Base URL:** `https://clawhub.ai/api/v1`

**Authentication:** None required (open API). Rate limit: 120 reads/min per IP.

**API Endpoints:**
- **Semantic Search**: `GET /api/v1/search?q={query}&limit=20` — vector/similarity search ranked by `score`
- **Browse/List**: `GET /api/v1/skills?limit=20&sort=stars|downloads|updated|trending&cursor={cursor}` — cursor-paginated browsing
- **Detail**: `GET /api/v1/skills/{slug}` — full skill details with owner, version, moderation status
- **File**: `GET /api/v1/skills/{slug}/file?path=SKILL.md&version={ver}` — raw file content (`text/plain`, NOT JSON)
- **Download**: `GET /api/v1/download?slug={slug}&version={ver}` — full skill as ZIP

**Response Fields (Search):**
- `score` (similarity), `slug`, `displayName`, `summary`, `version`, `updatedAt`

**Response Fields (Browse):**
- `slug`, `displayName`, `summary`, `version`, `stats.stars`, `stats.downloads`

**Content Fetching:**
ClawHub hosts skill files directly — no GitHub URL construction needed:
1. Fetch file content: `GET /api/v1/skills/{slug}/file?path=SKILL.md` (returns raw text)
2. For multi-file skills: `GET /api/v1/download?slug={slug}` (returns ZIP)
3. Run `scan_skill.py` manually (since `install_skill.py` is bypassed for ClawHub)

**Key Differences from SkillsMP/SkillHub:**
- Skills identified by `slug` (not GitHub paths)
- Direct file hosting (no GitHub URL construction)
- Explicit version numbers on every skill
- Built-in semantic/vector search
- VirusTotal integration for security scanning (`moderation` field)

### Skill Installation Flow

When installing a skill, the manager:
1. Identifies the source (SkillsMP search result, SkillHub search result, ClawHub search result, or local file)
2. Fetches skill content from GitHub (converts tree URL to raw URL) or directly from ClawHub (via `/file` endpoint)
3. Determines target scope (User/Global vs Project/Local)
4. Performs a "Sync Check" to detect other installed AI tools
5. Offers to sync the skill across all detected tools
6. Creates the skill directory structure: `.../skills/{skill-name}/SKILL.md`

### Skill Discovery

Skills are discovered from multiple sources:
- **SkillsMP.com** (primary, curated): Keyword search + AI semantic search, requires API key
- **SkillHub** (secondary, community): Keyword search, no API key required
- **ClawHub** (tertiary, versioned): Semantic/vector search, no API key required
- **Method**: API calls using curl/bash, parse JSON responses, display results with metadata and source labels

### Synchronization Logic

Synchronization uses a two-layer architecture:

**Layer 1: `sync_skills.py` (read-only diagnostic).** Detects installed AI tools, inventories skills across them, compares content using MD5 directory hashes, and outputs a status report (human-readable or JSON). It never modifies any files.

**Layer 2: SKILL.md agent instructions (action-capable with user approval).** The AI agent reads the sync report and can perform write operations (copy, overwrite, deploy) only after presenting proposed changes and receiving explicit user confirmation.

The sync reporter:
- Probes all 11 supported tool directories (user-level and optionally project-level)
- Compares directory hashes (not just modification times) for accurate drift detection
- Reports three statuses: in sync, out of sync (identifies newest by mtime), single-tool only
- Outputs human-readable table or JSON (`--json`) for programmatic consumption

## Working with This Repository

### File Locations

- **Skill definition**: `universal-skills-manager/SKILL.md` - The main skill logic and instructions
- **Install helper**: `universal-skills-manager/scripts/install_skill.py` - Python script for downloading skills from GitHub
- **Security scanner**: `universal-skills-manager/scripts/scan_skill.py` - Security scanner with 20+ detection categories
- **Frontmatter validator**: `universal-skills-manager/scripts/validate_frontmatter.py` - Cloud platform YAML frontmatter validator and fixer (Codex.ai/Codex Desktop/ChatGPT)
- **Sync status reporter**: `universal-skills-manager/scripts/sync_skills.py` - Read-only tool that detects installed AI tools, inventories skills, and reports sync status
- **Technical reference**: `docs/TECHNICAL.md` - API reference, script usage, security details, frontmatter spec
- **Scanner test suite**: `tests/test_scan_skill.py` - 65 tests covering all scanner detection categories
- **Sync test suite**: `tests/test_sync_skills.py` - 63 tests covering tool detection, inventory, comparison, output, per-file diffs, conflicts, and edge cases
- **Security policy**: `SECURITY.md` - Vulnerability reporting and security architecture
- **User documentation**: `README.md` - Installation, configuration, and usage guide
- **Developer context**: `AGENTS.md` - This file, technical architecture and guidelines

### Testing Changes

When modifying the skill:
1. Edit `universal-skills-manager/SKILL.md`
2. Verify environment variable `SKILLSMP_API_KEY` is set
3. Test API calls manually using curl (examples in README)
4. Install the modified skill locally to test: `cp -r universal-skills-manager ~/.Codex/skills/`
5. Test discovery, installation, and sync workflows

When modifying the security scanner (`scan_skill.py`):
1. Run the test suite: `python3 -m pytest tests/test_scan_skill.py -v`
2. All 65 tests must pass before committing
3. Test manually against a known-good skill directory
4. Test manually against a crafted malicious skill to verify detection

When modifying the sync status reporter (`sync_skills.py`):
1. Run the test suite: `python3 -m pytest tests/test_sync_skills.py -v`
2. All 63 tests must pass before committing
3. Test manually: `python3 universal-skills-manager/scripts/sync_skills.py`
4. Verify JSON output: `python3 universal-skills-manager/scripts/sync_skills.py --json`

## Development Guidelines

### Modifying the Skill

When editing `SKILL.md`:
- Maintain YAML frontmatter validity (name, description, homepage, metadata fields)
- Keep the structure: frontmatter → usage triggers → capabilities → operational rules
- Ensure instructions are clear for AI agent execution
- Test that the markdown renders correctly

### Adding New AI Tool Support

To add a new AI tool:
1. Add the tool to the ecosystem table in SKILL.md
2. Specify both User-level and Project-level paths
3. Document any tool-specific requirements (manifest files, naming conventions)
4. Update the "Cross-Platform Adaptation" section if the tool requires special handling

### Installed Skill Directory Structure

When the Universal Skills Manager installs a skill, it creates this structure in the target AI tool:
```
~/.Codex/skills/{skill-name}/     # Or other tool's path
  ├── SKILL.md (required)
  ├── Reference docs (optional)
  ├── Scripts (optional)
  └── Config files (optional)
```

For example, installing "code-debugging" creates:
```
~/.Codex/skills/code-debugging/SKILL.md
```

## Important Notes

- **API Key Optional**: The `SKILLSMP_API_KEY` environment variable enables SkillsMP search (curated, AI semantic). Without it, SkillHub's open catalog and ClawHub's versioned catalog are available as fallbacks. See README.md for configuration instructions.
- **Root Directory Safety**: The install script will abort with exit code 4 if the destination appears to be a root skills directory (contains skills but no SKILL.md). This prevents accidental data loss.
- **Update Comparison**: When updating an existing skill, the script compares files and shows a diff before overwriting, prompting for confirmation.
- **No overwriting without confirmation**: Always ask before overwriting existing skills unless "--force" is explicitly used
- **Structure integrity**: Never dump loose files into the root skills directory; always create a dedicated folder per skill
- **Cross-platform compatibility**: Some tools (OpenCode, Antigravity) may require additional manifest files generated from SKILL.md frontmatter
- **GitHub content fetching**: Skills from SkillsMP/SkillHub are fetched from GitHub using raw URLs converted from tree URLs. ClawHub skills are fetched directly via ClawHub's `/file` endpoint.
- **ClawHub install bypass**: ClawHub installs bypass `install_skill.py` (which expects GitHub URLs). Instead, content is fetched via ClawHub's API, saved to a temp directory, scanned with `scan_skill.py` manually, and then copied to the destination.
- **Cloud platform packaging**: Codex.ai, Codex Desktop, and ChatGPT all require ZIP file uploads. All three follow the same [Agent Skills specification](https://agentskills.io/specification) for SKILL.md frontmatter. The `validate_frontmatter.py` script validates compatibility for all three platforms. ChatGPT Skills are in beta (Business/Enterprise/Edu/Teachers/Healthcare plans).
- **Sync safety**: The `sync_skills.py` script is strictly read-only (it never modifies files). All sync write operations (copy, overwrite, deploy) are performed by the agent and require explicit user approval. No sync action is ever taken autonomously.
