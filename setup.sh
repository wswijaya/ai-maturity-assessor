#!/usr/bin/env zsh
#
# setup.sh — one-time project setup for AI Maturity Assessor
#
# USAGE
#   First run:   chmod +x setup.sh && ./setup.sh
#   To persist PYTHONPATH in the current shell: source setup.sh
#
# WARNING
#   Do NOT run with bash — this script requires zsh.
#   The shebang above ensures ./setup.sh always uses zsh; however,
#   `source setup.sh` must also be run from a zsh session.

set -e
set -o pipefail

# ---------------------------------------------------------------------------
# Resolve the project root (directory containing this script)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${(%):-%x}")" && pwd)"

# ---------------------------------------------------------------------------
# ENVIRONMENT SETUP
# ---------------------------------------------------------------------------

ENV_FILE="${SCRIPT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo ""
  echo "No .env file found."
  echo -n "Enter your ANTHROPIC_API_KEY: "
  read -r ANTHROPIC_API_KEY_INPUT
  echo "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY_INPUT}" > "${ENV_FILE}"
  echo ".env created."
fi

# Load variables from .env into the current shell.
set -o allexport
source "${ENV_FILE}"
set +o allexport

# Set PYTHONPATH to the project root so `src.*` imports resolve.
export PYTHONPATH="${SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# DEPENDENCY INSTALLATION
# ---------------------------------------------------------------------------

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is not installed or not on PATH." >&2
  exit 1
fi

if ! command -v pip3 &>/dev/null && ! python3 -m pip --version &>/dev/null 2>&1; then
  echo "Error: pip is not available. Install it with: python3 -m ensurepip" >&2
  exit 1
fi

echo ""
echo "Installing dependencies from requirements.txt…"
python3 -m pip install -r "${SCRIPT_DIR}/requirements.txt" --quiet || {
  echo "Error: pip install failed." >&2
  exit 1
}

# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

echo ""
echo "─────────────────────────────────────────"
echo " Setup complete"
echo "─────────────────────────────────────────"
echo " Python version : $(python3 --version)"
echo " PYTHONPATH     : ${PYTHONPATH}"

if [[ -n "${ANTHROPIC_API_KEY}" ]]; then
  echo " API key        : set"
else
  echo " API key        : MISSING — add ANTHROPIC_API_KEY to .env before running"
fi

echo ""
echo " Run the assessor:"
echo "   python3 src/cli.py"
echo "─────────────────────────────────────────"
echo ""
