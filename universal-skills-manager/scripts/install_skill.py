#!/usr/bin/env python3
"""
Universal Skill Installer

A robust, zero-dependency Python script for downloading and installing AI skills
from GitHub repositories. Uses atomic install pattern for safety.

Usage:
    python3 install_skill.py --url "https://github.com/user/repo/tree/main/skills/my-skill" --dest "~/.claude/skills/my-skill"

Features:
    - Atomic install: Downloads to temp, validates, then moves to destination
    - Multi-file validation: Validates .py, .sh, .json, .yaml files
    - Single API call: Only one GitHub API request to list directory
    - Raw URL downloads: No rate limiting for file downloads
"""

import argparse
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

if sys.platform == "win32" and not os.environ.get("PYTHONIOENCODING"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

VERSION = "1.4.0"


# =============================================================================
# URL Parsing
# =============================================================================

def parse_github_url(url: str) -> Optional[dict]:
    """
    Parse a GitHub tree URL into components.
    
    Input:  https://github.com/{owner}/{repo}/tree/{branch}/{path}
            https://github.com/{owner}/{repo}/tree/{branch}  (root level)
    Output: {"owner": ..., "repo": ..., "branch": ..., "path": ...}
    
    Returns None if URL is not a valid GitHub tree URL.
    """
    # Pattern: github.com/{owner}/{repo}/tree/{branch}/{path...} (path optional)
    pattern = r'https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)(?:/(.+?))?/?$'
    match = re.match(pattern, url)
    
    if not match:
        return None
    
    return {
        "owner": match.group(1),
        "repo": match.group(2),
        "branch": match.group(3),
        "path": match.group(4) or "",  # Empty string if at root
    }


def to_raw_url(owner: str, repo: str, branch: str, path: str, filename: str) -> str:
    """Convert GitHub components to raw.githubusercontent.com URL."""
    # URL-encode the filename to handle spaces and special characters
    from urllib.parse import quote
    encoded_filename = quote(filename, safe='')
    if path:
        encoded_path = '/'.join(quote(p, safe='') for p in path.split('/'))
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{encoded_path}/{encoded_filename}"
    else:
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{encoded_filename}"


def to_api_url(owner: str, repo: str, branch: str, path: str) -> str:
    """Convert GitHub components to API contents URL."""
    if path:
        return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    else:
        return f"https://api.github.com/repos/{owner}/{repo}/contents?ref={branch}"


# =============================================================================
# GitHub API & Downloads
# =============================================================================

def fetch_json(url: str, token: Optional[str] = None, verbose: bool = False) -> dict:
    """Fetch JSON from URL with optional auth token."""
    if verbose:
        print(f"  Fetching: {url}")
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    request = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"Not found: {url}. Check URL or use --token for private repos.")
        elif e.code == 403:
            raise RuntimeError(f"Rate limited or forbidden. Use --token for higher limits.")
        else:
            raise RuntimeError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")


def fetch_file(url: str, dest_path: Path, token: Optional[str] = None, verbose: bool = False) -> None:
    """Download a file from URL to destination path."""
    if verbose:
        print(f"  Downloading: {url}")
    
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    
    request = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(content)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Failed to download {url}: HTTP {e.code}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error downloading {url}: {e.reason}")


def list_directory_contents(owner: str, repo: str, branch: str, path: str, 
                            token: Optional[str] = None, verbose: bool = False) -> list:
    """List contents of a GitHub directory using API."""
    api_url = to_api_url(owner, repo, branch, path)
    contents = fetch_json(api_url, token, verbose)
    
    if not isinstance(contents, list):
        raise RuntimeError(f"Expected directory at {path}, got file")
    
    return contents


