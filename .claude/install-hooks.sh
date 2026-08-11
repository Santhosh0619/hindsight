#!/usr/bin/env bash
# Run after every fresh clone: bash .claude/install-hooks.sh
set -euo pipefail
REPO_ROOT=$(git rev-parse --show-toplevel)
cp "$REPO_ROOT/.claude/hooks/pre-commit"  "$REPO_ROOT/.git/hooks/pre-commit"
cp "$REPO_ROOT/.claude/hooks/pre-push"    "$REPO_ROOT/.git/hooks/pre-push"
cp "$REPO_ROOT/.claude/hooks/commit-msg"  "$REPO_ROOT/.git/hooks/commit-msg"
chmod +x "$REPO_ROOT/.git/hooks/pre-commit" \
         "$REPO_ROOT/.git/hooks/pre-push" \
         "$REPO_ROOT/.git/hooks/commit-msg"
echo "✓ Git hooks installed from .claude/hooks/"
