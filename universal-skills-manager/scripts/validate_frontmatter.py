#!/usr/bin/env python3
"""
SKILL.md Frontmatter Validator for claude.ai / Claude Desktop / ChatGPT

Validates and optionally fixes SKILL.md YAML frontmatter to comply with the
Agent Skills specification (https://agentskills.io/specification).

Cloud platform upload validators are strict — they reject skills with
unsupported top-level keys, nested metadata objects, or constraint violations.

Usage:
    # Validate only (report issues)
    python3 validate_frontmatter.py /path/to/SKILL.md

    # Validate and fix (writes corrected file)
    python3 validate_frontmatter.py /path/to/SKILL.md --fix

    # Fix and output to a different file
    python3 validate_frontmatter.py /path/to/SKILL.md --fix --output /path/to/fixed/SKILL.md

    # Validate a ZIP file
    python3 validate_frontmatter.py /path/to/skill.zip

    # Validate and fix a ZIP file (rewrites the ZIP)
    python3 validate_frontmatter.py /path/to/skill.zip --fix

Exit codes:
    0 - Valid (or fixed successfully with --fix)
    1 - Invalid (issues found, no --fix)
    2 - Error (file not found, parse error, etc.)
"""

import io
import re
import sys
import os
import json
import tempfile
import shutil
import zipfile
from pathlib import Path

if sys.platform == "win32" and not os.environ.get("PYTHONIOENCODING"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

VERSION = "1.0.0"

# =============================================================================
# Agent Skills Specification Constants
# =============================================================================

ALLOWED_TOP_LEVEL_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_MAX_LENGTH = 64
DESCRIPTION_MAX_LENGTH = 1024
COMPATIBILITY_MAX_LENGTH = 500
NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
CONSECUTIVE_HYPHENS = re.compile(r"--")


# =============================================================================
# Minimal YAML Frontmatter Parser (zero dependencies)
# =============================================================================

def parse_frontmatter(content: str) -> tuple:
    """Parse YAML frontmatter from SKILL.md content.

    Returns (frontmatter_dict, body_content, raw_frontmatter_str) or raises ValueError.
    Uses a minimal parser to avoid PyYAML dependency.
    """
    content = content.lstrip("\ufeff")  # strip BOM if present

    if not content.startswith("---"):
        raise ValueError("File does not start with YAML frontmatter delimiter (---)")

    # Find the closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        # Try end of file
        end_match = re.search(r"\n---\s*$", content[3:])
        if not end_match:
            raise ValueError("Could not find closing YAML frontmatter delimiter (---)")

    raw_fm = content[4:3 + end_match.start() + 1]  # between the --- markers
    body = content[3 + end_match.end():]

    data = _parse_yaml_minimal(raw_fm)

    # Detect block scalars in raw frontmatter (lost after parsing)
    # Track field name, scalar type (| or >), and whether it contains blank lines
    block_scalar_fields = {}
    for match in re.finditer(r"^([a-zA-Z0-9_-]+)\s*:\s*([|>])", raw_fm, re.MULTILINE):
        field_name = match.group(1)
        scalar_type = match.group(2)
        # Check for blank lines within the block scalar content
        start = match.end()
        has_blank_lines = False
        for line in raw_fm[start:].split("\n"):
            if line.strip() == "":
                has_blank_lines = True
            elif line and not line[0].isspace():
                break  # reached next top-level key
        block_scalar_fields[field_name] = {"type": scalar_type, "has_blank_lines": has_blank_lines}
    data["_block_scalar_fields"] = block_scalar_fields

    # Detect list-format allowed-tools (should be space-delimited string)
    at_match = re.search(r"^allowed-tools\s*:\s*\n((?:\s+-\s+.+\n?)+)", raw_fm, re.MULTILINE)
    if at_match:
        data["_allowed_tools_is_list"] = True
        # Extract the actual list items for fixing
        items = re.findall(r"^\s+-\s+(.+)", at_match.group(1), re.MULTILINE)
        data["_allowed_tools_items"] = [item.strip() for item in items]

    return data, body, raw_fm


def _parse_yaml_minimal(text: str) -> dict:
    """Minimal YAML parser for frontmatter key-value pairs.

    Handles: strings, booleans, numbers, simple lists, nested mappings.
    Does NOT handle: anchors, aliases, flow mappings, multi-document, tags.
    """
    result = {}
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        if indent > 0:
            i += 1
            continue  # skip nested lines for top-level parse

        # Parse key: value
        match = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)", stripped)
        if not match:
            i += 1
            continue

        key = match.group(1)
        value_str = match.group(2).strip()

        if value_str == "" or value_str == "|" or value_str == ">":
            # Could be a nested mapping or block scalar — collect indented lines
            nested_lines = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if not next_line.strip():
                    nested_lines.append("")
                    j += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent > indent:
                    nested_lines.append(next_line)
                    j += 1
                else:
                    break
            i = j

            if value_str in ("|", ">"):
                # Block scalar — join as string
                result[key] = "\n".join(l.strip() for l in nested_lines).strip()
            else:
                # Try to parse as nested mapping
                nested = _parse_nested_yaml(nested_lines, indent + 2)
                result[key] = nested
        else:
            result[key] = _parse_yaml_value(value_str)
            i += 1

    return result


