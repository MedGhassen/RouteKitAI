#!/usr/bin/env bash
# Run all RouteKitAI examples and print a report.
# Usage: ./scripts/run_examples.sh [--timeout SECONDS] [--examples-dir DIR]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXAMPLES_DIR="${REPO_ROOT}/examples"
TIMEOUT_SEC=60
REPORT_FILE=""
SKIP_PATTERN=""

# Portable timeout: use gtimeout (Homebrew) on macOS, timeout on Linux
if command -v gtimeout &>/dev/null; then
  RUN_TIMEOUT="gtimeout"
elif command -v timeout &>/dev/null; then
  RUN_TIMEOUT="timeout"
else
  RUN_TIMEOUT=""
fi

while [[ $# -gt 0 ]]; do
  case $1 in
    --timeout)
      TIMEOUT_SEC="$2"
      shift 2
      ;;
    --examples-dir)
      EXAMPLES_DIR="$2"
      shift 2
      ;;
    --report)
      REPORT_FILE="$2"
      shift 2
      ;;
    --skip)
      SKIP_PATTERN="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--timeout SECONDS] [--examples-dir DIR] [--report FILE] [--skip PATTERN]"
      echo "  --timeout    Timeout per example in seconds (default: 60)"
      echo "  --examples-dir  Path to examples directory (default: repo/examples)"
      echo "  --report     Write report to FILE (default: stdout only)"
      echo "  --skip       Skip examples whose path matches PATTERN (e.g. real)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

cd "$REPO_ROOT"

# Find example scripts (excluding __init__.py)
EXAMPLES=()
for f in "$EXAMPLES_DIR"/*.py; do
  [[ -f "$f" && "$(basename "$f")" != "__init__.py" ]] && EXAMPLES+=("$f")
done
# Sort by name
EXAMPLES=($(printf '%s\n' "${EXAMPLES[@]}" | sort))

PASSED=0
FAILED=0
SKIPPED=0
declare -a FAILED_NAMES
declare -a FAILED_REASONS

for example in "${EXAMPLES[@]}"; do
  name="$(basename "$example")"
  if [[ -n "$SKIP_PATTERN" && "$name" == *"$SKIP_PATTERN"* ]]; then
    ((SKIPPED++)) || true
    echo "[SKIP] $name (matches --skip $SKIP_PATTERN)"
    continue
  fi
  echo -n "Running $name ... "
  start=$(python -c "import time; print(time.time())" 2>/dev/null || echo "0")
  if [[ -n "$RUN_TIMEOUT" ]]; then
    out=$("$RUN_TIMEOUT" "$TIMEOUT_SEC" python "$example" 2>&1) || code=$?
  else
    out=$(python "$example" 2>&1) || code=$?
  fi
  end=$(python -c "import time; print(time.time())" 2>/dev/null || echo "0")
  elapsed=$(python -c "print(round($end - $start, 1))" 2>/dev/null || echo "?")
  if [[ ${code:-0} -eq 0 ]]; then
    echo "OK (${elapsed}s)"
    ((PASSED++)) || true
  else
    echo "FAIL (${elapsed}s)"
    ((FAILED++)) || true
    FAILED_NAMES+=("$name")
    # First line of output or exit code
    first_line=$(echo "$out" | head -1)
    FAILED_REASONS+=("${first_line:-exit code ${code:-1}}")
  fi
done

# Report
total=$((PASSED + FAILED + SKIPPED))
echo ""
echo "=============================================="
echo "           Examples run report"
echo "=============================================="
echo "  Total:   $total"
echo "  Passed:  $PASSED"
echo "  Failed:  $FAILED"
echo "  Skipped: $SKIPPED"
echo "=============================================="

if [[ $FAILED -gt 0 ]]; then
  echo ""
  echo "Failed examples:"
  for i in "${!FAILED_NAMES[@]}"; do
    echo "  - ${FAILED_NAMES[$i]}"
    echo "    Reason: $(echo "${FAILED_REASONS[$i]}" | head -1)"
  done
fi

if [[ -n "$REPORT_FILE" ]]; then
  {
    echo "Examples run report - $(date -Iseconds 2>/dev/null || date)"
    echo "Total: $total | Passed: $PASSED | Failed: $FAILED | Skipped: $SKIPPED"
    [[ $FAILED -gt 0 ]] && echo "Failed: ${FAILED_NAMES[*]}"
  } > "$REPORT_FILE"
  echo ""
  echo "Report written to $REPORT_FILE"
fi

[[ $FAILED -eq 0 ]]
