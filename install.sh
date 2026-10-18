#!/usr/bin/env bash
# ==============================================================================
# PreviewGen - macOS & Linux Installer
# ==============================================================================
set -euo pipefail

REPO="Mustaqeem66/Freepik-Preview-Generator"
APP_NAME="PreviewGen"
OS="$(uname -s)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

echo ""
echo "Installing PreviewGen for $OS..."

get_release_info() {
  local tag="${PREVIEWGEN_VERSION:-}"
  if [ -n "$tag" ]; then
    echo "https://api.github.com/repos/$REPO/releases/tags/$tag"
  else
    echo "https://api.github.com/repos/$REPO/releases/latest"
  fi
}

API_URL="$(get_release_info)"
RELEASE_JSON="$TEMP_DIR/release.json"
curl -fsSL "$API_URL" -o "$RELEASE_JSON"

verify_checksum() {
  local file="$1"
  local sha_file="$TEMP_DIR/SHA256SUMS.txt"
  local sha_url
  sha_url="$(grep -o 'https://[^"]*SHA256SUMS.txt' "$RELEASE_JSON" | head -n 1)"
  if [ -n "$sha_url" ]; then
    curl -fsSL "$sha_url" -o "$sha_file"
    local expected
    expected="$(grep "$(basename "$file")" "$sha_file" | awk '{print $1}')"
    if [ -n "$expected" ]; then
      local actual
      actual="$(sha256sum "$file" 2>/dev/null | awk '{print $1}' || shasum -a 256 "$file" | awk '{print $1}')"
      if [ "$expected" != "$actual" ]; then
        echo "Checksum verification failed for $(basename "$file"). Aborting installation." >&2
        exit 1
      fi
      echo "Checksum verified for $(basename "$file")."
    fi
  fi
}

case "$OS" in
  Darwin*)
    DMG_URL="$(grep -o 'https://[^"]*PreviewGen-macOS.dmg' "$RELEASE_JSON" | head -n 1)"
    if [ -z "$DMG_URL" ]; then
      echo "Could not find macOS DMG in release. Aborting." >&2
      exit 1
    fi
    DMG_PATH="$TEMP_DIR/PreviewGen.dmg"
    curl -fL "$DMG_URL" -o "$DMG_PATH"
    verify_checksum "$DMG_PATH"

    MOUNT_DIR="$TEMP_DIR/mount"
    mkdir -p "$MOUNT_DIR"
    hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_DIR" -nobrowse -quiet
    trap 'hdiutil detach "$MOUNT_DIR" -quiet 2>/dev/null || true; rm -rf "$TEMP_DIR"' EXIT

    SRC_APP="$MOUNT_DIR/$APP_NAME.app"
    if [ -d "$SRC_APP" ]; then
      rm -rf "/Applications/$APP_NAME.app"
      cp -R "$SRC_APP" "/Applications/"
      echo "PreviewGen installed to /Applications/$APP_NAME.app"
    else
      echo "Could not find $APP_NAME.app inside the disk image." >&2
      exit 1
    fi
    ;;

  Linux*)
    APPIMAGE_URL="$(grep -o 'https://[^"]*PreviewGen-Linux.AppImage' "$RELEASE_JSON" | head -n 1)"
    if [ -z "$APPIMAGE_URL" ]; then
      echo "Could not find Linux AppImage in release. Aborting." >&2
      exit 1
    fi
    BIN_DIR="$HOME/.local/bin"
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$BIN_DIR" "$APPS_DIR"
    TARGET_BIN="$BIN_DIR/previewgen"
    curl -fL "$APPIMAGE_URL" -o "$TARGET_BIN"
    verify_checksum "$TARGET_BIN"
    chmod +x "$TARGET_BIN"

    cat > "$APPS_DIR/previewgen.desktop" << EOF
[Desktop Entry]
Name=PreviewGen
GenericName=Preview Generator
Comment=Turn transparent cutouts and 3D files into marketplace JPG previews
Exec=$TARGET_BIN
Terminal=false
Type=Application
Categories=Graphics;
EOF
    chmod +x "$APPS_DIR/previewgen.desktop"
    echo "PreviewGen installed to $TARGET_BIN"
    ;;

  *)
    echo "Unsupported operating system: $OS" >&2
    exit 1
    ;;
esac
