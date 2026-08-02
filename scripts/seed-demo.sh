#! /usr/bin/env bash

set -euo pipefail

docker compose exec backend python scripts/seed_demo_data.py "$@"