def sanitize_filename(name: str) -> str:
    """
    Validate a filename from GitHub API response.
    Raises RuntimeError if name contains path traversal characters.
    Returns the validated name.
    """
    if not name or not name.strip():
        raise RuntimeError("Empty filename received from GitHub API")

    if '/' in name or '\\' in name:
        raise RuntimeError(f"Path separator in filename: {name!r}")

    if '..' in name:
        raise RuntimeError(f"Path traversal attempt in filename: {name!r}")

    if name == '.':
        raise RuntimeError(f"Invalid filename: {name!r}")

    if os.path.basename(name) != name:
        raise RuntimeError(f"Filename resolves to different path: {name!r}")

    return name


def verify_path_containment(child: Path, parent: Path) -> None:
    """Raise RuntimeError if child path is not inside parent directory."""
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        raise RuntimeError(
            f"Path escapes destination directory: {child} is not inside {parent}"
        )


def download_directory(owner: str, repo: str, branch: str, path: str,
                       dest_dir: Path, token: Optional[str] = None,
                       verbose: bool = False, current_depth: int = 0,
                       max_depth: int = 5) -> list:
    """
    Recursively download directory contents from GitHub.
    Returns list of downloaded file paths (relative to dest_dir).
    """
    if current_depth > max_depth:
        print(f"  Warning: Max depth {max_depth} reached, skipping deeper directories")
        return []

    downloaded = []
    contents = list_directory_contents(owner, repo, branch, path, token, verbose)

    for item in contents:
        item_name = sanitize_filename(item["name"])
        item_type = item["type"]

        if item_type == "file":
            # Download via raw URL
            raw_url = to_raw_url(owner, repo, branch, path, item_name)
            dest_path = dest_dir / item_name
            verify_path_containment(dest_path, dest_dir)
            fetch_file(raw_url, dest_path, token, verbose)
            downloaded.append(item_name)
            print(f"  ✓ {item_name}")

        elif item_type == "dir":
            # Recursively download subdirectory
            subdir = dest_dir / item_name
            verify_path_containment(subdir, dest_dir)
            subdir.mkdir(parents=True, exist_ok=True)
            sub_path = f"{path}/{item_name}"
            sub_files = download_directory(
                owner, repo, branch, sub_path, subdir,
                token, verbose, current_depth + 1, max_depth
            )
            downloaded.extend([f"{item_name}/{f}" for f in sub_files])

    return downloaded


# =============================================================================
# Validation
# =============================================================================

