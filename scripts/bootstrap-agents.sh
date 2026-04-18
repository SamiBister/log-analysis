#!/usr/bin/env bash
# bootstrap-agents.sh
#
# Installs the OrangIT agent system into this repository.
# Pulls .ai/ from the orangitfi/template repo using git sparse-checkout
# (no full clone), then generates platform-specific agent files for
# Claude Code, OpenCode, and GitHub Copilot.
#
# Requirements:
#   - git >= 2.25 (sparse-checkout support)
#   - uv  (https://docs.astral.sh/uv/getting-started/installation/)
#   - SSH access to github.com/orangitfi (git@github.com)
#
# Usage:
#   ./bootstrap-agents.sh                  # installs from main branch
#   ./bootstrap-agents.sh --ref v1.2.0     # installs a specific tag or branch

set -euo pipefail

TEMPLATE_REPO="git@github.com:orangitfi/template.git"
TEMPLATE_REF="main"
AI_DIR=".ai"
TMP_DIR="$(mktemp -d)"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      TEMPLATE_REF="$2"
      shift 2
      ;;
    --help|-h)
      sed -n '/^# /p' "$0" | sed 's/^# //'
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { echo "  [bootstrap] $*"; }
success() { echo "  [bootstrap] ✓ $*"; }
fail()    { echo "  [bootstrap] ✗ $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
info "Checking requirements..."

git_version=$(git --version 2>/dev/null | awk '{print $3}')
required_git="2.25.0"
if ! printf '%s\n%s\n' "$required_git" "$git_version" | sort -V -C 2>/dev/null; then
  fail "git >= 2.25 is required (found $git_version). sparse-checkout is not available."
fi

if ! command -v uv &>/dev/null; then
  fail "uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/"
fi

success "Requirements satisfied (git $git_version, uv $(uv --version 2>/dev/null | awk '{print $2}'))"

# ---------------------------------------------------------------------------
# Guard: warn if .ai/ already exists
# ---------------------------------------------------------------------------
if [[ -d "$AI_DIR" ]]; then
  echo ""
  echo "  WARNING: $AI_DIR already exists in this repository."
  echo "  Running bootstrap will overwrite it with the version from the template repo."
  echo "  Any local customisations in $AI_DIR will be lost."
  echo ""
  read -r -p "  Continue? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }
fi

# ---------------------------------------------------------------------------
# Sparse-checkout .ai/ from the template repo
# ---------------------------------------------------------------------------
info "Fetching .ai/ from $TEMPLATE_REPO (ref: $TEMPLATE_REF)..."

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

git clone \
  --no-checkout \
  --depth 1 \
  --branch "$TEMPLATE_REF" \
  --filter=blob:none \
  "$TEMPLATE_REPO" \
  "$TMP_DIR/template" 2>/dev/null

(
  cd "$TMP_DIR/template"
  git sparse-checkout init --cone
  git sparse-checkout set .ai scripts
  git checkout
)

if [[ ! -d "$TMP_DIR/template/.ai" ]]; then
  fail ".ai/ directory not found in the template repo at ref '$TEMPLATE_REF'."
fi

success "Fetched from template"

# ---------------------------------------------------------------------------
# Copy .ai/ into this repo
# ---------------------------------------------------------------------------
info "Installing .ai/ ..."

rm -rf "$AI_DIR"
cp -r "$TMP_DIR/template/.ai" "$AI_DIR"

# Remove any cached venv from the template — the consumer will build their own
rm -rf "$AI_DIR/.venv"

success "Installed .ai/"

# ---------------------------------------------------------------------------
# Copy update-agents.sh to the repo root
# ---------------------------------------------------------------------------
if [[ -f "$TMP_DIR/template/scripts/update-agents.sh" ]]; then
  cp "$TMP_DIR/template/scripts/update-agents.sh" ./update-agents.sh
  chmod +x ./update-agents.sh
  success "Installed update-agents.sh"
else
  info "update-agents.sh not found in template scripts/ — skipping"
fi

# ---------------------------------------------------------------------------
# Generate platform-specific agent files
# ---------------------------------------------------------------------------
info "Generating agent files for Claude Code, OpenCode, and GitHub Copilot..."

bash "$AI_DIR/scripts/generate-agents.sh"

success "Agent files generated"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "  Done. The following were created or updated:"
echo "    .ai/                 — agent source (YAML definitions, templates, build tooling)"
echo "    .claude/agents/      — Claude Code agent files"
echo "    .opencode/agent/     — OpenCode agent files"
echo "    .github/agents/      — GitHub Copilot agent files"
echo "    update-agents.sh     — run this to pull future updates"
echo ""
echo "  Edit agents:   .ai/agent/*.yaml"
echo "  Regenerate:    bash .ai/scripts/generate-agents.sh"
echo "  Update later:  ./update-agents.sh"
echo ""
echo "  Commit everything — .ai/, .claude/, .opencode/, .github/agents/,"
echo "  and update-agents.sh — to git."
echo ""
