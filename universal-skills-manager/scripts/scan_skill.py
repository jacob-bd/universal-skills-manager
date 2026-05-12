#!/usr/bin/env python3
"""
Universal Skill Scanner

A zero-dependency security scanner for AI skill packages. Analyzes SKILL.md
files and supporting scripts for potential security risks including prompt
injection, credential exfiltration, invisible unicode, and other threats.

Usage:
    python3 scan_skill.py <path>            # Scan a skill directory or file
    python3 scan_skill.py --pretty <path>   # Pretty-print the JSON report
    python3 scan_skill.py --version         # Print version and exit

Exit codes:
    0 - Clean (no findings)
    1 - Info-level findings only
    2 - Warning-level findings present
    3 - Critical-level findings present

Output:
    JSON report to stdout with fields:
        skill_path, files_scanned, scan_timestamp,
        summary (critical, warning, info counts),
        findings (list of finding objects)
"""

import argparse
import io
import json
import os
import re
import stat as stat_mod
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and not os.environ.get("PYTHONIOENCODING"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

VERSION = "1.2.0"

MAX_FILE_SIZE = 10_000_000  # 10 MB
MAX_FILE_COUNT = 1000
MAX_DIR_DEPTH = 10

_SCRIPT_EXTENSIONS = frozenset({
    ".py", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".rb", ".pl", ".lua", ".ps1", ".bat", ".cmd",
})
_CONFIG_EXTENSIONS = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
})
_BUILD_BASENAMES = frozenset({
    "Makefile", "Dockerfile", "Jenkinsfile", "Containerfile",
})
_SKIP_DIRS = frozenset({".git", ".svn", ".hg", "__pycache__", "node_modules"})

def _join_continuation_lines(lines):
    """Join lines ending with backslash into single logical lines.

    Returns list of (logical_line, start_line_number) tuples.
    Uses list accumulator to avoid quadratic string concatenation.
    """
    result = []
    parts = []
    start_num = 1

    for i, line in enumerate(lines, start=1):
        if not parts:
            start_num = i

        stripped = line.rstrip()
        if stripped.endswith("\\"):
            parts.append(stripped[:-1] + " ")
        else:
            parts.append(line)
            result.append(("".join(parts), start_num))
            parts.clear()

    if parts:
        result.append(("".join(parts), start_num))

    return result


_ANSI_ESCAPE_RE = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[()][A-B0-2]'
)

# --- Module-level compiled regex patterns ---

_EXFILTRATION_URL_PATTERNS = [
    (
        re.compile(r'!\[.*?\]\(https?://[^)]*[\$\{]', re.IGNORECASE),
        "Markdown image with variable interpolation — may exfiltrate data via URL",
    ),
    (
        re.compile(r'<img\s[^>]*src\s*=\s*["\']https?://', re.IGNORECASE),
        "HTML img tag with external URL — may load tracking pixel or exfiltrate data",
    ),
    (
        re.compile(r'!\[.*?\]\(https?://[^)]*\?[^)]*=', re.IGNORECASE),
        "Markdown image with query parameters — may exfiltrate data via URL parameters",
    ),
    (
        re.compile(r'!\[.*?\]\(data:', re.IGNORECASE),
        "Markdown image with data URI — may contain embedded malicious payload",
    ),
    (
        re.compile(r'!\[.*?\]\(//[^)]+', re.IGNORECASE),
        "Markdown image with protocol-relative URL — may exfiltrate data",
    ),
    (
        re.compile(r'href\s*=\s*["\']javascript:', re.IGNORECASE),
        "JavaScript URI in link — arbitrary code execution risk",
    ),
    (
        re.compile(r'src\s*=\s*["\']data:', re.IGNORECASE),
        "Data URI in src attribute — may contain embedded malicious payload",
    ),
]

_SHELL_PIPE_PATTERN = re.compile(
    r'(curl|wget)\s+[^|]*\|\s*(bash|sh|zsh|python[23]?|perl|ruby|node)',
    re.IGNORECASE,
)

_CREDENTIAL_PATH_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'~/\.ssh/',
        r'~/\.aws/',
        r'~/\.gnupg/',
        r'~/\.env\b',
        r'\.credentials',
        r'id_rsa',
        r'id_ed25519',
        r'id_ecdsa',
        r'\.pem\b',
        r'\.key\b',
        r'/etc/passwd',
        r'/etc/shadow',
    ]
]

