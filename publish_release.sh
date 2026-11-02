#!/usr/bin/env bash
# SPECTRA Universal Release Publisher
# Synchronizes verified code and developer diagnostic tools to the public repository
# (https://github.com/Pr0xyA-91/spectra.git) while strictly removing private agent/co-worker files.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Detect active branch if not specified
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
TARGET_MODE="${1:-$CURRENT_BRANCH}"

publish_branch() {
    local SRC_BRANCH="$1"
    local PUB_BRANCH=""
    local REMOTE_TARGET=""
    local EDITION_LABEL=""

    if [ "$SRC_BRANCH" = "windows" ]; then
        PUB_BRANCH="public-windows"
        REMOTE_TARGET="windows"
        EDITION_LABEL="Windows Multi-Manufacturer & Rust Hybrid"
    else
        SRC_BRANCH="main"
        PUB_BRANCH="public-main"
        REMOTE_TARGET="main"
        EDITION_LABEL="Linux Multi-Manufacturer & Rust Hybrid"
    fi

    echo "================================================================================"
    echo "[*] Publishing '$SRC_BRANCH' -> public '$REMOTE_TARGET' ($PUB_BRANCH)"
    echo "================================================================================"

    # Ensure working tree is clean
    if [ -n "$(git status --porcelain)" ]; then
        echo "[-] Error: Working directory has uncommitted changes. Please commit first." >&2
        exit 1
    fi

    # Ensure remote 'public' exists
    if ! git remote | grep -q "^public$"; then
        echo "[*] Adding remote 'public' (https://github.com/Pr0xyA-91/spectra.git)..."
        git remote add public https://github.com/Pr0xyA-91/spectra.git
    fi
    git fetch public

    # Switch to or create local public release branch
    if git rev-parse --verify "$PUB_BRANCH" >/dev/null 2>&1; then
        git checkout "$PUB_BRANCH"
    elif git rev-parse --verify "public/$REMOTE_TARGET" >/dev/null 2>&1; then
        git checkout -b "$PUB_BRANCH" "public/$REMOTE_TARGET"
    else
        git checkout -b "$PUB_BRANCH"
    fi

    # Reset working tree to match source branch
    git checkout "$SRC_BRANCH" -- .

    # Remove files that existed on public branch but were deleted in source branch
    for f in $(git ls-files); do
        if ! git cat-file -e "${SRC_BRANCH}:${f}" 2>/dev/null; then
            git rm -f "$f" >/dev/null 2>&1 || true
        fi
    done

    # Strictly remove private agent/coworker files
    PRIVATE_ITEMS=(
        "GEMINI.md"
        "SESSION_NOTES.md"
        "COWORKER_CONTEXT.md"
        "SPECTRA_AGY_GUIDE.md"
        "learning_proposal.md"
        ".agents"
        "publish_release.sh"
    )

    for item in "${PRIVATE_ITEMS[@]}"; do
        if [ -e "$item" ]; then
            rm -rf "$item"
            git rm -rf "$item" >/dev/null 2>&1 || true
        fi
    done

    # Windows specific: force-add native installer executables if present
    if [ "$SRC_BRANCH" = "windows" ]; then
        if [ -d "dist" ]; then
            git add -f dist/*.exe >/dev/null 2>&1 || true
        fi
        if [ -d "bin" ]; then
            git add -f bin/*.exe >/dev/null 2>&1 || true
        fi
    fi

    # Scrub desktop launcher paths for public portability
    for desktop_file in *.desktop; do
        if [ -f "$desktop_file" ]; then
            sed -i 's|Exec=/home/[^/]*/Projects/[^/]*/run.sh|Exec=bash -c '"'"'"$(dirname "%k")"/run.sh'"'"'|g' "$desktop_file"
            sed -i 's|Icon=/home/[^/]*/Projects/[^/]*/icon.png|Icon=utilities-system-monitor|g' "$desktop_file"
            git add "$desktop_file"
        fi
    done

    # Security Verification: Ensure NO private files remain tracked
    if git ls-files | grep -q -E "^(GEMINI|SESSION_NOTES|COWORKER_CONTEXT|SPECTRA_AGY_GUIDE)\.md$|^\.agents/|^publish_release\.sh$"; then
        echo "[-] Security Check FAILED: Private agent files are still tracked on $PUB_BRANCH!" >&2
        git ls-files | grep -E "^(GEMINI|SESSION_NOTES|COWORKER_CONTEXT|SPECTRA_AGY_GUIDE)\.md$|^\.agents/|^publish_release\.sh$"
        git checkout -f "$SRC_BRANCH"
        exit 1
    fi

    if git grep -q "/home/a91" 2>/dev/null; then
        echo "[-] Security Check FAILED: Hardcoded /home/a91 path detected on $PUB_BRANCH!" >&2
        git checkout -f "$SRC_BRANCH"
        exit 1
    fi

    # Completeness Verification: Ensure developer and diagnostic tools ARE included
    DEV_TOOLS=(
        "memory_mapper.py"
        "spectra_probe.py"
        "contrib/dump_machine_spec.py"
        "docs/JURA_MEMORY_MAP.md"
        "crates/spectra-core/src/lib.rs"
        "drivers/jura/driver.py"
        "drivers/nivona/driver.py"
        "drivers/lamanti_kl/driver.py"
        "drivers/lamanti_jn/driver.py"
    )

    for tool in "${DEV_TOOLS[@]}"; do
        if [ ! -e "$tool" ]; then
            echo "[-] Tool Verification FAILED: $tool is missing from $PUB_BRANCH!" >&2
            git checkout -f "$SRC_BRANCH"
            exit 1
        fi
    done

    # Commit release if working tree has changes
    git add -A
    if [ -n "$(git status --porcelain)" ]; then
        BUILD=$(grep '__build__' version.py 2>/dev/null | head -n1 | cut -d'"' -f2 || echo "")
        if [ -n "$BUILD" ]; then
            MSG="release: Sync Build ${BUILD} (${EDITION_LABEL}) to public distribution"
        else
            MSG="release: Sync release (${EDITION_LABEL}) to public distribution"
        fi
        git commit -m "$MSG"
        echo "[+] Created public release commit on $PUB_BRANCH: $MSG"
    else
        echo "[*] No changes to commit on $PUB_BRANCH (already up to date)."
    fi

    # Push to public remote
    echo "[*] Pushing $PUB_BRANCH -> public $REMOTE_TARGET..."
    if [ "$SRC_BRANCH" = "windows" ]; then
        git push public "${PUB_BRANCH}:${REMOTE_TARGET}" --force
    else
        git push public "${PUB_BRANCH}:${REMOTE_TARGET}"
    fi

    # Return to source branch cleanly
    git checkout "$SRC_BRANCH"
    echo "[✓] Successfully published '$SRC_BRANCH' to public '$REMOTE_TARGET'!"
}

# Execute requested mode
if [ "$TARGET_MODE" = "all" ] || [ "$TARGET_MODE" = "--all" ]; then
    # Publish Linux from spectra
    publish_branch "main"

    # Publish Windows from spectra-win if present
    WIN_DIR="$SCRIPT_DIR/../spectra-win"
    if [ -d "$WIN_DIR" ]; then
        echo ""
        echo "[*] Executing Windows release from $WIN_DIR..."
        (cd "$WIN_DIR" && ./publish_release.sh windows)
    else
        echo "[!] Warning: $WIN_DIR not found, skipping windows release."
    fi
else
    publish_branch "$TARGET_MODE"
fi

echo ""
echo "================================================================================"
echo "[✓] Public synchronization complete!"
echo "================================================================================"