def parse_simple_yaml(yaml_str: str) -> dict:
    """
    Parse simple key: value YAML (no nested objects, no lists).
    Sufficient for SKILL.md frontmatter.
    """
    result = {}
    for line in yaml_str.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def validate_skill_md(file_path: Path) -> tuple[bool, str]:
    """
    Validate SKILL.md has proper YAML frontmatter.
    Returns (success, error_message).
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        return False, f"Cannot read file: {e}"
    
    if not content.startswith('---'):
        return False, "Missing YAML frontmatter (must start with ---)"
    
    parts = content.split('---', 2)
    if len(parts) < 3:
        return False, "Invalid frontmatter (missing closing ---)"
    
    try:
        frontmatter = parse_simple_yaml(parts[1])
    except Exception as e:
        return False, f"Invalid YAML: {e}"
    
    if 'name' not in frontmatter:
        return False, "Missing required field: name"
    if 'description' not in frontmatter:
        return False, "Missing required field: description"
    
    return True, ""


def validate_python(file_path: Path) -> tuple[bool, str]:
    """Validate Python syntax using ast.parse()."""
    try:
        content = file_path.read_text(encoding='utf-8')
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"Python syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Cannot parse Python: {e}"


def validate_shell(file_path: Path) -> tuple[bool, str]:
    """Validate shell script syntax using bash -n."""
    try:
        result = subprocess.run(
            ['bash', '-n', str(file_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return False, f"Shell syntax error: {result.stderr.strip()}"
        return True, ""
    except FileNotFoundError:
        # bash not available, skip validation
        return True, ""
    except Exception as e:
        return False, f"Cannot validate shell script: {e}"


def validate_json(file_path: Path) -> tuple[bool, str]:
    """Validate JSON syntax."""
    try:
        content = file_path.read_text(encoding='utf-8')
        json.loads(content)
        return True, ""
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Cannot read JSON: {e}"


def validate_yaml(file_path: Path) -> tuple[bool, str]:
    """Validate basic YAML structure."""
    try:
        content = file_path.read_text(encoding='utf-8')
        # Basic check: can we parse key: value pairs?
        parse_simple_yaml(content)
        return True, ""
    except Exception as e:
        return False, f"Invalid YAML: {e}"


def validate_file(file_path: Path, verbose: bool = False) -> tuple[bool, str]:
    """
    Validate a file based on its extension.
    Returns (success, error_message).
    """
    name = file_path.name.lower()
    suffix = file_path.suffix.lower()
    
    if name == 'skill.md':
        return validate_skill_md(file_path)
    elif suffix == '.py':
        return validate_python(file_path)
    elif suffix == '.sh':
        return validate_shell(file_path)
    elif suffix == '.json':
        return validate_json(file_path)
    elif suffix in ('.yaml', '.yml'):
        return validate_yaml(file_path)
    else:
        # No validation for other file types
        return True, ""


def validate_all_files(directory: Path, verbose: bool = False) -> tuple[bool, list]:
    """
    Validate all files in directory recursively.
    Returns (all_valid, list_of_errors).
    """
    errors = []
    
    # First check: SKILL.md must exist
    skill_md = directory / "SKILL.md"
    if not skill_md.exists():
        errors.append("SKILL.md not found in skill directory")
        return False, errors
    
    # Validate all files
    for file_path in directory.rglob('*'):
        if file_path.is_file():
            valid, error = validate_file(file_path, verbose)
            if not valid:
                errors.append(f"{file_path.name}: {error}")
    
    return len(errors) == 0, errors


# =============================================================================
# Safety Checks
# =============================================================================

def check_root_skills_directory_safety(dest: Path, force: bool) -> None:
    """
    Abort if destination looks like a root skills directory.
    
    Root skills directory = has subdirs with SKILL.md but no SKILL.md itself.
    Fresh/empty directories are allowed.
    """
    if not dest.exists() or not dest.is_dir() or force:
        return  # Safe to proceed
    
    has_skill_md = (dest / "SKILL.md").exists()
    if has_skill_md:
        return  # This IS a skill, safe to update
    
    # Check for subdirectories containing SKILL.md (installed skills)
    installed_skills = [
        d.name for d in dest.iterdir() 
        if d.is_dir() and (d / "SKILL.md").exists()
    ]
    
    if installed_skills:
        # DANGER: This is a root skills directory!
        print("=" * 60, file=sys.stderr)
        print("CRITICAL ERROR: Root Skills Directory Detected", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"\nDestination: {dest}", file=sys.stderr)
        print(f"\nThis appears to be a root skills directory containing:", file=sys.stderr)
        for skill in installed_skills[:5]:
            print(f"  • {skill}", file=sys.stderr)
        if len(installed_skills) > 5:
            print(f"  ... and {len(installed_skills) - 5} more", file=sys.stderr)
        print(f"\nYou probably meant: {dest}/<skill-name>", file=sys.stderr)
        print("\nUse --force to override this safety check.", file=sys.stderr)
        sys.exit(4)


def file_hash(file_path: Path) -> str:
    """Calculate MD5 hash of a file for comparison."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def compare_skill_directories(new_dir: Path, existing_dir: Path) -> dict:
    """
    Compare two skill directories and return differences.
    
    Returns:
        {
            "identical": bool,
            "added": [list of new files],
            "removed": [list of deleted files],
            "modified": [list of changed files],
        }
    """
    def get_relative_files(base: Path) -> dict:
        """Get all files relative to base with their hashes."""
        files = {}
        for file_path in base.rglob('*'):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(base))
                files[rel_path] = file_hash(file_path)
        return files
    
    new_files = get_relative_files(new_dir)
    existing_files = get_relative_files(existing_dir)
    
    new_set = set(new_files.keys())
    existing_set = set(existing_files.keys())
    
    added = sorted(new_set - existing_set)
    removed = sorted(existing_set - new_set)
    
    # Check for modified files (same name, different hash)
    common = new_set & existing_set
    modified = sorted([f for f in common if new_files[f] != existing_files[f]])
    
    identical = len(added) == 0 and len(removed) == 0 and len(modified) == 0
    
    return {
        "identical": identical,
        "added": added,
        "removed": removed,
        "modified": modified,
    }


