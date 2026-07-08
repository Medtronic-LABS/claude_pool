#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="${CLAUDES_BASE:-$HOME/.claudes}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found on PATH." >&2
    exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
    echo "Warning: the 'claude' CLI was not found on PATH." >&2
    echo "Install/log in to Claude Code before using 'claudes launch|switch|usage|best'." >&2
fi

echo "Running installer: python3 $SCRIPT_DIR/claudes.py install"
python3 "$SCRIPT_DIR/claudes.py" install

if command -v claudes >/dev/null 2>&1; then
    echo
    echo "'claudes' is on PATH: $(command -v claudes)"
else
    echo
    echo "'claudes' isn't on PATH yet (likely /usr/local/bin isn't writable without sudo)."
    echo "Setting up a no-sudo fallback..."

    mkdir -p "$HOME/bin"
    ln -sf "$BASE_DIR/claudes" "$HOME/bin/claudes"
    echo "Linked: $HOME/bin/claudes -> $BASE_DIR/claudes"

    case "${SHELL:-}" in
        */zsh) RC_FILE="$HOME/.zshrc" ;;
        */bash) RC_FILE="$HOME/.bash_profile" ;;
        *) RC_FILE="$HOME/.profile" ;;
    esac

    PATH_LINE="export PATH=\"\$HOME/bin:\$HOME/.claudes:\$PATH\""
    if [ ! -f "$RC_FILE" ] || ! grep -qF "$PATH_LINE" "$RC_FILE"; then
        {
            echo ""
            echo "$PATH_LINE"
        } >> "$RC_FILE"
        echo "Added PATH entry to $RC_FILE"
    fi

    echo
    echo "Restart your terminal (or run: source $RC_FILE), then 'claudes' will be available."
fi

echo
echo "Base directory : $BASE_DIR"
echo "Next steps:"
echo "    claudes list"
echo "    claudes add <name>"
