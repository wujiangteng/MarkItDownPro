#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$ROOT_DIR/../.." && pwd)"
APP_NAME="MarkItDownPro"
PRODUCT_NAME="MarkItDownProApp"
BUILD_DIR="$ROOT_DIR/.build/release"
APP_DIR="$ROOT_DIR/.build/$APP_NAME.app"
ICON_FILE="$ROOT_DIR/Resources/AppIcon.icns"
RUNTIME_DIR="$APP_DIR/Contents/Resources/runtime"
PYTHON_DIR="$APP_DIR/Contents/Resources/python"

cd "$ROOT_DIR"
swift build -c release

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

cp "$BUILD_DIR/$PRODUCT_NAME" "$APP_DIR/Contents/MacOS/$APP_NAME"
if [[ -f "$ICON_FILE" ]]; then
    cp "$ICON_FILE" "$APP_DIR/Contents/Resources/AppIcon.icns"
fi

PYTHON_LINK="$(readlink "$PROJECT_ROOT/.venv/bin/python")"
if [[ -z "$PYTHON_LINK" ]]; then
    echo "Cannot resolve $PROJECT_ROOT/.venv/bin/python" >&2
    exit 1
fi
PYTHON_ROOT="$(cd "$(dirname "$PYTHON_LINK")/.." && pwd)"

mkdir -p "$RUNTIME_DIR" "$PYTHON_DIR"
rsync -a --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$PROJECT_ROOT/.venv/" "$RUNTIME_DIR/.venv/"
rsync -a --delete "$PYTHON_ROOT/" "$PYTHON_DIR/"
rsync -a --delete "$PROJECT_ROOT/src/" "$RUNTIME_DIR/src/"
rsync -a --delete \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$PROJECT_ROOT/vendor/" "$RUNTIME_DIR/vendor/"
cp "$PROJECT_ROOT/pyproject.toml" "$PROJECT_ROOT/uv.lock" "$RUNTIME_DIR/"

cat > "$APP_DIR/Contents/MacOS/markitdownpro-cli" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

CONTENTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
RUNTIME_DIR="$RESOURCES_DIR/runtime"
PYTHON="$RESOURCES_DIR/python/bin/python3.12"
SITE_PACKAGES="$RUNTIME_DIR/.venv/lib/python3.12/site-packages"

export VIRTUAL_ENV="$RUNTIME_DIR/.venv"
export PATH="$RUNTIME_DIR/.venv/bin:$RESOURCES_DIR/python/bin:$PATH"
export PYTHONPATH="$RUNTIME_DIR/src:$RUNTIME_DIR/vendor/markitdown/src:$RUNTIME_DIR/vendor/pdf2zh:$RUNTIME_DIR/vendor/texteller:$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON" -m markitdownpro.cli "$@"
SCRIPT
chmod +x "$APP_DIR/Contents/MacOS/markitdownpro-cli"

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.markitdownpro.app</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

echo "$APP_DIR"
