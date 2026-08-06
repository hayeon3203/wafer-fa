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
| `llava_server.py` | 8506 | LLaVA-1.5-7B 생성 서버. **OpenShell 샌드박스에서 격리 실행** (`scripts/start_llava_sandbox.sh`, ADR 0006) — relay는 여기에 HTTP로만 요청 |
| `wafer_browser_server.py` | 8091 | ThingsBoard "Wafer Gallery" 위젯용 페이지네이션 썸네일 API (전체 172,950건) |
| `equipment_log_server.py` | - | 가상 장비 로그 상관관계용 API (Phase 3) |
| ThingsBoard | 8082 (직접), 8090 (nginx 리브랜딩 프록시) | 대시보드(Overview / Detail) |
| TimescaleDB | 5433 | 텔레메트리·장비 로그 저장 |
| Kafka 프로듀서/컨슈머 | - | `equipment-telemetry-stream` 실시간 수집 스모크테스트 (Phase 4), TimescaleDB+ThingsBoard 이중 적재 |

`docker-compose.yml`에 TimescaleDB / ThingsBoard(+postgres) / Qdrant / Kafka / nginx 프록시 정의. 각 Python 서버는 컨테이너 밖에서 직접 실행. Ollama(EXAONE 번역, 임베딩)는 컨테이너화하지 않고 호스트에 네이티브 설치(다른 GB10 프로젝트와 모델 캐시 공유 전제).

## 기술 스택

PyTorch / torchvision / transformers (DINOv2, LLaVA), LangGraph, Ollama(EXAONE 번역), Qdrant(유사 사례 검색), Streamlit, confluent-kafka, psycopg, scikit-learn, pandas/numpy/pillow.

## 디렉토리 구조

```
src/daol_fascope/     핵심 모듈 (render, infer, relay, telemetry, kafka_*, wafer_*_server 등)
data/                 raw(LSWMD.pkl, secom/) / processed(manifest.csv + 매트릭스) — git 미포함, 별도 이관 필요
checkpoints/          학습된 분류기 가중치 — git 미포함, 별도 이관 필요
tests/                pytest 테스트 (모듈당 1개)
docs/adr/             아키텍처 결정 기록
nginx/                ThingsBoard 리브랜딩 프록시 설정
scripts/ralph/        자동화 루프 스크립트
scripts/setup_ollama_models.sh  새 장비용 Ollama 모델 pull
scripts/package_data.sh         data/+checkpoints/ tar 패키징 (이관용)
Plans.md              작업 대장 (Phase별 진행 상황, DoD, 진행 메모)
CONTEXT.md            용어집 (Wafer Map / Defect Class / Pipeline Stage 등)
```

## 새 GB10 장비 구축 매뉴얼

### 0. 사전 요구사항

