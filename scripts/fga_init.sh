#!/usr/bin/env bash
# OpenFGA 스토어 및 인증 모델 초기화
# 사용법: ./scripts/fga_init.sh
set -euo pipefail

FGA_URL="${FGA_API_URL:-http://localhost:8080}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_FILE="${SCRIPT_DIR}/../fga/model.json"

echo "▶ OpenFGA 서버 대기 중 (${FGA_URL})..."
for i in $(seq 1 30); do
  if curl -sf "${FGA_URL}/healthz" >/dev/null 2>&1; then
    echo "  서버 준비 완료"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "  오류: 서버가 응답하지 않습니다" >&2
    exit 1
  fi
  echo "  재시도 ${i}/30..."
  sleep 2
done

echo "▶ 기존 스토어 확인 중..."
STORE_ID=$(curl -sf "${FGA_URL}/stores" \
  | python3 -c "
import sys, json
stores = json.load(sys.stdin).get('stores', [])
match = next((s['id'] for s in stores if s['name'] == 'company-rag'), '')
print(match)
" 2>/dev/null || echo "")

if [ -n "$STORE_ID" ]; then
  echo "  기존 스토어 재사용: ${STORE_ID}"
else
  echo "▶ 스토어 생성 중..."
  STORE_ID=$(curl -sf -X POST "${FGA_URL}/stores" \
    -H "Content-Type: application/json" \
    -d '{"name":"company-rag"}' \
    | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
  echo "  생성됨: ${STORE_ID}"
fi

echo "▶ 인증 모델 생성 중..."
MODEL_ID=$(curl -sf -X POST "${FGA_URL}/stores/${STORE_ID}/authorization-models" \
  -H "Content-Type: application/json" \
  -d "@${MODEL_FILE}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['authorization_model_id'])")
echo "  모델 ID: ${MODEL_ID}"

echo ""
echo "✅ 완료! .env에 다음을 추가하세요:"
echo "FGA_API_URL=http://localhost:8080"
echo "FGA_STORE_ID=${STORE_ID}"
echo "POSTGRES_DSN=postgresql://fga:fga@localhost:5432/app"
echo "FGA_CACHE_BACKEND=postgres"
