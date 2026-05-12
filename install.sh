#!/bin/sh
# Universal Skills Manager - One-liner Installer
# https://github.com/jacob-bd/universal-skills-manager
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jacob-bd/universal-skills-manager/main/install.sh | sh
#   sh install.sh --help
#   sh install.sh --tools claude,gemini
#
# Requirements:
#   - Python 3.8 or later
#   - curl or git (for downloading)

set -e

# =============================================================================
# Configuration
# =============================================================================

REPO_URL="https://github.com/jacob-bd/universal-skills-manager"
TARBALL_URL="${REPO_URL}/archive/refs/heads/main.tar.gz"
SKILL_FOLDER="universal-skills-manager"

# =============================================================================
# Color Support (POSIX-compatible)
# =============================================================================

setup_colors() {
    if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ -n "$(tput colors 2>/dev/null)" ]; then
        RED=$(tput setaf 1)
        GREEN=$(tput setaf 2)
        YELLOW=$(tput setaf 3)
        BLUE=$(tput setaf 4)
        BOLD=$(tput bold)
        RESET=$(tput sgr0)
    else
        RED="" GREEN="" YELLOW="" BLUE="" BOLD="" RESET=""
    fi
}

# =============================================================================
# Utility Functions
# =============================================================================

info()    { printf "%s[INFO]%s  %s\n" "$BLUE" "$RESET" "$1"; }
warn()    { printf "%s[WARN]%s  %s\n" "$YELLOW" "$RESET" "$1"; }
error()   { printf "%s[ERROR]%s %s\n" "$RED" "$RESET" "$1" >&2; }
success() { printf "%s[OK]%s    %s\n" "$GREEN" "$RESET" "$1"; }

die() {
    error "$1"
    exit 1
}

# =============================================================================
# Argument Parsing
# =============================================================================

TOOLS_FILTER=""
SHOW_HELP=false

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --help|-h)
                SHOW_HELP=true
                shift
                ;;
            --tools)
                if [ -z "${2:-}" ]; then
                    die "--tools requires a comma-separated list (e.g., --tools claude,gemini)"
                fi
                TOOLS_FILTER="$2"
                shift 2
                ;;
            --tools=*)
                TOOLS_FILTER="${1#--tools=}"
                shift
                ;;
            *)
                warn "Unknown argument: $1"
                shift
                ;;
        esac
    done
}

# =============================================================================
# Help
# =============================================================================

show_help() {
    cat <<'HELP'
Universal Skills Manager - Installer

Usage:
  sh install.sh [OPTIONS]

Options:
  --help, -h        Show this help message
  --tools LIST      Comma-separated list of tools to install to
                    (skips auto-detection)
                    Valid: claude,gemini,antigravity,opencode,openclaw,
                           alef-agent,codex,goose,roo,cursor,cline,hermes
                    (gemini and codex both install to ~/.agents/skills/)

Examples:
  sh install.sh                        # Auto-detect and install
  sh install.sh --tools claude,gemini  # Install to specific tools only

What this does:
  1. Checks for Python 3.8+
  2. Detects which AI coding tools you have installed
  3. Downloads the Universal Skills Manager from GitHub
  4. Installs it to all detected tools
  5. Optionally sets up your SkillsMP API key (SkillHub and ClawHub search work without one)

Requirements:
  - Python 3.8 or later
  - curl or git (for downloading)
HELP
}

# =============================================================================
# Prerequisites
# =============================================================================

check_python() {
    PYTHON_CMD=""

    if command -v python3 >/dev/null 2>&1; then
        PYTHON_CMD="python3"
    elif command -v python >/dev/null 2>&1; then
        PY_MAJOR=$(python --version 2>&1 | sed 's/Python //' | cut -d. -f1)
        if [ "$PY_MAJOR" = "3" ]; then
            PYTHON_CMD="python"
        fi
    fi

    if [ -z "$PYTHON_CMD" ]; then
        die "Python 3 is required but not found. Please install Python 3.8+."
    fi

    # Verify minimum version (3.8)
    PY_VERSION=$($PYTHON_CMD --version 2>&1 | sed 's/Python //')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

    if [ "$PY_MAJOR" -lt 3 ] 2>/dev/null || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; } 2>/dev/null; then
        die "Python 3.8+ required, found $PY_VERSION"
    fi

    success "Python $PY_VERSION found ($PYTHON_CMD)"
}

# =============================================================================
# Tool Detection
# =============================================================================

# Stores detected tools as "ToolName|skills_path" entries separated by newlines
DETECTED_TOOLS=""
DETECTED_COUNT=0

