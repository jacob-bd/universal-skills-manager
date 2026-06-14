# Technical Reference

Detailed technical documentation for the Universal Skills Manager. For a quick overview, see the [README](../README.md).

## Table of Contents

- [Security Scanning](#security-scanning)
- [Install Script Usage](#install-script-usage)
- [Sync Status Reporter](#sync-status-reporter)
- [API Key Setup (All Options)](#api-key-setup)
- [API Reference](#api-reference)
- [Cloud Platforms (claude.ai / Claude Desktop / ChatGPT)](#cloud-platforms-claudeai--claude-desktop--chatgpt)
- [Frontmatter Compatibility](#frontmatter-compatibility)

---

## Security Scanning

Skills are automatically scanned for security threats at install time. The scanner (`scan_skill.py`) checks 30+ threat categories:

**Critical:**
- Symlink traversal and path escape attempts
- Invisible/zero-width Unicode characters hiding instructions
- Data exfiltration via markdown images with variable interpolation
- Remote code piped into shell interpreters (`curl | bash`)
- Unclosed HTML comments suppressing subsequent content

**Warning:**
- Credential file references (`~/.ssh/`, `~/.aws/`, etc.) and 30+ sensitive env var patterns
- Hardcoded secrets (AWS keys, GitHub PATs, Slack tokens, JWTs, private key blocks)
- Dangerous command execution (`eval()`, `os.system()`, `subprocess.run()`)
- Prompt injection (instruction overrides, role hijacking, safety bypasses)
- Homoglyph characters (Cyrillic look-alikes that bypass text-based checks)
- Data URIs, JavaScript URIs, and protocol-relative URLs
- Supply Chain risks (unpinned deps, remote execution via pip, obfuscation, typosquatting)
- Excessive Agency (unrestricted tools, autonomous high-impact actions, unbounded resources)
- Output Handling (unvalidated outputs to SQL/shell, cross-context leakage)
- Memory Poisoning (unvalidated persistence, context stuffing)
- Rogue Agent behavior (self-modification, persistence mechanisms like cron)
- Privilege Escalation (sudo/root command usage)
- Tool Misuse (dangerous parameters like shell=True, --force)

**Info:**
- Encoded content (base64, hex, URL-encoded payloads)
- LLM delimiter tokens, cross-skill escalation attempts
- Binary files and unreadable files
- System Prompt Leakage (attempting to print or expose internal instructions)
- Trigger Abuse (overly broad trigger patterns)

**Scanner defenses:** Triple-layer symlink protection, fd-based TOCTOU mitigation, 10MB file size limit, ANSI escape stripping, Unicode NFC normalization, continuation line joining for multi-line payloads.

Findings are displayed with severity levels and you choose whether to proceed. See also [Security Scanning Reference](SECURITY_SCANNING.md) and [SECURITY.md](../SECURITY.md).

---

## Install Script Usage

The skill includes a Python helper script (`install_skill.py`) for downloading skills from GitHub:

```bash
# Preview what would be downloaded (dry-run)
python3 path/to/install_skill.py \
  --url "https://github.com/user/repo/tree/main/skill-folder" \
  --dest "~/.agents/skills/my-skill" \
  --dry-run

# Actually install to your preferred tool
python3 path/to/install_skill.py \
  --url "https://github.com/user/repo/tree/main/skill-folder" \
  --dest "~/.agents/skills/my-skill" \
  --force
```

**Script features:**
- Zero dependencies (Python 3 stdlib only)
- Atomic install (downloads to temp, validates, then copies to destination)
- Safety check prevents accidental targeting of root skills directories
- Compares new vs existing skills before update (shows diff)
- Validates `.py`, `.sh`, `.json`, `.yaml` files
- Supports subdirectories and nested files
- Skip security scan with `--skip-scan` (not recommended)

---

## Sync Status Reporter

The skill includes a read-only diagnostic tool (`sync_skills.py`) that detects installed AI tools, inventories skills across them, compares content via hashes, and outputs a sync status report. It never creates, modifies, or deletes any files.

```bash
# Check sync status across all detected tools
python3 path/to/sync_skills.py

# Check a specific skill only
python3 path/to/sync_skills.py --skill code-review

# Include project-level skill directories
python3 path/to/sync_skills.py --project-dir /path/to/project

# Machine-readable JSON output
python3 path/to/sync_skills.py --json

# Show per-file hash details for out-of-sync skills
python3 path/to/sync_skills.py --verbose
```

**Script features:**
- Zero dependencies (Python 3 stdlib only)
- Detects all 11 supported AI tools by probing for their skills directories
- Supports both user-level (global) and project-level (local) scopes
- Compares directory content using MD5 hashes (not just modification times)
- Reports four statuses: **in sync** (identical hashes), **out of sync** (2 distinct versions, identifies newest by mtime), **conflict** (3+ distinct versions, multi-way divergence), **single-tool only** (informational)
- Per-file verbose diff: `--verbose` shows which specific files are added/removed/modified between locations
- File count display for single-tool skills (e.g., `(19 files)`)
- Exit code 2 when drift detected (enables cron/CI alerting); exit 0 when all in sync
- Human-readable table output (default) or JSON for programmatic use

**Two-layer architecture:** The script only reports status. All write operations (copy, overwrite, deploy) are performed by the AI agent after presenting proposed changes and receiving explicit user confirmation.

---

## API Key Setup

The Universal Skills Manager uses a SkillsMP API key for curated search with AI semantic matching. **The API key is optional** -- without it, you can still search SkillHub and ClawHub.

### Option 1: Shell Profile (Recommended)

```bash
# For Zsh users (macOS default)
echo 'export SKILLSMP_API_KEY="your_api_key_here"' >> ~/.zshrc
source ~/.zshrc

# For Bash users
echo 'export SKILLSMP_API_KEY="your_api_key_here"' >> ~/.bashrc
source ~/.bashrc
```

### Option 2: .env File in Home Directory

```bash
# Create ~/.env
cat > ~/.env << 'EOF'
SKILLSMP_API_KEY=your_api_key_here
EOF

# Add to your shell profile to auto-load
echo 'source ~/.env' >> ~/.zshrc
```

### Option 3: Session-based (Temporary)

```bash
export SKILLSMP_API_KEY="your_api_key_here"
```

This only persists for the current terminal session.

### Windows Users

PowerShell:
```powershell
[System.Environment]::SetEnvironmentVariable('SKILLSMP_API_KEY', 'your_api_key_here', 'User')
```

Command Prompt:
```cmd
setx SKILLSMP_API_KEY "your_api_key_here"
```

Restart your terminal for changes to take effect.

### Getting Your API Key

1. Visit [SkillsMP.com](https://skillsmp.com)
2. Navigate to the API section
3. Generate or copy your API key

### Verify API Key Setup

```bash
echo $SKILLSMP_API_KEY

curl -X GET "https://skillsmp.com/api/v1/skills/search?q=test&limit=1" \
  -H "Authorization: Bearer $SKILLSMP_API_KEY" \
  -H "User-Agent: Universal-Skills-Manager"
```

If configured correctly, you should see a JSON response with skill data.

---

## API Reference

> **Note:** Always include a `User-Agent` header in all API requests. SkillsMP is behind Cloudflare and returns 403 Forbidden for bare curl requests.

### SkillsMP (Curated, API Key Required)

**Keyword Search**
```bash
curl -X GET "https://skillsmp.com/api/v1/skills/search?q=debugging&limit=20&sortBy=recent" \
  -H "Authorization: Bearer $SKILLSMP_API_KEY" \
  -H "User-Agent: Universal-Skills-Manager"
```

**AI Semantic Search**
```bash
curl -X GET "https://skillsmp.com/api/v1/skills/ai-search?q=help+me+debug+code" \
  -H "Authorization: Bearer $SKILLSMP_API_KEY" \
  -H "User-Agent: Universal-Skills-Manager"
```

**Wildcard / Top Skills** (use `q=*` with `sortBy=stars` when no specific query):
```bash
curl -X GET "https://skillsmp.com/api/v1/skills/search?q=*&limit=20&sortBy=stars" \
  -H "Authorization: Bearer $SKILLSMP_API_KEY" \
  -H "User-Agent: Universal-Skills-Manager"
```

**Response Format:**
```json
{
  "success": true,
  "data": {
    "skills": [
      {
        "id": "skill-id",
        "name": "code-debugging",
        "author": "AuthorName",
        "description": "Systematic debugging methodology...",
        "githubUrl": "https://github.com/user/repo/tree/main/skills/code-debugging",
        "stars": 15,
        "updatedAt": 1768838561
      }
    ]
  }
}
```

### SkillHub (Community, No API Key Required)

**Search Skills**
```bash
curl -X GET "https://skills.palebluedot.live/api/skills?q=debugging&limit=20" \
  -H "User-Agent: Universal-Skills-Manager"
```

**Get Skill Details (required before install)**
```bash
curl -X GET "https://skills.palebluedot.live/api/skills/{id}" \
  -H "User-Agent: Universal-Skills-Manager"
```

**Response Format (Search):**
```json
{
  "skills": [
    {
      "id": "wshobson/agents/debugging-strategies",
      "name": "debugging-strategies",
      "description": "Master systematic debugging...",
      "githubOwner": "wshobson",
      "githubRepo": "agents",
      "githubStars": 27021,
      "securityScore": 100
    }
  ],
  "pagination": { "page": 1, "limit": 20, "total": 1000 }
}
```

### ClawHub (Versioned, Semantic Search, No API Key Required)

**Semantic Search**
```bash
curl -X GET "https://clawhub.ai/api/v1/search?q=debugging&limit=20" \
  -H "User-Agent: Universal-Skills-Manager"
```

**Browse by Stars** (also supports `sort=downloads`, `sort=trending`, `sort=updated`)
```bash
curl -X GET "https://clawhub.ai/api/v1/skills?limit=20&sort=stars" \
  -H "User-Agent: Universal-Skills-Manager"
```

**Get Skill Details**
```bash
curl -X GET "https://clawhub.ai/api/v1/skills/{slug}" \
  -H "User-Agent: Universal-Skills-Manager"
```

**Get Skill File (raw text, NOT JSON)**
```bash
curl -X GET "https://clawhub.ai/api/v1/skills/{slug}/file?path=SKILL.md" \
  -H "User-Agent: Universal-Skills-Manager"
```

**Response Format (Search):**
```json
{
  "results": [
    {
      "score": 0.82,
      "slug": "self-improving-agent",
      "displayName": "Self-Improving Agent",
      "summary": "An agent that iteratively improves itself...",
      "version": "1.0.0",
      "updatedAt": "2026-01-15T10:30:00Z"
    }
  ]
}
```

**Key Differences:** ClawHub hosts skill files directly (not on GitHub), uses slug-based identifiers, supports semantic/vector search, and includes explicit version numbers. Rate limit: 120 reads/min per IP.

---

## Cloud Platforms (claude.ai / Claude Desktop / ChatGPT)

All three cloud platforms require skills to be uploaded as ZIP files and follow the same [Agent Skills specification](https://agentskills.io/specification) for SKILL.md frontmatter validation.

### Platform Upload Paths

| Platform | Upload Path | Plans |
|----------|------------|-------|
| **claude.ai** | Settings → Capabilities → Upload Skill | All Claude plans |
| **Claude Desktop** | Settings → Capabilities → Upload Skill | All Claude plans |
| **ChatGPT** | Profile → Skills → New skill → Upload from your computer | Business, Enterprise, Edu, Teachers, Healthcare (beta) |

### ChatGPT Skills Notes

- Skills are currently in beta and off by default for Enterprise/Edu — workspace admins must enable them in Permissions & roles
- Skills can be shared within a workspace and installed for other members
- ChatGPT also has a [Skills editor](https://chatgpt.com/skills/editor) for building skills in-browser
- Skills can be @-mentioned in conversations for explicit invocation
- Skills follow the open [Agent Skills standard](https://agentskills.io/home) and are portable across tools
- OpenAI also provides a [Skills API](https://developers.openai.com/api/docs/guides/tools-skills/) (`POST /v1/skills`) for programmatic upload with versioning

### ChatGPT Skills Limits

| Limit | Value |
|-------|-------|
| Max uncompressed file size | 25 MB |
| Max ZIP upload size | 50 MB |
| Max files per skill | 500 |
| SKILL.md matching | Case-insensitive |

### Known Limitation (Claude Desktop)

Claude Desktop has a [known bug](https://github.com/anthropics/claude-code/issues) where custom domains added to the network egress whitelist are not included in the JWT token. This means the Universal Skills Manager cannot reach SkillsMP, SkillHub, or ClawHub APIs even when the domains are whitelisted. Until this is fixed, **Claude Code CLI is the recommended way to use this skill**.

### Manual Packaging

If you want to manually package a skill for any cloud platform:

1. Copy the skill folder and optionally create `config.json`:
   ```bash
   cp -r universal-skills-manager /tmp/
   echo '{"skillsmp_api_key": "YOUR_KEY_HERE"}' > /tmp/universal-skills-manager/config.json
   ```

2. Create ZIP:
   ```bash
   cd /tmp && zip -r universal-skills-manager.zip universal-skills-manager/
   ```

3. Upload to your platform:
   - **claude.ai / Claude Desktop**: Go to Settings → Capabilities → Click "Upload skill" → Select ZIP
   - **ChatGPT**: Click profile → Skills → "New skill" → "Upload from your computer" → Select ZIP

**Security Note:** If the packaged ZIP contains your API key, do not share it publicly or commit it to version control.

---

## Frontmatter Compatibility

Cloud platforms use strict YAML parsing for SKILL.md frontmatter. Claude Desktop uses [`strictyaml`](https://hitchdev.com/strictyaml/) (not standard PyYAML), and ChatGPT follows the same [Agent Skills spec](https://agentskills.io/specification) validation. Many third-party skills fail to upload with "malformed YAML frontmatter" or "unexpected key" errors.

### Allowed Frontmatter Fields (Agent Skills Spec)

| Field | Required | Constraints |
|-------|----------|-------------|
| `name` | Yes | Max 64 chars, lowercase letters/numbers/hyphens only, must match directory name |
| `description` | Yes | Max 1024 chars. No angle brackets (`<` `>`). Literal block scalars (`\|`) with blank lines fail. Folded scalars (`>`) work but inline strings are safest |
| `license` | No | License name or reference to bundled file |
| `compatibility` | No | Max 500 chars, environment requirements |
| `metadata` | No | Flat string key-value pairs only (no nested objects, no arrays) |
| `allowed-tools` | No | Space-delimited string of pre-approved tools (not a YAML list) |

### Validation Script

The `validate_frontmatter.py` script checks and auto-fixes skills for cloud platform compatibility (claude.ai, Claude Desktop, and ChatGPT):

```bash
# Check a skill for issues
python3 scripts/validate_frontmatter.py /path/to/SKILL.md

# Auto-fix and overwrite
python3 scripts/validate_frontmatter.py /path/to/SKILL.md --fix

# Fix a skill inside a ZIP file
python3 scripts/validate_frontmatter.py /path/to/skill.zip --fix
```

**What `--fix` does:**
- Moves unsupported top-level keys (e.g., `version`, `author`) into `metadata` as string values
- Collapses literal block scalar (`|`) descriptions to inline quoted strings (error if blank lines present). Folded scalars (`>`) trigger a warning but are not auto-fixed since they work in current testing
- Converts YAML list-format `allowed-tools` to space-delimited string
- Strips angle brackets from description
- Flattens nested `metadata` objects to flat string key-value pairs
- Truncates fields exceeding length limits

The skill's functionality is preserved. When using the Universal Skills Manager to package skills for cloud platforms, this check runs automatically -- you'll be notified of any issues and asked before any fixes are applied.

### Sources

- [Agent Skills Specification](https://agentskills.io/specification)
- [agentskills/agentskills reference SDK](https://github.com/agentskills/agentskills/tree/main/skills-ref) (uses `strictyaml`)
- [anthropics/skills quick_validate.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/quick_validate.py)
- [OpenAI Skills API Docs](https://developers.openai.com/api/docs/guides/tools-skills/)
- [OpenAI Skills Cookbook](https://developers.openai.com/cookbook/examples/skills_in_api)
