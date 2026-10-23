#!/usr/bin/env bash
# Helper script to sync the latest tested code to the public 'wrat-sniffer' repository
# while strictly excluding GEMINI.md and any private development notes.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_BRANCH="${1:-main}"

echo "[*] Syncing release from '$SOURCE_BRANCH' to public repository (wrat-sniffer)..."

# Ensure working directory is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "[-] Error: Working directory has uncommitted changes. Please commit or stash first." >&2
    exit 1
fi

# Switch to public-main
git checkout public-main

# Sync all files from SOURCE_BRANCH
git checkout "$SOURCE_BRANCH" -- .

# Strictly ensure GEMINI.md is removed
if [ -f "GEMINI.md" ]; then
    git rm -f GEMINI.md
fi

# Commit if there are changes
if [ -n "$(git status --porcelain)" ]; then
    VERSION=$(grep '__version__' stats_collector.py | head -n1 | cut -d'"' -f2)
    git commit -m "release: Sync v${VERSION} release to public distribution"
    echo "[+] Created public release commit for v${VERSION}"
fi

# Push to public remote
echo "[*] Pushing to public remote (wrat-sniffer)..."
git push public public-main:main

# Switch back to original branch
git checkout "$SOURCE_BRANCH"

echo "[✓] Public release sync complete!"