def _parse_nested_yaml(lines: list, base_indent: int) -> dict:
    """Parse nested YAML lines into a dict (recursive)."""
    result = {}
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        # Check if this is a list item
        list_match = re.match(r"^(\s*)- (.+)", line)
        if list_match:
            # This is a list — find the parent key and collect items
            i += 1
            continue

        # Parse key: value
        match = re.match(r"^\s*([a-zA-Z0-9_-]+)\s*:\s*(.*)", stripped)
        if not match:
            i += 1
            continue

        key = match.group(1)
        value_str = match.group(2).strip()

        if value_str == "":
            # Nested mapping or list
            nested_lines = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if not next_line.strip():
                    nested_lines.append("")
                    j += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent > indent:
                    nested_lines.append(next_line)
                    j += 1
                else:
                    break
            i = j

            # Check if it's a list
            first_content = next((l for l in nested_lines if l.strip()), "")
            if first_content.strip().startswith("- "):
                items = []
                for nl in nested_lines:
                    lm = re.match(r"^\s*- (.+)", nl)
                    if lm:
                        items.append(_parse_yaml_value(lm.group(1).strip()))
                result[key] = items
            else:
                result[key] = _parse_nested_yaml(nested_lines, indent + 2)
        else:
            result[key] = _parse_yaml_value(value_str)
            i += 1

    return result


def _parse_yaml_value(s: str):
    """Parse a YAML scalar value."""
    # Remove quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]

    # Flow-style list
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1]
        items = [_parse_yaml_value(item.strip()) for item in inner.split(",") if item.strip()]
        return items

    # Booleans
    if s.lower() in ("true", "yes", "on"):
        return True
    if s.lower() in ("false", "no", "off"):
        return False

    # Null
    if s.lower() in ("null", "~", ""):
        return None

    # Numbers
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass

    return s


# =============================================================================
# Validation
# =============================================================================