detect_tools() {
    info "Detecting installed AI tools..."
    echo ""

    check_tool "Claude Code"        "$HOME/.claude"             "$HOME/.claude/skills"
    check_tool_gemini_codex
    check_tool "Anti-Gravity"       "$HOME/.gemini/antigravity" "$HOME/.gemini/antigravity/skills"
    check_tool "OpenCode"           "$HOME/.config/opencode"    "$HOME/.config/opencode/skills"
    check_tool "OpenClaw"           "$HOME/.openclaw"           "$HOME/.openclaw/workspace/skills"
    check_tool "Alef Agent"         "$HOME/.alef-agent"         "$HOME/.alef-agent/workspace/skills"
    check_tool "block/goose"        "$HOME/.config/goose"       "$HOME/.config/goose/skills"
    check_tool "Roo Code"           "$HOME/.roo"                "$HOME/.roo/skills"
    check_tool "Cursor"             "$HOME/.cursor"             "$HOME/.cursor/skills"
    check_tool "Cline"              "$HOME/.cline"              "$HOME/.cline/skills"
    check_tool_hermes

    if [ "$DETECTED_COUNT" -eq 0 ]; then
        echo ""
        warn "No supported AI tools detected on this system."
        warn "Supported tools: Claude Code, Gemini CLI, OpenCode, Cursor, and more."
        warn "Install one of these tools first, then re-run this script."
        exit 0
    fi

    echo ""
    info "Found $DETECTED_COUNT tool(s)"
}

check_tool() {
    tool_name="$1"
    tool_dir="$2"
    skills_dir="$3"

    if [ -d "$tool_dir" ]; then
        DETECTED_TOOLS="${DETECTED_TOOLS}${tool_name}|${skills_dir}
"
        DETECTED_COUNT=$((DETECTED_COUNT + 1))
        success "Found: $tool_name"
    fi
}

check_tool_gemini_codex() {
    # Gemini CLI (v0.30+) and OpenAI Codex both use ~/.agents/skills/.
    # Gemini CLI also reads ~/.gemini/skills/ but gives .agents/ precedence.
    # We install to ~/.agents/skills/ only to avoid duplicate-skill conflicts.
    if [ -d "$HOME/.gemini" ] || [ -d "$HOME/.agents" ]; then
        DETECTED_TOOLS="${DETECTED_TOOLS}Gemini CLI / Codex|${HOME}/.agents/skills
"
        DETECTED_COUNT=$((DETECTED_COUNT + 1))
        success "Found: Gemini CLI / Codex"
    fi
}

check_tool_hermes() {
    # Hermes Agent: $HERMES_HOME overrides ~/.hermes (common on Windows where
    # it defaults to AppData\Local\hermes).
    HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}"
    if [ -d "$HERMES_DIR" ]; then
        DETECTED_TOOLS="${DETECTED_TOOLS}Hermes Agent|${HERMES_DIR}/skills
"
        DETECTED_COUNT=$((DETECTED_COUNT + 1))
        success "Found: Hermes Agent"
    fi
}

# =============================================================================
# Tool Filtering (--tools flag)
# =============================================================================

filter_tools() {
    if [ -z "$TOOLS_FILTER" ]; then
        return
    fi

    FILTERED=""
    FILTERED_COUNT=0

    # Split comma-separated filter into positional params, then restore IFS
    OLD_IFS="$IFS"
    IFS=','
    # shellcheck disable=SC2086
    set -- $TOOLS_FILTER
    IFS="$OLD_IFS"

    for short_name in "$@"; do
        case "$short_name" in
            claude)       match="Claude Code" ;;
            gemini)       match="Gemini CLI / Codex" ;;
            antigravity)  match="Anti-Gravity" ;;
            opencode)     match="OpenCode" ;;
            openclaw)     match="OpenClaw" ;;
            alef-agent)   match="Alef Agent" ;;
            codex)        match="Gemini CLI / Codex" ;;
            goose)        match="block/goose" ;;
            roo)          match="Roo Code" ;;
            cursor)       match="Cursor" ;;
            cline)        match="Cline" ;;
            hermes)       match="Hermes Agent" ;;
            *)
                warn "Unknown tool: $short_name (skipping)"
                continue
                ;;
        esac

        # Iterate newline-separated DETECTED_TOOLS
        OLD_IFS="$IFS"
        IFS='
'
        for entry in $DETECTED_TOOLS; do
            [ -z "$entry" ] && continue
            entry_name=$(echo "$entry" | cut -d'|' -f1)
            if [ "$entry_name" = "$match" ]; then
                FILTERED="${FILTERED}${entry}
"
                FILTERED_COUNT=$((FILTERED_COUNT + 1))
            fi
        done
        IFS="$OLD_IFS"
    done

    if [ "$FILTERED_COUNT" -eq 0 ]; then
        die "None of the specified tools (${TOOLS_FILTER}) were detected on this system."
    fi

    DETECTED_TOOLS="$FILTERED"
    DETECTED_COUNT="$FILTERED_COUNT"
}

