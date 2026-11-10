#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "=== Launching Semantic YT Studio ==="

# Prefer Python 3.13 (since python-tk@3.13 is installed) then 3.12, 3.11, python3
PYTHON_CMD=""
for candidate in python3.13 /opt/homebrew/bin/python3.13 python3.12 /opt/homebrew/bin/python3.12 python3.11 /opt/homebrew/bin/python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        ver=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
        if [ "$ver" != "3.14" ] && [ -n "$ver" ]; then
            PYTHON_CMD="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    PYTHON_CMD="python3"
fi

echo "Using Python: $($PYTHON_CMD --version) ($PYTHON_CMD)"

# 1. Setup Virtual Environment if not present or broken
if [ ! -f ".venv/bin/activate" ]; then
    echo "Creating Python virtual environment (.venv)..."
    rm -rf .venv
    # Homebrew Python does not ship bundled ensurepip wheels, so use --without-pip
    "$PYTHON_CMD" -m venv --without-pip .venv
fi

# 2. Configure compatibility patches for macOS & Homebrew Python
SITE_PACKAGES=$(find .venv/lib -maxdepth 2 -name "site-packages" 2>/dev/null | head -1)
if [ -n "$SITE_PACKAGES" ]; then
    mkdir -p "$SITE_PACKAGES"

    # Patch platform.mac_ver & ensure site-packages takes precedence
    cat << 'EOF' > "$SITE_PACKAGES/patch_mac.py"
import sys, os, platform

site_pkg = os.path.dirname(os.path.abspath(__file__))
if site_pkg in sys.path:
    sys.path.remove(site_pkg)
sys.path.insert(0, site_pkg)

_orig = platform.mac_ver
def _safe_mac_ver(*args, **kwargs):
    ver, info, arch = _orig(*args, **kwargs)
    if not ver:
        return ("14.5.0", info, arch)
    return (ver, info, arch)
platform.mac_ver = _safe_mac_ver
EOF
    echo "import patch_mac" > "$SITE_PACKAGES/patch_mac.pth"

    # Fix Homebrew pyexpat dynamic link for the active python version
    PY_VER=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [ ! -f "$SITE_PACKAGES/pyexpat.cpython-${PY_VER//./}-darwin.so" ]; then
        ORIG_PYEXPAT=$(find "/opt/homebrew/Cellar/python@$PY_VER" -name "pyexpat.*.so" 2>/dev/null | head -1)
        EXPAT_DYLIB=$(find /opt/homebrew/Cellar/expat -name "libexpat.1.dylib" 2>/dev/null | head -1)
        if [ -n "$ORIG_PYEXPAT" ] && [ -n "$EXPAT_DYLIB" ]; then
            cp "$ORIG_PYEXPAT" "$SITE_PACKAGES/pyexpat.cpython-${PY_VER//./}-darwin.so"
            install_name_tool -change /usr/lib/libexpat.1.dylib "$EXPAT_DYLIB" "$SITE_PACKAGES/pyexpat.cpython-${PY_VER//./}-darwin.so" 2>/dev/null || true
            codesign -f -s - "$SITE_PACKAGES/pyexpat.cpython-${PY_VER//./}-darwin.so" 2>/dev/null || true
        fi
    fi

    # Install pip by copying from Homebrew (following symlinks with -L)
    if [ ! -d "$SITE_PACKAGES/pip" ]; then
        for hb_pip in /opt/homebrew/lib/python3.*/site-packages/pip; do
            if [ -d "$hb_pip" ]; then
                echo "Copying pip from Homebrew ($hb_pip)..."
                cp -RL "$(dirname "$hb_pip")"/pip* "$SITE_PACKAGES/" 2>/dev/null || true
                break
            fi
        done
    fi
fi

source .venv/bin/activate

# 3. Check and install Python dependencies
echo "Checking and installing Python dependencies..."
python -m pip install -r requirements.txt

# 4. Check and install Flow Engine dependencies
if [ ! -d "flow-engine/node_modules" ]; then
    echo "Installing flow-engine dependencies..."
    (cd flow-engine && npm install --omit=dev)
fi

# 5. Check and install YouTube acquisition dependencies
if [ ! -d "providers/youtube/acquisition/node_modules" ]; then
    echo "Installing YouTube acquisition dependencies..."
    (cd providers/youtube/acquisition && npm install --omit=dev)
fi

# 6. Launch App GUI
echo "Starting Semantic YT Studio GUI..."
exec python app.py "$@"
