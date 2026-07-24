# Daol FAScope

반도체 웨이퍼 다이(die) 단위 테스트 결과 그리드를 보고 불량 패턴을 분류하고, 분류 결과를 근거로 원인·심각도·조치 레시피까지 이어서 생성하는 데모 파이프라인. WM-811K 데이터셋 기반, SemiFA를 참고해 설계.

## 파이프라인 (5단계)

| 단계 | 내용 | 담당 |
|------|------|------|
| Classify | 웨이퍼 맵(다이 격자, 0=배경/1=정상/2=불량) → 9종 불량 유형(또는 정상) 분류 | DINOv2 (frozen backbone) + MLP head |
| Describe | 분류된 패턴이 웨이퍼 상에서 어떻게 보이는지 설명 생성 | LLaVA-1.5-7B (비전+텍스트) |
| Root Cause | 공정상 예상 원인 추정 | LLaVA-1.5-7B |
| Severity | CRITICAL/MAJOR/MINOR/NONE 판정 | LLaVA-1.5-7B |
| Recipe | 유사 과거 사례 검색(Qdrant) 참고해 조치 레시피 제안 | LLaVA-1.5-7B |

Describe~Recipe 4단계는 LangGraph로 엮은 relay 그래프. 각 단계 결과(영문)는 EXAONE-3.5-7.8B(Ollama 로컬 서빙)로 한글 번역해서 최종 노출.

Wafer Map은 원본 다이 테스트 결과 매트릭스이고, 화면에 보이는 이미지는 그 매트릭스를 색칠해 렌더링한 것 — 실제 카메라 사진이 아님 (`render.py`). 운영 목표는 디지털 트윈에서 이 매트릭스를 자동 수집하는 것.

## 구성 요소 / 포트

| 이름 | 포트 | 역할 |
|------|------|------|
| `app.py` (Streamlit) | 8501 | Stage 1(분류)만 로컬 스모크테스트용 데모 |
| `wafer_predict_server.py` | 8092 | ThingsBoard "Wafer Detail" 실행 버튼 API — 랜덤 샘플 뽑아 5단계 파이프라인 전체 실행, `pipeline_stage` 텔레메트리 순차 전송 |
| `wafer_browser_server.py` | 8091 | ThingsBoard "Wafer Gallery" 위젯용 페이지네이션 썸네일 API (전체 172,950건) |
| `equipment_log_server.py` | - | 가상 장비 로그 상관관계용 API (Phase 3) |
| ThingsBoard | 8082 (직접), 8090 (nginx 리브랜딩 프록시) | 대시보드(Overview / Detail) |
| TimescaleDB | 5433 | 텔레메트리·장비 로그 저장 |
| Kafka 프로듀서/컨슈머 | - | `equipment-telemetry-stream` 실시간 수집 스모크테스트 (Phase 4), TimescaleDB+ThingsBoard 이중 적재 |

`docker-compose.yml`에 TimescaleDB / ThingsBoard(+postgres) / nginx 프록시 정의. 각 Python 서버는 컨테이너 밖에서 직접 실행.

## 기술 스택

PyTorch / torchvision / transformers (DINOv2, LLaVA), LangGraph, Ollama(EXAONE 번역), Qdrant(유사 사례 검색), Streamlit, confluent-kafka, psycopg, scikit-learn, pandas/numpy/pillow.

## 디렉토리 구조

```
src/daol_fascope/     핵심 모듈 (render, infer, relay, telemetry, kafka_*, wafer_*_server 등)
data/                 raw(LSWMD.pkl) / processed(manifest.csv + 매트릭스)
checkpoints/          학습된 분류기 가중치
tests/                pytest 테스트 (모듈당 1개)
docs/adr/             아키텍처 결정 기록
nginx/                ThingsBoard 리브랜딩 프록시 설정
scripts/ralph/        자동화 루프 스크립트
Plans.md              작업 대장 (Phase별 진행 상황, DoD, 진행 메모)
CONTEXT.md            용어집 (Wafer Map / Defect Class / Pipeline Stage 등)
```

## 실행 방법

```bash
# 1. 인프라 (TimescaleDB, ThingsBoard, nginx 프록시)
docker compose up -d

# 2. 파이썬 venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 로컬 분류 데모
streamlit run app.py --server.port 8501

# 4. ThingsBoard 연동 서버 (텔레메트리 전송하려면 THINGSBOARD_DEVICE_TOKEN 필요)
THINGSBOARD_DEVICE_TOKEN=<device-token> PYTHONPATH=src python3 -m daol_fascope.wafer_predict_server
PYTHONPATH=src python3 -m daol_fascope.wafer_browser_server
```

테스트: `PYTHONPATH=src pytest`

## 참고 문서

- `Plans.md` — Phase별 작업 대장 (진행 상황, 실험 기록, 트러블슈팅)
- `CONTEXT.md` — 용어집
- `docs/adr/` — 아키텍처 결정 기록
