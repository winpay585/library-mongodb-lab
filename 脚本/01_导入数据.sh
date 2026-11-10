#!/bin/bash
# 数据导入：把 数据/ 里的三个 txt 导进 library 库。
#
# 在哪跑：nosql01。端口用第一个参数指定（单机 27017 / 副本集 27018 / mongos 27022）。
# 前置：books.txt、readers.txt、borrow_logs.txt 已经放到 /data/lib/tmp/data。
# 注意：--drop 会清空集合，所以导入要放在建索引、开分片之前做。
#
# 用法：bash 01_导入数据.sh 27017
#       已经开了认证再加账号：MONGO_USER=platform_admin MONGO_PASS=Admin2026pwd MONGO_AUTHDB=admin bash 01_导入数据.sh 27017
#       导到临时库里试：DB=library_probe bash 01_导入数据.sh 27017
set -e

PORT=${1:-27017}
DB=${DB:-library}
DATA=${DATA_DIR:-/data/lib/tmp/data}
AUTH=""
if [ -n "$MONGO_USER" ]; then
  AUTH="-u $MONGO_USER -p $MONGO_PASS --authenticationDatabase ${MONGO_AUTHDB:-$DB}"
fi

for c in books readers borrow_logs; do
  echo "== 导入 $c =="
  # shellcheck disable=SC2086
  mongoimport --port "$PORT" --db "$DB" --collection "$c" $AUTH \
    --file "$DATA/$c.txt" --jsonArray --drop
done

mongosh --port "$PORT" $AUTH --quiet --eval "
const d = db.getSiblingDB('$DB');
['books', 'readers', 'borrow_logs'].forEach(c => print(c + '  ' + d[c].countDocuments()));
"
