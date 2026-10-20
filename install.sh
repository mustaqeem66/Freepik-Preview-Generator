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

hash_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    # macOS ships shasum; keep this branch independent of awk's exit status so a
    # missing sha256sum can never be masked by the pipeline succeeding.
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | awk '{print $NF}'
  else
    return 1
  fi
}

verify_checksum() {
  local file="$1"
  local name
  name="$(basename "$file")"
  local sha_file="$TEMP_DIR/SHA256SUMS.txt"
  local sha_url
  sha_url="$(grep -o 'https://[^"]*SHA256SUMS.txt' "$RELEASE_JSON" | head -n 1)"
  if [ -z "$sha_url" ]; then
    echo "The selected release publishes no SHA256SUMS.txt; refusing an unverified install." >&2
    exit 1
  fi
  if ! curl -fsSL "$sha_url" -o "$sha_file"; then
    echo "Could not download SHA256SUMS.txt. Aborting installation." >&2
    exit 1
  fi
  local expected
  expected="$(awk -v n="$name" '$2 == n || $2 == "*" n {print $1; exit}' "$sha_file")"
  if [ -z "$expected" ]; then
    echo "No SHA-256 entry for $name in SHA256SUMS.txt. Aborting installation." >&2
    exit 1
  fi
  local actual
  if ! actual="$(hash_sha256 "$file")" || [ -z "$actual" ]; then
    echo "No SHA-256 tool available (sha256sum/shasum/openssl). Aborting installation." >&2
    exit 1
  fi
  expected="$(printf '%s' "$expected" | tr '[:upper:]' '[:lower:]')"
  actual="$(printf '%s' "$actual" | tr '[:upper:]' '[:lower:]')"
  if [ "$expected" != "$actual" ]; then
    echo "Checksum verification failed for $name. Aborting installation." >&2
    exit 1
  fi
  echo "Checksum verified for $name."
}

case "$OS" in
  Darwin*)
    DMG_URL="$(grep -o 'https://[^"]*PreviewGen-macOS.dmg' "$RELEASE_JSON" | head -n 1)"
    if [ -z "$DMG_URL" ]; then
      echo "Could not find macOS DMG in release. Aborting." >&2
      exit 1
    fi
    DMG_PATH="$TEMP_DIR/PreviewGen-macOS.dmg"
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
      # Quarantine is a security decision, so it is never stripped silently:
      # the user makes that choice, once, in Finder.
      mkdir -p "$HOME/Desktop"
      ln -sfn "/Applications/$APP_NAME.app" "$HOME/Desktop/$APP_NAME.app" 2>/dev/null || true
      echo "PreviewGen installed to /Applications/$APP_NAME.app"
      echo "If macOS blocks the first launch, open it once via right-click > Open in Finder."
      if [ -z "${PREVIEWGEN_NO_LAUNCH:-}" ]; then
        open "/Applications/$APP_NAME.app" || true
      fi
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
    APPIMAGE_PATH="$TEMP_DIR/PreviewGen-Linux.AppImage"
    curl -fL "$APPIMAGE_URL" -o "$APPIMAGE_PATH"
    verify_checksum "$APPIMAGE_PATH"
    # Only replace an existing installation after verification succeeds.
    install -m 755 "$APPIMAGE_PATH" "$TARGET_BIN"

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

    # Desktop shortcut (best effort: Desktop may not exist on servers).
    if [ -d "$HOME/Desktop" ]; then
      cp "$APPS_DIR/previewgen.desktop" "$HOME/Desktop/previewgen.desktop"
      chmod +x "$HOME/Desktop/previewgen.desktop"
      gio set "$HOME/Desktop/previewgen.desktop" metadata::trusted true 2>/dev/null || true
    fi

    cat > "$BIN_DIR/previewgen-uninstall" << EOF
#!/usr/bin/env bash
set -eu
rm -f "$TARGET_BIN" "$BIN_DIR/previewgen-uninstall" "$APPS_DIR/previewgen.desktop" "\$HOME/Desktop/previewgen.desktop"
echo "PreviewGen has been uninstalled."
EOF
    chmod +x "$BIN_DIR/previewgen-uninstall"

    echo "PreviewGen installed to $TARGET_BIN"
    if [ -z "${PREVIEWGEN_NO_LAUNCH:-}" ]; then
      nohup "$TARGET_BIN" >/dev/null 2>&1 &
    fi
    ;;

  *)
    echo "Unsupported operating system: $OS" >&2
    exit 1
    ;;
esac
