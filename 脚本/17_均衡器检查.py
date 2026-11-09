"""等待均衡器完成块迁移，然后输出真实分布与路由对比。

用法：python scripts\\lab_shard_balance.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import paramiko

HOST = "192.168.121.134"
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"
MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

CHUNKS_JS = """
const cfg = db.getSiblingDB('config');
const g = cfg.chunks.aggregate([
  {$match: {uuid: cfg.collections.findOne({_id: 'library.borrow_logs'}).uuid}},
  {$group: {_id: '$shard', n: {$sum: 1}}}
]).toArray();
print('borrow_logs 块分布: ' + JSON.stringify(g));
const gb = cfg.chunks.aggregate([
  {$match: {uuid: cfg.collections.findOne({_id: 'library.books'}).uuid}},
  {$group: {_id: '$shard', n: {$sum: 1}}}
]).toArray();
print('books 块分布: ' + JSON.stringify(gb));
print('均衡器状态: ' + JSON.stringify(sh.getBalancerState()));
"""

DIST_JSON = """
print('getShardDistribution(borrow_logs) = ' + JSON.stringify(
  db.getSiblingDB('library').borrow_logs.getShardDistribution()));
print('getShardDistribution(books) = ' + JSON.stringify(
  db.getSiblingDB('library').books.getShardDistribution()));
"""

ROUTE_JS = """
function shardsOf(q, coll) {
  const ex = db.getSiblingDB('library')[coll].find(q).explain();
  const s = (ex.queryPlanner.winningPlan.shards || []).map(x => x.shardName);
  return s.length ? s.join(',') : '(单分片/未分发)';
}
print('① 按分片键 reader_card=R20240001 → ' + shardsOf({reader_card: 'R20240001'}, 'borrow_logs'));
print('② 不按分片键 status=逾期       → ' + shardsOf({status: '逾期'}, 'borrow_logs'));
print('③ 按分片键 isbn=9787115428028 → ' + shardsOf({isbn: '9787115428028'}, 'books'));
"""

PER_SHARD = """
const d = db.getSiblingDB('library');
print('总文档 borrow_logs=' + d.borrow_logs.countDocuments() + ' books=' + d.books.countDocuments());
"""


def main() -> None:
    log: list[str] = []

    def conn() -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(HOST, port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        return cli

    def sh(cmd: str, timeout: int = 180) -> str:
        cli = conn()
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"$ {cmd}")
        log.append(text)
        log.append("")
        return text

    def put(remote: str, text: str) -> None:
        cli = conn()
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    put("/data/lib/tmp/b_chunks.js", CHUNKS_JS)
    put("/data/lib/tmp/b_dist.js", DIST_JSON)
    put("/data/lib/tmp/b_route.js", ROUTE_JS)
    put("/data/lib/tmp/b_per.js", PER_SHARD)

    # 轮询等待均衡结束（最多 3 分钟）
    for i in range(36):
        text = sh(f"mongosh --port 27022 {MON} /data/lib/tmp/b_chunks.js")
        if "shard2" in text:
            log.append(f">>> 第 {i * 5} 秒检测到 shard2 已有数据块，均衡已完成")
            break
        time.sleep(5)
    else:
        log.append(">>> 3 分钟内均衡器未迁移数据块")

    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/b_dist.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/b_route.js")
    sh(f"mongosh --port 27022 {MON} /data/lib/tmp/b_per.js")

    (OUT / "shard_balance.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
