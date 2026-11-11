#!/bin/bash
# 启动本机的全部 MongoDB 实例。三台机器各执行一次。
# 用法：bash 00_启动实例.sh
# 说明：conf 原文在仓库 配置/<主机名>/ 下，先放到 /data/lib/conf 再跑本脚本。
#       已经在监听的实例会被跳过，重复执行不会起出两份。

CONF=/data/lib/conf
HOST=$(hostname -s)

echo "[$HOST] 启动实例"

# 按顺序：配置服务器 -> 副本集 -> 分片 -> 单机
for f in cfg1.conf cfg2.conf cfg3.conf rs1.conf rs2.conf rs3.conf shard1.conf shard2.conf; do
    [ -f "$CONF/$f" ] || continue
    port=$(awk '/^[[:space:]]*port:/{print $2; exit}' "$CONF/$f")
    if ss -lnt 2>/dev/null | grep -q ":$port "; then
        echo "  跳过 $f（$port 已在监听）"
        continue
    fi
    echo "  起 $f"
    mongod -f "$CONF/$f" >/dev/null 2>&1
done

# 27017 单机：standalone.conf 与 standalone-auth.conf 同占 27017，只起带认证的那份
if [ -f "$CONF/standalone-auth.conf" ]; then
    if ss -lnt 2>/dev/null | grep -q ':27017 '; then
        echo "  跳过 standalone-auth.conf（27017 已在监听）"
    else
        echo "  起 standalone-auth.conf"
        mongod -f "$CONF/standalone-auth.conf" >/dev/null 2>&1
    fi
fi

# 27016 统一口径实例，只有 nosql01 上有
if [ -f /export/servers/standalone/mongod.conf ]; then
    if ss -lnt 2>/dev/null | grep -q ':27016 '; then
        echo "  跳过 27016 实例（已在监听）"
    else
        echo "  起 27016 实例"
        mongod -f /export/servers/standalone/mongod.conf >/dev/null 2>&1
    fi
fi

# 等配置服务器与分片选主完成，再起路由
sleep 10

if [ -f "$CONF/mongos.conf" ]; then
    if ss -lnt 2>/dev/null | grep -q ':27022 '; then
        echo "  跳过 mongos.conf（27022 已在监听）"
    else
        echo "  起 mongos.conf"
        mongos -f "$CONF/mongos.conf" >/dev/null 2>&1
        sleep 5
    fi
fi

echo "[$HOST] 监听端口："
ss -lnt | grep -E ':270(1[6-9]|2[0-2])' | awk '{print "  "$4}' | sort
