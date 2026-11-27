#!/usr/bin/env bash
# publish.sh -- assembles the public GitHub release from the working tree.
#
# Creates or resets an orphan branch 'public', copies only the approved file set,
# scans for sensitive content, then pushes to the 'github' remote.
#
# Usage:
#   bash publish.sh           -- full publish
#   bash publish.sh --dry-run -- assemble and scan only, no push
#
# Requirements: git, gh (GitHub CLI, authenticated)
# Remote must be named 'github'. Run: git remote add github <url>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRANCH="public"
REMOTE="github"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

die() { echo "publish.sh: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Public file manifest -- edit this list to change what goes to GitHub.
# Paths are relative to repo root. Directories are copied recursively.
# ---------------------------------------------------------------------------
PUBLIC_PATHS=(
    src/architekton
    config
    scripts/install.sh
    scripts/uninstall.sh
    scripts/preflight.py
    skills/architekton
    src/mod
    docs/install.md
    docs/windows.md
    docs/troubleshooting.md
    docs/running.md
    docs/customizing.md
    docs/architecture.md
    tests
    README.md
    CHANGELOG.md
    LICENSE
    README_images
)

# ---------------------------------------------------------------------------
# 0. Sanity checks
# ---------------------------------------------------------------------------
cd "$REPO_ROOT"

[[ -n "$(git status --porcelain | grep -v '^?? ')" ]] && die "Working tree has uncommitted changes to tracked files. Commit or stash first."

git remote get-url "$REMOTE" >/dev/null 2>&1 || die "Remote '$REMOTE' not configured. Run: git remote add $REMOTE <url>"

# ---------------------------------------------------------------------------
# 1. Verify public paths exist in git
# ---------------------------------------------------------------------------
echo "=== Verifying public file set ==="
missing=0
for path in "${PUBLIC_PATHS[@]}"; do
    if ! git ls-files --error-unmatch "$path" >/dev/null 2>&1 && \
       ! git ls-tree -d HEAD "$path" >/dev/null 2>&1; then
        echo "  MISSING  $path (not tracked by git)" >&2
        missing=1
    else
        echo "  OK       $path"
    fi
done
[[ "$missing" == "1" ]] && die "One or more public paths are missing from git. Check manifest."

# ---------------------------------------------------------------------------
# 2. Assemble orphan branch using git archive (tracked files only)
# ---------------------------------------------------------------------------
echo "=== Assembling public branch ==="
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# git archive guarantees only committed, tracked files land in the publish --
# no git-ignored files (benchmark results, .venv, etc.) can slip through.
git archive HEAD -- "${PUBLIC_PATHS[@]}" | tar -x -C "$WORKDIR"

# ---------------------------------------------------------------------------
# 3. Content scan -- run on the assembled snapshot, not the live tree
# ---------------------------------------------------------------------------
echo "=== Content scan ==="
BLOCKLIST="$REPO_ROOT/.publish-blocklist"
scan_failed=0
if [[ -f "$BLOCKLIST" ]]; then
    while IFS= read -r pattern; do
        [[ -z "$pattern" || "$pattern" == \#* ]] && continue
        hits=$(grep -rIlE "$pattern" "$WORKDIR" 2>/dev/null || true)
        if [[ -n "$hits" ]]; then
            echo "  BLOCKED  pattern '$pattern' found in:" >&2
            while IFS= read -r hit; do
                echo "           ${hit#$WORKDIR/}" >&2
            done <<< "$hits"
            scan_failed=1
        fi
    done < "$BLOCKLIST"
else
    echo "  WARNING: .publish-blocklist not found -- skipping content scan" >&2
fi

if [[ "$scan_failed" == "1" ]]; then
    echo "" >&2
    echo "Publish blocked. Fix the content issues above before retrying." >&2
    exit 1
fi
echo "  OK       content scan passed"

# ---------------------------------------------------------------------------
# 4. Build the orphan branch
# ---------------------------------------------------------------------------
VERSION=""
if [[ -f "$REPO_ROOT/src/architekton/__init__.py" ]]; then
    VERSION=$(grep -m1 '__version__' "$REPO_ROOT/src/architekton/__init__.py" 2>/dev/null | sed "s/.*= *['\"]//;s/['\"].*//") || true
fi
[[ -z "$VERSION" ]] && VERSION="$(date +%Y-%m-%d)"

TMPGIT="$(mktemp -d)"
trap 'rm -rf "$WORKDIR" "$TMPGIT"' EXIT

git -C "$TMPGIT" init -q
git -C "$TMPGIT" checkout --orphan "$BRANCH"

# Copy assembled files into the temp git repo
cp -r "$WORKDIR"/. "$TMPGIT/"

git -C "$TMPGIT" add -A
git -C "$TMPGIT" commit -q -m "Release $VERSION"

echo "  built orphan branch '$BRANCH' ($(git -C "$TMPGIT" diff-tree --no-commit-id -r --name-only HEAD | wc -l | tr -d ' ') files)"

if [[ "$DRY_RUN" == "1" ]]; then
    echo ""
    echo "Dry run complete. No push performed."
    echo "Files that would be published:"
    git -C "$TMPGIT" diff-tree --no-commit-id -r --name-only HEAD | sed 's/^/  /'
    exit 0
fi

# ---------------------------------------------------------------------------
# 5. Push to public remote
# ---------------------------------------------------------------------------
echo "=== Pushing to $REMOTE ==="
REMOTE_URL="$(git remote get-url "$REMOTE")"
git -C "$TMPGIT" remote add origin "$REMOTE_URL"
git -C "$TMPGIT" push --force origin "$BRANCH:$BRANCH"

echo ""
echo "Published $VERSION to $REMOTE_URL (branch: $BRANCH)"
echo "If this is the default branch, set it on GitHub: Settings -> Branches -> Default branch -> $BRANCH"
