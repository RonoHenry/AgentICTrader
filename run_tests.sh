#!/usr/bin/env bash
# Run every AgentICTrader test suite (root + backend) and exit nonzero if any
# test fails. Thin wrapper around scripts/run_all_tests.py; see README "Testing".
#
#   ./run_tests.sh                    # all suites; live-service tests deselected
#   ./run_tests.sh --live             # + tests marked infrastructure; starts
#                                     #   docker/docker-compose.test.yml first
#   ./run_tests.sh --coverage         # + per-suite coverage report (pytest-cov)
#   ./run_tests.sh --suite backend    # any other scripts/run_all_tests.py option
#   ./run_tests.sh -- -x -k risk      # arguments after -- are passed to pytest
#   ./run_tests.sh --dry-run          # print the pytest commands, run nothing
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root" || exit 1

# Interpreter: the active virtualenv, else ./.venv, else whatever python is on PATH.
# (VIRTUAL_ENV is checked directly: it can be inherited without its Scripts/bin
# directory being first on PATH.)
py=""
for candidate in "${VIRTUAL_ENV:+$VIRTUAL_ENV/Scripts/python.exe}" "${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}"                  .venv/Scripts/python.exe .venv/bin/python; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
        py="$candidate"
        break
    fi
done
if [[ -z "$py" ]]; then
    if command -v python3 >/dev/null 2>&1; then py=python3; else py=python; fi
fi

live=0
coverage=0
dry_run=0
runner_args=()
pytest_args=()
after_dashdash=0
for arg in "$@"; do
    if (( after_dashdash )); then
        pytest_args+=("$arg")
        continue
    fi
    case "$arg" in
        --live) live=1; runner_args+=(--live) ;;
        --coverage) coverage=1 ;;
        --dry-run) dry_run=1; runner_args+=(--dry-run) ;;
        --) after_dashdash=1 ;;
        *) runner_args+=("$arg") ;;
    esac
done

if (( coverage )); then
    if ! "$py" -c "import pytest_cov" >/dev/null 2>&1; then
        echo "error: --coverage needs pytest-cov (pip install pytest-cov)" >&2
        exit 4
    fi
    pytest_args=(--cov --cov-report=term-missing ${pytest_args[@]+"${pytest_args[@]}"})
fi

if (( live && !dry_run )); then
    # Live tests need the test services (InfluxDB) from docker-compose.test.yml.
    # Qdrant / MLflow / Kafka-backed tests additionally need those services running.
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        echo "Starting test services (docker/docker-compose.test.yml)..."
        if ! docker compose -f docker/docker-compose.test.yml up -d --wait; then
            echo "warning: test services failed to start; live tests will fail" >&2
        fi
    else
        echo "warning: Docker is not available; live tests that need it will fail" >&2
    fi
fi

"$py" scripts/run_all_tests.py ${runner_args[@]+"${runner_args[@]}"} -- ${pytest_args[@]+"${pytest_args[@]}"}
exit $?
