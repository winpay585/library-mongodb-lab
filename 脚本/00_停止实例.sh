#!/bin/bash
# 停止本机的全部 MongoDB 实例。三台机器各执行一次。
# 用法：bash 00_停止实例.sh
# 说明：先停路由再停数据节点，SIGTERM 让 mongod 正常落盘后退出；10 秒内没退的才用 kill -9。

HOST=$(hostname -s)
echo "[$HOST] 停止实例"

stop_pat() {
    pat=$1
    pids=$(pgrep -f "$pat" | grep -v $$ 2>/dev/null)
    [ -z "$pids" ] && return 0
    kill -TERM $pids 2>/dev/null
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        pids=$(pgrep -f "$pat" | grep -v $$ 2>/dev/null)
        [ -z "$pids" ] && return 0
    done
    kill -9 $pids 2>/dev/null
}

stop_pat 'mongos -f /data/lib/conf'
stop_pat 'mongod -f /data/lib/conf'
stop_pat 'mongod -f /export/servers/standalone'

echo "[$HOST] 剩余监听端口："
left=$(ss -lnt | grep -E ':270(1[6-9]|2[0-2])' | awk '{print $4}')
if [ -z "$left" ]; then
    echo "  无"
else
    echo "$left" | sed 's/^/  /'
fi
