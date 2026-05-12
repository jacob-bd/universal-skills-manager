# Universal Skills Manager

<p align="center">
  <img src="assets/mascot.png" alt="Universal Skills Manager" width="100%">
</p>

<p align="center">
  <a href="https://skillsmp.com">SkillsMP.com</a> •
  <a href="https://skills.palebluedot.live">SkillHub</a> •
  <a href="https://clawhub.ai">ClawHub</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a> •
  <a href="#supported-tools">Supported Tools</a>
</p>

---

**v1.13.0** · Three-source skill discovery · 11 supported AI tools · Cross-tool sync status reporter · ChatGPT cloud upload · Hardened security scanning

A centralized skill manager for AI coding assistants. Discovers, installs, and synchronizes skills from multiple sources — [SkillsMP.com](https://skillsmp.com) (curated, AI semantic search), [SkillHub](https://skills.palebluedot.live) (community skills, no API key required), and [ClawHub](https://clawhub.ai) (versioned skills, semantic search, no API key required) — across multiple AI tools including Claude Code, OpenAI Codex, Gemini CLI, and more.

## Demo

**Latest Overview (v1.6.0)**

<p align="center">
  <a href="https://youtu.be/-6QdwLFR_a0">
    <img src="https://img.youtube.com/vi/-6QdwLFR_a0/0.jpg" alt="Universal Skills Manager Latest Overview" width="100%">
  </a>
</p>

This video covers:
- Security scanning at install time
- Claude Desktop ZIP packaging and frontmatter compatibility
- And more

---

**Original Demo**

<p align="center">
  <a href="https://youtu.be/PnOD9pJCk1U">
    <img src="https://img.youtube.com/vi/PnOD9pJCk1U/0.jpg" alt="Universal Skills Manager Demo" width="100%">
  </a>
</p>

This video covers:
- Installation
- Searching for a skill
- Installing a skill
- Generating a skill report
- Synchronizing skills among multiple tools

## Features

- 🔍 **Multi-Source Search**: Find skills from SkillsMP (curated, AI semantic search), SkillHub (community catalog), and ClawHub (versioned skills, semantic search) — no API key needed for SkillHub or ClawHub
- 📦 **One-Click Install**: Download and validate skills with atomic installation (temp → validate → install)
- 🛡️ **Security Scanning**: 20+ detection categories across 3 severity levels at install time ([details](docs/TECHNICAL.md#security-scanning))
- 🔄 **Cross-Tool Sync**: Detect out-of-sync skills across tools, see which copy is newest, and sync with explicit approval — powered by `sync_skills.py` (read-only status reporter) plus agent-driven copy operations
- 📊 **Skill Matrix Report**: See which skills are installed on which tools at a glance
- ⚡ **One-Liner Installer**: `curl | sh` auto-detects your tools and installs everywhere, with `--tools` flag for targeting specific tools
- ✅ **Multi-File Validation**: Validates `.py`, `.sh`, `.json`, `.yaml` files during install
- 🌍 **Global Installation**: User-level skills available across all projects
- ☁️ **Cloud Upload Packaging**: Create ready-to-upload ZIP files for claude.ai/Claude Desktop/ChatGPT

## Installation

### Option 1: One-Liner Install (Recommended)

Auto-detects your installed AI tools and installs to all of them:

```bash
curl -fsSL https://raw.githubusercontent.com/jacob-bd/universal-skills-manager/main/install.sh | sh
```

Or install to specific tools only:

```bash
# Install to Claude Code and Gemini CLI only
curl -fsSL https://raw.githubusercontent.com/jacob-bd/universal-skills-manager/main/install.sh -o /tmp/install.sh
sh /tmp/install.sh --tools claude,gemini

# Or pipe directly — install to Codex only
curl -fsSL https://raw.githubusercontent.com/jacob-bd/universal-skills-manager/main/install.sh | sh -s -- --tools codex
```

**Supported `--tools` values:** `claude`, `gemini`, `antigravity`, `opencode`, `openclaw`, `alef-agent`, `codex`, `goose`, `roo`, `cursor`, `cline`, `hermes` (`gemini` and `codex` both install to `~/.agents/skills/`)

> **Note:** The installer automatically installs to **all** detected AI tools without prompting for confirmation. If you only want to install to specific tools, use the `--tools` flag to target them explicitly.

### Option 2: Manual Install

```bash
git clone https://github.com/jacob-bd/universal-skills-manager.git
cd universal-skills-manager
cp -r universal-skills-manager ~/.claude/skills/   # or your tool's path from the table below
```

After installing, restart your AI tool to pick up the new skill.

## Quick Start

Once installed, just ask your AI assistant:

```
"Search for a debugging skill"
"Install the humanizer skill"
"Show me my skill report"
"Sync the skill-creator to all my tools"
"What skills do I have in Codex vs Claude?"
"Check which of my skills are out of sync"
```

## How It Works

1. **Discovery**: The AI queries multiple sources (SkillsMP, SkillHub, ClawHub) using keyword or semantic search
2. **Selection**: You choose which skill to install from the results
3. **Fetching**: The AI fetches the skill content from GitHub or directly from ClawHub
4. **Installation**: Creates the proper directory structure and runs security scanning
5. **Synchronization**: Runs `sync_skills.py` to detect tools and compare skill versions, then copies to other locations with your approval

## Supported Tools

| AI Tool | Global Path | Local Path |
|---------|-------------|------------|
| **Claude Code** | `~/.claude/skills/` | `./.claude/skills/` |
| **Cursor** | `~/.cursor/skills/` | `./.cursor/skills/` |
| **Gemini CLI / Codex** | `~/.agents/skills/` | `./.agents/skills/` |
| **Google Anti-Gravity** | `~/.gemini/antigravity/skills/` | `./.antigravity/extensions/` |
| **OpenCode** | `~/.config/opencode/skills/` | `./.opencode/skills/` |
| **OpenClaw** | `~/.openclaw/workspace/skills/` | `./.openclaw/skills/` |
| **Alef Agent** | `~/.alef-agent/workspace/skills/` | N/A (daemon, no project scope) |
| **block/goose** | `~/.config/goose/skills/` | `./.goose/agents/` |
| **Roo Code** | `~/.roo/skills/` | `./.roo/skills/` |
| **Cline** | `~/.cline/skills/` | `./.cline/skills/` |
| **Hermes Agent** | `~/.hermes/skills/` | `./.hermes/skills/` |

## Cloud Platforms (claude.ai, Claude Desktop, ChatGPT)

For claude.ai, Claude Desktop, or ChatGPT, skills need to be uploaded as ZIP files. If you have the skill installed in Claude Code or another local tool, just ask:

```
"Package this skill for claude.ai"
"Create a ZIP for Claude Desktop"
"Package this for ChatGPT"
```

The AI will validate the skill's frontmatter for compatibility, package it, and provide platform-specific upload instructions.

| Platform | Upload Path |
|----------|------------|
| **claude.ai / Claude Desktop** | Settings → Capabilities → Upload skill |
| **ChatGPT** | Profile → Skills → New skill → Upload from your computer |

> **ChatGPT Note:** Skills are currently in beta and available on Business, Enterprise, Edu, Teachers, and Healthcare plans.

> **Claude Desktop Limitation:** Claude Desktop has a [known bug](https://github.com/anthropics/claude-code/issues) where custom domains added to the network egress whitelist aren't included in the JWT token. Until this is fixed, **Claude Code CLI is the recommended way to use the Universal Skills Manager**.

For manual packaging, frontmatter compatibility details, and the validation script, see [Technical Docs: Cloud Platforms](docs/TECHNICAL.md#cloud-platforms-claudeai--claude-desktop--chatgpt).

## Configuration

A SkillsMP API key enables curated search with AI semantic matching. **The API key is optional** — SkillHub and ClawHub work without one.

```bash
# Add to your shell profile (Zsh)
echo 'export SKILLSMP_API_KEY="your_key"' >> ~/.zshrc
source ~/.zshrc
```

Get your key at [SkillsMP.com](https://skillsmp.com). For other setup methods (Bash, .env file, Windows, verification), see [Technical Docs: API Key Setup](docs/TECHNICAL.md#api-key-setup).

## Repository Structure

```
universal-skills-manager/
├── install.sh                       # One-liner installer script
├── README.md                        # This file
├── CHANGELOG.md                     # Version history
├── CLAUDE.md                        # Claude Code context file
├── SECURITY.md                      # Security policy and vulnerability reporting
├── docs/
│   ├── TECHNICAL.md                 # Technical reference (APIs, scripts, security details)
│   ├── SECURITY_SCANNING.md         # Security scanner reference
│   ├── scan_skill-security-analysis.md  # Full security analysis of scanner
│   └── remediation-final-code-review.md # Code review of security hardening
├── tests/
│   ├── conftest.py                  # Test fixtures
│   ├── test_scan_skill.py           # Scanner test suite (65 tests)
│   └── test_sync_skills.py          # Sync reporter test suite (63 tests)
└── universal-skills-manager/        # The skill itself
    ├── SKILL.md                     # Skill definition and logic
    ├── config.json                  # API key config template
    └── scripts/
        ├── install_skill.py         # Helper script for downloading skills
        ├── scan_skill.py            # Security scanner (20+ detection categories)
        ├── sync_skills.py           # Read-only sync status reporter across AI tools
        └── validate_frontmatter.py  # Cloud platform YAML frontmatter validator
```

## Contributing

Skills are sourced from the community via [SkillsMP.com](https://skillsmp.com), [SkillHub](https://skills.palebluedot.live), and [ClawHub](https://clawhub.ai). To contribute:

1. Create your skill with proper YAML frontmatter
2. Host it on GitHub (for SkillsMP/SkillHub) or publish directly to ClawHub
3. Submit to SkillsMP.com for curated indexing, let SkillHub auto-index from GitHub, or publish via ClawHub's platform

## License

MIT License - See repository for details

## Support

- **Issues**: [GitHub Issues](https://github.com/jacob-bd/universal-skills-manager/issues)
- **Technical Docs**: [docs/TECHNICAL.md](docs/TECHNICAL.md) — API reference, scripts, security details
- **SkillsMP**: [skillsmp.com](https://skillsmp.com) · **SkillHub**: [skills.palebluedot.live](https://skills.palebluedot.live) · **ClawHub**: [clawhub.ai](https://clawhub.ai)

## Acknowledgments

This skill was inspired by the [skill-lookup](https://skillsmp.com/skills/f-prompts-chat-plugins-claude-prompts-chat-skills-skill-lookup-skill-md) skill by f-prompts.

Special thanks to [@ben-alkov](https://github.com/ben-alkov) for the comprehensive security analysis and hardening of `scan_skill.py` (PR #2).