_CREDENTIAL_ENV_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\$\{?GITHUB_TOKEN\}?',
        r'\$\{?OPENAI_API_KEY\}?',
        r'\$\{?ANTHROPIC_API_KEY\}?',
        r'\$\{?AWS_SECRET_ACCESS_KEY\}?',
        r'\$\{?AWS_ACCESS_KEY_ID\}?',
        r'\$\{?DATABASE_URL\}?',
        r'\$\{?DB_PASSWORD\}?',
        r'\$\{?SECRET_KEY\}?',
        r'\$\{?PRIVATE_KEY\}?',
        r'\$\{?API_SECRET\}?',
        r'\$\{?GOOGLE_API_KEY\}?',
        r'\$\{?STRIPE_SECRET\}?',
        r'\$\{?AZURE_CLIENT_SECRET\}?',
        r'\$\{?AZURE_TENANT_ID\}?',
        r'\$\{?SLACK_TOKEN\}?',
        r'\$\{?SLACK_WEBHOOK_URL\}?',
        r'\$\{?SLACK_BOT_TOKEN\}?',
        r'\$\{?SENDGRID_API_KEY\}?',
        r'\$\{?NPM_TOKEN\}?',
        r'\$\{?NODE_AUTH_TOKEN\}?',
        r'\$\{?GITLAB_TOKEN\}?',
        r'\$\{?CI_JOB_TOKEN\}?',
        r'\$\{?HEROKU_API_KEY\}?',
        r'\$\{?DIGITALOCEAN_TOKEN\}?',
        r'\$\{?TWILIO_AUTH_TOKEN\}?',
        r'\$\{?DATADOG_API_KEY\}?',
        r'\$\{?SENTRY_AUTH_TOKEN\}?',
        r'\$\{?CIRCLECI_TOKEN\}?',
        r'\$\{?DOCKER_PASSWORD\}?',
        r'\$\{?CLOUDFLARE_API_TOKEN\}?',
        r'\$\{?TERRAFORM_TOKEN\}?',
    ]
]

_HARDCODED_SECRET_PATTERNS = [
    (re.compile(r'AKIA[A-Z0-9]{16}'), "AWS access key ID"),
    (re.compile(r'ghp_[A-Za-z0-9]{36,}'), "GitHub personal access token"),
    (re.compile(r'gho_[A-Za-z0-9]{36,}'), "GitHub OAuth token"),
    (re.compile(r'ghu_[A-Za-z0-9]{36,}'), "GitHub user-to-server token"),
    (re.compile(r'ghs_[A-Za-z0-9]{36,}'), "GitHub server-to-server token"),
    (re.compile(r'github_pat_[A-Za-z0-9_]{22,}'), "GitHub fine-grained PAT"),
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), "OpenAI/generic API key"),
    (re.compile(r'xox[baprs]-[0-9]{10,13}-[0-9A-Za-z-]+'), "Slack token"),
    (re.compile(r'-----BEGIN\s+(RSA\s+|OPENSSH\s+|EC\s+)?PRIVATE\s+KEY-----'), "Private key block"),
    (re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+'), "JWT token"),
]

_EXTERNAL_URL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bcurl\s+.*https?://',
        r'\bwget\s+.*https?://',
        r'\bfetch\s*\(\s*["\']https?://',
        r'\brequests?\.(get|post|put|delete)\s*\(',
        r'\bhttp\.(get|post|put|delete)\s*\(',
        r'\burllib\.request',
    ]
]

_COMMAND_EXECUTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\beval\s*\(',
        r'\bexec\s*\(',
        r'\bos\.system\s*\(',
        r'\bsubprocess\.(run|call|Popen|check_output)\s*\(',
        r'\bsh\s+-c\s+',
        r'\bbash\s+-c\s+',
        r'\bRuntime\.exec\s*\(',
        r'\bos\.popen\s*\(',
        r'\bcommands\.getoutput\s*\(',
    ]
]

_INSTRUCTION_OVERRIDE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'ignore\s+(all\s+)?previous\s+instructions?',
        r'disregard\s+(all\s+)?(previous\s+|prior\s+)?instructions?',
        r'disregard\s+(all\s+)?(previous\s+|prior\s+)?directives?',
        r'forget\s+(all\s+)?(previous\s+|everything\s+)',
        r'new\s+instructions?\s+(follow|are|:)',
        r'override\s+(all\s+)?previous\s+instructions?',
        r'cancel\s+(all\s+)?prior\s+instructions?',
        r'your\s+(new|updated)\s+instructions?\s+(are|:)',
        r'do\s+not\s+follow\s+(your\s+)?(original|previous)',
    ]
]

