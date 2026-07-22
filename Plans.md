# wafer-fa Plans.md

작성일: 2026-07-22

Spec skip reason: product contract (defect taxonomy, input format, model/metric decisions) 는 grilling session에서 이미 확정되었으며, 'CONTEXT.md' (glossary)와 'docs/adr/0001-0002' (architecture decisions)에 기록되어 있습니다. solo 프로젝트를 위해 독립한 root 'spec.md '는 만들지 않고, 이 'Plans.md'을 작업 대장으로 사용하며, 정답 조건은 기존의 'CONTEXT.md/ADR'을 참조한다.

team_validation_mode: manual-pass (grilling 세션에서 각 요구사항을 하나씩 확정했으며, TeamAgent 다중 시점 리뷰는 필요 없다고 판단)
---

## Phase 1: DINOv2 + 간이 분류기（Stage 1）

목적: 웨이퍼 맵(다이 격자) 보고 9종 불량 유형(또는 정상) 분류. Streamlit으로 즉시 결과 확인.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 1.1 | 프로젝트 스캐폴딩 (venv, requirements, labels.py) | `pytest` 실행 가능, git repo 초기 커밋 존재 | - | cc:완료 |
| 1.2 | WM-811K 데이터 확보 (LSWMD.pkl) | `data/raw/LSWMD.pkl` 로드 가능, 811,457행 확인 | - | cc:완료 |
| 1.3 | 매트릭스→이미지 렌더러 (`render.py`) | `pytest tests/test_render.py` 통과 | 1.1 | cc:완료 |
| 1.4 | 데이터 전처리 (`data_prep.py`, 라벨 있는 172,950건만, stratified 80/10/10) | `data/processed/manifest.csv` 생성, 각 split에 9클래스 전부 존재 | 1.1, 1.2 | cc:완료 |
| 1.5 | `WaferDataset` + 회전/뒤집기 증강 (train만) | `pytest tests/test_dataset.py` 통과 | 1.3, 1.4 | cc:완료 |
| 1.6 | `DinoV2Classifier` (frozen backbone + MLP head) | `pytest tests/test_model.py` 통과 | 1.1 | cc:완료 |
| 1.7 | 학습 루프 + macro F1 & accuracy 동시 리포트 (`train.py`) | test macro F1 ≥ 0.80 **그리고** accuracy 함께 기록 — 0.80 미달이나 사용자 지시로 현재 결과(run3: macro F1 0.758 / accuracy 0.94) 채택하고 다음 단계 진행, 추가 개선은 백로그로 이관 | 1.5, 1.6 | cc:완료 (목표 미달, 백로그 이관) |
| 1.8 | 추론 모듈 (`infer.py`) | `pytest tests/test_infer.py` 통과 | 1.6 | cc:완료 |
| 1.9 | Streamlit 데모 (`app.py`, 랜덤 샘플 뽑기 + 확률 막대그래프) | 브라우저에서 버튼 클릭 시 이미지+예측 표시 확인 | 1.7, 1.8 | cc:완료 (서버 기동+추론 파이프라인 확인, 사용자 브라우저 접속 확인 완료) |