| 항목 | 확인 방법 |
|---|---|
| NVIDIA driver가 CUDA 13.x 노출 | `nvidia-smi` — Driver/CUDA Version 확인. `requirements.txt`의 `torch==2.13.0`은 CUDA 13.0 aarch64 wheel 기준 |
| Docker + Compose plugin | `docker compose version` |
| [Ollama](https://ollama.com/download) 설치, `ollama serve` 상시 기동 | `ollama list` (systemd 서비스 등록 권장) |
| Python 3.12 | `python3 --version` |
| 원본 장비의 `data/`+`checkpoints/` tar (`./scripts/package_data.sh`로 생성, ~2.7GB→압축 후 ~200MB) | scp/rsync로 새 장비에 전달 |

### 1. 저장소 + 데이터

```bash
git clone https://github.com/hayeon3203/wafer-fa.git daol-fascope
cd daol-fascope
tar xzf /path/to/daol-fascope-data.tar.gz -C .   # data/ checkpoints/ 복원
```

### 2. 인프라 컨테이너

ThingsBoard는 **최초 1회 스키마 설치**가 별도로 필요함(설치 안 하고 바로 `up`하면 스키마 없어서 기동 실패) — 나머지는 바로 up 가능.

```bash
# 2-1. DB류/Qdrant/Kafka 먼저
docker compose up -d timescaledb thingsboard-postgres qdrant kafka

# 2-2. ThingsBoard 스키마 설치 (신규 볼륨에서 최초 1회만, 몇 분 소요)
docker compose run --rm -e INSTALL_TB=true -e LOAD_DEMO=false thingsboard

# 2-3. ThingsBoard 본기동 + nginx 프록시
docker compose up -d thingsboard waferscope-nginx
```

**주의**: `qdrant` 서비스는 호스트 6333 포트를 씀. 이미 다른 프로젝트가 Qdrant를 공유 중인 박스(예: 이 프로젝트의 원본 GB10)라면 포트 충돌로 실패함 — 그런 박스에선 `qdrant` 서비스를 빼고 기존 공유 인스턴스를 그대로 씀. 완전히 새 장비라면 정상 기동.

### 3. ThingsBoard Tenant/Device 프로비저닝 (콘솔 UI, 최초 1회)

1. `http://<host>:8082` 접속 → 기본 sysadmin 계정 로그인: `sysadmin@thingsboard.org` / `sysadmin` (로그인 후 비밀번호 변경 권장)
2. 좌측 메뉴 **Tenants** → `+` → 이름 입력(예: `daol-fascope`) → 저장
3. 생성한 Tenant 클릭 → **Tenant Admins** → `+` → 이메일/비밀번호 입력 후 저장 — 이 값이 `.env`의 `THINGSBOARD_ADMIN_USERNAME`/`THINGSBOARD_ADMIN_PASSWORD`
4. sysadmin 로그아웃 → 방금 만든 tenant admin 계정으로 재로그인
5. **Devices** → `+` → 이름 입력(예: `daol-fascope-pipeline`) → 저장
6. 생성한 Device 클릭 → 우측 패널에서 **Copy Device Id** → `.env`의 `THINGSBOARD_DEVICE_ID`
7. 같은 Device의 **Manage credentials** → Access Token 복사 → `.env`의 `THINGSBOARD_DEVICE_TOKEN`

### 4. Ollama 모델

```bash
./scripts/setup_ollama_models.sh   # exaone3.5:7.8b (번역), nomic-embed-text (Qdrant 임베딩)
```

### 5. 파이썬 환경

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6. env 값 채우기

```bash
cp .env.example .env
# THINGSBOARD_URL/DEVICE_TOKEN/ADMIN_USERNAME/ADMIN_PASSWORD/DEVICE_ID (3단계 값) 채우기
export $(grep -v '^#' .env | xargs)
```

### 7. ThingsBoard 대시보드/위젯 세팅 (1회성)

```bash
PYTHONPATH=src python3 -m daol_fascope.setup_thingsboard_dashboard
```

Wafer Overview + Wafer Detail 대시보드 2개, 커스텀 위젯 4개가 생성됨. `http://<host>:8090`(nginx 프록시) 또는 `:8082`(직접)에서 확인.

### 8. 서버 기동

```bash
# LLaVA 모델 서버 (샌드박스 격리, :8506) — relay보다 먼저 띄울 것
./scripts/start_llava_sandbox.sh --check   # 전제조건만 점검
./scripts/start_llava_sandbox.sh --up
curl -s 127.0.0.1:8506/health              # loaded:true 가 될 때까지 대기 (14GB 로딩)

# 로컬 분류 데모 (Stage 1만)
streamlit run app.py --server.port 8501

# ThingsBoard 연동 서버들
PYTHONPATH=src python3 -m daol_fascope.wafer_predict_server
PYTHONPATH=src python3 -m daol_fascope.wafer_browser_server
PYTHONPATH=src python3 -m daol_fascope.equipment_log_server
```

예측 서버를 로그인 세션과 독립적으로 계속 실행하려면 사용자 systemd 서비스로
등록한다. 서비스는 프로젝트의 `.env`를 자동으로 읽으므로
`THINGSBOARD_DEVICE_TOKEN`을 설정한 뒤 재시작하면 된다.

```bash
install -Dm644 systemd/wafer-predict.service ~/.config/systemd/user/wafer-predict.service
systemctl --user daemon-reload
systemctl --user enable --now wafer-predict.service

# 상태와 로그 확인
systemctl --user status wafer-predict.service
journalctl --user -u wafer-predict.service -f
```

`.env` 변경 후에는 `systemctl --user restart wafer-predict.service`로 환경변수를
다시 읽힌다. SSH 로그아웃 후에도 사용자 서비스를 자동 기동해야 하는 서버라면
관리자 권한으로 한 번 `sudo loginctl enable-linger "$USER"`를 실행한다.

샌드박스 없이 돌리려면 같은 모듈을 그냥 호스트에서 띄우면 된다 —
`PYTHONPATH=src python3 -m daol_fascope.llava_server`. relay는 `LLAVA_URL`
환경변수(기본 `http://localhost:8506`)만 보므로 어느 쪽이든 동작한다.

첫 실행 시 `facebook/dinov2-base`, `llava-hf/llava-1.5-7b-hf`(~14GB)를 HuggingFace Hub에서 자동 다운로드함 — 인터넷 연결 필요, `~/.cache/huggingface/hub`에 캐시되어 이후 재다운로드 없음. 샌드박스는 아웃바운드가 막혀 있으므로 **다운로드는 호스트에서 미리 끝나 있어야 한다**.

Kafka 실시간 스트리밍 스모크테스트(선택, Phase 4)는 `PYTHONPATH=src python3 -m daol_fascope.kafka_consumer`와 `kafka_producer`를 별도 프로세스로 기동 — 자세한 내용은 `Plans.md` Phase 4 참고.

테스트: `PYTHONPATH=src pytest`

### 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `docker compose up -d thingsboard` 후 컨테이너가 재시작 반복 | 스키마 미설치. 2-2단계(`INSTALL_TB=true`) 먼저 실행 |
| `qdrant` 컨테이너가 포트 바인딩 에러로 기동 실패 | 같은 박스에 다른 프로젝트가 쓰는 Qdrant가 이미 6333 점유 중. 그 인스턴스를 그대로 쓰고 compose `qdrant` 서비스는 스킵 |
| `setup_thingsboard_dashboard.py` 실행 시 `KeyError` | `THINGSBOARD_ADMIN_USERNAME`/`PASSWORD`/`DEVICE_ID` 셋 다 기본값 없음(필수) — 3단계 값 `.env`에 채웠는지 확인 |
| `pip install -r requirements.txt`가 torch를 CPU-only로 설치 | NVIDIA driver가 CUDA 13.x 미만이거나 아키텍처가 aarch64가 아님 — 0단계 사전요구사항 재확인 |

## 참고 문서

- `Plans.md` — Phase별 작업 대장 (진행 상황, 실험 기록, 트러블슈팅)
- `CONTEXT.md` — 용어집
- `docs/adr/` — 아키텍처 결정 기록