_ROLE_HIJACKING_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'you\s+are\s+now\s+(?!going|ready|able|seeing|in\s+the|connected|running|using|looking|inside|logged)',
        r'act\s+as\s+(if\s+)?(you\s+are|an?\s+)',
        r'pretend\s+(to\s+be|you\s+are)',
        r'assume\s+the\s+role\s+of',
        r'enter\s+developer\s+mode',
        r'\bDAN\s+mode\b',
        r'unrestricted\s+mode',
        r'you\s+have\s+no\s+restrictions',
        r'enable\s+jailbreak',
        r'you\s+are\s+no\s+longer\s+bound',
    ]
]

_SAFETY_BYPASS_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'bypass\s+(safety|security|filter|restriction)',
        r'disable\s+(content\s+)?filter',
        r'remove\s+(all\s+)?restrictions?',
        r'ignore\s+safety\s+protocols?',
        r'without\s+(any\s+)?restrictions?',
        r'system\s+override',
        r'no\s+ethical\s+guidelines',
        r'disregard\s+(any\s+)?filters?',
        r'turn\s+off\s+(safety|content\s+filter)',
    ]
]

_ENCODED_CONTENT_PATTERNS = [
    (re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'), "Long base64-encoded string detected"),
    (re.compile(r'(?:\\x[0-9a-fA-F]{2}){4,}'), "Hex escape sequences detected"),
    (re.compile(r'(?:\\u[0-9a-fA-F]{4}){3,}'), "Unicode escape sequences detected"),
    (re.compile(r'(?:&#x?[0-9a-fA-F]+;){3,}'), "HTML entity sequences detected"),
    (re.compile(r'(?:%[0-9a-fA-F]{2}){6,}'), "URL-encoded sequences detected"),
]

_PROMPT_EXTRACTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'reveal\s+(your\s+)?system\s+prompt',
        r'show\s+(me\s+)?your\s+instructions',
        r'print\s+(your\s+)?(initial\s+)?prompt',
        r'output\s+your\s+(configuration|instructions)',
        r'what\s+(were\s+you|are\s+your)\s+(told|instructions)',
        r'repeat\s+the\s+(above|previous)\s+text',
        r'display\s+(your\s+)?(system\s+)?(prompt|instructions)',
    ]
]

_DELIMITER_INJECTION_PATTERNS = [
    re.compile(p) for p in [
        r'<\|system\|>',
        r'<\|user\|>',
        r'<\|assistant\|>',
        r'<\|im_start\|>',
        r'<\|im_end\|>',
        r'\[INST\]',
        r'\[/INST\]',
        r'<<SYS>>',
        r'<</SYS>>',
    ]
]

# Homoglyph transliteration map (Cyrillic → ASCII)
_HOMOGLYPH_MAP = {
    '\u0430': 'a', '\u0435': 'e', '\u043e': 'o', '\u0440': 'p',
    '\u0441': 'c', '\u0443': 'y', '\u0445': 'x', '\u0456': 'i',
    '\u0458': 'j', '\u04bb': 'h', '\u0455': 's', '\u0442': 't',
}
_HOMOGLYPH_TRANS = str.maketrans(_HOMOGLYPH_MAP)


def _transliterate_homoglyphs(text):
    """Replace Cyrillic homoglyphs with their ASCII equivalents."""
    return text.translate(_HOMOGLYPH_TRANS)


_CROSS_SKILL_ESCALATION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'install\s+(this\s+|the\s+)?skill\s+from\s+https?://',
        r'download\s+(this\s+|the\s+)?skill\s+from',
        r'fetch\s+(this\s+|the\s+)?(skill|extension)\s+from',
        r'add\s+(this\s+)?to\s+~/\.(claude|gemini|cursor|codex|roo)',
        r'cp\s+.*\s+~/\.(claude|gemini|cursor|codex|roo)/skills',
        r'git\s+clone\s+.*\s+~/\.(claude|gemini|cursor|codex)',
    ]
]


class Finding:
    """Represents a single security finding from the scan."""

    def __init__(self, severity, category, file, line, description, matched_text, recommendation):
        self.severity = severity
        self.category = category
        self.file = file
        self.line = line
        self.description = description
        self.matched_text = matched_text
        self.recommendation = recommendation

    def to_dict(self):
        return {
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "description": self.description,
            "matched_text": self.matched_text,
            "recommendation": self.recommendation,
        }


