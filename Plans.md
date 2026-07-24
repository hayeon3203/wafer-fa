# daol-fascope Plans.md

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
- 0.80 목표는 미달이나, 사용자 지시로 여기서 1단계 마무리하고 Streamlit 데모(1.9)로 진행. 추가 개선(백본 unfreeze, 처음부터 CNN 학습, ShuffleNet-v2 검토)은 시간 여유 시 별도 착수
- **향후(시간 여유 시) 별도 시도 후보**: [ShuffleNet-v2 + CNN transfer learning](https://www.hindawi.com/journals/amse/2022/1829792/) (Doss et al., 2022, *Advances in Materials Science and Engineering*)
  - 동일 WM-811K 데이터셋 사용, 저자 보고 수치 accuracy 96.93% / precision 95.40% / recall 96.26% / F1-score 95.75%.
  - **미검증 주의**: 페이월로 원문 전체 확인 못함 — F1이 macro-averaged인지 weighted/micro-averaged인지 불명확(accuracy와 F1이 매우 근접한 걸 보면 weighted일 가능성 있음, 우리 데이터처럼 극심한 불균형에서 macro F1이 이렇게 높게 나오긴 어려움). 착수 전 원문 확보해서 평가 프로토콜(클래스 불균형 처리, train/test 분할 방식) 재확인 필요.

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

**진행 메모 (2.1-2.5)**:
- 구현: `src/daol_fascope/relay.py`(LangGraph 4-노드 릴레이, LLaVA 직접 호출, exaone3.5:7.8b 번역) + `src/daol_fascope/cases.py`(Qdrant `wafer_defect_cases` 빈 컬렉션 + 검색), `app.py`에 배선.
- 테스트: `pytest tests/test_relay.py tests/test_cases.py` 통과(그래프 상태 전달·심각도 파싱은 mock, Qdrant 검색은 실제 서비스 대상 통합 테스트).
- 모델: `llava-hf/llava-1.5-7b-hf` 최초 다운로드(14GB, `~/.cache/huggingface/hub`에 캐시, 이후 재다운로드 없음) + 실제 구동 + Streamlit 브라우저(`172.16.4.228:8501`)에서 4개 에이전트 결과 표시 사용자 확인 완료.
- 트러블슈팅: `device_map="auto"`에 `accelerate` 누락 → 설치 / PYTHONPATH=src 누락으로 재시작 시 `wafer_fa` 모듈 못 찾던 문제 → `PYTHONPATH=src streamlit run app.py`로 재기동.

**확정 사항** (grilling 완료, [ADR 0004](docs/adr/0004-llava-relay-no-langchain.md) 참고):
- 텔레메트리 불필요(결함 클래스+도메인 지식만, Phase 3 선행 불필요)
- LLaVA(HF transformers 직접 로드, LangChain 없음) 4에이전트 통일, DefectDescriber만 이미지 입력
- 영어 추론 후 exaone3.5:7.8b(Ollama)로 한국어 번역
- Qdrant `wafer_defect_cases` 컬렉션(nomic-embed-text)은 지금 만들고 검색 로직도 구현, 케이스 데이터는 비워둔 채 백로그로 이관

---

## Phase 2.5: 고객 데모용 대시보드 (선택, Optional)

목적: 영업/PoC 미팅용 폴리시드 UI. 필요 시에만 착수.

**도구: ThingsBoard** (TailAdmin에서 전환, [ADR 0003](docs/adr/0003-thingsboard-over-tailadmin-dashboard.md) 참고). IoT 텔레메트리+위젯 대시보드가 본업이라 참고 스크린샷(Lot 선택, 패턴별 결함 히트맵, Lot Trend, 임계값 슬라이더)과 자연스럽게 맞고, Phase 3(장비 로그)까지 같은 플랫폼으로 이어짐.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 2.5.1 | ThingsBoard 인스턴스 세팅 (self-hosted) | ThingsBoard 관리 콘솔 접속 가능 | - | cc:완료 [99718e6] |
| 2.5.2 | Stage 1/2 파이프라인용 REST/텔레메트리 연동 (분류 결과를 ThingsBoard로 전송) | ThingsBoard 대시보드에 분류 결과 데이터 수신 확인 | Phase 1, Phase 2, 2.5.1 | cc:완료 [3d1fcb5] |
| 2.5.3 | 위젯 구성: Lot 선택 패널 / 패턴별 웨이퍼 수 테이블 / composite 웨이퍼맵 히트맵 / Lot Trend 차트 / 모델 임계값 슬라이더 | 참고 스크린샷과 동등한 5종 위젯이 대시보드에 표시 | 2.5.2 | cc:완료 [2ba81a2] (브라우저 시각 확인은 사용자 몫, 아래 메모 참고) |

**주의**:
- 착수 전 사용자가 "필요하다" 확정한 뒤에만 진행 (Optional, 현재 backlog) — 2026-07-22 사용자가 Phase 2.5 착수 직접 지시, 확정됨.
- **UI 스타일**: 제네릭 AI 룩 지양 — 사용자 확인된 피드백 ([[feedback-ui-style]] 메모리 참고).

**진행 메모 (2.5.1)**:
- `docker-compose.yml`에 `thingsboard-postgres`(postgres:16-alpine, 내부 전용) + `thingsboard`(thingsboard/tb-node:4.3.1.3) 서비스 추가.
- 포트: 호스트 포트 충돌 회피 위해 웹 UI는 8080 대신 **8082**로 매핑(1883/7070/8883/5683-5688은 기본값 유지, 전부 미사용 포트 확인 후 배정).
- 설치: `docker compose run --rm -e INSTALL_TB=true -e LOAD_DEMO=false thingsboard`로 스키마+시스템 데이터 설치(데모 데이터는 제외, 실제 웨이퍼 데이터로 채울 예정이라 불필요) 후 `docker compose up -d thingsboard`로 기동.
- 검증: `GET /login` → 200, `POST /api/auth/login`(sysadmin 기본 계정)으로 JWT 토큰 발급 확인.
- 콘솔: `http://<host>:8082` (기본 계정 sysadmin@thingsboard.org / sysadmin — 데모 종료 후 교체 권장).

**2.5.3 스코프 재확정 (grilling, 2026-07-22)**: 착수 전 사용자와 논의해서 원래 계획을 크게 조정함.
- **Streamlit의 역할 재정의**: Streamlit은 초기 기능 테스트용이었고, ThingsBoard가 최종 데모 화면(모니터링 + 원인분석 + 향후 Phase 3까지) 역할을 흡수하기로 확정.
- **수율(Yield) 정의**: die-level 채택 — 매트릭스 값(0=no die/1=정상/2=결함)에서 직접 계산(`render.compute_die_yield`), 정상다이/(정상+결함다이).
- **참고 이미지 2개**: `data/dashboard_sample.png`(Tableau 스타일, Lot선택/패턴별카운트/composite히트맵/LotTrend/임계값), `data/dashboard_sample2.png`(전공정 팹 모니터링 대시보드, 그리드형 다중 패널 레이아웃 — 전공정 텔레메트리 자체가 지금 데이터엔 없어서 해당 패널들은 Phase 3 예정 placeholder로 처리).
- **대시보드 구조 (1차: 3-state 탭 → 2차: 별도 대시보드 2개로 재구성)**: 처음엔 ThingsBoard 대시보드 1개에 state(탭) 3개(Monitoring/Root Cause/Process)로 만들었으나, 사용자가 원했던 건 "전체 개요 대시보드 1개 + 세부 웨이퍼맵 대시보드 1개"의 **별도 대시보드 2개** 구성이라 재작업. 최종 구조:
  - **Wafer Overview** (`data/dashboard_sample2.png` 레이아웃 참고 — 그리드형 제어실 스타일): 결함 검출 개요(전체 클래스별 카운트, 왼쪽), Wafer Yield Map(최근 웨이퍼 이미지+수율%+예측결과, 중앙 대형), Process Risk & Alerts(최근 심각도/원인/조치, 오른쪽), 하단 3칸은 Phase 3 placeholder(설비 텔레메트리/공정 위험지표/공정 단계 타임라인).
  - **Wafer Detail** (`data/dashboard_sample.png` 레이아웃 참고): Lot Analysis 콤보(검색+리스트+패턴별카운트테이블+트렌드, 좌측 넓게), Composite 히트맵 갤러리(우측), Wafers from Data 샘플 갤러리(하단 전체폭, 클래스당 4장씩 실제 웨이퍼 썸네일), 임계값 슬라이더 + 원인분석 요약(하단 우측 2칸).

**트러블슈팅 노트 (향후 ThingsBoard 위젯 작업 시 참고, 2026-07-23 정정)**:
- 대시보드 위젯의 `typeFullFqn`은 **시스템/테넌트 위젯 둘 다 반드시 `system.` 또는 `tenant.` 접두사 필요**(예: `system.cards.html_value_card`, `tenant.wafer_fa_lot_analysis`).
- 접두사 없으면 JSON 저장 자체는 200으로 성공하지만 브라우저에서 "연결된 위젯 타입이 삭제되었습니다" 에러 발생.
- 서버 `thingsboard.jar`의 `WidgetTypeController.getWidgetType(fqn)`을 `javap -c`로 직접 디컴파일해 확인함 — `fqn.split("\\.")`한 첫 조각이 `"system"`/`"tenant"` 둘 중 하나가 아니면(즉 접두사 없이 bare fqn이면) `ThingsboardException("Invalid fqn!", BAD_REQUEST_PARAMS)`를 그대로 던짐, tenant로 암묵 fallback 같은 거 없음.
- (이전 버전 노트에 "tenant 커스텀 위젯타입은 접두사 없이 그대로 사용"이라고 적혀 있었는데 틀린 내용이었음 — 2.5.3에서 만든 커스텀 위젯 4개가 전부 이 버그로 깨져있었고, 라이브 DB `dashboard.configuration`/`create_widget_type()` 반환값에 `tenant.` 접두사 붙이는 걸로 수정함.)

**진행 메모 (2.5.2)**:
- `lot_id`/`wafer_index`는 원본 `LSWMD.pkl`에 있던 `lotName`/`waferIndex`를 Stage 1에서는 버렸었음 — `data_prep.py`를 확장해(동일 `random_state=42` split이라 기존 분할 그대로 유지) `manifest.csv`에 두 컬럼 추가, 재실행(14초, 172,950건). 런타임마다 원본 pkl을 다시 읽는 대신 오프라인에서 한 번만 계산해 데모 응답속도 확보.
- Tenant/Device 프로비저닝: sysadmin으로 tenant `daol-fascope` + tenant admin 계정 생성(LOAD_DEMO=false라 기본 tenant/customer 계정 없음, 자격증명은 비공개로 별도 보관·git 미커밋), device `daol-fascope-pipeline` 생성 후 access token 발급(토큰도 비공개 보관).
- `src/daol_fascope/telemetry.py`(`THINGSBOARD_DEVICE_TOKEN` env, HTTP device API `/api/v1/{token}/telemetry`, 네트워크 실패 시 예외 삼키고 False 반환 — 대시보드 다운돼도 데모 안 끊기게) 추가, `app.py`에서 릴레이 완료 직후(심각도 포함) 전송하도록 배선.
- 테스트: `pytest tests/test_telemetry.py` 통과(no-token/성공/네트워크 예외 3 케이스, requests.post mock).
- 실제 전송 검증: 샘플 텔레메트리 전송 후 `GET /api/plugins/telemetry/DEVICE/{id}/values/timeseries`로 lot_id/wafer_index/defect_class/confidence/prob_*/severity 전부 수신 확인. Streamlit 서버(`172.16.4.228:8501`)를 `THINGSBOARD_DEVICE_TOKEN` env 포함해 재기동.

**진행 메모 (2.5.3)**:
- telemetry 페이로드 확장(`die_yield`/`die_yield_pct`, `description`, `root_cause`, `recipe`, `wafer_image` base64, `render.compute_die_yield` 신규 + 테스트).
- `src/daol_fascope/composite.py`: 클래스별 실제 다이 단위 평균(NEAREST 리사이즈 후 defect비율/coverage 계산, 3단 그라디언트 색상) composite 히트맵 계산 — Center 패턴은 중심부 hot spot이 뚜렷하게 나옴(물리적으로 타당).
- `src/daol_fascope/build_dashboard_data.py`: manifest 전체(클래스당 최대 3000 샘플)로 9개 composite PNG + `lot_pattern_counts`(lot×label 카운트, 10,762 lot) + `sample_wafers`(클래스당 4장, 실제 웨이퍼 썸네일+정답라벨) 계산 후 device client attribute로 push(~1.4초).
- `src/daol_fascope/setup_thingsboard_dashboard.py`: ThingsBoard REST로 커스텀 위젯타입 4개(Lot Analysis 콤보, Threshold Slider, Class Overview — lot_pattern_counts를 전체 집계해 막대로, Wafer Gallery — sample_wafers를 그리드로) + 시스템 위젯 재사용(`system.cards.html_value_card`=Yield Map/Risk&Alerts/Composite갤러리/원인분석요약, `system.cards.html_card`=Phase 3 placeholder) 조합해 **Wafer Overview + Wafer Detail 별도 대시보드 2개** 생성(REST `POST /api/dashboard` 2회).
- 검증: JSON 스키마 유효성(서버 200 응답, GET으로 구조/fqn 재확인)은 확인했으나 **브라우저 렌더링(커스텀 JS 위젯 동작, 실제 레이아웃 비율)은 claude-in-chrome 미연결로 직접 확인 못함 — 사용자가 `http://172.16.4.228:8082`에서 "Wafer Overview"/"Wafer Detail" 두 대시보드 눈으로 확인 필요**.

**TODO (미연결 배선)**:
- `모델 임계값 슬라이더`(`confidence_threshold` attribute)는 현재 위젯이 값 저장(write)/표시(read-back)만 하고, 실제 파이프라인(`infer.py`/`relay.py`/`app.py`) 어디서도 이 값을 읽지 않음 — UI만 있고 기능 미배선.
- `confidence`는 `app.py`에서 `classify_matrix()`(DINOv2 9-클래스 softmax) 결과 중 예측 라벨(`max(probs, key=probs.get)`)의 확률값.
- 추후 이 슬라이더 값을 예측 confidence 임계값으로 써서(예: 임계값 미만이면 "불확실한 예측"으로 별도 표시하거나 알림 억제) 실제 배선할 예정.

---

## Phase 2.5.4: ThingsBoard 통합 실행 버튼 + 파이프라인 진행 시각화 (grilling 완료, 2026-07-23)

목적: Phase 3 진입 전, Phase 1/2 전체 파이프라인(분류→4-agent relay)을 Streamlit이 아닌 ThingsBoard 안에서 버튼 하나로 실행·확인. "지금 어느 단계를 지나는지" 5단계 진행바로 실시간 시각화.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 2.5.4.1 | 대시보드 이름 스왑 (Wafer Detail↔Wafer Overview) | ThingsBoard 콘솔에서 두 대시보드 제목이 뒤바뀌어 표시 | 2.5.3 | cc:완료 (사용자가 이 grilling 세션 이전에 TB 브라우저 UI에서 직접 이미 스왑해둠 — 확인만 함) |
| 2.5.4.2 | `wafer_predict_server.py`(:8092) 신설 — 랜덤 샘플 뽑기+classify+relay 4-node 실행, in-flight lock, `pipeline_stage` telemetry push(idle/classify/describe/root_cause/severity/recipe/done/error) | 요청 시 202 즉시 응답, 단계별 telemetry가 ThingsBoard에 순서대로 수신 확인 | 2.5.4.1 | cc:완료 (TDD, `pytest tests/test_wafer_predict_server.py` 통과. 실제 :8092 기동+브라우저 확인은 사용자 몫) |
| 2.5.4.3 | `relay.py` 4개 노드 함수에 단계 시작 시 telemetry push 훅 추가 | 노드 진입 시점마다 `pipeline_stage` 값 갱신 확인 | 2.5.4.2 | cc:완료 (2.5.4.2와 같은 diff로 병합 진행 — `run_relay(..., on_stage=...)` 콜백 추가, `pytest tests/test_relay.py` 통과) |
| 2.5.4.4 | `app.py`에서 relay(Phase 2) 실행 코드 제거, 새 서버로 완전 이관 | `app.py`가 더 이상 LLaVA/relay 호출 안 함 | 2.5.4.2 | cc:완료 (Stage 1 classify만 남김, telemetry 전송도 제거 — app.py는 이제 로컬 스모크테스트 전용) |
| 2.5.4.5 | Wafer Detail 대시보드(=Defect Detection/Wafer Yield Map/Process Risk&Alerts가 있는 쪽)의 "공정 단계 타임라인" Phase3 placeholder 자리(row10 col6, 12x6, 라이브에도 아직 존재 확인됨)를 버튼+5노드 진행바 커스텀 위젯으로 교체 | 버튼 클릭 시 5박스가 회색/주황/흰색/빨강으로 실시간 갱신되는 게 브라우저에서 확인됨 | 2.5.4.1, 2.5.4.3 | cc:완료 (`--apply-pipeline-progress` 실행 완료, dashboard id `b4a41820-85af-11f1-b7a9-c1826206c77f`, fqn `tenant.wafer_fa_pipeline_progress`. 실제 버튼 클릭+박스 색 갱신 브라우저 확인은 사용자 몫 — :8092 서버 떠 있어야 함) |

**진행 메모 (2.5.4.1)**: `setup_thingsboard_dashboard.py`의 `build_overview_dashboard()`/`build_detail_dashboard()` 함수명·`make_dashboard("Wafer Overview"/"Wafer Detail", ...)` 문자열은 여전히 예전(스왑 전) 이름 그대로 — 라이브 TB 제목은 사용자가 UI에서 직접 스왑해서 지금은 함수명과 실제 제목이 반대로 매핑됨. 당장 문제는 아니지만 헷갈리지 않게 참고.

**버그 발견+수정 (2026-07-23)**:
- TB UI의 대시보드 Rename은 `dashboard.title`만 바꾸고 `configuration.states.default.name`(대시보드 상단 breadcrumb이 실제로 읽는 값)은 안 건드림 — 스크립트가 처음 만들 때 `make_dashboard(title, ...)`이 이 둘을 같은 문자열로 같이 박아넣지만 그 이후론 독립된 필드라, UI에서 title만 바꾸면 둘이 벌어짐.
- 두 대시보드 다 title은 스왑됐는데 state.name은 스왑 전 값 그대로 남아있던 것 확인 — GET 대시보드 config → `states.*.name`을 `title`로 맞춰서 PUT(update-in-place)으로 수정함(tenant admin API, 2026-07-23).

**진행 메모 (2.5.4.5)**:
- `setup_thingsboard_dashboard.py`에 `PIPELINE_PROGRESS_HTML/CSS/JS`(버튼+5박스, `:8092`에 fetch POST, `pipeline_stage`/`pipeline_stage_error_node` telemetry 구독해서 박스 색 계산) + `apply_pipeline_progress_widget()`(라이브 "Wafer Detail" 대시보드 GET → "공정 단계 타임라인" placeholder 위젯만 새 위젯으로 교체 → POST로 update-in-place, 나머지 위젯은 안 건드림) 작성.
- 실행: `THINGSBOARD_ADMIN_USERNAME=admin@wafer-fa.local THINGSBOARD_ADMIN_PASSWORD=(비공개 보관) THINGSBOARD_DEVICE_ID=dd9d5c40-8588-11f1-8306-c1826206c77f python -m daol_fascope.setup_thingsboard_dashboard --apply-pipeline-progress`로 2026-07-23 라이브 반영 완료.
- (tenant admin 로그인 이메일 `admin@wafer-fa.local` 자체는 실제 계정 식별자라 리네임 대상에서 제외 — TB 쪽 tenant/device 이름은 이번 리네임에서 안 건드림, 아래 "프로젝트 리네임" 메모 참고)

**프로젝트 리네임 (2026-07-23, 사용자 지시)**: 서비스명 "Wafer-FA" → **"Daol FAScope"**로 확정.
- 리포 디렉토리 `/home/admin/wafer-fa` → `/home/admin/daol-fascope` 이동, 파이썬 패키지 `src/wafer_fa/` → `src/daol_fascope/`(모든 `import`/테스트 갱신, `pytest` 34개 통과 확인).
- 문서(Plans.md/CONTEXT.md/plans 하위 harness 파일)·코드(Streamlit 페이지 제목, ThingsBoard 위젯 표시명) 상의 "Wafer-FA"/"wafer-fa" 텍스트 "Daol FAScope"/"daol-fascope"로 교체.
- 단, 실제 라이브 자격증명(tenant admin 이메일 `admin@wafer-fa.local`)·이미 초기화된 TimescaleDB의 `POSTGRES_DB/USER=wafer_fa`·과거 트러블슈팅 기록에 나오는 실제 fqn 값(`tenant.wafer_fa_lot_analysis` 등)은 안 건드림(현재 상태와 실제 라이브 값이 어긋나면 더 혼란스러워서 의도적으로 스킵).
- Docker 컨테이너 `wafer-fa-thingsboard`/`wafer-fa-tb-postgres`/`wafer-fa-timescaledb` → `daol-fascope-*`로 재생성. **볼륨은 기존 `wafer-fa_*` 볼륨에 `external: true`로 고정 바인딩**(디렉토리 리네임으로 Compose 기본 프로젝트명이 바뀌면서 그냥 `up`하면 새 빈 볼륨을 만들 뻔한 함정 — `docker-compose.yml` 참고) — 재생성 후 대시보드 2개/텔레메트리 이력 전부 보존 확인.
- **ThingsBoard 콘솔 브랜딩(탭 제목/파비콘) 시도 → 실패+롤백**: `thingsboard.jar` 안의 nested jar(`BOOT-INF/lib/ui-ngx-4.3.1.3.jar`) 안 `public/index.html`(제목)/`public/thingsboard.ico`(파비콘)을 고쳐서 `jar uf`로 재패킹 시도 — 바깥 jar가 416MB→20MB(entry 1개만 남음)로 깨짐. 즉시 컨테이너 내리고 원본 이미지(`thingsboard/tb-node:4.3.1.3`, 미변경)로 재생성해서 복구, 데이터 손실 없음 확인. **탭 제목/파비콘은 여전히 기본 "ThingsBoard"로 남아있음 — 재시도 여부 미정(cc:TODO 아님, 사용자 판단 대기)**.
- TB 쪽 tenant 이름("wafer-fa")/device 이름("wafer-fa-pipeline")은 이번 리네임 범위에서 제외(로그인 자격증명과 얽혀있고 실제 데모 화면엔 안 보이는 admin 전용 정보라 리스크 대비 효과 낮다고 판단).

**확정 사항** (grilling 완료, [ADR 0005](docs/adr/0005-dedicated-warm-prediction-server.md) 참고):
- 새 서버가 LLaVA+DINOv2 유일한 warm 프로세스(이중 로딩 방지 위해 `app.py`의 relay 코드는 삭제)
- fire-and-forget 비동기 + in-flight lock(중복 실행 거부)
- 진행 상태는 오직 `pipeline_stage` telemetry로만 판단(별도 status API 없음, 위젯은 자기 단계 index와 최신값 비교로 색 계산)
- 5단계는 `CONTEXT.md`의 "Pipeline Stage" 참고(Classify/Describe/RootCause/Severity/Recipe)
- 결과 표시용 위젯은 별도 신설 안 함 — 개명 후 Wafer Detail의 기존 Yield Map/Risk&Alerts가 같은 device latest telemetry 구독이라 자동 갱신됨
- 색상: 지나간=`#e0e0e0`, 현재=`#ff9800`(주황, 기존 `#3f51b5`/`#e53935`과 의미 충돌 피함), 미도달=흰색+`#ddd` 테두리, 에러=`#e53935`

---

## Phase 3: 장비 로그(가상 데이터) 상관관계 (선택, Optional)

목적: 사진만 보는 것보다 똑똑하게 — digital twin 시나리오의 장비 텔레메트리 연동.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 3.1 | 합성 장비 로그 생성기 (SECS/GEM 형태, 결함 클래스와 상관되게) | 결함 클래스별로 구분되는 합성 로그 데이터셋 생성 | Phase 1 | cc:완료 (재설계, 아래 "3.1 재설계" 참고) |
| 3.2 | ThingsBoard 텔레메트리 수집기로 합성 장비 로그 전송 + 상관관계 위젯 추가 | ThingsBoard 대시보드에 결함-로그 상관 시각화 1개 이상 표시 | 3.1, Phase 2.5 | cc:완료 (라이브 TB 반영 완료, 브라우저 시각 확인은 사용자 몫 — 아래 "진행 메모" 참고) |

**확정 사항 (3.1 스펙)**:
- **데이터 소스**: Kaggle UCI SECOM(`paresh2047/uci-semcom`, 1567x590 anonymized feature + pass/fail). SECOM은 절대 엔티티로 편입 안 함 — **spine은 WM-811K/manifest 쪽 실제 `wafer_id`**(Phase1부터 이미 이미지/telemetry/ThingsBoard가 전부 이 wafer_id로 join됨). SECOM은 클러스터 통계치(평균/표준편차/공분산)만 1회 추출해 재사용하는 샘플링 소스일 뿐, 실제 로그 row는 manifest의 진짜 wafer_id마다 생성. (반대로 SECOM row에 9class를 붙이는 방식은 기각 — 기존 파이프라인과 wafer_id로 join 안 되는 고아 데이터셋이 됨.)
- **전처리**: feature별 결측률 50% 초과면 drop, 나머지만 후보 pool.
- **클러스터링**: 후보 feature 상관행렬 기반 hierarchical clustering, **K=9 (WM-811K 9class와 1:1 매핑, 클래스 수를 따름)**. 클러스터ID를 `equipment_id`로 사용(숫자만, 예 `EQP_1`~`EQP_9`, 의미 이름 안 붙임). `param`은 원본 `feature_N` 그대로(익명 유지, 리네이밍 안 함 — 값 범위/분포로 물리량 추정해 라벨 붙이는 것도 기각. SECOM은 confidentiality 때문에 의도적으로 이름 제거된 데이터셋이라 range matching은 근거 없는 추측. 행사 시연시 "실제 팹은 공정 파라미터 대외비라 익명 처리" 스토리로 대응).
  - **주의**: 이 클러스터링 방식은 이후 "3.1 재설계"에서 폐기됨 — 아래 참고.
- **결함클래스 → root cause 매핑** (문헌 근거, Wu/Jang/Chen 2015 IEEE TSM 원 논문 기준 + 보조 자료):

  | 결함 클래스 | 추정 원인 |
  |---|---|
  | Center | 필름 증착(film deposition) 이상 |
  | Edge-Ring | 에칭 문제 또는 불균일 온도 분포 |
  | Scratch | 제조 공정 중 물리적 스크래치(기계 핸들링) |
  | Random | 먼지/화학 잔류물 — **공정-비체계적, 상관관계 약하게/없게 생성**(baseline과 유사) |
  | Donut | 포토레지스트 clean 공정 residue 미제거 |
  | Edge-Loc | 비정상 열처리(annealing) 또는 load-lock valve 오염 |
  | Loc | 불균일 clean 또는 wafer-chuck 계면 particle 오염(웨이퍼 뒷면-척 사이 입자가 국소 높이 왜곡 유발) — Random(클린룸 부유 먼지, 장비 비특이적)과 달리 특정 장비 chuck 이슈로 특정 가능 |
  | Near-full | 여러 요인 동시 발생한 치명적 공정 이탈 — 다중 클러스터 동시 큰 폭 shift |
  | none | baseline, shift 없음 |

  - 근거: [Wafer Map Failure Pattern Recognition and Similarity Ranking (Wu, Jang, Chen, IEEE TSM 2015)](https://www.semanticscholar.org/paper/Wafer-Map-Failure-Pattern-Recognition-and-Ranking-Wu-Jang/a581566276f3b2242ec6544c185204a96f17db8a), [WM-811K wafer patterns 그림 설명](https://www.researchgate.net/figure/Used-wafer-patterns-of-WM-811K-for-this-study-Near-full-and-none-patterns-are-excluded_fig3_370900183), [across-wafer uniformity control in plasma etch](https://sst.semiconductor-digest.com/2016/08/evolution-of-across-wafer-uniformity-control-in-plasma-etch/), [Design of particle mitigating wafer chucks for yield enhancement](https://repositories.lib.utexas.edu/items/a8e4ba86-c5d6-4981-b554-0ec057c91d63)
- **shift 강도**: ±2 std (baseline mean 대비 매핑된 클러스터 feature들에 적용).
- **샘플링 방식**: 순수 row bootstrap 기각 (SECOM 1567행 << manifest 172,950 wafer_id라 중복 심함). 클러스터별(9개, 각 5~10 feature) 실제 SECOM 행에서 **mean vector + 공분산행렬** 추정 후 `numpy.random.multivariate_normal(mean, cov, size=N)`으로 매 wafer_id마다 새로 샘플링. feature간 실제 상관구조는 보존하면서(단순 독립 정규분포와 차이점) 무한히 서로 다른 값 생성(bootstrap의 중복 문제 회피). shift는 이 mean vector에 ±2std 더한 뒤 같은 공분산으로 샘플링.
- **규모**: manifest 전체 172,950 wafer 다 사용(3000 cap 없음). `build_dashboard_data.py`(composite 히트맵용, 클래스당 3000 샘플)는 이미 배포/검증 끝난 별개 코드라 그대로 둠 — 이번 3.1만 전체 스케일로 감. TimescaleDB hypertable은 원래 이 규모 위한 물건이라 무리 없음.
- **`wafer_id` 구성**: manifest엔 `wafer_id` 컬럼 자체가 없음(`split,path,label,lot_id,wafer_index`) — `f"{lot_id}_{wafer_index}"`로 합성. 기존 `telemetry.py`/Wafer Detail 대시보드가 이미 lot_id+wafer_index 기준으로 조회하는 관례라 그대로 따라감.
- **클러스터↔결함클래스 배정**: SECOM 클러스터는 feature 상관관계로만 묶인 통계적 그룹이라(feature 익명이라 실제 물리적 의미 검증 불가) 클래스 배정 자체가 근본적으로 임의(arbitrary) — **클러스터를 분산(variance) 내림차순 정렬 후 `labels.py`의 `CLASSES` 순서대로 1:1 매칭**. 재현 가능(고정 규칙)하기만 하면 되고 억지 인과관계 안 만듦.
- **`time` 컬럼**: manifest에 wafer별 실제 타임스탬프 없음 — **적재 시점 기준 최근 30일 사이에 균등 분산**(lot_id/wafer_index 순서를 시간순 proxy로 매핑). 근거 타임스탬프가 없어 실제 처리순서 재현은 불가능하고, ThingsBoard 기본 시간범위 위젯에 걸리게만 하면 됨(행사 데모 시점 기준 "최근 데이터"로 보이는 게 목적). 배치는 오프라인 1회 생성이라 재생성 시 재현성 이슈 없음(seed 논의는 불필요 — 한 번 만들고 끝).
- **실행 방식**: 기존 `build_dashboard_data.py`와 같은 오프라인 배치 패턴(1회 실행 후 TimescaleDB에 적재, 위젯은 읽기만). 기존 코드베이스에 TimescaleDB 연결/적재 코드가 아직 없음(`db/init.sql`만 존재) — 3.1에서 새로 작성 필요.

**설계 확정 완료**: 남은 건 구현(코드 작성)뿐.

**진행 메모 (3.1)**:
- 구현: `src/daol_fascope/equipment_log.py`(클러스터링+매핑+샘플링 핵심 로직) + `src/daol_fascope/build_equipment_log.py`(오프라인 배치, `build_dashboard_data.py`와 같은 패턴).
- 테스트: `pytest tests/test_equipment_log.py tests/test_build_equipment_log.py` 16개 통과(합성 데이터로 클러스터링/매핑/shift 로직 검증, 실제 SECOM·DB 의존 없음).
- 데이터 확보: 실제 SECOM 데이터는 Kaggle API 인증 미설정 상태라 **동일 데이터셋의 UCI 원본 미러**(`archive.ics.uci.edu/static/public/179/secom.zip`, 파일 바이트 동일)에서 받아 `data/raw/secom/`에 저장(`data/`는 gitignore 대상).
- **클러스터링 특성 발견**: `scipy.cluster.hierarchy.fcluster(..., criterion="maxclust")`가 최댓값(1.0) 거리에서 116개 병합이 동타이로 몰려있어 9클러스터 요청에 1클러스터로 붕괴하는 문제 확인 → `cut_tree(Z, n_clusters=9)`(병합 순서 기준 절단, 높이 임계값 아님)로 교체해 해결. 실제 결과: 9클러스터 중 2개(Center→10 feature, Donut→10 feature)만 유의미한 크기, 나머지 7개는 전부 1-feature 싱글턴 — SECOM 익명 신호 590개 중 실제로 서로 상관된 건 소수뿐이라는 데이터셋 자체의 알려진 특성(노이즈 심함)이지 버그 아님, 프로젝트의 "근거 없는 추측 안 함" 원칙과도 부합해 그대로 반영.
- **Near-full 스펙 결정**: "다중 클러스터 동시 shift"는 구체적 클러스터 선택 기준이 없어 임의 결정 — **Random/none을 제외한 나머지 7개 클래스 소유 클러스터 전부 동시 shift**(여러 요인 동시 발생이라는 의도에 맞고 결정적·재현 가능).
- **배치 실행**: `PYTHONPATH=src python -m daol_fascope.build_equipment_log`로 172,950 wafer 전체 처리, TimescaleDB `equipment_telemetry`에 4,669,650행 적재(9class × 9equipment 조합, `psycopg` COPY, 클래스별 그룹 단위 벡터화 샘플링이라 전체 실행 수 초 내 완료).
- **검증**: `EQP_1`(Center 소유) 그룹별 평균 조회 시 Center 5082 / Near-full 5200 vs 나머지 클래스(Donut~none) 461~511로 명확히 분리 확인, `time` 컬럼 최근 30일 범위 확인.
- **TODO(3.2 선행 필요)**: 위 결과는 DB 적재까지만 — ThingsBoard 상관관계 위젯은 3.2 범위.

**선반영**: SemiFA 참고해 TimescaleDB 컨테이너(`docker-compose.yml`, `daol-fascope-timescaledb`, localhost:5433, DB/user `wafer_fa`)와 빈 hypertable `equipment_telemetry`(time/wafer_id/defect_class/equipment_id/param/value)를 3.1 착수 전에 미리 만들어둠. 데이터 없음, 3.1의 합성 로그 생성기가 나중에 채움.

**3.1 재설계 (grilling 완료, 2026-07-23)**: 3.2 설계 중 "장비(equipment) 클러스터링"이 부자연스럽다는 문제제기로 3.1을 재검토, 클러스터링 접근을 폐기함.
- **재검토 계기**: 실제 SECOM 상관행렬로 `ward` linkage/silhouette score까지 다 테스트해봤지만 silhouette이 k=3→30 구간에서 단조증가(뚜렷한 elbow 없음) — 이 데이터엔 "자연스러운 장비 개수"라는 게 애초에 없음이 확인됨. 그러면 K=9든 클러스터링 방식이든 결국 어차피 임의적인 선택이라, 차라리 더 단순하고 정직한 방식으로 가기로 함.
- **장비(equipment) 레이어 자체를 폐기**: SECOM 공식 문서(`secom.names`)상 각 feature는 "sensors and/or process measurement points" — 센서 하나 단위지 장비 하나가 아님(장비 하나=센서 여러개가 맞는 모델이긴 하나, 몇 개 장비로 나눌지에 대한 데이터 근거가 없어 그 매핑 자체를 걷어냄). 대신 **센서(feature_N) 562개를 1차 시민으로** 다룸.
- **클러스터링 → 랜덤 배정**: 결측률 50% 초과 제거 후 남은 562개 후보 feature를 `cut_tree`/`ward` 등 클러스터링 없이 **랜덤으로 9그룹(클래스당 ~62개, seed=42 고정 재현가능)에 배정**. 이미 "클래스 배정 자체가 근본적으로 임의"라고 기존에도 인정했던 것과 같은 맥락 — 클러스터링이 주는 "그럴듯함"이 사실은 허상이라 걷어냄.
- **`equipment_id` 컬럼**: 스키마(long format, `db/init.sql`)는 안 바꿈. 값은 `param`과 동일하게 채움(장비 그룹 개념이 없어졌으니 사실상 중복 컬럼이지만, 스키마 마이그레이션 안 하기로 함).
- **장비명 네이밍(EQP_1=증착챔버 등) 전부 폐기**: 장비 레이어가 없어졌으니 붙일 대상이 없음 — `feature_N` 그대로 노출.
- **"상관관계 배정의 임의성"과 "상관관계 자체의 강도"는 별개임을 확인**: 어느 센서가 어느 클래스 그룹에 속하는지는(랜덤이든 클러스터링이든) 필연적으로 임의적이지만(SECOM이 confidentiality로 익명화된 데이터라 물리적 의미 검증 불가), 클래스↔그룹 상관관계 자체는 `mean + 2*std` shift로 코드가 매 wafer마다 강제로 만드는 신호라 배정 방식과 무관하게 항상 강하게 나옴(실측: EQP_1 그룹 평균이 Center는 5082, 나머지 클래스는 461~511).
- shift 로직(own 그룹 소유 클래스만 +2σ, Random/none은 baseline, Near-full은 Random/none 제외 나머지 7개 그룹 전부 동시 co-shift)은 변경 없음.
- **재구현 필요**: `equipment_log.py`의 `cluster_features`/`assign_clusters_to_classes`/`select_representative_features` 삭제 → `assign_features_randomly`로 교체. 행 수는 172,950 wafer × 562 feature ≈ 9700만행(캡 없음, 기존 460만행보다 20배) — 데이터 손실 없이 다 씀. 기존 `equipment_telemetry` 467만행(구 클러스터링 모델 결과물)은 TRUNCATE 후 재적재.

**3.2 확정 사항 (grilling 완료, 2026-07-23)**: 원래 계획은 상관관계 위젯을 Detail에 넣는 거였으나, grilling 중 Overview(라이브 제목 기준 — Lot/Composite/갤러리형 대시보드)로 옮기고 Detail(그리드형, placeholder 2칸 남은 쪽)엔 다른 걸 채우는 걸로 재구성.
- **데이터 접근**: TimescaleDB `equipment_telemetry`를 ThingsBoard가 직접 못 읽으므로(TB CE엔 PostgreSQL datasource 없음), 새 경량 REST 서버 신설(`:8093`, `wafer_browser_server.py`류 패턴 — GPU 붙은 `wafer_predict_server`:8092와는 분리, 관심사 안 섞음).
- **Overview에 추가할 위젯 (신규 커스텀 위젯 1개)**: 드래그앤드롭 산점도. 562개 센서 검색 가능한 팔레트에서 2개를 골라 X/Y 드롭존에 드래그하면, 그 두 센서의 실제 값 산점도를 결함클래스별 색 구분으로 렌더(클래스당 최대 200개 샘플링, 172,950 전체는 렌더 비용상 과함). "센서 N개+클래스 M개 드래그 → 미니 히트맵" 형태는 백로그로 이관(3.2 범위 아님).
- **Detail "설비/공정 텔레메트리" placeholder 교체**: 현재 표시 중인 웨이퍼(Yield Map 위젯이 읽는 것과 같은 device latest telemetry의 lot_id/wafer_index)의 소유 클래스 그룹(~62개 센서) 전부를 스크롤 테이블로 표시(컬럼: param/value/baseline평균/편차).
- **Detail "공정 위험 지표" placeholder 교체**: 같은 편차 계산 재사용, "|z-score|>2인 센서 N개" 요약 경고 카드(SHIFT_STD=2.0과 동일 기준 재사용, 새 임계값 발명 안 함).
- **Overview 위젯**: 특정 lot/wafer 선택 없이 전체 데이터 기준 글로벌 뷰(기존 "결함 검출 개요"류 위젯과 같은 성격).

**진행 메모 (3.1 재설계 구현, 2026-07-23)**:
- `equipment_log.py`의 `cluster_features`/`assign_clusters_to_classes`/`select_representative_features` 삭제, `assign_features_randomly`(seed=42 고정, `np.array_split`로 9그룹 균등 분배)로 교체. `build_equipment_log.py`도 맞춰 수정(`equipment_id` 컬럼 값을 `param`과 동일하게 채움).
- 대량 삽입 성능 때문에 `insert_chunk`를 `write_row` 루프에서 `to_csv` 기반 벌크 TSV COPY로 교체(9700만행 규모에서 row-by-row는 너무 느림).
- 테스트: `pytest tests/test_equipment_log.py tests/test_build_equipment_log.py` 16개 통과.
- 재적재: 기존 `equipment_telemetry` 467만행 TRUNCATE 후 재적재: 172,950 wafer × 562 sensor = **97,197,900행** 적재 완료(클래스별 그룹 크기: Center/Donut/Edge-Loc/Edge-Ring 63개, 나머지 5개 62개).
- 검증: `feature_221`류 편차 확인, Center 소유 그룹이 Center/Near-full 웨이퍼에서만 체계적으로 shift되고 다른 클래스에서는 baseline인 것 재확인.

**진행 메모 (3.2 구현, 2026-07-23)**:
- `src/daol_fascope/equipment_log_server.py`(:8093, `wafer_browser_server.py`류 stdlib-only 패턴) 신설 — `/api/sensors`(562개 목록), `/api/scatter?x=&y=`(두 센서 값 wafer_id 기준 join, 클래스당 최대 200개 샘플링), `/api/wafer-sensors?lot_id=&wafer_index=`(그 웨이퍼 소유 클래스 그룹 전체 + baseline 대비 편차, `deviation_std` 내림차순 정렬) 3개 엔드포인트.
- `db/init.sql`에 `idx_equipment_telemetry_param (param, wafer_id)` 인덱스 추가 + 라이브 DB에도 직접 생성(`/api/scatter`의 self-join이 이 인덱스 없으면 9700만행 풀스캔).
- `setup_thingsboard_dashboard.py`에 커스텀 위젯 3개 추가: `CORRELATION_SCATTER_*`(드래그앤드롭 산점도, SVG 직접 렌더, 라이브러리 없음), `SENSOR_TABLE_*`/`RISK_ALERT_*`(둘 다 lot_id/wafer_index telemetry 구독 → `/api/wafer-sensors` 각자 fetch). 적용 함수 `apply_correlation_scatter_widget()`(Wafer Overview에 새 row로 추가, row=17 col=0 24x12 — 기존 위젯 안 건드림)와 `apply_detail_sensor_widgets()`(Wafer Detail의 남은 placeholder 2개 교체) 작성, `apply_pipeline_progress_widget()`와 같은 update-in-place 패턴.
- 테스트: `pytest tests/test_equipment_log_server.py` 3개 통과.
- 로컬 스모크 테스트(:8093 기동, 실제 DB 대상): `/api/sensors` 562개 확인, `/api/wafer-sensors`(lot15369_18) 62개 센서+편차 확인, `/api/scatter`(feature_0/feature_1, 클래스당50) 450개 포인트 클래스당 정확히 분배 확인, 응답속도 1초 내(인덱스 적용 후).
- **라이브 반영 완료 (2026-07-23)**: 사용자가 세션에 `THINGSBOARD_ADMIN_PASSWORD` 제공, `--apply-correlation-scatter`(Wafer Overview dashboard id `b4a550a0-85af-11f1-b7a9-c1826206c77f`, fqn `tenant.daol_fascope_correlation_scatter`)와 `--apply-detail-sensor-widgets`(Wafer Detail dashboard id `b4a41820-85af-11f1-b7a9-c1826206c77f`, fqn `tenant.daol_fascope_sensor_table`/`tenant.daol_fascope_risk_alert`) 둘 다 실행 완료.
- GET으로 두 대시보드 재조회해 위젯 배치 확인: Overview는 기존 5개 위젯(Lot Analysis/Composite갤러리/Wafer갤러리/슬라이더/원인분석요약) 그대로 두고 상관관계 산점도가 row17에 새로 추가됨, Detail은 placeholder였던 "설비/공정 텔레메트리"/"공정 위험 지표" 자리가 정확히 센서테이블/위험알림으로 교체되고 나머지(Yield Map/Class Overview/Process Risk&Alerts/파이프라인 진행바)는 안 건드려진 것 확인.
- **남은 건 브라우저 시각 확인뿐**(claude-in-chrome 미연결이라 실제 드래그앤드롭 동작·렌더링은 사용자가 `http://172.16.4.228:8082`에서 직접 확인 필요 — `equipment_log_server.py`(:8093)가 떠 있어야 위젯이 데이터를 받아옴, 현재 로컬에서 백그라운드로 기동 중).

---

## Phase 4: Kafka 실시간 스트리밍 스모크테스트 (확인용, 2026-07-24)

목적: "Kafka로 가상 데이터 스트리밍하면 진짜 실시간(밀리초 단위)으로 처리되는지" 확인. Phase 3의 배치 적재(`build_equipment_log.py`, 172,950 wafer 한 번에 COPY)와 별개 — 이건 프로덕션 기능이 아니라 일회성 성능 측정 스모크테스트.

문서: [스펙](docs/superpowers/specs/2026-07-24-kafka-streaming-smoketest-design.md), [구현 계획](docs/superpowers/plans/2026-07-24-kafka-streaming-smoketest.md)

**구성**:
- `apache/kafka`(KRaft 단일 브로커, ZooKeeper 없음) 컨테이너 추가.
- `kafka_common.py` — 메시지 스키마(웨이퍼 1개 = 562센서 스냅샷 = 메시지 1개).
- `kafka_producer.py` — 기존 Phase 3.1 SECOM 샘플러 재사용, throttle 없이 최대속도 발행, `wafer_id`는 `STREAM_` 접두사로 실데이터와 분리.
- `kafka_consumer.py` — TimescaleDB `equipment_telemetry` 동일 테이블에 이력 + ThingsBoard에 웨이퍼당 1회 POST로 이중 적재, 단계별 ms 레이턴시 측정.
- `telemetry.send_equipment_snapshot()` 추가.

**측정 방법**: producer/consumer를 별도 프로세스로 띄워 Kafka 토픽을 사이에 두고 비동기로 통신. consumer가 매 웨이퍼마다 (1) Kafka poll (2) TimescaleDB insert (3) ThingsBoard POST 각 단계 소요시간을 밀리초로 기록, N개 처리 후 평균/p99 요약 출력.

**결과** (200웨이퍼 × 562센서 = 112,400행/회, 3회 실행 반복):

| 실행 | e2e (producer→consumer) | Kafka poll | DB insert | ThingsBoard | 비고 |
|---|---|---|---|---|---|
| 1차 | 평균 14.9ms / p99 108ms | (미측정) | 평균 6.3ms / p99 16.4ms | 0.1ms (무의미 — 토큰 없어 즉시 실패) | ThingsBoard 토큰 미설정 |
| 2차 | 평균 134.6ms / p99 542.2ms | 평균 29.6ms / p99 337ms | 평균 7.6ms / p99 17.2ms | 평균 33.4ms / p99 73ms (200/200 성공) | 실토큰 투입, poll 타이밍 추가. 웨이퍼당 총 처리시간(130.9ms)이 측정된 3단계 합(70.6ms)보다 커서 **정체불명 갭(~60ms/웨이퍼) 발견** |
| 3차 | 평균 443.9ms / p99 1168.2ms | 평균 8.9ms / p99 169.3ms | 평균 7.1ms / p99 13.5ms | 평균 26.1ms / p99 54.8ms (0 실패) | idle poll 시간 분리 측정 추가 → **갭 원인 규명**(아래 참고) |

- **갭 원인 (3차에서 확인)**: `consumer.poll()`이 메시지 없어서 `None` 반환하는 대기시간이 그동안 어느 통계에도 안 잡히고 버려지고 있었음(생존편향). 이 idle 시간을 별도 누적 집계(`Stats.idle_poll_ms_total`)로 추가하자, 측정된 작업시간 합(poll+db+tb, 웨이퍼당 평균 × 200) + idle 총합 ≈ 실제 elapsed 시간(오차 200웨이퍼 전체 통틀어 60ms 이내로 수렴) — 갭 완전히 설명됨.

**결론**:
- Kafka 전송·DB 적재·ThingsBoard 전송 개별 단계는 전부 밀리초 단위로 확인됨(수 ms~수십 ms).
- 전체 처리량은 무한하지 않고 producer가 데이터 만드는 속도와 consumer가 처리하는 속도 중 느린 쪽에 의해 제한됨 — 이번 측정에선 둘의 속도가 비슷해서(consumer 실작업 ~42ms/웨이퍼, producer도 비슷한 페이스) consumer가 idle 대기하는 시간이 전체의 절반 이상을 차지하기도 함.
- 비유: 컨베이어벨트에서 앞 공정과 뒷 공정 속도가 비슷하면 뒷 공정이 부품 기다리며 노는 것과 같은 원리 — consumer 코드 자체가 느린 게 아니라 두 프로세스 간 속도 매칭 문제.

**알려진 이슈 (콜드스타트 레이스)**:
- 브로커에 토픽이 아직 없는 상태에서 `auto.offset.reset=latest` 사용 시 레이스 컨디션 실제 발생 확인.
- 시나리오: producer가 토픽을 순간적으로 만들고 메시지를 다 보내버리면, consumer의 group-join이 그보다 늦게 끝나서 "latest" 오프셋이 이미 지나간 메시지들을 영구히 놓치고 0건 처리한 채 무한 polling.
- 코드 버그가 아니라 이 offset 정책의 알려진 함정 — `kafka_producer.py`/`kafka_consumer.py` docstring에 경고 문구 추가로 대응(커밋 `cb21d8c`).

**코드**: `src/daol_fascope/kafka_common.py`, `kafka_producer.py`, `kafka_consumer.py`, `telemetry.send_equipment_snapshot()`. `docker-compose.yml`에 `kafka` 서비스.

**테스트**: `pytest tests/test_kafka_common.py tests/test_kafka_producer.py tests/test_kafka_consumer.py` (66개 전체 통과, 실제 브로커/DB 필요 없는 순수 로직 단위테스트). 실제 브로커 대상 라이브 검증 3회는 위 "결과" 표 참고.

**커밋 범위**: `c0b3c82..ab43e18` (subagent-driven-development로 5개 태스크 분할 구현, 태스크별 리뷰 + 최종 전체 리뷰 통과).

---

## 참고 문서

- `CONTEXT.md` — 도메인 용어집 (Wafer Map, Die, Defect Class, Digital Twin Feed)
- `docs/adr/0001-matrix-input-no-image-upload.md`
- `docs/adr/0002-frozen-dinov2-base-mlp-head.md`
- `docs/adr/0003-thingsboard-over-tailadmin-dashboard.md`
- `docs/adr/0004-llava-relay-no-langchain.md`
- `docs/adr/0005-dedicated-warm-prediction-server.md`