def display_skill_diff(diff: dict, dest: Path, force: bool) -> bool:
    """
    Display diff and prompt user for confirmation.
    
    Returns True if user approves (or force=True), False otherwise.
    """
    if diff["identical"]:
        print(f"\n✓ Skill is already up to date: {dest}")
        return False  # No need to reinstall
    
    print(f"\n📋 Changes detected for skill at: {dest}")
    print("-" * 50)
    
    if diff["added"]:
        print(f"\n  ➕ New files ({len(diff['added'])}):", )
        for f in diff["added"][:10]:
            print(f"      {f}")
        if len(diff["added"]) > 10:
            print(f"      ... and {len(diff['added']) - 10} more")
    
    if diff["removed"]:
        print(f"\n  ➖ Removed files ({len(diff['removed'])}):", )
        for f in diff["removed"][:10]:
            print(f"      {f}")
        if len(diff["removed"]) > 10:
            print(f"      ... and {len(diff['removed']) - 10} more")
    
    if diff["modified"]:
        print(f"\n  📝 Modified files ({len(diff['modified'])}):", )
        for f in diff["modified"][:10]:
            print(f"      {f}")
        if len(diff["modified"]) > 10:
            print(f"      ... and {len(diff['modified']) - 10} more")
    
    print("-" * 50)
    
    if force:
        print("  (--force specified, proceeding without prompt)")
        return True
    
    try:
        if not sys.stdin.isatty():
            raise EOFError
        response = input("\nProceed with update? [y/N]: ")
        return response.lower() == 'y'
    except EOFError:
        print("\n  Non-interactive mode: update requires --force to proceed.")
        return False


# =============================================================================
# Manifest (skills.lock.json)
# =============================================================================

MANIFEST_FILENAME = "skills.lock.json"


def compute_directory_hash(directory: Path) -> str:
    """
    Compute a composite SHA-256 hash of all files in a directory.
    Files are processed in sorted order for deterministic results.
    """
    hasher = hashlib.sha256()
    file_paths = sorted(
        [p for p in directory.rglob('*') if p.is_file()],
        key=lambda p: str(p.relative_to(directory))
    )
    for file_path in file_paths:
        rel_path = str(file_path.relative_to(directory))
        hasher.update(rel_path.encode('utf-8'))
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
        except OSError:
            continue  # Skip unreadable files
    return f"sha256:{hasher.hexdigest()}"


def extract_skill_version(skill_dir: Path) -> Optional[str]:
    """
    Extract version from SKILL.md using fallback methods:
    1. YAML frontmatter 'version' field
    2. HTML comment <!-- Version: X.Y.Z -->
    Returns None if no version info found.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    try:
        content = skill_md.read_text(encoding='utf-8')
    except OSError:
        return None

    # Method 1: Check frontmatter for version field
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = parse_simple_yaml(parts[1])
                if 'version' in frontmatter and frontmatter['version']:
                    return frontmatter['version']
            except Exception:
                pass

    # Method 2: Check HTML comment <!-- Version: X.Y.Z -->
    version_match = re.search(r'<!--\s*Version:\s*(\S+)\s*-->', content, re.IGNORECASE)
    if version_match:
        return version_match.group(1)

    return None


def _extract_skill_description(skill_dir: Path) -> str:
    """Extract description from SKILL.md frontmatter. Returns empty string on failure."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return ""

    try:
        content = skill_md.read_text(encoding='utf-8')
    except OSError:
        return ""

    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = parse_simple_yaml(parts[1])
                return frontmatter.get('description', '')
            except Exception:
                pass
    return ""


