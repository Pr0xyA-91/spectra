#!/usr/bin/env bash
# Helper script to sync the latest tested code to the public 'spectra' repository
# while strictly excluding GEMINI.md and any private development notes.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_BRANCH="${1:-main}"

echo "[*] Syncing release from '$SOURCE_BRANCH' to public repository (spectra)..."

# Ensure working directory is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "[-] Error: Working directory has uncommitted changes. Please commit or stash first." >&2
    exit 1
fi

# Switch to public-main
git checkout public-main

# Sync all files from SOURCE_BRANCH
git checkout "$SOURCE_BRANCH" -- .

# Remove any tracked files on public-main that were deleted in SOURCE_BRANCH
for f in $(git ls-files); do
    if ! git cat-file -e "${SOURCE_BRANCH}:${f}" 2>/dev/null; then
        git rm -f "$f" >/dev/null 2>&1 || true
    fi
done

# Strictly ensure private notes and guidelines are removed
if [ -f "GEMINI.md" ]; then
    git rm -f GEMINI.md
fi
if [ -f "SESSION_NOTES.md" ]; then
    git rm -f SESSION_NOTES.md
fi

# Scrub hardcoded user home directories for public portability
for desktop_file in *.desktop; do
    if [ -f "$desktop_file" ]; then
        sed -i 's|Exec=/home/[^/]*/Projects/[^/]*/run.sh|Exec=bash -c '"'"'"$(dirname "%k")"/run.sh'"'"'|g' "$desktop_file"
        sed -i 's|Icon=/home/[^/]*/Projects/[^/]*/icon.png|Icon=utilities-system-monitor|g' "$desktop_file"
        git add "$desktop_file"
    fi
done

# Verify no private files or hardcoded home paths remain in tracked files
if git ls-files | grep -q -E "^(GEMINI|SESSION_NOTES)\.md$"; then
    echo "[-] Error: Private markdown files are still tracked on public-main!" >&2
    exit 1
fi
if git grep -q "/home/a91" -- ':!publish_release.sh'; then
    echo "[-] Error: Hardcoded /home/a91 path detected in tracked files on public-main!" >&2
    exit 1
fi

# Commit if there are changes
if [ -n "$(git status --porcelain)" ]; then
    VERSION=$(grep '__version__' stats_collector.py | head -n1 | cut -d'"' -f2)
    MSG="${2:-release: Sync v${VERSION} release to public distribution}"
    git commit -m "$MSG"
    echo "[+] Created public release commit: $MSG"
fi

# Push to public remote
echo "[*] Pushing to public remote (spectra)..."
git push public public-main:main

# Switch back to original branch
git checkout "$SOURCE_BRANCH"

echo "[✓] Public release sync complete!"
