#!/bin/bash

pkill -f "python qqbot.py"
while pgrep -f "python qqbot.py" > /dev/null; do
    echo "🕒 等待进程退出..."
    sleep 1
done

cd "$(dirname "$0")"

screen -dmS aha bash -c "export BOT_ENV='main' && python qqbot.py"

echo "✅ 已启动 ncatbot。通过 screen -r aha 附加对话，Ctrl+A D 分离；pkill -f 'python qqbot.py' 终止进程"