def read_manifest(manifest_path: Path) -> dict:
    """Read existing skills.lock.json or return empty manifest structure."""
    if manifest_path.exists() and manifest_path.is_file():
        try:
            content = manifest_path.read_text(encoding='utf-8')
            data = json.loads(content)
            if isinstance(data, dict) and "skills" in data:
                return data
            else:
                print(f"  Warning: Malformed manifest at {manifest_path}, creating new one")
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Warning: Could not read manifest ({e}), creating new one")

    return {"version": "1.0", "skills": {}}


def write_manifest(manifest_path: Path, manifest: dict) -> None:
    """Atomically write manifest to disk using tmp + rename."""
    tmp_path = manifest_path.with_suffix('.tmp')
    try:
        content = json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'
        tmp_path.write_text(content, encoding='utf-8')
        os.replace(str(tmp_path), str(manifest_path))
    except OSError:
        # Fallback: try direct write
        try:
            if tmp_path.exists():
                tmp_path.unlink()
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + '\n',
                encoding='utf-8'
            )
        except OSError as e:
            print(f"  Warning: Could not write manifest: {e}")


def update_manifest_entry(dest: Path, source_url: str, verbose: bool = False) -> None:
    """
    After a successful install, update the manifest with the skill entry.
    The manifest lives in the parent directory (the tool's root skills dir).
    """
    manifest_path = dest.parent / MANIFEST_FILENAME
    skill_name = dest.name
    now = datetime.now(timezone.utc).isoformat()

    manifest = read_manifest(manifest_path)

    # Count files
    file_count = sum(1 for p in dest.rglob('*') if p.is_file())

    # Compute hash and extract metadata
    files_hash = compute_directory_hash(dest)
    version = extract_skill_version(dest)
    description = _extract_skill_description(dest)

    # Preserve original install date if updating
    existing = manifest["skills"].get(skill_name, {})
    installed_at = existing.get("installed_at", now)

    manifest["skills"][skill_name] = {
        "name": skill_name,
        "description": description,
        "source_url": source_url,
        "installed_at": installed_at,
        "updated_at": now,
        "version": version,
        "files_hash": files_hash,
        "file_count": file_count,
    }

    write_manifest(manifest_path, manifest)

    if verbose:
        print(f"  Updated manifest: {manifest_path}")


def display_manifest(manifest_path: Path) -> None:
    """Display installed skills from a manifest file."""
    manifest = read_manifest(manifest_path)
    skills = manifest.get("skills", {})

    if not skills:
        print("No skills tracked in manifest.")
        return

    print(f"\nInstalled skills ({len(skills)}):")
    print("-" * 70)
    print(f"  {'Name':<25} {'Version':<10} {'Files':<6} {'Description'}")
    print("-" * 70)

    for name, info in sorted(skills.items()):
        version = info.get("version") or "unknown"
        file_count = info.get("file_count", "?")
        desc = info.get("description", "")
        if len(desc) > 35:
            desc = desc[:32] + "..."
        print(f"  {name:<25} {version:<10} {file_count:<6} {desc}")

    print("-" * 70)
    print(f"  Total: {len(skills)} skill(s)")
    print(f"  Manifest: {manifest_path}")


# =============================================================================
# Tool-specific Modifications
# =============================================================================

def _inject_frontmatter_extras(skill_path: Path, extras: dict) -> None:
    """Inject extra frontmatter fields into SKILL.md for tool-specific compatibility."""
    if not skill_path.exists():
        return
        
    content = skill_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return

    try:
        end_idx = content.index("---", 3)
    except ValueError:
        return
        
    frontmatter = content[3:end_idx]

    for key, value in extras.items():
        # Remove any existing line for this key
        frontmatter = re.sub(rf"\n{re.escape(key)}:.*", "", frontmatter)
        # Add the field
        frontmatter = frontmatter.rstrip() + f"\n{key}: {value}\n"

    content = "---" + frontmatter + "---" + content[end_idx + 3 :]
    skill_path.write_text(content, encoding="utf-8")


