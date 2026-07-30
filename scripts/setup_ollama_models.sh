#!/bin/bash
# 새 장비에 daol-fascope 배포 시 필요한 Ollama 모델 pull.
# 전제: Ollama 자체는 이 스크립트가 설치하지 않음 (시스템 서비스,
# https://ollama.com/download 로 별도 설치 + `ollama serve` 기동 필요).
#
# Usage:
#   ./scripts/setup_ollama_models.sh

set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama 명령 없음. https://ollama.com/download 에서 먼저 설치하세요." >&2
  exit 1
fi

echo "== exaone3.5:7.8b (relay.py 한국어 번역) =="
ollama pull exaone3.5:7.8b

echo "== nomic-embed-text (cases.py Qdrant 케이스 임베딩) =="
ollama pull nomic-embed-text

echo "완료. 'ollama list'로 확인 가능."