# =============================================================================
# Download Repository
# =============================================================================

TEMP_DIR=""
SKILL_SOURCE=""

download_repo() {
    TEMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'skill_install')
    trap 'rm -rf "$TEMP_DIR"' EXIT

    echo ""
    info "Downloading Universal Skills Manager..."

    if command -v git >/dev/null 2>&1; then
        if git clone --depth 1 --quiet "$REPO_URL" "$TEMP_DIR/repo" 2>/dev/null; then
            SKILL_SOURCE="$TEMP_DIR/repo/$SKILL_FOLDER"
        else
            warn "git clone failed, falling back to curl..."
            download_via_curl
        fi
    else
        download_via_curl
    fi

    # Verify download
    if [ ! -f "$SKILL_SOURCE/SKILL.md" ]; then
        die "Download failed: SKILL.md not found in downloaded content."
    fi

    # Extract project version from CHANGELOG.md
    SKILL_VERSION=""
    CHANGELOG_FILE="$(dirname "$SKILL_SOURCE")/CHANGELOG.md"
    if [ -f "$CHANGELOG_FILE" ]; then
        SKILL_VERSION=$(grep -m1 '## \[' "$CHANGELOG_FILE" | sed 's/## \[\(.*\)\].*/\1/')
    fi

    success "Downloaded successfully"
}

download_via_curl() {
    if ! command -v curl >/dev/null 2>&1; then
        die "Neither git nor curl found. Please install one of them."
    fi

    curl -fsSL "$TARBALL_URL" -o "$TEMP_DIR/repo.tar.gz" || \
        die "Failed to download from $TARBALL_URL"

    tar -xzf "$TEMP_DIR/repo.tar.gz" -C "$TEMP_DIR" || \
        die "Failed to extract downloaded archive."

    # GitHub tarballs extract to {repo}-{branch}/
    EXTRACTED_DIR=""
    for dir in "$TEMP_DIR"/universal-skills-manager-*; do
        if [ -d "$dir" ]; then
            EXTRACTED_DIR="$dir"
            break
        fi
    done

    if [ -z "$EXTRACTED_DIR" ]; then
        die "Could not find extracted repository directory."
    fi

    SKILL_SOURCE="$EXTRACTED_DIR/$SKILL_FOLDER"
}

# =============================================================================
# Install to Each Tool
# =============================================================================

INSTALLED_COUNT=0
FAILED_COUNT=0

install_to_tools() {
    echo ""
    info "Installing Universal Skills Manager..."
    echo ""

    OLD_IFS="$IFS"
    IFS='
'
    for entry in $DETECTED_TOOLS; do
        [ -z "$entry" ] && continue
        tool_name=$(echo "$entry" | cut -d'|' -f1)
        skills_dir=$(echo "$entry" | cut -d'|' -f2)
        dest_dir="${skills_dir}/${SKILL_FOLDER}"

        # Create skills directory if needed
        mkdir -p "$skills_dir" 2>/dev/null || true

        # Check if user already has a config.json (contains API key) before we move anything
        has_existing_config=false
        if [ -f "${dest_dir}/config.json" ]; then
            has_existing_config=true
        fi

        # Atomic install: backup existing, copy new, restore on failure
        if [ -d "$dest_dir" ]; then
            rm -rf "${dest_dir}.bak" 2>/dev/null || true
            mv "$dest_dir" "${dest_dir}.bak"
        fi

        if cp -r "$SKILL_SOURCE" "$dest_dir" 2>/dev/null; then
            # Restore user's config.json so their API key isn't overwritten by the empty template
            if [ "$has_existing_config" = true ] && [ -f "${dest_dir}.bak/config.json" ]; then
                cp "${dest_dir}.bak/config.json" "${dest_dir}/config.json"
            fi
            success "Installed to $tool_name: $dest_dir"
            INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
            # Remove backup on success
            rm -rf "${dest_dir}.bak" 2>/dev/null || true
        else
            error "Failed to install to $tool_name: $dest_dir"
            # Restore backup on failure
            if [ -d "${dest_dir}.bak" ]; then
                mv "${dest_dir}.bak" "$dest_dir"
                warn "Restored previous version for $tool_name"
            fi
            FAILED_COUNT=$((FAILED_COUNT + 1))
        fi
    done
    IFS="$OLD_IFS"
}

# =============================================================================
# API Key Setup
# =============================================================================

