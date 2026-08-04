# 0006 — LLaVA를 OpenShell 샌드박스로 분리한다

## 맥락

Stage 2 릴레이(`relay.py`)는 LangGraph 4노드를 돌리면서 LLaVA-1.5-7B(~14GB)를
**같은 프로세스 안에서** `from_pretrained` 로 올리고 있었다. 모델만 격리하고
싶어도 프로세스 경계가 없어 격리 단위가 없다.

참고한 선례는 DaolVision Task 8.2.1이다. 거기서는 모델 6종이 처음부터 독립
HTTP 서버였기 때문에, 서버 프로세스만 샌드박스로 옮기고 `openshell forward` 로
원래 localhost 포트에 붙여서 **에이전트 코드 무수정**으로 격리가 끝났다.

## 결정

LLaVA를 `daol_fascope.llava_server` 로 분리하고, `relay.generate()` 는 그 서버에
HTTP로 요청만 한다. 모델 서버는 `scripts/start_llava_sandbox.sh` 로 OpenShell
샌드박스(`--gpu`)에서 띄우고 `:8506` 으로 forward 한다.

**LangGraph 릴레이는 호스트에 남는다.** 같이 넣을 수 없다 — 샌드박스는 정책상
아웃바운드가 전부 막혀 있다(실측: 호스트의 Qdrant :6333, ThingsBoard :8082,
Ollama :11434 로 curl 하면 전부 `403`). 릴레이는 이 셋을 다 부른다.

> 격리 대상은 **밖으로 전화를 걸지 않는 잎 노드**여야 한다. 모델 서버는 요청을
> 받아 답만 하므로 여기에 해당한다.

웨이트·venv·코드는 호스트에 남기고 bind mount 로 **동일 절대경로**에 물린다
(venv의 shebang과 `pyvenv.cfg` 가 절대경로라 위치를 바꾸면 인터프리터 사슬이
끊긴다). 복사도 스테이징도 없다. 마운트는 전부 읽기전용 — bind mount 는 호스트
원본 그 자체라 쓰기를 열면 샌드박스가 웨이트를 덮어쓸 수 있다.

## 결과

- LLaVA 프로세스는 landlock 파일 정책 + 아웃바운드 차단 아래서 돈다. 웨이트
  디렉토리와 자기 venv 말고는 못 읽고, 아무 데도 못 나간다.
- `relay.py` 가 `torch`/`transformers` 를 더는 import 하지 않는다. 릴레이 프로세스가
  가벼워지고, 테스트가 GPU 없이 돈다.
- ADR 0005("워밍업된 단일 LLaVA 프로세스")는 유효하다. 위치만 샌드박스로 옮겼고,
  `llava_server.main()` 이 리스닝 전에 모델을 올려 워밍 상태를 유지한다.
- 대가: 노드마다 HTTP 홉이 하나씩 는다(localhost, 페이로드는 PNG 1장). 생성
  시간이 수십 초라 무시할 수준.
- `HF_HUB_OFFLINE=1` 이 필수다. 아웃바운드 403이라 `from_pretrained` 가
  huggingface.co 를 때리면 마운트한 웨이트를 두고도 실패한다.

## 대안 (기각)

**`wafer_predict_server` 를 통째로 샌드박스에 넣기** — 코드 수정 0줄이라 제일
싸 보였지만 못 쓴다. 그 프로세스가 Qdrant·ThingsBoard·Ollama 를 부르는데
아웃바운드가 403이다. `network_middlewares` 정책으로 여는 길이 있어 보이나,
그러면 "격리했다"는 말의 값이 떨어진다 — 격리하려던 프로세스에 나가는 구멍을
다시 뚫는 셈이다.
