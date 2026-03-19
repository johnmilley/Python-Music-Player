#!/bin/bash
# Install lp desktop entry and icon for Linux
# Run after building with PyInstaller

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ICON_SRC="$SCRIPT_DIR/icon.png"

# Install icon to standard locations
for size in 64 128 256; do
    ICON_DIR="$HOME/.local/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$ICON_DIR"
    cp "$ICON_SRC" "$ICON_DIR/lp.png"
done

# Install desktop entry
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

# Find the executable
if [ -f "$SCRIPT_DIR/dist/lp/lp" ]; then
    EXEC_PATH="$SCRIPT_DIR/dist/lp/lp"
else
    EXEC_PATH="$(which lp 2>/dev/null || echo "$SCRIPT_DIR/dist/lp/lp")"
fi

sed "s|Exec=lp|Exec=$EXEC_PATH|" "$SCRIPT_DIR/lp.desktop" > "$DESKTOP_DIR/lp.desktop"

# Update icon cache
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Installed: $DESKTOP_DIR/lp.desktop"
echo "Icon installed to ~/.local/share/icons/hicolor/"
echo "You may need to log out and back in for the icon to appear everywhere."
