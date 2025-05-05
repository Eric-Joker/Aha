#!/bin/bash

pkill -f "python qqbot.py"
while pgrep -f "python qqbot.py" > /dev/null; do
    echo "🕒 等待进程退出..."
    sleep 1
done
cd "$( cd "$( dirname "$0" )" && pwd )"
rm -f nohup.out
export BOT_ENV="main"
nohup python qqbot.py > nohup.out 2>&1 </dev/null &
echo "✅ 已启动 ncatbot"
