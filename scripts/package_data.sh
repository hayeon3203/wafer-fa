#!/bin/bash
# data/ + checkpoints/ 는 .gitignore 대상이라 git으로 새 장비에 안 옮겨감(약 2.7GB).
# 이 스크립트로 묶어서 새 장비로 옮긴 뒤 daol-fascope 루트에서 풀면 됨:
#   tar xzf daol-fascope-data.tar.gz -C /path/to/daol-fascope
#
# Usage:
#   ./scripts/package_data.sh [출력파일 경로, 기본: ./daol-fascope-data.tar.gz]

set -euo pipefail

OUT="${1:-daol-fascope-data.tar.gz}"
cd "$(dirname "$0")/.."

echo "패키징: data/ checkpoints/ -> $OUT"
tar czf "$OUT" data checkpoints
echo "완료: $(du -h "$OUT" | cut -f1)"