def validate(data: dict) -> list:
    """Validate frontmatter dict against Agent Skills spec.

    Returns a list of issue dicts: {"level": "error"|"warning", "field": str, "message": str}
    """
    issues = []

    # Check required fields
    if "name" not in data:
        issues.append({"level": "error", "field": "name", "message": "Required field 'name' is missing"})
    if "description" not in data:
        issues.append({"level": "error", "field": "description", "message": "Required field 'description' is missing"})

    # Check for unsupported top-level keys
    for key in data:
        if key.startswith("_"):
            continue  # skip internal metadata keys
        if key not in ALLOWED_TOP_LEVEL_KEYS:
            issues.append({
                "level": "error",
                "field": key,
                "message": f"Unsupported top-level key '{key}'. Allowed: {', '.join(sorted(ALLOWED_TOP_LEVEL_KEYS))}"
            })

    # Validate name
    name = data.get("name", "")
    if name:
        if not isinstance(name, str):
            issues.append({"level": "error", "field": "name", "message": f"'name' must be a string, got {type(name).__name__}"})
        else:
            if len(name) > NAME_MAX_LENGTH:
                issues.append({"level": "error", "field": "name", "message": f"'name' exceeds {NAME_MAX_LENGTH} chars (got {len(name)})"})
            if not NAME_PATTERN.match(name):
                issues.append({"level": "error", "field": "name", "message": "'name' must be lowercase letters, numbers, and hyphens only"})
            if CONSECUTIVE_HYPHENS.search(name):
                issues.append({"level": "error", "field": "name", "message": "'name' must not contain consecutive hyphens (--)"})

    # Validate description
    desc = data.get("description", "")
    if desc:
        if not isinstance(desc, str):
            issues.append({"level": "error", "field": "description", "message": f"'description' must be a string, got {type(desc).__name__}"})
        else:
            if len(desc) > DESCRIPTION_MAX_LENGTH:
                issues.append({"level": "error", "field": "description", "message": f"'description' exceeds {DESCRIPTION_MAX_LENGTH} chars (got {len(desc)})"})
            if '<' in desc or '>' in desc:
                issues.append({"level": "error", "field": "description", "message": "Description cannot contain angle brackets (< or >)"})

    # Validate compatibility
    compat = data.get("compatibility")
    if compat is not None:
        if not isinstance(compat, str):
            issues.append({"level": "error", "field": "compatibility", "message": f"'compatibility' must be a string, got {type(compat).__name__}"})
        elif len(compat) > COMPATIBILITY_MAX_LENGTH:
            issues.append({"level": "error", "field": "compatibility", "message": f"'compatibility' exceeds {COMPATIBILITY_MAX_LENGTH} chars (got {len(compat)})"})

    # Validate metadata (must be flat string key-value pairs)
    meta = data.get("metadata")
    if meta is not None:
        if not isinstance(meta, dict):
            issues.append({"level": "error", "field": "metadata", "message": f"'metadata' must be a mapping, got {type(meta).__name__}"})
        else:
            for mk, mv in meta.items():
                if isinstance(mv, dict):
                    issues.append({
                        "level": "error",
                        "field": f"metadata.{mk}",
                        "message": f"Nested object in metadata.{mk} — cloud platforms only allow flat string values"
                    })
                elif isinstance(mv, list):
                    issues.append({
                        "level": "error",
                        "field": f"metadata.{mk}",
                        "message": f"Array in metadata.{mk} — cloud platforms only allow flat string values"
                    })
                elif not isinstance(mv, str):
                    issues.append({
                        "level": "warning",
                        "field": f"metadata.{mk}",
                        "message": f"metadata.{mk} is {type(mv).__name__}, should be a string (quote it)"
                    })

    # Validate allowed-tools (must be space-delimited string, not a YAML list)
    at = data.get("allowed-tools")
    if at is not None and not isinstance(at, str) and not data.get("_allowed_tools_is_list"):
        issues.append({"level": "error", "field": "allowed-tools", "message": f"'allowed-tools' must be a space-delimited string, not a YAML list. Use: allowed-tools: Read Write Edit"})

    # Check for block scalars in description
    # Literal scalars (|) with blank lines are known to fail on cloud platforms. We flag:
    #   - | with blank lines → error (known to fail)
    #   - | without blank lines → warning (untested, may fail)
    #   - > (any) → warning (works in testing, but inline strings are safest)
    block_fields = data.get("_block_scalar_fields", {})
    if "description" in block_fields:
        info = block_fields["description"]
        if info["type"] == "|" and info["has_blank_lines"]:
            issues.append({
                "level": "error",
                "field": "description",
                "message": "Description uses a literal block scalar (|) with blank lines — known to fail on cloud platforms. Use a simple inline string instead"
            })
        elif info["type"] == "|":
            issues.append({
                "level": "warning",
                "field": "description",
                "message": "Description uses a literal block scalar (|) — may cause issues on cloud platforms. Inline strings are safest"
            })
        else:
            issues.append({
                "level": "warning",
                "field": "description",
                "message": "Description uses a folded block scalar (>) — works in current testing, but inline strings are safest for maximum compatibility"
            })
    # Warn about block scalars in other fields too
    for field, info in block_fields.items():
        if field != "description" and field in ALLOWED_TOP_LEVEL_KEYS:
            issues.append({
                "level": "warning",
                "field": field,
                "message": f"'{field}' uses a YAML block scalar ({info['type']}) — may cause issues with strict parsers"
            })

    # Check for list-format allowed-tools
    if data.get("_allowed_tools_is_list"):
        issues.append({
            "level": "error",
            "field": "allowed-tools",
            "message": "'allowed-tools' must be a space-delimited string, not a YAML list. Use: allowed-tools: Read Write Edit"
        })

    return issues


# =============================================================================
# Fixer
# =============================================================================

