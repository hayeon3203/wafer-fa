#!/usr/bin/env bash
# LLaVA 모델 서버를 OpenShell 샌드박스에서 띄운다 (docs/adr/0006).
#
# 격리되는 건 모델 서버 하나뿐이다. LangGraph 릴레이(relay.py)는 호스트에 남는다 —
# 샌드박스는 아웃바운드가 정책으로 막혀 있어(모든 외부 호출 403) Qdrant :6333,
# ThingsBoard :8082, Ollama :11434 를 못 부른다. 요청을 받기만 하는 잎 노드인
# 모델 서버가 가둘 수 있는 유일한 조각이다.
#
# 웨이트·venv·코드는 호스트에 그대로 둔다. openshell 0.0.96 의 docker 드라이버가
# 호스트 bind mount 를 정식 지원하므로 복사도 스테이징도 없다. 게이트웨이 쪽에서
# 한 번만 열어주면 된다:
#
#   ~/.config/openshell/gateway.toml
#     [openshell.drivers.docker]
#     enable_bind_mounts = true
#   ~/.config/openshell/gateway.env
#     OPENSHELL_GATEWAY_CONFIG=/home/admin/.config/openshell/gateway.toml
#   systemctl --user restart openshell-gateway
#
# 안 열려 있으면 create 가 "... requires enable_bind_mounts = true" 로 명확히
# 죽으므로 따로 점검하지 않는다.
#
# 사용법:
#   ./scripts/start_llava_sandbox.sh --check   # 아무것도 안 바꾸고 전제조건만 점검
#   ./scripts/start_llava_sandbox.sh --smoke   # 호스트 venv 가 이미지 안에서 도는지 검증
#   ./scripts/start_llava_sandbox.sh --up      # 샌드박스 + forward
#   ./scripts/start_llava_sandbox.sh --down    # forward 해제 + 샌드박스 삭제
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${REPO_ROOT}/docker/Dockerfile.runtime"
IMAGE="${RUNTIME_IMAGE:-daol-fascope/runtime:1}"

NAME=llava
PORT=8506
HF_HUB="${HF_HUB:-/home/admin/.cache/huggingface/hub}"
LLAVA_WEIGHTS="${HF_HUB}/models--llava-hf--llava-1.5-7b-hf"
VENV="${REPO_ROOT}/.venv"
POLICY="${REPO_ROOT}/docker/policies/${NAME}.yaml"

# 마운트 경로는 샌드박스 안에서도 호스트와 **동일한 절대경로**여야 한다 — venv 의
# shebang 과 pyvenv.cfg 에 절대경로가 박혀 있어 다른 위치에 붙이면 인터프리터
# 사슬이 끊긴다. 전부 읽기전용이다. bind mount 는 호스트 원본 그 자체라 쓰기를
# 열면 샌드박스가 호스트 웨이트를 덮어쓸 수 있다.
MOUNTS=("${REPO_ROOT}/src" "$VENV" "$LLAVA_WEIGHTS")

die() { echo "ERROR: $*" >&2; exit 1; }

