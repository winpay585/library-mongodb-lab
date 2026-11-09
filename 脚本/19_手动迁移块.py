"""把 borrow_logs 的一半数据块手动迁到 shard2，验证分布与路由差异。

用法：python scripts\\lab_shard_move.py
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

MOVE_JS = """
function chunksOf(ns) {
  const cfg = db.getSiblingDB('config');
  const c = cfg.collections.findOne({_id: ns});
  return cfg.chunks.find({uuid: c.uuid}).sort({'min.reader_card': 1, 'min.isbn': 1}).toArray();
}
const bl = chunksOf('library.borrow_logs');
print('borrow_logs 现有块数：' + bl.length);
bl.slice(0, Math.floor(bl.length / 2)).forEach((c, i) => {
  const r = db.adminCommand({moveChunk: 'library.borrow_logs', bounds: [c.min, c.max], to: 'shard2'});
  print('  迁移第 ' + (i + 1) + ' 块 → ' + (r.ok === 1 ? 'OK' : '失败: ' + r.errmsg));
});
const bk = chunksOf('library.books');
print('books 现有块数：' + bk.length);
const r2 = db.adminCommand({moveChunk: 'library.books', bounds: [bk[0].min, bk[0].max], to: 'shard2'});
print('  books 第 1 块迁移 → ' + (r2.ok === 1 ? 'OK' : '失败: ' + r2.errmsg));
"""

AFTER_JS = """
const cfg = db.getSiblingDB('config');
[['library.borrow_logs', 'borrow_logs'], ['library.books', 'books']].forEach(([ns, name]) => {
  const c = cfg.collections.findOne({_id: ns});
  const g = cfg.chunks.aggregate([{$match: {uuid: c.uuid}}, {$group: {_id: '$shard', n: {$sum: 1}}}]).toArray();
  print(name + ' 块分布: ' + JSON.stringify(g));
});
print('--- getShardDistribution ---');
['borrow_logs', 'books'].forEach(n => {
  const o = db.getSiblingDB('library')[n].getShardDistribution();
  const parts = [];
  Object.keys(o).forEach(k => {
    if (k !== 'Totals') parts.push(k.replace(/ .*/, '') + ': 文档 ' + o[k].docs + ' 块 ' + o[k].chunks);
  });
  print(n + ' → ' + parts.join(' | ') + ' | 合计 ' + o.Totals.docs + ' 文档 ' + o.Totals.chunks + ' 块');
});
"""

ROUTE_JS = """
function shardsOf(q, coll) {
  const ex = db.getSiblingDB('library')[coll].find(q).explain();
  const s = (ex.queryPlanner.winningPlan.shards || []).map(x => x.shardName);
  return s.length ? s.join(',') : '(1 个分片)';
}
print('① 带分片键 reader_card=R20240001 → 命中 ' + shardsOf({reader_card: 'R20240001'}, 'borrow_logs'));
print('② 不带分片键 status=逾期       → 命中 ' + shardsOf({status: '逾期'}, 'borrow_logs'));
print('③ 带分片键 isbn=9787115428028 → 命中 ' + shardsOf({isbn: '9787115428028'}, 'books'));
print('④ 全表扫描（无分片键范围）     → 命中 ' +
      shardsOf({}, 'borrow_logs'));
"""


def main() -> None:
    log: list[str] = []

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)

    def sh(cmd: str, timeout: int = 240) -> None:
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        log.append(f"$ {cmd}")
        log.append((out.read() + err.read()).decode("utf-8", "replace").strip())
        log.append("")

    sftp = cli.open_sftp()
    for name, js in (("move", MOVE_JS), ("after", AFTER_JS), ("route", ROUTE_JS)):
        with sftp.open(f"/data/lib/tmp/m_{name}.js", "w") as f:
            f.write(js)
    sftp.close()

    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/m_move.js")
    time.sleep(8)
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/m_after.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/m_route.js")

    cli.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "shard_move.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
