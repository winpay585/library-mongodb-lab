"""阶段三（C）：先导入后开分片——重新分片两个集合、切块、均衡、查看分布与路由。

用法：python scripts\\lab_shard_shard.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

HOST = "192.168.121.134"
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"
MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

SHARD_JS = """
const lib = db.getSiblingDB('library');
try {
  printjson(db.adminCommand({shardCollection: 'library.borrow_logs', key: {reader_card: 'hashed'}}));
} catch (e) { print('borrow_logs: ' + e.codeName); }
try {
  printjson(db.adminCommand({shardCollection: 'library.books', key: {isbn: 'hashed'}}));
} catch (e) { print('books: ' + e.codeName); }
print('分片集合：' + JSON.stringify(db.getSiblingDB('config').collections.find({}, {_id: 1, key: 1}).toArray()));
"""

SPLIT_JS = """
const pts = ['-6917529027641081856', '-4611686018427387904', '-2305843009213693952',
             '0', '2305843009213693952', '4611686018427387904', '6917529027641081856'];
let ok = 0;
pts.forEach(p => {
  const r = db.adminCommand({split: 'library.borrow_logs', middle: {reader_card: NumberLong(p)}});
  if (r.ok === 1) ok++;
});
print('borrow_logs 切出新块：' + ok);
const r2 = db.adminCommand({split: 'library.books', middle: {isbn: NumberLong('0')}});
print('books 切块结果 ok=' + r2.ok);
db.adminCommand({balancerStart: 1});
print('均衡器已启动');
"""

DIST_JS = """
print('== borrow_logs 分片分布 ==');
const a = db.getSiblingDB('library').borrow_logs.getShardDistribution();
['shard1', 'shard2'].forEach(s => {
  if (a[s]) print(s + ': 文档 ' + a[s].docs + ' 块 ' + a[s].chunks + ' 大小 ' + a[s].data);
});
print('合计文档 ' + a.totals.docs + '，块 ' + a.totals.chunks);
print('== books 分片分布 ==');
const b = db.getSiblingDB('library').books.getShardDistribution();
['shard1', 'shard2'].forEach(s => {
  if (b[s]) print(s + ': 文档 ' + b[s].docs + ' 块 ' + b[s].chunks + ' 大小 ' + b[s].data);
});
print('合计文档 ' + b.totals.docs + '，块 ' + b.totals.chunks);
"""

ROUTE_JS = """
print('== 按分片键查询的路由 ==');
const ex = db.getSiblingDB('library').borrow_logs.find({reader_card: 'R20240001'}).explain();
print(JSON.stringify(ex.queryPlanner.winningPlan.shards));
print('== 不按分片键查询（广播） ==');
const ex2 = db.getSiblingDB('library').borrow_logs.find({status: '逾期'}).explain();
print(JSON.stringify(ex2.queryPlanner.winningPlan.shards));
"""

STATUS_JS = """
const s = db.adminCommand({listShards: 1});
print('分片：' + s.shards.map(x => x._id + ' => ' + x.host).join(' ; '));
const c = db.getSiblingDB('config').databases.findOne({_id: 'library'});
print('library 主分片：' + (c ? c.primary : '未知'));
"""


def main() -> None:
    log: list[str] = []

    def conn() -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(HOST, port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        return cli

    def sh(cmd: str, timeout: int = 240) -> tuple[int, str]:
        cli = conn()
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"$ {cmd}")
        log.append(text)
        log.append(f"[exit {rc}]")
        log.append("")
        return rc, text

    def put(remote: str, text: str) -> None:
        cli = conn()
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    for name, js in (("shard", SHARD_JS), ("split", SPLIT_JS), ("dist", DIST_JS),
                     ("route", ROUTE_JS), ("status", STATUS_JS)):
        put(f"/data/lib/tmp/sh_{name}.js", js)

    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/sh_shard.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/sh_split.js")
    time.sleep(25)
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/sh_dist.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/sh_route.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/sh_status.js")

    (OUT / "shard_sharding.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
