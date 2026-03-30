#!/bin/bash
# setup.sh — One-command setup for sts2-tui
#
# Usage:
#   ./setup.sh                    # auto-detect Steam path
#   ./setup.sh /path/to/game      # manual Steam game directory

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPS_DIR="$REPO_DIR/deps"
STS2_CLI_DIR="$DEPS_DIR/sts2-cli"

echo "=== sts2-tui setup ==="

# ── Step 1: Clone sts2-cli into deps/ ──

mkdir -p "$DEPS_DIR"

if [ -d "$STS2_CLI_DIR" ]; then
    echo "sts2-cli already cloned, pulling latest..."
    cd "$STS2_CLI_DIR" && git pull --ff-only 2>/dev/null || true
    cd "$REPO_DIR"
else
    echo "Cloning sts2-cli..."
    git clone https://github.com/keyunjie96/sts2-cli.git "$STS2_CLI_DIR"
fi

# ── Step 2: Build sts2-cli ──

echo "Building sts2-cli..."
cd "$STS2_CLI_DIR"

if [ ! -f "lib/sts2.dll" ]; then
    if [ -n "$1" ]; then
        ./setup.sh "$1"
    else
        ./setup.sh
    fi
else
    dotnet build src/Sts2Headless/Sts2Headless.csproj
fi

cd "$REPO_DIR"

# ── Step 3: Install sts2-tui ──

echo "Installing sts2-tui..."
pip3 install -e .

echo ""
echo "=== Ready! ==="
echo ""
echo "  python -m sts2_tui.tui              # play"
echo "  python -m sts2_tui.tui --lang zh    # Chinese mode"
