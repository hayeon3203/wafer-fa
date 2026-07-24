# Kafka 실시간 스트리밍 스모크테스트 설계

날짜: 2026-07-24
상태: 승인됨 (브레인스토밍 완료)

## 목적

실제 실시간 파이프라인 데모용 — Kafka로 가상 장비 센서 데이터를 producer→broker→consumer로 스트리밍하면서, 그 처리 성능(처리량/레이턴시)을 측정하는 스모크테스트. 기존 Phase 3(오프라인 배치, `build_equipment_log.py`)와 별개 — 배치 데이터/테이블 구조는 그대로 두고 위에 실시간 경로만 추가.

## 인프라

`docker-compose.yml`에 Kafka 컨테이너 1개 추가.

- 이미지: **`apache/kafka`** (Apache 공식 이미지, KRaft 모드 3.7+). `bitnami/kafka`는 서드파티 패키징이고 2024년 말부터 무료 태그 정책이 바뀌어 장기 안정성이 떨어져서 기각.
- **KRaft 단일 브로커** — ZooKeeper 없음. ZooKeeper는 Kafka 구버전이 쓰던 별도 코디네이션 프로세스(브로커 메타데이터/리더 선출)였고, KRaft가 브로커 자체 컨센서스로 대체해서 지금은 컨테이너 하나 안 늘려도 됨.
- 토픽: `equipment-telemetry-stream`, 파티션 1개 (단일 producer/consumer, 병렬성 불필요).

## Producer (`src/daol_fascope/kafka_producer.py`)

- 기존 `equipment_log.py`의 `build_assignments()` / `sample_wafer_readings()` 그대로 재사용 (SECOM 통계 기반 562-센서 샘플링 로직, Phase 3.1과 동일).
- 매 웨이퍼: manifest에서 랜덤 row 하나 뽑아 `defect_class` 획득. `wafer_id`는 `f"STREAM_{run_id}_{i}"`로 새로 합성 — 기존 배치 9700만행(Phase 3.1)과 PK 충돌 없게 분리.
- **웨이퍼 1개 = 메시지 1개** (562개 (param, value) 쌍을 JSON 배열로 묶어서 1 메시지, `produced_at` 타임스탬프 포함). 센서마다 메시지 쪼개지 않음 — 오버헤드만 커짐.
- throttle 없음 — 최대 속도로 publish.
- CLI: `--wafers N` (기본값 1000) — N개 다 보내면 종료.

## Consumer (`src/daol_fascope/kafka_consumer.py`)

메시지(웨이퍼 1개, 562값) 수신마다:

1. **TimescaleDB**: 기존 `equipment_telemetry` 테이블(스키마 변경 없음)에 562행 bulk insert — `build_equipment_log.py`와 같은 COPY 기반 벌크 패턴 재사용.
2. **ThingsBoard**: `telemetry.py`에 `send_equipment_snapshot()` 신규 함수 추가 — 562값을 **웨이퍼당 POST 1번**으로 device telemetry API에 전송 (키-값 562개 담은 단일 payload). 센서마다 개별 POST 하면 그게 병목이 되어 측정 의미가 사라지므로 배치.
   - 기존 위젯 중 이 payload를 시각화하는 위젯은 없음 — 이번 스모크테스트 범위 아님, 스트리밍 동작 확인 + 성능 측정이 목적.
3. 레이턴시 계산: `consumed_at - produced_at` (producer가 메시지에 심어둔 타임스탬프 기준), DB insert 소요시간, TB POST 소요시간을 각각 따로 측정.
4. 처리량 계산: 초당 처리 웨이퍼 수.

## 종료 조건 & 출력

고정 웨이퍼 개수(`--wafers N`) 처리 완료 시 자동 종료. 콘솔에 요약 출력:

- 총 처리량 (msg/sec, wafer/sec)
- 레이턴시: producer→consumer / DB insert / TB POST — 각각 평균, p99
- 성공/실패 카운트 (TB POST는 네트워크 실패 삼키고 실패로만 카운트, 전체 파이프라인 안 끊음 — 기존 `telemetry.py`의 실패-무시 관례 유지)

별도 ThingsBoard 성능 위젯은 만들지 않음(콘솔 출력만).

## 의존성

`confluent-kafka` (librdkafka 바인딩) 신규 추가 — 순수 파이썬 `kafka-python`보다 처리량이 높아 성능 측정이 목적인 이번 작업에 적합, 사실상 업계 표준 클라이언트.

## 테스트

`tests/test_kafka_producer.py` / `tests/test_kafka_consumer.py` — 메시지 스키마 직렬화, 레이턴시/처리량 계산 로직만 유닛테스트 (실제 Kafka 브로커/DB 없이 mock). 실제 브로커 대상 end-to-end 동작은 `docker compose up kafka` 후 사용자가 직접 실행.

## 범위 밖 (백로그)

- ThingsBoard 실시간 성능 지표 위젯 (필요해지면 별도 착수)
- Kafka 다중 파티션/컨슈머 그룹 (지금은 스모크테스트, 확장성 검증 아님)
- throttle 옵션 (지금은 최대속도 측정만)
