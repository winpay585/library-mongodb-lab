#!/bin/bash
# 故障转移演练：杀掉主节点的 mongod 进程，测选举耗时，再把进程拉回来，看它是否按 priority 重新当选。
#
# 在哪跑：要跑到"当前主节点"这台机器上（脚本只杀本机进程，其它节点靠网络轮询）。
#   先在任何一台机器上确认主节点：
#     mongosh --port 27018 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet \
#       --eval 'print(db.hello().primary)'
#   然后登录那台机器执行：bash 08_故障转移演练.sh
#
# 用法：bash 08_故障转移演练.sh [端口]

PORT=${1:-27018}
AUTH="-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"
HOSTS="nosql01 nosql02 nosql03"
ME=$(hostname)
CONF=/data/lib/conf/rs${ME: -1}.conf

PRIMARY=$(mongosh --port "$PORT" $AUTH --eval 'print(db.hello().primary)' | tail -1 | cut -d: -f1)
echo "副本集当前主节点：$PRIMARY，本机：$ME"
if [ "$PRIMARY" != "$ME" ]; then
  echo "本机不是主节点，停止。请到 $PRIMARY 上执行本脚本。"
  exit 1
fi

PID=$(ss -lntp | grep ":$PORT " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
if [ -z "$PID" ]; then
  echo "没找到监听 $PORT 的 mongod 进程"
  exit 1
fi

echo "== 杀掉本机 mongod（pid=$PID）=="
T0=$(date +%s%3N)
kill -9 "$PID"
sleep 1
ss -lntp | grep ":$PORT " || echo "端口已释放"

echo "== 轮询其它节点，看多久选出新主 =="
NEW=""
for i in $(seq 1 150); do
  for h in $HOSTS; do
    [ "$h" = "$ME" ] && continue
    ok=$(mongosh --quiet "mongodb://$h:$PORT/admin?directConnection=true" $AUTH \
         --eval 'print(db.hello().isWritablePrimary)' 2>/dev/null | tail -1)
    if [ "$ok" = "true" ]; then
      NEW=$h
      T1=$(date +%s%3N)
      echo "新主节点：$h，选举耗时 $(( T1 - T0 )) 毫秒"
      break
    fi
  done
  [ -n "$NEW" ] && break
  sleep 0.2
done
[ -z "$NEW" ] && { echo "两分半没选出新主，检查副本集配置"; exit 1; }

echo "== 新主能否写入 =="
TS=$(date +%Y%m%d%H%M%S)
mongosh --quiet "mongodb://$NEW:$PORT/admin?directConnection=true" $AUTH --eval "
const d = db.getSiblingDB('library');
d.books.insertOne({isbn: 'failover-probe-$TS', title: '故障转移写入探针', category: '测试', price: 0, stock: 1});
print('写入成功，books=' + d.books.countDocuments());"

echo "== 拉起原来的主节点 =="
mongod --config "$CONF"
sleep 10
mongosh --port "$PORT" $AUTH --eval 'rs.status().members.forEach(m => print(m.name, m.stateStr, "health=" + m.health))'

echo "== 清掉探针数据（写到当前的主节点，旧主回主后就不是它了）=="
CUR=$(mongosh --port "$PORT" $AUTH --eval 'print(db.hello().primary)' | tail -1 | cut -d: -f1)
mongosh --quiet "mongodb://$CUR:$PORT/admin?directConnection=true" $AUTH --eval '
const d = db.getSiblingDB("library");
d.books.deleteMany({isbn: /failover-probe/});
print("已清理，books=" + d.books.countDocuments());'

echo "== 复制延迟 =="
mongosh --port "$PORT" $AUTH --eval 'rs.printSecondaryReplicationInfo()'
