#!/usr/bin/env bash
# update-agents.sh
#
# Updates the OrangIT agent system to the latest version from the template
# repo. Preserves any local agent customisations in .ai/agent/ by merging
# — new agents are added, existing ones are updated only if unchanged locally,
# and locally modified agents are left alone with a warning.
#
# Requirements: same as bootstrap-agents.sh (git >= 2.25, uv, SSH to github)
#
# Usage:
#   ./update-agents.sh                  # update from main branch
#   ./update-agents.sh --ref v1.2.0     # update to a specific tag or branch
#   ./update-agents.sh --force          # overwrite all local changes without prompting

set -euo pipefail

TEMPLATE_REPO="git@github.com:orangitfi/template.git"
TEMPLATE_REF="main"
AI_DIR=".ai"
TMP_DIR="$(mktemp -d)"
FORCE=false

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)    TEMPLATE_REF="$2"; shift 2 ;;
    --force)  FORCE=true; shift ;;
    --help|-h)
      sed -n '/^# /p' "$0" | sed 's/^# //'
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { echo "  [update] $*"; }
success() { echo "  [update] ✓ $*"; }
warn()    { echo "  [update] ! $*"; }
fail()    { echo "  [update] ✗ $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
[[ -d "$AI_DIR" ]] || fail ".ai/ not found. Run bootstrap-agents.sh first."

if ! command -v uv &>/dev/null; then
  fail "uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/"
fi

# ---------------------------------------------------------------------------
# Fetch latest .ai/ from template
# ---------------------------------------------------------------------------
info "Fetching latest .ai/ from $TEMPLATE_REPO (ref: $TEMPLATE_REF)..."

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
  git sparse-checkout set .ai
  git checkout
)

[[ -d "$TMP_DIR/template/.ai" ]] || \
  fail ".ai/ not found in template repo at ref '$TEMPLATE_REF'."

success "Fetched template"

# ---------------------------------------------------------------------------
# Merge agent YAML files — preserve local modifications
# ---------------------------------------------------------------------------
UPDATED=()
SKIPPED=()
ADDED=()

info "Merging agent definitions..."

for src_yaml in "$TMP_DIR/template/.ai/agent/"*.yaml; do
  name="$(basename "$src_yaml")"
  dst_yaml="$AI_DIR/agent/$name"

  if [[ ! -f "$dst_yaml" ]]; then
    # New agent in template — always add it
    cp "$src_yaml" "$dst_yaml"
    ADDED+=("$name")
  elif diff -q "$src_yaml" "$dst_yaml" &>/dev/null; then
    # Identical — nothing to do (already up to date)
    :
  else
    if [[ "$FORCE" == true ]]; then
      cp "$src_yaml" "$dst_yaml"
      UPDATED+=("$name")
    else
      # Check if local file differs from the previously installed version.
      # We use git to detect whether the local file has uncommitted changes.
      if git -C "$(pwd)" diff --quiet HEAD -- "$dst_yaml" 2>/dev/null; then
        # No local uncommitted changes — safe to update
        cp "$src_yaml" "$dst_yaml"
        UPDATED+=("$name")
      else
        # Local uncommitted changes — skip and warn
        SKIPPED+=("$name")
      fi
    fi
  fi
done

# ---------------------------------------------------------------------------
# Update non-agent files (templates, build tooling, scripts)
# — always overwrite, these are infrastructure not customised per-repo
# ---------------------------------------------------------------------------
info "Updating build tooling and templates..."

for dir in templates orangit_agents scripts; do
  rm -rf "$AI_DIR/$dir"
  cp -r "$TMP_DIR/template/.ai/$dir" "$AI_DIR/$dir"
done

cp "$TMP_DIR/template/.ai/pyproject.toml" "$AI_DIR/pyproject.toml"

# Remove stale venv — force a clean rebuild with the updated tooling
rm -rf "$AI_DIR/.venv" "$AI_DIR/uv.lock"

success "Build tooling updated"

# ---------------------------------------------------------------------------
# Regenerate platform files
# ---------------------------------------------------------------------------
info "Regenerating agent files..."
bash "$AI_DIR/scripts/generate-agents.sh"
success "Agent files regenerated"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "  Update complete (ref: $TEMPLATE_REF)"
echo ""

if [[ ${#ADDED[@]} -gt 0 ]]; then
  echo "  New agents added:"
  for f in "${ADDED[@]}"; do echo "    + $f"; done
  echo ""
fi

if [[ ${#UPDATED[@]} -gt 0 ]]; then
  echo "  Agents updated from template:"
  for f in "${UPDATED[@]}"; do echo "    ~ $f"; done
  echo ""
fi

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
  warn "Agents with local uncommitted changes — skipped (not overwritten):"
  for f in "${SKIPPED[@]}"; do echo "    ! $f"; done
  echo ""
  echo "  To overwrite local changes and take the template version:"
  echo "    ./update-agents.sh --force"
  echo ""
  echo "  To keep your changes and update the rest:"
  echo "    Commit or stash your changes first, then re-run ./update-agents.sh"
  echo ""
fi

echo "  Commit .ai/, .claude/agents/, .opencode/agent/, .github/agents/ to git."
echo ""
