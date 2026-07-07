#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$ROOT_DIR/../.." && pwd)"
APP_NAME="MarkItDownPro"
PRODUCT_NAME="MarkItDownProApp"
BUILD_DIR="$ROOT_DIR/.build/release"
APP_DIR="$ROOT_DIR/.build/$APP_NAME.app"
ICON_FILE="$ROOT_DIR/Resources/AppIcon.icns"
APP_VENV_DIR="$ROOT_DIR/.build/app-venv"
RUNTIME_DIR="$APP_DIR/Contents/Resources/runtime"
PYTHON_DIR="$APP_DIR/Contents/Resources/python"

prune_python_tree() {
    local target="$1"

    find "$target" -type d -name '__pycache__' -prune -exec rm -rf {} +
    find "$target" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
    find "$target" -type d \( \
        -iname 'test' -o \
        -iname 'tests' -o \
        -iname 'testing' -o \
        -iname 'doc' -o \
        -iname 'docs' -o \
        -iname 'example' -o \
        -iname 'examples' \
    \) -prune -exec rm -rf {} +
}

prune_venv_bin() {
    local bin_dir="$1/bin"
    local name

    [[ -d "$bin_dir" ]] || return 0
    for path in "$bin_dir"/*; do
        [[ -e "$path" ]] || continue
        name="$(basename "$path")"
        case "$name" in
            python|python3|python3.12|markitdownpro|pdf2zh|texteller|rapidocr_onnxruntime|pymupdf)
                ;;
            *)
                rm -f "$path"
                ;;
        esac
    done
}

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

rm -rf "$APP_VENV_DIR"
rsync -a --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$PROJECT_ROOT/.venv/" "$APP_VENV_DIR/"
prune_python_tree "$APP_VENV_DIR"
prune_venv_bin "$APP_VENV_DIR"

mkdir -p "$RUNTIME_DIR" "$PYTHON_DIR"
rsync -a --delete "$APP_VENV_DIR/" "$RUNTIME_DIR/.venv/"
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
