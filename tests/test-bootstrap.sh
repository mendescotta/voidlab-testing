#!/usr/bin/env bash
# Entry point for ci-check.sh's shell test discovery.
set -euo pipefail
exec python3 "$(dirname "$0")/test-bootstrap.py"
