"""阶段三（B）：分片集群业务侧——账号、挂分片、开分片、导数据、验证分布与路由。

用法：python scripts\\lab_shard_data.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"
MONGOS = "27022"
MON = f"-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

FIRST_USER = """
const admin = db.getSiblingDB('admin');
admin.createUser({user:'platform_admin', pwd:'Admin2026pwd', roles:[{role:'root', db:'admin'}]});
print('platform_admin 已创建（mongos localhost 例外）');
"""

BIZ_USERS = """
const lib = db.getSiblingDB('library');
['lib_admin:dbOwner', 'lib_editor:readWrite', 'lib_reader:read'].forEach(s => {
  const [u, r] = s.split(':');
  try { lib.createUser({user: u, pwd: 'lib2026pwd', roles: [{role: r, db: 'library'}]});
        print(u + ' 已创建'); } catch (e) { print(u + ' 跳过: ' + e.codeName); }
});
print('账号：' + lib.getUsers().users.map(u => u.user).join(', '));
"""

ENABLE = """
printjson(db.adminCommand({addShard: 'shard1rs/nosql01:27020,nosql02:27020', name: 'shard1'}));
printjson(db.adminCommand({addShard: 'shard2rs/nosql03:27021,nosql02:27021', name: 'shard2'}));
print('已启用分片的数据库：' + JSON.stringify(db.adminCommand({enableSharding: 'library'})));
printjson(db.adminCommand({shardCollection: 'library.borrow_logs', key: {reader_card: 'hashed'}}));
printjson(db.adminCommand({shardCollection: 'library.books', key: {isbn: 'hashed'}}));
print('分片状态：' + JSON.stringify(db.adminCommand({listShards: 1}).shards.map(s => s._id + '=' + s.host)));
"""

SPLIT = """
// 把借阅日志按哈希值切成 8 块，让均衡器有机会把数据分到两个分片
const pts = ['-6917529027641081856', '-4611686018427387904', '-2305843009213693952',
             '0', '2305843009213693952', '4611686018427387904', '6917529027641081856'];
pts.forEach(p => {
  try { db.adminCommand({split: 'library.borrow_logs', middle: {reader_card: NumberLong(p)}}); }
  catch (e) { print('split 跳过 ' + p + ': ' + e.codeName); }
});
try { db.adminCommand({split: 'library.books', middle: {isbn: NumberLong('0')}}); } catch (e) {}
db.adminCommand({balancerStart: 1});
print('已切分并启动均衡器');
"""

DIST = """
print('== 分片分布 ==');
printjson(db.getSiblingDB('library').borrow_logs.getShardDistribution());
printjson(db.getSiblingDB('library').books.getShardDistribution());
print('== 路由验证（按分片键查） ==');
const ex = db.getSiblingDB('library').borrow_logs.find({reader_card: 'R20240001'}).explain();
print('查询命中分片：' + JSON.stringify(ex.queryPlanner.winningPlan.shards || ex.queryPlanner.winningPlan.stage));
"""

STATUS = """
sh.status().databases.forEach(d => {
  if (d._id === 'library') { print('库 ' + d._id + ' primaryShard=' + d.primary); }
});
"""


def main() -> None:
    log: list[str] = []

    def conn(name: str) -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[name], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        return cli

    def sh(host: str, cmd: str, timeout: int = 240) -> tuple[int, str]:
        cli = conn(host)
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"[{host}] $ {cmd}")
        log.append(text)
        log.append(f"[exit {rc}]")
        log.append("")
        return rc, text

    def put(remote: str, text: str) -> None:
        cli = conn("nosql01")
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    # 1. 首个账号（mongos 的 localhost 例外，必须显式走 127.0.0.1）
    put("/data/lib/tmp/sh_first.js", FIRST_USER)
    sh("nosql01", f"mongosh 'mongodb://127.0.0.1:{MONGOS}/?directConnection=true' --quiet /data/lib/tmp/sh_first.js")

    # 2. 业务账号
    put("/data/lib/tmp/sh_users.js", BIZ_USERS)
    sh("nosql01", f"mongosh --port {MONGOS} {MON} /data/lib/tmp/sh_users.js")

    # 3. 挂分片 + 开分片
    put("/data/lib/tmp/sh_enable.js", ENABLE)
    sh("nosql01", f"mongosh --port {MONGOS} {MON} /data/lib/tmp/sh_enable.js")

    # 4. 通过 mongos 导入数据
    for col in ("books", "readers", "borrow_logs"):
        sh("nosql01", f"mongoimport --port {MONGOS} -u lib_admin -p lib2026pwd --authenticationDatabase library "
                      f"--db library --collection {col} --file /data/lib/tmp/data/{col}.txt --jsonArray --drop")

    # 5. 各分片条数
    for host, port in (("nosql01", 27020), ("nosql03", 27021)):
        sh(host, f"mongosh --port {port} -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet "
                 "--eval 'const d=db.getSiblingDB(\"library\");"
                 "print(\"books=\"+d.books.countDocuments()+\" borrow_logs=\"+d.borrow_logs.countDocuments())'")

    # 6. 切块 + 均衡 + 分布
    put("/data/lib/tmp/sh_split.js", SPLIT)
    sh("nosql01", f"mongosh --port {MONGOS} {MON} /data/lib/tmp/sh_split.js")
    time.sleep(20)
    put("/data/lib/tmp/sh_dist.js", DIST)
    sh("nosql01", f"mongosh --port {MONGOS} {MON} /data/lib/tmp/sh_dist.js")
    put("/data/lib/tmp/sh_status.js", STATUS)
    sh("nosql01", f"mongosh --port {MONGOS} {MON} /data/lib/tmp/sh_status.js")
    sh("nosql01", f"mongosh --port {MONGOS} {MON} --eval 'db.getSiblingDB(\"library\").borrow_logs.countDocuments()'")

    (OUT / "shard_data.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
