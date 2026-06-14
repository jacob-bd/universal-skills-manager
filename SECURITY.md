# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in the Universal Skills Manager, please report it responsibly.

**Preferred method:** Open a [GitHub Issue](https://github.com/jacob-bd/universal-skills-manager/issues) with the label "security". For sensitive issues that should not be disclosed publicly, reach out via Red Hat Slack (if applicable) or email.

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Affected component (`scan_skill.py`, `install_skill.py`, `SKILL.md` instructions, etc.)
- Severity assessment (if you have one)

**What's in scope:**
- The security scanner (`scan_skill.py`) -- detection bypasses, evasion techniques, false negatives
- The installer (`install_skill.py`) -- path traversal, symlink attacks, network security, credential handling
- The skill definition (`SKILL.md`) -- overly broad instructions, credential exposure, unintended side effects

**What's NOT in scope:**
- Skills discovered/installed via SkillsMP, SkillHub, or ClawHub (those are third-party)
- The SkillsMP, SkillHub, or ClawHub APIs themselves

## Response Timeline

- **Acknowledgment:** Within 48 hours
- **Assessment:** Within 1 week
- **Fix (if accepted):** Best effort, typically within 2 weeks for critical issues

## Security Architecture

### Security Scanner (`scan_skill.py` v1.3.0)

The scanner runs automatically during skill installation and checks for 30+ threat categories:

**Critical detections:**
- Symlink traversal and path escape attempts
- Invisible/zero-width Unicode characters hiding instructions
- Data exfiltration via markdown images with variable interpolation
- Remote code piped into shell interpreters (`curl | bash`)
- Unclosed HTML comments suppressing subsequent content
- ANSI escape injection in terminal output

**Warning detections:**
- Credential file path references (`~/.ssh/`, `~/.aws/`, etc.)
- Sensitive environment variable references (30+ patterns)
- Hardcoded secrets (AWS keys, GitHub PATs, Slack tokens, JWTs, private keys)
- Dangerous command execution patterns (`eval()`, `os.system()`, `subprocess.run()`)
- External URL fetching that may load untrusted content
- Prompt injection indicators (instruction overrides, role hijacking, safety bypasses)
- Homoglyph characters (Cyrillic look-alikes that bypass text matching)
- Data URIs, JavaScript URIs, and protocol-relative URLs
- Oversized files (>10MB) that may cause resource exhaustion
- Supply Chain risks (unpinned dependencies, remote execution via pip, obfuscation, typosquatting)
- Excessive Agency (unrestricted tools, autonomous high-impact actions, unbounded resources)
- Output Handling (unvalidated outputs to SQL/shell, cross-context leakage)
- Memory Poisoning (unvalidated persistence, context stuffing)
- Rogue Agent behavior (self-modification, persistence mechanisms like cron)
- Privilege Escalation (sudo/root command usage)
- Tool Misuse (dangerous parameters like shell=True, --force)

**Info detections:**
- Base64/hex/URL-encoded content that may hide payloads
- LLM delimiter tokens (`<|system|>`, `[INST]`, etc.)
- Cross-skill escalation attempts
- Binary or non-UTF-8 files
- Unreadable files (permission denied)
- System Prompt Leakage (attempting to print or expose internal instructions)
- Trigger Abuse (overly broad trigger patterns)

**Scanner defenses:**
- Symlink protection: triple-layer (`followlinks=False`, `is_symlink()`, `resolve().relative_to()`)
- TOCTOU mitigation: fd-based file reading with `O_NOFOLLOW`
- Resource limits: 10MB file size, 1000 file count, 10 directory depth
- ANSI escape stripping on all output fields
- Unicode NFC normalization before pattern matching
- Continuation line joining for multi-line payload detection
- Finding deduplication to prevent report inflation

### Installer (`install_skill.py` v1.3.0)

- Atomic installation pattern (temp dir, validate, move)
- Path traversal protection (`sanitize_filename`, `verify_path_containment`)
- Symlink detection in existing skill directories
- Root skills directory safety check (prevents overwriting multiple skills)
- Diff-before-overwrite with user confirmation
- Manifest tracking (`skills.lock.json`) with SHA-256 content hashes

### Credential Handling

- The `SKILLSMP_API_KEY` is declared as the primary credential in skill metadata
- The API key is only used for authenticated requests to the SkillsMP API
- For claude.ai ZIP packaging: the key is stored locally in `config.json` inside the ZIP and is never transmitted to third-party servers
- The scanner flags any hardcoded credentials in skill files being installed

## Known Limitations

- The scanner uses denylist-based detection (regex pattern matching). An allowlist approach would provide stronger coverage but is not yet implemented.
- Homoglyph transliteration covers common Cyrillic-to-Latin substitutions. Other scripts (Greek, Armenian, etc.) are not yet covered.
- The `sk-` API key pattern (`sk-[a-zA-Z0-9]{20,}`) may produce false positives on legitimate strings with that prefix.

## Acknowledgments

- [@ben-alkov](https://github.com/ben-alkov) -- Security analysis and hardening of `scan_skill.py` (PR #2), addressing 20 findings across 4 severity levels with comprehensive test coverage.