def fix_frontmatter(data: dict) -> dict:
    """Fix frontmatter to comply with Agent Skills spec.

    Returns a new dict with fixes applied.
    """
    fixed = {}
    metadata = dict(data.get("metadata", {})) if isinstance(data.get("metadata"), dict) else {}

    for key, value in data.items():
        if key.startswith("_"):
            continue  # skip internal metadata keys
        if key in ALLOWED_TOP_LEVEL_KEYS:
            fixed[key] = value
        else:
            # Move unsupported top-level keys into metadata as strings
            metadata[key] = _to_string(value)

    # Fix metadata: flatten nested objects and arrays to strings
    fixed_meta = {}
    for mk, mv in metadata.items():
        if isinstance(mv, dict):
            # Flatten nested dict: each sub-key becomes a prefixed metadata key
            for sk, sv in _flatten_dict(mv, mk):
                fixed_meta[sk] = _to_string(sv)
        elif isinstance(mv, list):
            fixed_meta[mk] = ", ".join(_to_string(item) for item in mv)
        elif not isinstance(mv, str):
            fixed_meta[mk] = _to_string(mv)
        else:
            fixed_meta[mk] = mv

    if fixed_meta:
        fixed["metadata"] = fixed_meta

    # Fix block scalar descriptions: collapse to single-line inline string
    if "description" in fixed and isinstance(fixed["description"], str):
        desc = fixed["description"]
        # Collapse multi-line to single line (replace newlines with spaces, collapse whitespace)
        desc = re.sub(r"\s*\n\s*", " ", desc).strip()
        fixed["description"] = desc

    # Strip angle brackets from description (Anthropic's validator rejects them)
    if "description" in fixed and isinstance(fixed["description"], str):
        fixed["description"] = fixed["description"].replace("<", "").replace(">", "")

    # Truncate description if too long
    if "description" in fixed and isinstance(fixed["description"], str):
        if len(fixed["description"]) > DESCRIPTION_MAX_LENGTH:
            fixed["description"] = fixed["description"][:DESCRIPTION_MAX_LENGTH - 3] + "..."

    # Fix allowed-tools: must be a space-delimited string
    at = fixed.get("allowed-tools")
    # Check if we have extracted list items from raw parsing
    at_items = data.get("_allowed_tools_items", [])
    if at_items:
        fixed["allowed-tools"] = " ".join(at_items)
    elif at is not None and not isinstance(at, str):
        if isinstance(at, list):
            fixed["allowed-tools"] = " ".join(_to_string(item) for item in at)
        elif isinstance(at, dict):
            fixed["allowed-tools"] = " ".join(str(k) for k in at.keys()) if at else ""
        else:
            fixed["allowed-tools"] = _to_string(at)

    # Truncate compatibility if too long
    if "compatibility" in fixed and isinstance(fixed["compatibility"], str):
        if len(fixed["compatibility"]) > COMPATIBILITY_MAX_LENGTH:
            fixed["compatibility"] = fixed["compatibility"][:COMPATIBILITY_MAX_LENGTH - 3] + "..."

    return fixed


def _flatten_dict(d: dict, prefix: str) -> list:
    """Flatten a nested dict into a list of (key, value) pairs."""
    items = []
    for k, v in d.items():
        full_key = f"{prefix}-{k}"
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, full_key))
        else:
            items.append((full_key, v))
    return items


def _to_string(value) -> str:
    """Convert any value to a string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(_to_string(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


# =============================================================================
# YAML Serializer (minimal, for writing fixed frontmatter)
# =============================================================================

def serialize_frontmatter(data: dict) -> str:
    """Serialize a frontmatter dict back to YAML string."""
    lines = []

    # Write in a stable order: required first, then optional
    key_order = ["name", "description", "license", "compatibility", "allowed-tools", "metadata"]
    for key in key_order:
        if key not in data:
            continue
        value = data[key]

        if key == "metadata" and isinstance(value, dict):
            lines.append("metadata:")
            for mk, mv in value.items():
                lines.append(f"  {mk}: {_yaml_quote(mv)}")
        else:
            lines.append(f"{key}: {_yaml_quote(value)}")

    return "\n".join(lines)


def _yaml_quote(value) -> str:
    """Quote a value for YAML output if needed."""
    if not isinstance(value, str):
        return str(value)

    # Always quote strings that contain special YAML characters
    needs_quoting = any(c in value for c in ":{}[]#&*!|>'\"%@`,?") or value.lower() in (
        "true", "false", "yes", "no", "null", "on", "off"
    )

    if needs_quoting or len(value) > 80:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'

    return value


# =============================================================================
# ZIP handling
# =============================================================================

def find_skill_md_in_zip(zip_path: str) -> str | None:
    """Find SKILL.md in a ZIP file, return its archive path."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("SKILL.md") and "/" + "SKILL.md" in "/" + name:
                return name
    return None


