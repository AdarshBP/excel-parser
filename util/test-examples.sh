#!/usr/bin/env bash
# Validate and push every example, then compare row counts.
#
#   ./util/test-examples.sh            # run all
#   ./util/test-examples.sh --validate # validate only, no push
#
# Requires: PG credentials in .env (or environment), Python 3.
# Run from the repo root.
set -uo pipefail
cd "$(dirname "$0")/.."

VALIDATE_ONLY=false
[ "${1:-}" = "--validate" ] && VALIDATE_ONLY=true

TOOLS="$(pwd)/tools"
EXAMPLES="$(pwd)/examples"
PASS=0
FAIL=0
SKIP=0

# Expected row counts: name=count (0 = must fail validation)
get_expected() {
  case "$1" in
    01_simple)             echo 3 ;;
    02_features)           echo 12 ;;
    03_uuid_keys)          echo 4 ;;
    04_postgres_schema)    echo 4 ;;
    05_data_types)         echo 4 ;;
    06_references)         echo 9 ;;
    07_validation_errors)  echo 0 ;;
    08_source_mismatch)    echo 0 ;;
    12_petpooja_growth)    echo 31 ;;
    13_smartq_payment)     echo 33 ;;
    14_zomato_business)    echo 470 ;;
    15_magicpin_ledger)    echo 1141 ;;
    16_source_ref_showcase) echo 3 ;;
    17_kitchen_sink)       echo 18 ;;
    *)                     echo SKIP ;;
  esac
}

# Load .env if present
[ -f .env ] && set -a && source .env && set +a

echo "=== Excel Parser — example test suite ==="
echo ""

for dir in "$EXAMPLES"/*/; do
  name=$(basename "$dir")
  expect=$(get_expected "$name")

  # Skip examples not in the expected list (client files 09-11)
  if [ "$expect" = "SKIP" ]; then
    echo "  SKIP  $name (no expected count / client files)"
    SKIP=$((SKIP + 1))
    continue
  fi

  # Find config and source files
  config=$(find "$dir" -maxdepth 1 -name "*_config.xlsx" | head -1)
  source_f=$(find "$dir" -maxdepth 1 \( -name "*_source.xlsx" -o -name "*_source.csv" \) | head -1)
  if [ -z "$config" ] || [ -z "$source_f" ]; then
    echo "  SKIP  $name (missing config or source file)"
    SKIP=$((SKIP + 1))
    continue
  fi

  config_base=$(basename "$config")
  source_base=$(basename "$source_f")

  # Work in a temp dir so no artifacts are left in the example folder
  work=$(mktemp -d)
  cp "$config" "$source_f" "$work/"
  cd "$work"

  # Examples 07 and 08 must FAIL validation
  if [ "$expect" = "0" ]; then
    val_output=$(python3 "$TOOLS/validator.py" "$config_base" "$source_base" --ddl schema.postgres.sql 2>&1 || true)
    if echo "$val_output" | grep -q "NOT loadable"; then
      echo "  PASS  $name — validation correctly rejected"
      PASS=$((PASS + 1))
    else
      echo "  FAIL  $name — should have failed validation but didn't"
      FAIL=$((FAIL + 1))
    fi
    cd "$EXAMPLES/.."
    rm -rf "$work"
    continue
  fi

  # Validate
  val_output=$(python3 "$TOOLS/validator.py" "$config_base" "$source_base" --ddl schema.postgres.sql 2>&1 || true)
  if echo "$val_output" | grep -q "NOT loadable"; then
    echo "  FAIL  $name — validation failed unexpectedly"
    echo "        $(echo "$val_output" | tail -1)"
    FAIL=$((FAIL + 1))
    cd "$EXAMPLES/.."
    rm -rf "$work"
    continue
  fi

  if [ "$VALIDATE_ONLY" = "true" ]; then
    echo "  PASS  $name — validation OK"
    PASS=$((PASS + 1))
    cd "$EXAMPLES/.."
    rm -rf "$work"
    continue
  fi

  # Push (executor)
  exec_output=$(python3 "$TOOLS/executor.py" "$config_base" "$source_base" --trace 0 2>&1)
  last_line=$(echo "$exec_output" | tail -1)

  # Extract row count — handle both fresh push and dedup
  if echo "$last_line" | grep -q "already been loaded"; then
    echo "  PASS  $name — dedup (already pushed, identical content)"
    PASS=$((PASS + 1))
  elif echo "$last_line" | grep -qE "^file_id"; then
    # Extract total rows: "file_id xxx: 18 rows into postgres ..."
    actual=$(echo "$last_line" | grep -oE '[0-9]+ rows' | head -1 | grep -oE '[0-9]+')
    if [ "$actual" = "$expect" ]; then
      echo "  PASS  $name — $actual rows (expected $expect)"
      PASS=$((PASS + 1))
    else
      echo "  FAIL  $name — got $actual rows, expected $expect"
      FAIL=$((FAIL + 1))
    fi
  else
    echo "  FAIL  $name — unexpected output: $last_line"
    FAIL=$((FAIL + 1))
  fi

  cd "$EXAMPLES/.."
  rm -rf "$work"
done

echo ""
echo "=== Results: $PASS passed, $FAIL failed, $SKIP skipped ==="

[ "$FAIL" -gt 0 ] && exit 1
exit 0