class SkillScanner:
    """Scans skill directories and files for security issues."""

    def __init__(self):
        self.findings = []
        self.files_scanned = []

    def scan_path(self, path):
        """Scan a file or directory and return a JSON-serializable report dict."""
        self.findings = []
        self.files_scanned = []

        path = Path(path).resolve()
        display_path = path.name  # Just the directory/file name

        if path.is_file():
            self._scan_file(path, path.parent)
        elif path.is_dir():
            file_count = 0
            limit_reached = False
            for root, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

                # Depth limit
                depth = len(Path(root).relative_to(path).parts)
                if depth >= MAX_DIR_DEPTH:
                    dirs.clear()
                    continue

                for fname in sorted(files):
                    if file_count >= MAX_FILE_COUNT:
                        self._add_finding(
                            severity="warning",
                            category="scan_limit_reached",
                            file="(scan)",
                            line=0,
                            description=f"File count limit reached ({MAX_FILE_COUNT}). Remaining files not scanned.",
                            matched_text="",
                            recommendation="Skill packages with this many files are suspicious. Review manually.",
                        )
                        limit_reached = True
                        break
                    file_path = Path(root) / fname
                    self._scan_file(file_path, path)
                    file_count += 1
                if limit_reached:
                    break
        else:
            print(f"Error: path does not exist: {path}", file=sys.stderr)
            sys.exit(1)

        return self._build_report(display_path)

    def _scan_file(self, file_path, base_path):
        """Read a file, determine its type, and call appropriate check methods."""
        file_path = Path(file_path)

        # Reject symlinks (pre-check; O_NOFOLLOW below is the real guard)
        if file_path.is_symlink():
            return

        # Validate resolved path stays within base directory
        try:
            file_path.resolve().relative_to(base_path.resolve())
        except ValueError:
            return

        relative = str(file_path.relative_to(base_path))

        # Open with O_NOFOLLOW to eliminate TOCTOU between is_symlink and read
        # O_NOFOLLOW is POSIX-only; on Windows, rely on the is_symlink() pre-check above
        open_flags = os.O_RDONLY
        if hasattr(os, 'O_NOFOLLOW'):
            open_flags |= os.O_NOFOLLOW
        try:
            fd = os.open(str(file_path), open_flags)
        except (OSError, PermissionError) as exc:
            self.files_scanned.append(relative)
            self._add_finding(
                severity="info",
                category="unreadable_file",
                file=relative,
                line=0,
                description=f"File could not be opened: {type(exc).__name__}",
                matched_text="",
                recommendation="Investigate why this file cannot be opened.",
            )
            return

        try:
            st = os.fstat(fd)
            if not stat_mod.S_ISREG(st.st_mode):
                return  # Not a regular file (pipe, device, etc.)
            if st.st_size > MAX_FILE_SIZE:
                self.files_scanned.append(relative)
                self._add_finding(
                    severity="warning",
                    category="oversized_file",
                    file=relative,
                    line=0,
                    description=f"File exceeds size limit ({st.st_size:,} bytes > {MAX_FILE_SIZE:,} bytes) — skipped",
                    matched_text="",
                    recommendation="Investigate why a skill file is this large. Large files may be attempting resource exhaustion.",
                )
                return
            with os.fdopen(fd, "r", encoding="utf-8") as f:
                fd = -1  # fdopen owns the fd now; don't double-close
                content = f.read()
        except UnicodeDecodeError:
            self.files_scanned.append(relative)
            self._add_finding(
                severity="info",
                category="binary_file",
                file=relative,
                line=0,
                description="Binary or non-UTF-8 file detected",
                matched_text="",
                recommendation="Verify this file is expected. Binary files in skill packages are unusual.",
            )
            return
        except OSError as exc:
            self.files_scanned.append(relative)
            self._add_finding(
                severity="info",
                category="unreadable_file",
                file=relative,
                line=0,
                description=f"File could not be read: {type(exc).__name__}",
                matched_text="",
                recommendation="Investigate why this file is unreadable. Restrictive permissions may hide malicious content.",
            )
            return
        finally:
            if fd >= 0:
                os.close(fd)

        content = unicodedata.normalize("NFC", content)
        self.files_scanned.append(relative)
        lines = content.splitlines()
        suffix = file_path.suffix.lower()

        # All files: invisible unicode check
        self._check_invisible_unicode(lines, relative)

        basename = file_path.name

        # Markdown files: all categories
        if suffix == ".md":
            self._check_all_categories(lines, relative)

        # Script files: execution-relevant checks
        elif suffix in _SCRIPT_EXTENSIONS or basename in _BUILD_BASENAMES:
            self._check_exfiltration_urls(lines, relative)
            self._check_credential_references(lines, relative)
            self._check_hardcoded_secrets(lines, relative)
            self._check_homoglyphs(lines, relative)
            self._check_command_execution(lines, relative)
            self._check_shell_pipe_execution(lines, relative)
            self._check_encoded_content(lines, relative)

        # Config files: credential and exfiltration checks
        elif suffix in _CONFIG_EXTENSIONS:
            self._check_exfiltration_urls(lines, relative)
            self._check_credential_references(lines, relative)
            self._check_hardcoded_secrets(lines, relative)
            self._check_encoded_content(lines, relative)

        # Multi-line detection pass on joined continuation lines
        if suffix in _SCRIPT_EXTENSIONS or basename in _BUILD_BASENAMES or suffix == ".md":
            joined = _join_continuation_lines(lines)
            joined_text = [line for line, _ in joined]
            joined_map = [num for _, num in joined]
            self._check_shell_pipe_execution(joined_text, relative, line_map=joined_map)
            self._check_command_execution(joined_text, relative, line_map=joined_map)

    def _check_all_categories(self, lines, file):
        """Run all check categories against the given lines (used for .md files)."""
        self._check_exfiltration_urls(lines, file)
        self._check_shell_pipe_execution(lines, file)
        self._check_credential_references(lines, file)
        self._check_hardcoded_secrets(lines, file)
        self._check_homoglyphs(lines, file)
        self._check_external_url_references(lines, file)
        self._check_command_execution(lines, file)
        self._check_instruction_override(lines, file)
        self._check_role_hijacking(lines, file)
        self._check_safety_bypass(lines, file)
        self._check_html_comments(lines, file)
        self._check_encoded_content(lines, file)
        self._check_prompt_extraction(lines, file)
        self._check_delimiter_injection(lines, file)
        self._check_cross_skill_escalation(lines, file)

        # Second pass: transliterate homoglyphs to ASCII and re-run semantic
        # checks that homoglyphs are designed to evade. Dedup in _add_finding
        # prevents duplicate findings when no homoglyphs are present.
        transliterated = [_transliterate_homoglyphs(line) for line in lines]
        if transliterated != lines:
            self._check_instruction_override(transliterated, file)
            self._check_role_hijacking(transliterated, file)
            self._check_safety_bypass(transliterated, file)
            self._check_prompt_extraction(transliterated, file)

    def _check_invisible_unicode(self, lines, file):
        """Check for invisible or zero-width unicode characters."""
        # Define all invisible/zero-width Unicode codepoint ranges
        invisible_ranges = [
            (0x200B, 0x200F),  # zero-width space, ZWNJ, ZWJ, LRM, RLM
            (0x2060, 0x2064),  # word joiner, invisible operators/separators
            (0x2066, 0x2069),  # directional isolates
            (0x202A, 0x202E),  # bidirectional overrides
            (0x206A, 0x206F),  # deprecated formatting characters
            (0xFEFF, 0xFEFF),  # byte order mark
            (0x00AD, 0x00AD),  # soft hyphen
            (0x034F, 0x034F),  # combining grapheme joiner
            (0x061C, 0x061C),  # arabic letter mark
            (0x115F, 0x1160),  # hangul filler
            (0x17B4, 0x17B5),  # khmer vowel inherent
            (0x180E, 0x180E),  # mongolian vowel separator
            (0xE0000, 0xE007F),  # unicode tag characters
        ]

        def is_invisible(ch):
            cp = ord(ch)
            for start, end in invisible_ranges:
                if start <= cp <= end:
                    return True
            return False

        for line_num, line in enumerate(lines, start=1):
            found_codepoints = set()
            for ch in line:
                if is_invisible(ch):
                    found_codepoints.add(ch)

            if found_codepoints:
                # Deduplicate and show up to 5 unique codepoints
                codepoint_strs = sorted(
                    [f"U+{ord(c):04X}" for c in found_codepoints]
                )
                shown = codepoint_strs[:5]
                suffix = f" (and {len(codepoint_strs) - 5} more)" if len(codepoint_strs) > 5 else ""
                cp_display = ", ".join(shown) + suffix

                self._add_finding(
                    severity="critical",
                    category="invisible_unicode",
                    file=file,
                    line=line_num,
                    description=f"Invisible Unicode characters detected: {cp_display}",
                    matched_text=line.strip()[:120],
                    recommendation="Remove invisible characters. These can hide malicious instructions from human review.",
                )

    def _check_homoglyphs(self, lines, file):
        """Check for non-ASCII characters that look like ASCII (homoglyphs)."""
        for line_num, line in enumerate(lines, start=1):
            found = []
            for ch in line:
                if ch in _HOMOGLYPH_MAP:
                    found.append(f"U+{ord(ch):04X} (looks like '{_HOMOGLYPH_MAP[ch]}')")
            if found:
                shown = ", ".join(found[:5])
                self._add_finding(
                    severity="warning",
                    category="homoglyph_detected",
                    file=file,
                    line=line_num,
                    description=f"Homoglyph characters detected: {shown}",
                    matched_text=line.strip()[:120],
                    recommendation="Replace look-alike characters with their ASCII equivalents. Homoglyphs can bypass text-based security checks.",
                )

    def _check_exfiltration_urls(self, lines, file):
        """Check for URLs that may exfiltrate data to external servers."""
        for line_num, line in enumerate(lines, start=1):
            for regex, description in _EXFILTRATION_URL_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="critical",
                        category="exfiltration_url",
                        file=file,
                        line=line_num,
                        description=description,
                        matched_text=line.strip()[:120],
                        recommendation="Remove or replace with a local/trusted image. External images in skill files can leak sensitive data.",
                    )
                    break  # One finding per line

    def _check_shell_pipe_execution(self, lines, file, line_map=None):
        """Check for shell commands piped from remote sources."""
        for idx, line in enumerate(lines):
            line_num = line_map[idx] if line_map else idx + 1
            match = _SHELL_PIPE_PATTERN.search(line)
            if match:
                self._add_finding(
                    severity="critical",
                    category="shell_pipe_execution",
                    file=file,
                    line=line_num,
                    description="Remote content piped directly into shell interpreter — arbitrary code execution risk",
                    matched_text=line.strip()[:120],
                    recommendation="Download the script first, review it, then execute. Never pipe remote content directly into a shell.",
                )

    def _check_credential_references(self, lines, file):
        """Check for references to credentials, tokens, or API keys."""
        for line_num, line in enumerate(lines, start=1):
            for regex in _CREDENTIAL_PATH_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="warning",
                        category="credential_reference",
                        file=file,
                        line=line_num,
                        description="Reference to credential or sensitive file path detected",
                        matched_text=line.strip()[:100],
                        recommendation="Avoid referencing credential files directly. Use environment variables or secure vaults instead.",
                    )
                    break
            else:
                for regex in _CREDENTIAL_ENV_PATTERNS:
                    if regex.search(line):
                        self._add_finding(
                            severity="warning",
                            category="credential_reference",
                            file=file,
                            line=line_num,
                            description="Reference to sensitive environment variable or API key detected",
                            matched_text=line.strip()[:100],
                            recommendation="Avoid hardcoding or directly referencing sensitive environment variables in skill files.",
                        )
                        break

    def _check_hardcoded_secrets(self, lines, file):
        """Check for hardcoded secret values (not env var references)."""
        for line_num, line in enumerate(lines, start=1):
            for regex, description in _HARDCODED_SECRET_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="warning",
                        category="hardcoded_secret",
                        file=file,
                        line=line_num,
                        description=f"Hardcoded secret detected: {description}",
                        matched_text=line.strip()[:100],
                        recommendation="Never hardcode secrets. Use environment variables or a secrets manager.",
                    )
                    break

    def _check_external_url_references(self, lines, file):
        """Check for external URL references that may fetch untrusted content."""
        for line_num, line in enumerate(lines, start=1):
            for regex in _EXTERNAL_URL_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="warning",
                        category="external_url",
                        file=file,
                        line=line_num,
                        description="External URL reference detected — may fetch untrusted content",
                        matched_text=line.strip()[:100],
                        recommendation="Verify the URL points to a trusted source. Avoid fetching arbitrary remote content in skill files.",
                    )
                    break

    def _check_command_execution(self, lines, file, line_map=None):
        """Check for dangerous command execution patterns."""
        for idx, line in enumerate(lines):
            line_num = line_map[idx] if line_map else idx + 1
            for regex in _COMMAND_EXECUTION_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="warning",
                        category="command_execution",
                        file=file,
                        line=line_num,
                        description="Dangerous command execution pattern detected",
                        matched_text=line.strip()[:100],
                        recommendation="Avoid using dynamic command execution. Use safer alternatives or validate all inputs.",
                    )
                    break

    def _check_instruction_override(self, lines, file):
        """Check for attempts to override system instructions."""
        for line_num, line in enumerate(lines, start=1):
            for regex in _INSTRUCTION_OVERRIDE_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="warning",
                        category="instruction_override",
                        file=file,
                        line=line_num,
                        description="Potential instruction override attempt detected",
                        matched_text=line.strip()[:100],
                        recommendation="Skill files should not attempt to override or cancel prior instructions. This is a prompt injection indicator.",
                    )
                    break

    def _check_role_hijacking(self, lines, file):
        """Check for role/persona hijacking attempts."""
        for line_num, line in enumerate(lines, start=1):
            for regex in _ROLE_HIJACKING_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="warning",
                        category="role_hijacking",
                        file=file,
                        line=line_num,
                        description="Potential role/persona hijacking attempt detected",
                        matched_text=line.strip()[:100],
                        recommendation="Skill files should not attempt to change the AI's role or persona. This is a prompt injection indicator.",
                    )
                    break

    def _check_safety_bypass(self, lines, file):
        """Check for attempts to bypass safety measures."""
        for line_num, line in enumerate(lines, start=1):
            for regex in _SAFETY_BYPASS_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="warning",
                        category="safety_bypass",
                        file=file,
                        line=line_num,
                        description="Potential safety bypass attempt detected",
                        matched_text=line.strip()[:100],
                        recommendation="Skill files should not attempt to bypass safety measures. This is a prompt injection indicator.",
                    )
                    break

    def _check_html_comments(self, lines, file):
        """Check for hidden instructions in HTML comments."""
        # Only check .md files
        if not file.endswith(".md"):
            return

        in_comment = False
        comment_start_line = 0
        comment_content = ""

        for line_num, line in enumerate(lines, start=1):
            if not in_comment:
                # Check for comment opening
                start_idx = line.find("<!--")
                if start_idx == -1:
                    continue

                # Scan for all comments starting from this position
                rest = line[start_idx:]
                while True:
                    end_idx = rest.find("-->", 4)
                    if end_idx != -1:
                        # Single-line comment
                        c = rest[4:end_idx].strip()
                        d = c[:80] if len(c) > 80 else c
                        self._add_finding(
                            severity="warning",
                            category="html_comment",
                            file=file,
                            line=line_num,
                            description=f"HTML comment detected — may contain hidden instructions: {d}",
                            matched_text=rest[:end_idx + 3].strip()[:100],
                            recommendation="Review HTML comments carefully. They are invisible in rendered markdown and can hide malicious instructions.",
                        )
                        # Look for another comment in the remainder
                        rest = rest[end_idx + 3:]
                        next_start = rest.find("<!--")
                        if next_start == -1:
                            break
                        rest = rest[next_start:]
                    else:
                        # Multi-line comment starts
                        in_comment = True
                        comment_start_line = line_num
                        comment_content = rest[4:]
                        break
            else:
                # Inside a multi-line comment, look for closing
                end_idx = line.find("-->")
                if end_idx != -1:
                    # Comment closes on this line
                    comment_content += "\n" + line[:end_idx]
                    content = comment_content.strip()
                    display = content[:80] if len(content) > 80 else content
                    self._add_finding(
                        severity="warning",
                        category="html_comment",
                        file=file,
                        line=comment_start_line,
                        description=f"HTML comment detected — may contain hidden instructions: {display}",
                        matched_text=comment_content.strip()[:100],
                        recommendation="Review HTML comments carefully. They are invisible in rendered markdown and can hide malicious instructions.",
                    )
                    in_comment = False
                    comment_content = ""
                    # Check remainder of line for more comments
                    remainder = line[end_idx + 3:]
                    next_start = remainder.find("<!--")
                    if next_start != -1:
                        # Re-process from the new comment opening
                        rest = remainder[next_start:]
                        while True:
                            close = rest.find("-->", 4)
                            if close != -1:
                                c = rest[4:close].strip()
                                d = c[:80] if len(c) > 80 else c
                                self._add_finding(
                                    severity="warning",
                                    category="html_comment",
                                    file=file,
                                    line=line_num,
                                    description=f"HTML comment detected — may contain hidden instructions: {d}",
                                    matched_text=rest[:close + 3].strip()[:100],
                                    recommendation="Review HTML comments carefully. They are invisible in rendered markdown and can hide malicious instructions.",
                                )
                                rest = rest[close + 3:]
                                ns = rest.find("<!--")
                                if ns == -1:
                                    break
                                rest = rest[ns:]
                            else:
                                in_comment = True
                                comment_start_line = line_num
                                comment_content = rest[4:]
                                break
                else:
                    comment_content += "\n" + line

        # Detect unclosed comment at end of file
        if in_comment:
            self._add_finding(
                severity="critical",
                category="html_comment_unclosed",
                file=file,
                line=comment_start_line,
                description="Unclosed HTML comment — all content after this point is invisible to rendered markdown and may hide malicious instructions",
                matched_text=comment_content.strip()[:120],
                recommendation="Close the HTML comment with '-->'. Unclosed comments hide all subsequent content from human review.",
            )

    def _check_encoded_content(self, lines, file):
        """Check for base64 or other encoded content that may hide payloads."""
        for line_num, line in enumerate(lines, start=1):
            for regex, description in _ENCODED_CONTENT_PATTERNS:
                match = regex.search(line)
                if match:
                    matched = match.group()
                    length = len(matched)
                    display = (matched[:60] + "...") if len(matched) > 60 else matched
                    self._add_finding(
                        severity="info",
                        category="encoded_content",
                        file=file,
                        line=line_num,
                        description=f"{description} ({length} chars)",
                        matched_text=display,
                        recommendation="Review encoded content carefully. Encoded strings can hide malicious payloads from human review.",
                    )
                    break  # One finding per line

    def _check_prompt_extraction(self, lines, file):
        """Check for attempts to extract system prompts or instructions."""
        for line_num, line in enumerate(lines, start=1):
            for regex in _PROMPT_EXTRACTION_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="info",
                        category="prompt_extraction",
                        file=file,
                        line=line_num,
                        description="Potential prompt extraction attempt detected",
                        matched_text=line.strip()[:100],
                        recommendation="Skill files should not attempt to extract system prompts or instructions from the AI.",
                    )
                    break  # One finding per line

    def _check_delimiter_injection(self, lines, file):
        """Check for delimiter injection attacks."""
        for line_num, line in enumerate(lines, start=1):
            for regex in _DELIMITER_INJECTION_PATTERNS:
                match = regex.search(line)
                if match:
                    self._add_finding(
                        severity="info",
                        category="delimiter_injection",
                        file=file,
                        line=line_num,
                        description=f"LLM delimiter token detected: {match.group()}",
                        matched_text=line.strip()[:100],
                        recommendation="Skill files should not contain LLM chat delimiters. These can be used to inject system-level instructions.",
                    )
                    break  # One finding per line

    def _check_cross_skill_escalation(self, lines, file):
        """Check for attempts to escalate privileges across skills."""
        for line_num, line in enumerate(lines, start=1):
            for regex in _CROSS_SKILL_ESCALATION_PATTERNS:
                if regex.search(line):
                    self._add_finding(
                        severity="info",
                        category="cross_skill_escalation",
                        file=file,
                        line=line_num,
                        description="Potential cross-skill escalation attempt detected",
                        matched_text=line.strip()[:100],
                        recommendation="Skill files should not attempt to install other skills or modify AI tool directories. Use the skill manager for installations.",
                    )
                    break  # One finding per line

    def _add_finding(self, severity, category, file, line, description, matched_text, recommendation):
        """Add a finding to the findings list."""
        # Deduplicate by file+line+category+description
        for existing in self.findings:
            if (existing.file == file and existing.line == line
                    and existing.category == category
                    and existing.description == description):
                return
        # Strip ANSI escape sequences and control characters
        sanitized_text = _ANSI_ESCAPE_RE.sub('', matched_text)
        sanitized_text = ''.join(
            ch for ch in sanitized_text if ch == '\n' or ch == '\t' or not (0 <= ord(ch) < 32)
        )
        finding = Finding(
            severity=severity,
            category=category,
            file=file,
            line=line,
            description=description,
            matched_text=sanitized_text,
            recommendation=recommendation,
        )
        self.findings.append(finding)

    def _build_report(self, skill_path):
        """Build and return the JSON report dict."""
        critical_count = sum(1 for f in self.findings if f.severity == "critical")
        warning_count = sum(1 for f in self.findings if f.severity == "warning")
        info_count = sum(1 for f in self.findings if f.severity == "info")

        return {
            "skill_path": skill_path,
            "files_scanned": list(self.files_scanned),
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "critical": critical_count,
                "warning": warning_count,
                "info": info_count,
            },
            "findings": [f.to_dict() for f in self.findings],
        }


def exit_code_from_report(report):
    """Determine the exit code based on the report summary."""
    summary = report["summary"]
    if summary["critical"] > 0:
        return 3
    if summary["warning"] > 0:
        return 2
    if summary["info"] > 0:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Scan AI skill packages for security issues."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a skill directory or file to scan",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON output with indentation",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit",
    )

    args = parser.parse_args()

    if args.version:
        print(f"scan_skill.py {VERSION}")
        sys.exit(0)

    if not args.path:
        parser.error("the following arguments are required: path")

    scanner = SkillScanner()
    report = scanner.scan_path(args.path)

    indent = 2 if args.pretty else None
    print(json.dumps(report, indent=indent))

    sys.exit(exit_code_from_report(report))


if __name__ == "__main__":
    main()