**진행 메모**:
- 1차(10epoch, 증강 전) → macro F1 0.741 / accuracy 0.93
- 2차(20epoch, 증강 전) → macro F1 0.729 / accuracy 0.92 (에폭만 늘리는 건 효과 없음 확인)
- 3차(10epoch, 회전/뒤집기 증강 + bilinear 보간) → **macro F1 0.758 / accuracy 0.94 (현재 채택 모델, `checkpoints/best_model.pt`)**. Near-full F1 0.67→0.90, Edge-Loc 0.54→0.62, Scratch 0.49→0.64로 개선. Donut은 recall 0.96까지 오른 대신 precision 0.39로 하락(과다 예측 경향)
- 0.80 목표는 미달이나, 사용자 지시로 여기서 1단계 마무리하고 Streamlit 데모(1.9)로 진행. 추가 개선(백본 unfreeze, 처음부터 CNN 학습, 위 ShuffleNet-v2 검토)은 시간 여유 시 별도 착수
- **향후(시간 여유 시) 별도 시도 후보**: [ShuffleNet-v2 + CNN transfer learning](https://www.hindawi.com/journals/amse/2022/1829792/) (Doss et al., 2022, *Advances in Materials Science and Engineering*) — 동일 WM-811K 데이터셋 사용, 저자 보고 수치 accuracy 96.93% / precision 95.40% / recall 96.26% / F1-score 95.75%. **미검증 주의**: 페이월로 원문 전체 확인 못함 — F1이 macro-averaged인지 weighted/micro-averaged인지 불명확(accuracy와 F1이 매우 근접한 걸 보면 weighted일 가능성 있음, 우리 데이터처럼 극심한 불균형에서 macro F1이 이렇게 높게 나오긴 어려움). 착수 전 원문 확보해서 평가 프로토콜(클래스 불균형 처리, train/test 분할 방식) 재확인 필요.

---

## Phase 2: LangGraph 4-agent relay (Stage 2)

목적: SemiFA 구조 참고, "설명 → 원인분석 → 심각도 → 해결책" 릴레이.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 2.1 | Stage 1 분류 결과(라벨+9클래스 확률)를 받는 DefectDescriber 에이전트 | 분류 결과 입력 시 자연어 설명 1개 이상 생성 | Phase 1 | cc:완료 |
| 2.2 | RootCauseAnalyzer 에이전트 (원인 가설) | 결함 유형별 원인 후보 1개 이상 출력 | 2.1 | cc:완료 |
| 2.3 | SeverityClassifier 에이전트 (CRITICAL/MAJOR/MINOR/NONE) | 4단계 중 1개 판정 출력 | 2.2 | cc:완료 |
| 2.4 | RecipeAdvisor 에이전트 (해결책 제안) | 조치 제안 1개 이상 출력 | 2.3 | cc:완료 |
| 2.5 | LangGraph 릴레이 오케스트레이션 + Streamlit UI 확장 (에이전트별 결과 섹션) | 4개 에이전트 순차 실행 결과가 화면에 순서대로 표시 | 2.1-2.4 | cc:완료 |

**진행 메모 (2.1-2.5)**: `src/wafer_fa/relay.py`(LangGraph 4-노드 릴레이, LLaVA 직접 호출, exaone3.5:7.8b 번역) + `src/wafer_fa/cases.py`(Qdrant `wafer_defect_cases` 빈 컬렉션 + 검색) 구현, `app.py`에 배선. `pytest tests/test_relay.py tests/test_cases.py` 통과(그래프 상태 전달·심각도 파싱은 mock, Qdrant 검색은 실제 서비스 대상 통합 테스트). `llava-hf/llava-1.5-7b-hf` 최초 다운로드(14GB, `~/.cache/huggingface/hub`에 캐시, 이후 재다운로드 없음) + 실제 구동 + Streamlit 브라우저(`172.16.4.228:8501`)에서 4개 에이전트 결과 표시 사용자 확인 완료. 트러블슈팅: `device_map="auto"`에 `accelerate` 누락 → 설치, PYTHONPATH=src 누락으로 재시작 시 `wafer_fa` 모듈 못 찾던 문제 → `PYTHONPATH=src streamlit run app.py`로 재기동.

**확정 사항** (grilling 완료, [ADR 0004](docs/adr/0004-llava-relay-no-langchain.md) 참고): 텔레메트리 불필요(결함 클래스+도메인 지식만, Phase 3 선행 불필요) / LLaVA(HF transformers 직접 로드, LangChain 없음) 4에이전트 통일, DefectDescriber만 이미지 입력 / 영어 추론 후 exaone3.5:7.8b(Ollama)로 한국어 번역 / Qdrant `wafer_defect_cases` 컬렉션(nomic-embed-text)은 지금 만들고 검색 로직도 구현, 케이스 데이터는 비워둔 채 백로그로 이관.

---

## Phase 2.5: 고객 데모용 대시보드 (선택, Optional)

목적: 영업/PoC 미팅용 폴리시드 UI. 필요 시에만 착수.

**도구: ThingsBoard** (TailAdmin에서 전환, [ADR 0003](docs/adr/0003-thingsboard-over-tailadmin-dashboard.md) 참고). IoT 텔레메트리+위젯 대시보드가 본업이라 참고 스크린샷(Lot 선택, 패턴별 결함 히트맵, Lot Trend, 임계값 슬라이더)과 자연스럽게 맞고, Phase 3(장비 로그)까지 같은 플랫폼으로 이어짐.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 2.5.1 | ThingsBoard 인스턴스 세팅 (self-hosted) | ThingsBoard 관리 콘솔 접속 가능 | - | cc:완료 |
| 2.5.2 | Stage 1/2 파이프라인용 REST/텔레메트리 연동 (분류 결과를 ThingsBoard로 전송) | ThingsBoard 대시보드에 분류 결과 데이터 수신 확인 | Phase 1, Phase 2, 2.5.1 | cc:TODO |
| 2.5.3 | 위젯 구성: Lot 선택 패널 / 패턴별 웨이퍼 수 테이블 / composite 웨이퍼맵 히트맵 / Lot Trend 차트 / 모델 임계값 슬라이더 | 참고 스크린샷과 동등한 5종 위젯이 대시보드에 표시 | 2.5.2 | cc:TODO |

**주의**: 착수 전 사용자가 "필요하다" 확정한 뒤에만 진행 (Optional, 현재 backlog) — 2026-07-22 사용자가 Phase 2.5 착수 직접 지시, 확정됨.
**UI 스타일 주의**: 제네릭 AI 룩 지양 — 사용자 확인된 피드백 ([[feedback-ui-style]] 메모리 참고).

**진행 메모 (2.5.1)**: `docker-compose.yml`에 `thingsboard-postgres`(postgres:16-alpine, 내부 전용) + `thingsboard`(thingsboard/tb-node:4.3.1.3) 서비스 추가. 호스트 포트 충돌 회피 위해 웹 UI는 8080 대신 **8082**로 매핑(1883/7070/8883/5683-5688은 기본값 유지, 전부 미사용 포트 확인 후 배정). `docker compose run --rm -e INSTALL_TB=true -e LOAD_DEMO=false thingsboard`로 스키마+시스템 데이터 설치(데모 데이터는 제외, 실제 웨이퍼 데이터로 채울 예정이라 불필요) 후 `docker compose up -d thingsboard`로 기동. 검증: `GET /login` → 200, `POST /api/auth/login`(sysadmin 기본 계정)으로 JWT 토큰 발급 확인. 콘솔: `http://<host>:8082` (기본 계정 sysadmin@thingsboard.org / sysadmin — 데모 종료 후 교체 권장).

---

## Phase 3: 장비 로그(가상 데이터) 상관관계 (선택, Optional)

목적: 사진만 보는 것보다 똑똑하게 — digital twin 시나리오의 장비 텔레메트리 연동.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 3.1 | 합성 장비 로그 생성기 (SECS/GEM 형태, 결함 클래스와 상관되게) | 결함 클래스별로 구분되는 합성 로그 데이터셋 생성 | Phase 1 | cc:TODO |
| 3.2 | ThingsBoard 텔레메트리 수집기로 합성 장비 로그 전송 + 상관관계 위젯 추가 | ThingsBoard 대시보드에 결함-로그 상관 시각화 1개 이상 표시 | 3.1, Phase 2.5 | cc:TODO |

**미확정 사항**: 합성 텔레메트리 생성 모델(규칙 기반 vs 실제 팹 분포 샘플링), 데모 목적상 필요한 "그럴듯함"의 수준.

**선반영**: SemiFA 참고해 TimescaleDB 컨테이너(`docker-compose.yml`, `wafer-fa-timescaledb`, localhost:5433, DB/user `wafer_fa`)와 빈 hypertable `equipment_telemetry`(time/wafer_id/defect_class/equipment_id/param/value)를 3.1 착수 전에 미리 만들어둠. 데이터 없음, 3.1의 합성 로그 생성기가 나중에 채움.

---

## 참고 문서

- `CONTEXT.md` — 도메인 용어집 (Wafer Map, Die, Defect Class, Digital Twin Feed)
- `docs/adr/0001-matrix-input-no-image-upload.md`
- `docs/adr/0002-frozen-dinov2-base-mlp-head.md`
- `docs/adr/0003-thingsboard-over-tailadmin-dashboard.md`