# 포트를 쥔 프로세스가 systemd 유닛이면 유닛 이름을 돌려준다. 그냥 kill 하면
# systemd 가 되살려서 전환이 조용히 실패한다.
port_unit() {
    local pid unit
    pid=$(ss -tlnpH "sport = :$PORT" 2>/dev/null \
          | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
    [ -n "$pid" ] || return 1
    unit=$(grep -oE '[A-Za-z0-9@._-]+\.service' "/proc/$pid/cgroup" 2>/dev/null | tail -1)
    [ -n "$unit" ] || return 1
    printf '%s' "$unit"
}

check() {
    local rc=0 busy=0
    openshell status >/dev/null 2>&1 || { echo "  [x] openshell 게이트웨이 응답 없음"; rc=1; }
    [ -f "$DOCKERFILE" ] || { echo "  [x] $DOCKERFILE 없음"; rc=1; }
    for p in "${MOUNTS[@]}"; do
        [ -e "$p" ] || { echo "  [x] 마운트 원본 없음 — $p"; rc=1; }
    done
    if ss -tln 2>/dev/null | grep -qE "[:.]${PORT}[[:space:]]"; then
        unit="$(port_unit || true)"
        if [ -n "$unit" ]; then
            echo "  [!] :$PORT — systemd 유닛 $unit 가 점유 중"
            echo "        systemctl --user stop $unit && systemctl --user disable $unit"
        else
            echo "  [!] :$PORT 호스트에서 사용 중 — 전환하려면 먼저 내려야 함"
        fi
        busy=1
    fi
    echo "  [i] 메모리 available: $(free -g | awk '/^Mem:/{print $7}') GiB"
    [ "$busy" = 0 ] && echo "  [i] :$PORT 비어 있음 — --up 가능"
    [ "$rc" = 0 ] && echo "  [ok] 전제조건 통과"
    # 0=이상없음, 1=전제조건 실패, 2=전제조건은 OK지만 포트가 호스트에 물려 있음
    [ "$rc" = 0 ] && [ "$busy" = 1 ] && return 2
    return $rc
}

# 샌드박스는 landlock 파일시스템 정책으로 /sandbox·/tmp·/usr 정도만 열어둔다.
# 마운트를 붙여도 정책에 없으면 못 읽는다 — 경로를 그대로 정책에도 등록해야 한다.
write_policy() {
    mkdir -p "$(dirname "$POLICY")"
    {
        echo "version: 1"
        echo "filesystem_policy:"
        echo "  include_workdir: true"
        echo "  read_only:"
        for p in /usr /lib /proc /dev/urandom /app /etc /var/log; do echo "  - $p"; done
        echo "  - /sys"   # CUDA 초기화가 /sys 의 디바이스 토폴로지를 읽는다
        echo "  - $REPO_ROOT"
        for p in "${MOUNTS[@]}"; do echo "  - $p"; done
        echo "  read_write:"
        for p in /sandbox /tmp /dev/null; do echo "  - $p"; done
        # torch 의 shared-memory 와 NVIDIA 디바이스 노드는 쓰기가 필요하다.
        for p in /dev/shm /dev/nvidiactl /dev/nvidia0 \
                 /dev/nvidia-uvm /dev/nvidia-uvm-tools; do echo "  - $p"; done
        echo "landlock:"
        echo "  compatibility: best_effort"
        echo "process:"
        echo "  run_as_user: sandbox"
        echo "  run_as_group: sandbox"
    } > "$POLICY"
}

driver_json() {
    python3 -c '
import json, sys
mounts = [{"type": "bind", "source": p, "target": p, "read_only": True} for p in sys.argv[1:]]
json.dump({"docker": {"mounts": mounts}}, sys.stdout)
' "${MOUNTS[@]}"
}

wait_ready() {
    local i=0
    while [ $i -lt 120 ]; do
        openshell sandbox list 2>/dev/null | grep -E "^${NAME}[[:space:]]" | grep -q Ready && return 0
        sleep 5; i=$((i+1))
    done
    return 1
}

up() {
    write_policy
    # 살아있는 샌드박스에 policy set 으로 범위를 좁히는 건 서버가 거부한다.
    # 정책은 create 시점에만 줄 수 있으므로 매번 지우고 새로 만든다.
    openshell sandbox delete "$NAME" >/dev/null 2>&1 || true

    # HF_HUB_OFFLINE=1 이 필수다. 샌드박스 아웃바운드가 403 이라 from_pretrained 가
    # huggingface.co 를 때리면 마운트한 웨이트를 두고도 실패한다.
    # HF_HOME 은 명시한다 — 로그인 유저가 sandbox 라 기본값이 /home/sandbox/.cache 가 된다.
    #
    # HOME=/tmp — 샌드박스 로그인 유저는 sandbox 라 HOME 이 /home/sandbox 인데 거긴
    # 정책상 못 쓴다. 캐시를 $HOME 밑에 만드는 라이브러리가 전부 여기서 죽는다.
    # 실측: torch 가 첫 generate 때 triton 캐시를 열다가
    # "[Errno 13] Permission denied: '/home/sandbox/.triton'". 기동과 /health 는
    # 멀쩡히 통과하고 **추론에서만** 터지므로 헬스체크로는 못 잡는다.
    # 라이브러리마다 캐시 환경변수를 하나씩 쫓아다니는 대신 HOME 을 쓰기 가능한
    # /tmp 로 돌린다(정책상 이미 read_write). HF 캐시는 HF_HOME 으로 따로 고정돼 있다.
    #
    # create 에는 --workdir 가 없다. 커맨드는 CLI 가 argv 로 그대로 넘기므로
    # sh -c 안에서 cd 한다. --no-tty 없으면 비대화 세션에서 PTY 할당을 시도하다
    # 스크립트째 죽는다. create 는 Ready 이후에도 커맨드에 붙어 있으므로 setsid 로
    # 떼어놓고 Ready 를 직접 기다린다. 출력을 버리면 기동 실패 사유가 통째로
    # 사라지므로 로그로 남긴다.
    setsid openshell sandbox create --name "$NAME" --gpu --no-tty \
        --policy "$POLICY" \
        --driver-config-json "$(driver_json)" \
        --env "PYTHONPATH=${REPO_ROOT}/src" \
        --env "HOME=/tmp" \
        --env "HF_HOME=/home/admin/.cache/huggingface" \
        --env "HF_HUB_OFFLINE=1" \
        --env "LLAVA_HOST=0.0.0.0" \
        --env "LLAVA_PORT=${PORT}" \
        --from "$DOCKERFILE" \
        -- sh -c "cd '$REPO_ROOT' && exec ${VENV}/bin/python -m daol_fascope.llava_server" \
        < /dev/null > "/tmp/start_llava_sandbox.log" 2>&1 &
    wait_ready || die "샌드박스가 Ready 가 되지 않음 — /tmp/start_llava_sandbox.log 확인"

    # forward start 는 포그라운드로 붙잡으므로 --background 필수. 그게 남기는 ssh
    # 데몬이 이 스크립트의 stdout 을 물려받아 파이프가 안 닫히므로 리다이렉트로 끊는다.
    openshell forward start --background "$PORT" "$NAME" >/dev/null 2>&1
    sleep 2
    # 포트로 curl 만 해보면 안 된다 — 호스트가 같은 포트를 다시 잡았을 때 그쪽이
    # 응답해서 전환 실패가 성공으로 보인다. forward 상태를 본다.
    openshell forward list 2>/dev/null \
        | awk -v n="$NAME" -v p="$PORT" '$1==n && $3==p {print $NF}' \
        | grep -q running \
        || die "forward 가 붙지 않았다 (:$PORT). --check 로 포트 점유를 확인할 것"

    echo "  기동 완료 (:$PORT). 웨이트 14GB 로딩 중 — /health 의 loaded 가 true 가 될 때까지 기다릴 것:"
    echo "    curl -s 127.0.0.1:${PORT}/health"
}

# 이 설계의 유일한 가정 — "호스트 venv 를 원래 경로에 마운트하면 얇은 이미지 안에서
# 그대로 돈다" — 를 검증한다. GPU 도 포트도 웨이트도 안 건드리고 import 만 한다.
smoke() {
    docker image inspect "$IMAGE" >/dev/null 2>&1 \
        || docker build -q -f "$DOCKERFILE" -t "$IMAGE" "$(dirname "$DOCKERFILE")" >/dev/null
    docker run --rm -v "${VENV}:${VENV}:ro" -v "${REPO_ROOT}/src:${REPO_ROOT}/src:ro" \
        -e "PYTHONPATH=${REPO_ROOT}/src" "$IMAGE" \
        "${VENV}/bin/python" -c \
        "import sys, torch, transformers; import daol_fascope.llava_server as s; \
         print(sys.version.split()[0], torch.__version__, transformers.__version__, s.PORT)"
}

down() {
    openshell forward stop "$PORT" 2>/dev/null || true
    openshell sandbox delete "$NAME" 2>/dev/null || true
    echo "  내림: $NAME (:$PORT)"
}

case "${1:---check}" in
    # 포트가 물려 있는 건 --check 입장에선 정상 상태(보고만 한다)라 exit 0.
    --check) rc=0; check || rc=$?; [ "$rc" = 1 ] && exit 1; exit 0 ;;
    --smoke) smoke ;;
    --up)
        rc=0; check || rc=$?
        [ "$rc" = 1 ] && die "전제조건 실패"
        [ "$rc" = 2 ] && die "호스트가 :$PORT 를 쓰고 있다. 그 프로세스를 먼저 내릴 것 — 이 스크립트는 남의 서버를 죽이지 않는다."
        up ;;
    --down)  down ;;
    *)       die "사용법: $0 [--check|--smoke|--up|--down]" ;;
esac