check_api_key() {
    echo ""

    if [ -n "${SKILLSMP_API_KEY:-}" ]; then
        success "SKILLSMP_API_KEY is already set"
        return
    fi

    warn "SKILLSMP_API_KEY is not set."
    info "A SkillsMP API key enables curated search with AI semantic matching."
    info "Without it, you can still search SkillHub and ClawHub — no key needed."
    echo ""

    # Skip prompt if no terminal available for user input
    if ! (exec </dev/tty) 2>/dev/null; then
        info "Non-interactive mode: skipping API key setup."
        info "Set it later: export SKILLSMP_API_KEY=\"your_key\""
        return
    fi

    printf "  Would you like to set it up now? [y/N]: "
    read -r response </dev/tty

    if [ "$response" = "y" ] || [ "$response" = "Y" ]; then
        printf "  Enter your SkillsMP API key: "
        read -r api_key </dev/tty

        if [ -z "$api_key" ]; then
            warn "No key entered. Skipping API key setup."
            info "You can set it later: export SKILLSMP_API_KEY=\"your_key\""
            return
        fi

        # Validate key prefix
        case "$api_key" in
            sk_live_skillsmp_*)
                ;;
            *)
                error "Invalid API key format. SkillsMP keys start with 'sk_live_skillsmp_'"
                info "Get your key at: https://skillsmp.com"
                return
                ;;
        esac

        # Detect shell config file
        if [ -f "$HOME/.zshrc" ]; then
            SHELL_RC="$HOME/.zshrc"
        elif [ -f "$HOME/.bashrc" ]; then
            SHELL_RC="$HOME/.bashrc"
        else
            SHELL_RC="$HOME/.profile"
        fi

        printf "\n# SkillsMP API Key (added by Universal Skills Manager installer)\n" >> "$SHELL_RC"
        printf "export SKILLSMP_API_KEY=\"%s\"\n" "$api_key" >> "$SHELL_RC"

        success "API key added to $SHELL_RC"

        # Also write to config.json in each installed location for immediate availability
        # (env var won't be active until terminal restart, but config.json works right away)
        OLD_IFS="$IFS"
        IFS='
'
        for entry in $DETECTED_TOOLS; do
            [ -z "$entry" ] && continue
            skills_dir=$(echo "$entry" | cut -d'|' -f2)
            config_file="${skills_dir}/${SKILL_FOLDER}/config.json"
            if [ -d "${skills_dir}/${SKILL_FOLDER}" ]; then
                printf '{\n  "skillsmp_api_key": "%s"\n}\n' "$api_key" > "$config_file"
            fi
        done
        IFS="$OLD_IFS"

        success "API key saved to config.json in all installed locations"
        info "Run 'source $SHELL_RC' or restart your terminal to activate the env variable."
        info "The key is also available immediately via config.json (no restart needed)."
    else
        info "You can set it later:"
        info "  export SKILLSMP_API_KEY=\"your_key\""
        info "  Add to ~/.zshrc or ~/.bashrc for persistence."
        info "  Note: SkillHub and ClawHub search work without a key."
    fi
}

# =============================================================================
# Summary
# =============================================================================

show_summary() {
    echo ""
    echo "${BOLD}========================================${RESET}"
    if [ -n "$SKILL_VERSION" ]; then
        echo "${BOLD}  Installation Complete! (v${SKILL_VERSION})${RESET}"
    else
        echo "${BOLD}  Installation Complete!${RESET}"
    fi
    echo "${BOLD}========================================${RESET}"
    echo ""
    printf "  Installed to: %s%d%s tool(s)\n" "$GREEN" "$INSTALLED_COUNT" "$RESET"
    if [ "$FAILED_COUNT" -gt 0 ]; then
        printf "  Failed:       %s%d%s tool(s)\n" "$RED" "$FAILED_COUNT" "$RESET"
    fi
    echo ""
    echo "  ${BOLD}Next steps:${RESET}"
    echo "  1. Restart your AI coding tool to pick up the new skill"
    echo "  2. Try: \"Search for a debugging skill\""
    echo "  3. Or:  \"Show my skill report\""
    echo ""
    if [ -z "${SKILLSMP_API_KEY:-}" ]; then
        echo "  ${YELLOW}Tip:${RESET} Set SKILLSMP_API_KEY for curated SkillsMP search (optional)."
        echo "  Get one at: https://skillsmp.com"
        echo "  SkillHub and ClawHub search work without a key."
        echo ""
    fi
    echo "  Docs: https://github.com/jacob-bd/universal-skills-manager"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    setup_colors
    parse_args "$@"

    if [ "$SHOW_HELP" = true ]; then
        show_help
        exit 0
    fi

    echo ""
    echo "${BOLD}Universal Skills Manager - Installer${RESET}"
    echo ""

    check_python
    detect_tools
    filter_tools
    download_repo
    install_to_tools
    check_api_key
    show_summary
}

main "$@"
