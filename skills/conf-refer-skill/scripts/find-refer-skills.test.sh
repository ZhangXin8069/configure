#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/find_refer_skills_cases.py"
