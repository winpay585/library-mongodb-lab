"""阶段三（C）：建索引 → 开分片 → 切块均衡 → 验证分布与查询路由。

用法：python scripts\\lab_shard_final.py
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

IDX_JS = """
const d = db.getSiblingDB('library');
d.books.createIndex({isbn: 'hashed'}, {name: 'idx_isbn_hashed'});
d.books.createIndex({isbn: 1}, {unique: true, name: 'uk_isbn'});
d.books.createIndex({category: 1}, {name: 'idx_category'});
d.books.createIndex({title: 'text'}, {name: 'idx_title_text'});
d.books.createIndex({category: 1, isbn: 1}, {name: 'idx_cat_isbn'});
d.readers.createIndex({card_no: 1}, {unique: true, name: 'uk_card_no'});
d.readers.createIndex({college: 1}, {name: 'idx_college'});
d.readers.createIndex({college: 1, card_no: 1}, {name: 'idx_college_card'});
d.borrow_logs.createIndex({reader_card: 'hashed'}, {name: 'idx_card_hashed'});
d.borrow_logs.createIndex({book_isbn: 1}, {name: 'idx_book_isbn'});
d.borrow_logs.createIndex({borrow_date: -1}, {name: 'idx_date_desc'});
d.borrow_logs.createIndex({book_isbn: 1, borrow_date: -1}, {name: 'idx_isbn_date'});
d.borrow_logs.createIndex({status: 1}, {name: 'idx_status'});
print('books 索引=' + d.books.getIndexes().length + ' readers=' + d.readers.getIndexes().length
      + ' borrow_logs=' + d.borrow_logs.getIndexes().length);
"""

SHARD_JS = """
printjson(db.adminCommand({shardCollection: 'library.borrow_logs', key: {reader_card: 'hashed'}}));
printjson(db.adminCommand({shardCollection: 'library.books', key: {isbn: 'hashed'}}));
const c = db.getSiblingDB('config').collections.find({}, {_id: 1, key: 1}).toArray();
print('分片集合：' + JSON.stringify(c));
"""

SPLIT_JS = """
const pts = ['-6917529027641081856', '-4611686018427387904', '-2305843009213693952',
             '0', '2305843009213693952', '4611686018427387904', '6917529027641081856'];
let ok = 0;
pts.forEach(p => {
  const r = db.adminCommand({split: 'library.borrow_logs', middle: {reader_card: NumberLong(p)}});
  if (r.ok === 1) ok++;
});
print('borrow_logs 新切出块数：' + ok);
const r2 = db.adminCommand({split: 'library.books', middle: {isbn: NumberLong('0')}});
print('books 切块 ok=' + r2.ok);
db.adminCommand({balancerStart: 1});
print('均衡器已启动');
"""

DIST_JS = """
print('== borrow_logs 分布 ==');
const a = db.getSiblingDB('library').borrow_logs.getShardDistribution();
['shard1', 'shard2'].forEach(s => { if (a[s]) print(s + ': 文档 ' + a[s].docs + '  块 ' + a[s].chunks + '  大小 ' + a[s].data); });
print('合计 文档 ' + a.totals.docs + '  块 ' + a.totals.chunks);
print('== books 分布 ==');
const b = db.getSiblingDB('library').books.getShardDistribution();
['shard1', 'shard2'].forEach(s => { if (b[s]) print(s + ': 文档 ' + b[s].docs + '  块 ' + b[s].chunks + '  大小 ' + b[s].data); });
print('合计 文档 ' + b.totals.docs + '  块 ' + b.totals.chunks);
"""

ROUTE_JS = """
function shardsOf(q, coll) {
  const ex = db.getSiblingDB('library')[coll].find(q).explain();
  return (ex.queryPlanner.winningPlan.shards || []).map(s => s.shardName).join(',');
}
print('按分片键查 reader_card=R20240001  → 命中分片: ' + shardsOf({reader_card: 'R20240001'}, 'borrow_logs'));
print('不按分片键查 status=逾期          → 命中分片: ' + shardsOf({status: '逾期'}, 'borrow_logs'));
print('按分片键查 isbn=9787115428028    → 命中分片: ' + shardsOf({isbn: '9787115428028'}, 'books'));
print('插入一条并按 isbn 回查：');
db.getSiblingDB('library').books.insertOne({isbn: 'shard-probe-001', title: '分片写入探针', category: '测试', price: 1, stock: 1});
print('  查到 → 命中分片: ' + shardsOf({isbn: 'shard-probe-001'}, 'books'));
db.getSiblingDB('library').books.deleteOne({isbn: 'shard-probe-001'});
"""

STATUS_JS = """
const s = db.adminCommand({listShards: 1});
print('分片成员：');
s.shards.forEach(x => print('  ' + x._id + ' => ' + x.host));
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

    for name, js in (("idx", IDX_JS), ("shard", SHARD_JS), ("split", SPLIT_JS),
                     ("dist", DIST_JS), ("route", ROUTE_JS), ("status", STATUS_JS)):
        put(f"/data/lib/tmp/f_{name}.js", js)

    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/f_idx.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/f_shard.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/f_split.js")
    time.sleep(25)
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/f_dist.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/f_route.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/f_status.js")

    (OUT / "shard_final.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
