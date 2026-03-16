#!/usr/bin/env bash
# Install WeasyPrint system dependencies + Python deps for report_generation.
#
# One-liner (from project root):
#   bash report_generation/setup_weasyprint.sh
# Or from report_generation/:
#   bash setup_weasyprint.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"
if [[ ! -f "$REQUIREMENTS" ]]; then
  echo "Error: requirements.txt not found at $REQUIREMENTS" >&2
  exit 1
fi

echo "=== Installing WeasyPrint system dependencies ==="
case "$(uname -s)" in
  Darwin)
    if command -v brew &>/dev/null; then
      brew install pkg-config cairo pango
      echo "On macOS, if WeasyPrint fails to load libs, run:"
      echo '  export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH  # Apple Silicon'
      echo '  export DYLD_FALLBACK_LIBRARY_PATH=/usr/local/lib:$DYLD_FALLBACK_LIBRARY_PATH    # Intel'
    else
      echo "Homebrew not found. Install from https://brew.sh then re-run this script." >&2
      exit 1
    fi
    ;;
  Linux)
    if command -v apt-get &>/dev/null; then
      sudo apt-get update
      sudo apt-get install -y python3-pip libcairo2 libgdk-pixbuf2.0-0 libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libharfbuzz-subset0 libffi-dev libjpeg-dev libopenjp2-7-dev 2>/dev/null || \
      sudo apt-get install -y python3-pip libcairo2 libgdk-pixbuf2.0-0 libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libharfbuzz-subset0
    elif command -v dnf &>/dev/null; then
      sudo dnf install -y python3-pip pango
    elif command -v pacman &>/dev/null; then
      sudo pacman -S --noconfirm python-pip pango
    else
      echo "Unsupported Linux package manager (apt/dnf/pacman). Install Pango and pip manually." >&2
      exit 1
    fi
    ;;
  *)
    echo "Unsupported OS: $(uname -s). Install Pango and pip manually." >&2
    exit 1
    ;;
esac

echo "=== Installing Python dependencies ==="
# Prefer venv in project root if present
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="${PROJECT_ROOT}/.venv"
if [[ -d "$VENV" && -x "$VENV/bin/pip" ]]; then
  "$VENV/bin/pip" install -r "$REQUIREMENTS"
  echo "Installed into existing venv: $VENV"
elif command -v python3 &>/dev/null; then
  python3 -m pip install --user -r "$REQUIREMENTS"
  echo "Installed with: python3 -m pip (user)"
else
  echo "python3 not found." >&2
  exit 1
fi

ENV_FILE="${SCRIPT_DIR}/.env"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"
if [[ ! -f "$ENV_EXAMPLE" ]]; then
  cat > "$ENV_EXAMPLE" <<'EOF'
# Example env file for report_generation
# Copy to .env and fill in your own keys.

# 'gemini' (default) or 'qwen'
MODEL_PROVIDER=gemini

# Required when MODEL_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: override default Gemini model
# GEMINI_MODEL_NAME=gemini-2.5-pro

# Optional: only needed when MODEL_PROVIDER=qwen
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# Optional: override default Qwen model
# QWEN_MODEL_NAME=qwen-vl-plus
EOF
  echo "Created .env.example at $ENV_EXAMPLE"
fi

echo "=== Done ==="
echo "Run report: python3 $SCRIPT_DIR/report_generation.py [customer_name]"