def read_skill_md_from_zip(zip_path: str, archive_path: str) -> str:
    """Read SKILL.md content from a ZIP file."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        return zf.read(archive_path).decode("utf-8")


def fix_zip(zip_path: str, archive_path: str, fixed_content: str) -> None:
    """Replace SKILL.md in a ZIP file with fixed content."""
    temp_fd, temp_path = tempfile.mkstemp(suffix=".zip")
    os.close(temp_fd)

    try:
        with zipfile.ZipFile(zip_path, "r") as zin:
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.namelist():
                    if item == archive_path:
                        zout.writestr(item, fixed_content.encode("utf-8"))
                    else:
                        zout.writestr(item, zin.read(item))
        shutil.move(temp_path, zip_path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


# =============================================================================
# Main
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate SKILL.md frontmatter for claude.ai / Claude Desktop / ChatGPT compatibility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 validate_frontmatter.py SKILL.md          # Check for issues
  python3 validate_frontmatter.py SKILL.md --fix     # Fix issues in-place
  python3 validate_frontmatter.py skill.zip --fix    # Fix SKILL.md inside ZIP
  python3 validate_frontmatter.py SKILL.md --json    # Machine-readable output
        """
    )
    parser.add_argument("path", help="Path to SKILL.md or .zip file")
    parser.add_argument("--fix", action="store_true", help="Fix issues (writes corrected file)")
    parser.add_argument("--output", "-o", help="Output path for fixed file (default: overwrite input)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()
    path = Path(args.path)

    if not path.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(2)

    # Determine if ZIP or SKILL.md
    is_zip = path.suffix.lower() == ".zip"
    archive_path = None

    try:
        if is_zip:
            archive_path = find_skill_md_in_zip(str(path))
            if not archive_path:
                print(f"Error: No SKILL.md found in {path}", file=sys.stderr)
                sys.exit(2)
            content = read_skill_md_from_zip(str(path), archive_path)
        else:
            content = path.read_text(encoding="utf-8")

        data, body, raw_fm = parse_frontmatter(content)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(2)

    issues = validate(data)

    if args.json_output:
        result = {
            "file": str(path),
            "valid": len([i for i in issues if i["level"] == "error"]) == 0,
            "issues": issues,
        }
        if args.fix and issues:
            result["fixed"] = True
        print(json.dumps(result, indent=2))
    else:
        if not issues:
            print(f"✓ {path}: Frontmatter is valid for claude.ai / Claude Desktop / ChatGPT")
        else:
            errors = [i for i in issues if i["level"] == "error"]
            warnings = [i for i in issues if i["level"] == "warning"]
            print(f"✗ {path}: Found {len(errors)} error(s), {len(warnings)} warning(s)\n")
            for issue in issues:
                icon = "✗" if issue["level"] == "error" else "⚠"
                print(f"  {icon} [{issue['field']}] {issue['message']}")

    if args.fix and issues:
        fixed_data = fix_frontmatter(data)
        fixed_fm = serialize_frontmatter(fixed_data)
        fixed_content = f"---\n{fixed_fm}\n---\n{body.lstrip(chr(10))}"

        # Validate the fix
        re_issues = validate(fixed_data)
        re_errors = [i for i in re_issues if i["level"] == "error"]

        if re_errors:
            print(f"\nWarning: Could not fully auto-fix all issues ({len(re_errors)} remaining).", file=sys.stderr)
            for issue in re_errors:
                print(f"  ✗ [{issue['field']}] {issue['message']}", file=sys.stderr)
            sys.exit(1)

        if is_zip:
            output_path = args.output or str(path)
            if args.output:
                shutil.copy2(str(path), output_path)
            fix_zip(output_path, archive_path, fixed_content)
            if not args.json_output:
                print(f"\n✓ Fixed SKILL.md inside {output_path}")
        else:
            output_path = args.output or str(path)
            Path(output_path).write_text(fixed_content, encoding="utf-8")
            if not args.json_output:
                print(f"\n✓ Fixed frontmatter written to {output_path}")

        sys.exit(0)

    # Exit code: 0 if valid, 1 if issues
    sys.exit(0 if not any(i["level"] == "error" for i in issues) else 1)


if __name__ == "__main__":
    main()
