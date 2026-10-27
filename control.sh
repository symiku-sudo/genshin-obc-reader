#!/data/data/com.termux/files/usr/bin/sh
set -eu
READER_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
READER_SOCKET="$READER_DIR/data/reader.tmux.sock"
READER_URL='http://127.0.0.1:8766/'
mkdir -p "$READER_DIR/data"
healthy() { curl -fsS --max-time 2 "${READER_URL}api/stats" >/dev/null 2>&1; }
session_exists() { tmux -S "$READER_SOCKET" has-session -t obc-reader 2>/dev/null; }
case "${1:-status}" in
  start)
    if healthy; then
      echo "服务已经运行：$READER_URL"
      exit 0
    fi
    if ! command -v tmux >/dev/null 2>&1; then
      echo "未找到 tmux。请在 Termux 中运行 sh $READER_DIR/start.sh，并保持终端运行。" >&2
      exit 1
    fi
    if ! session_exists; then
      tmux -f /dev/null -S "$READER_SOCKET" new-session -d -s obc-reader -c "$READER_DIR" 'exec sh ./start.sh >>data/service.log 2>&1'
    fi
    READER_ATTEMPT=0
    until healthy; do
      READER_ATTEMPT=$((READER_ATTEMPT + 1))
      if [ "$READER_ATTEMPT" -ge 150 ]; then
        if session_exists; then
          echo "服务仍在初始化（可能正在升级缓存）。稍后执行 sh $READER_DIR/control.sh status 检查。"
          exit 0
        fi
        echo "服务启动失败，请查看 $READER_DIR/data/service.log" >&2
        exit 1
      fi
      sleep 0.2
    done
    echo "阅读室已启动：$READER_URL"
    ;;
  status)
    if healthy; then
      echo "HTTP 正常：$READER_URL"
      if session_exists; then echo '独立 tmux 会话正在运行'; else echo '服务由其他终端启动'; fi
    else
      echo '服务未运行或无法连接'
      exit 1
    fi
    ;;
  stop)
    if session_exists; then
      tmux -S "$READER_SOCKET" kill-session -t obc-reader
      echo '已停止阅读室后台会话'
    else
      echo '没有此脚本启动的后台会话'
    fi
    ;;
  *) echo '用法：sh control.sh {start|status|stop}' >&2; exit 2 ;;
esac