def _get_frontmatter_extras_for_dest(dest: Path) -> dict:
    """Check destination path against registry to find frontmatter extras."""
    try:
        from sync_skills import TOOLS
    except ImportError:
        return {}
        
    for tool in TOOLS:
        if "frontmatter_extras" not in tool:
            continue
            
        user_path_str = tool.get("user_path")
        if user_path_str:
            user_path = Path(user_path_str).expanduser().resolve()
            try:
                # Check if dest is inside user_path
                dest.resolve().relative_to(user_path)
                return tool["frontmatter_extras"]
            except ValueError:
                pass
                
        project_path_str = tool.get("project_path")
        if project_path_str:
            if str(dest.resolve()).endswith(project_path_str) or project_path_str in str(dest.resolve()):
                return tool["frontmatter_extras"]
                
    return {}


# =============================================================================
# Installation
# =============================================================================

def _check_for_symlinks(directory: Path) -> None:
    """Raise RuntimeError if directory contains any symlinks."""
    for item in directory.rglob('*'):
        if item.is_symlink():
            raise RuntimeError(
                f"Symlink detected in existing skill directory: {item}\n"
                f"This is unexpected and may indicate tampering. "
                f"Remove symlinks manually before updating."
            )


def install_skill(temp_dir: Path, dest: Path, verbose: bool = False) -> None:
    """
    Copy validated skill from temp to destination using atomic swap.

    If destination exists:
      1. Check for symlinks (safety)
      2. Rename dest -> dest.bak
      3. Copy temp -> dest
      4. On success: remove dest.bak
      5. On failure: remove partial dest, restore dest.bak
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup_path = dest.with_name(dest.name + ".bak")

    if dest.exists():
        # Safety: check for symlinks in existing directory
        _check_for_symlinks(dest)

        # Remove any stale backup from a previous failed install
        if backup_path.exists():
            shutil.rmtree(backup_path)

        # Step 1: Move existing to backup
        if verbose:
            print(f"  Backing up existing: {dest.name} -> {dest.name}.bak")
        os.rename(str(dest), str(backup_path))

        try:
            # Step 2: Copy new content
            shutil.copytree(str(temp_dir), str(dest))

            # Step 3: Success - remove backup
            shutil.rmtree(backup_path)
            if verbose:
                print(f"  Removed backup: {backup_path.name}")
        except Exception:
            # Step 4: Failure - restore backup
            if dest.exists():
                shutil.rmtree(dest)
            os.rename(str(backup_path), str(dest))
            raise  # Re-raise so caller sees the error
    else:
        # Fresh install, no backup needed
        shutil.copytree(str(temp_dir), str(dest))


# =============================================================================
# Security Scanning
# =============================================================================

def find_scanner_script() -> Optional[Path]:
    """Find scan_skill.py in the same directory as this script."""
    script_dir = Path(__file__).parent
    scanner = script_dir / "scan_skill.py"
    if scanner.exists():
        return scanner
    return None


def run_security_scan(skill_dir: Path, force: bool = False) -> bool:
    """
    Run security scan on a skill directory before installation.

    Returns True if installation should proceed, False to abort.

    Policy:
    - If scanner exists: it MUST succeed. Failures block installation.
    - If scanner does not exist: warn and allow (standalone usage).
    - --skip-scan bypasses this entirely (checked by caller).
    - --force bypasses user prompts for findings, NOT scanner failures.
    """
    scanner = find_scanner_script()
    if scanner is None:
        print("  Warning: Security scanner (scan_skill.py) not found.")
        print("  Install the full Universal Skills Manager for security scanning.")
        return True  # Allow standalone usage

    print("\nRunning security scan...")

    try:
        result = subprocess.run(
            [sys.executable, str(scanner), str(skill_dir)],
            capture_output=True,
            text=True,
            timeout=30
        )
    except subprocess.TimeoutExpired:
        print("  ERROR: Security scan timed out.", file=sys.stderr)
        print("  Installation blocked. Use --skip-scan to bypass.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  ERROR: Security scan failed to run: {e}", file=sys.stderr)
        print("  Installation blocked. Use --skip-scan to bypass.", file=sys.stderr)
        return False

    # Parse JSON output from scanner
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("  ERROR: Could not parse security scan results.", file=sys.stderr)
        if result.stderr:
            print(f"  Scanner stderr: {result.stderr.strip()}", file=sys.stderr)
        print("  Installation blocked. Use --skip-scan to bypass.", file=sys.stderr)
        return False

    # Extract summary and findings
    summary = report.get("summary", {})
    findings = report.get("findings", [])
    total = (summary.get("critical", 0)
             + summary.get("warning", 0)
             + summary.get("info", 0))

    if total == 0:
        print("  No security threats detected")
        return True

    # Display findings grouped by severity
    severity_order = ["critical", "warning", "info"]

    print(f"\n  Security scan found {total} issue(s):")
    print("  " + "-" * 48)

    for severity in severity_order:
        severity_findings = [f for f in findings if f.get("severity") == severity]
        if not severity_findings:
            continue

        print(f"\n  [{severity.upper()}]")
        for finding in severity_findings:
            file_name = finding.get("file", "unknown")
            line = finding.get("line")
            message = finding.get("description", "No description")
            location = f"{file_name}:{line}" if line else file_name
            print(f"    - {location}: {message}")

    print("  " + "-" * 48)

    # Summary line with counts
    parts = []
    for severity in severity_order:
        count = summary.get(severity, 0)
        if count > 0:
            parts.append(f"{count} {severity}")
    print(f"  Summary: {', '.join(parts)}")

    if force:
        print("\n  Note: --force specified, proceeding despite security findings")
        return True

    try:
        if not sys.stdin.isatty():
            raise EOFError
        response = input("\nProceed with installation? [y/N]: ")
        return response.lower() == 'y'
    except EOFError:
        print("\n  Non-interactive mode: use --force to proceed despite security findings.")
        return False


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Download and install AI skills from GitHub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url "https://github.com/user/repo/tree/main/skills/my-skill" --dest "~/.claude/skills/my-skill"
  %(prog)s --url "https://github.com/user/repo/tree/main/skills/my-skill" --dest "/tmp/test" --dry-run
        """
    )
    
    parser.add_argument(
        '--url', required=False,
        help='GitHub URL to skill folder (tree URL format)'
    )
    parser.add_argument(
        '--dest', required=False,
        help='Local destination path for skill installation'
    )
    parser.add_argument(
        '--token',
        help='GitHub personal access token (for private repos or higher rate limits)'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Overwrite existing skill without prompting and bypass safety checks'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be downloaded without actually installing'
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='Show detailed progress'
    )
    parser.add_argument(
        '--max-depth', type=int, default=5,
        help='Maximum directory depth to recurse (default: 5)'
    )
    parser.add_argument(
        '--skip-scan', action='store_true',
        help='Skip security scan (not recommended)'
    )
    parser.add_argument(
        '--version', action='store_true',
        help='Show version information and exit'
    )
    parser.add_argument(
        '--manifest',
        help='Show installed skills from manifest (e.g., ~/.claude/skills/skills.lock.json)'
    )
    
    args = parser.parse_args()

    # Show version
    if args.version:
        print(f"Universal Skill Installer v{VERSION}")
        sys.exit(0)

    # Show manifest
    if args.manifest:
        manifest_path = Path(args.manifest).expanduser().resolve()
        display_manifest(manifest_path)
        sys.exit(0)

    # Validate required arguments
    if not args.url or not args.dest:
        parser.error("the following arguments are required: --url, --dest")
    
    # Expand ~ in destination path
    dest = Path(args.dest).expanduser().resolve()
    
    # Parse GitHub URL
    print(f"Parsing URL: {args.url}")
    parsed = parse_github_url(args.url)
    if not parsed:
        print("Error: Invalid GitHub URL format", file=sys.stderr)
        print("Expected: https://github.com/{owner}/{repo}/tree/{branch}/{path}", file=sys.stderr)
        sys.exit(2)
    
    print(f"Repository: {parsed['owner']}/{parsed['repo']}")
    print(f"Branch: {parsed['branch']}")
    print(f"Path: {parsed['path']}")
    print(f"Destination: {dest}")
    
    # Safety check: Prevent accidental targeting of root skills directory
    check_root_skills_directory_safety(dest, args.force)
    
    # Dry run mode
    if args.dry_run:
        print("\n[DRY RUN] Would download:")
        try:
            contents = list_directory_contents(
                parsed['owner'], parsed['repo'], parsed['branch'], parsed['path'],
                args.token, args.verbose
            )
            for item in contents:
                item_type = "📁" if item["type"] == "dir" else "📄"
                print(f"  {item_type} {item['name']}")
            print("\n[DRY RUN] No files were downloaded")
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    
    # Create temp directory for atomic install
    with tempfile.TemporaryDirectory(prefix="skill_install_") as temp_dir:
        temp_path = Path(temp_dir) / "skill"
        temp_path.mkdir()
        
        # Step 1: Download all files to temp
        print("\nDownloading skill files...")
        try:
            downloaded = download_directory(
                parsed['owner'], parsed['repo'], parsed['branch'], parsed['path'],
                temp_path, args.token, args.verbose, max_depth=args.max_depth
            )
        except RuntimeError as e:
            print(f"\nError during download: {e}", file=sys.stderr)
            sys.exit(1)
        
        if not downloaded:
            print("Error: No files downloaded", file=sys.stderr)
            sys.exit(1)
        
        print(f"\nDownloaded {len(downloaded)} file(s)")
        
        # Step 2: Validate all files
        print("\nValidating files...")
        valid, errors = validate_all_files(temp_path, args.verbose)
        
        if not valid:
            print("\nValidation failed:", file=sys.stderr)
            for error in errors:
                print(f"  ✗ {error}", file=sys.stderr)
            print("\nInstallation aborted. No files were written to destination.", file=sys.stderr)
            sys.exit(2)
        
        print("  ✓ All files valid")

        # Inject frontmatter extras if tool requires it
        extras = _get_frontmatter_extras_for_dest(dest)
        if extras:
            if args.verbose:
                print(f"\nInjecting frontmatter extras for destination: {extras}")
            _inject_frontmatter_extras(temp_path / "SKILL.md", extras)

        # Step 2.5: Security scan
        if not args.skip_scan:
            should_proceed = run_security_scan(temp_path, args.force)
            if not should_proceed:
                print("Installation aborted by user after security scan.")
                sys.exit(0)
        else:
            print("\n  (Security scan skipped via --skip-scan)")

        # Step 3: Compare if destination already exists
        if dest.exists():
            diff = compare_skill_directories(temp_path, dest)
            should_install = display_skill_diff(diff, dest, args.force)
            if not should_install:
                if diff["identical"]:
                    sys.exit(0)  # Already up to date
                else:
                    print("Aborted.")
                    sys.exit(0)
        
        # Step 4: Install (copy from temp to destination)
        print(f"\nInstalling to: {dest}")
        try:
            install_skill(temp_path, dest, args.verbose)
        except Exception as e:
            print(f"\nError during installation: {e}", file=sys.stderr)
            sys.exit(3)
    
    # Step 5: Update manifest
    try:
        update_manifest_entry(dest, args.url, args.verbose)
    except Exception as e:
        print(f"  Warning: Could not update manifest: {e}")

    print(f"\n✓ Skill installed successfully to: {dest}")
    sys.exit(0)


if __name__ == '__main__':
    main()
