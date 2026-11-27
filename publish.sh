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
# 1. Content scan -- abort if any blocklist pattern fires in the public files
# ---------------------------------------------------------------------------
echo "=== Content scan ==="
BLOCKLIST="$REPO_ROOT/.publish-blocklist"
scan_failed=0
if [[ -f "$BLOCKLIST" ]]; then
    while IFS= read -r pattern; do
        [[ -z "$pattern" || "$pattern" == \#* ]] && continue
        for path in "${PUBLIC_PATHS[@]}"; do
            full="$REPO_ROOT/$path"
            [[ -e "$full" ]] || continue
            hits=$(grep -rIlE "$pattern" "$full" 2>/dev/null || true)
            if [[ -n "$hits" ]]; then
                echo "  BLOCKED  pattern '$pattern' found in:" >&2
                while IFS= read -r hit; do
                    echo "           $hit" >&2
                done <<< "$hits"
                scan_failed=1
            fi
        done
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
# 2. Verify public paths exist
# ---------------------------------------------------------------------------
echo "=== Verifying public file set ==="
missing=0
for path in "${PUBLIC_PATHS[@]}"; do
    if [[ ! -e "$REPO_ROOT/$path" ]]; then
        echo "  MISSING  $path" >&2
        missing=1
    else
        echo "  OK       $path"
    fi
done
[[ "$missing" == "1" ]] && die "One or more public paths are missing. Check manifest."

# ---------------------------------------------------------------------------
# 3. Assemble orphan branch in a temp directory
# ---------------------------------------------------------------------------
echo "=== Assembling public branch ==="
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

for path in "${PUBLIC_PATHS[@]}"; do
    src="$REPO_ROOT/$path"
    [[ -e "$src" ]] || continue
    dest="$WORKDIR/$path"
    mkdir -p "$(dirname "$dest")"
    cp -r "$src" "$dest"
done

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
