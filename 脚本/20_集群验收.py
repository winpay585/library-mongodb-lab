"""集群总验收：三台节点信息、各实例端口、三套部署的数据与状态、分片分布与路由。

用法：python scripts\\lab_final_verify.py
"""

from __future__ import annotations

import os
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"
MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

DIST_JS = """
const cfg = db.getSiblingDB('config');
[['library.borrow_logs', 'borrow_logs'], ['library.books', 'books']].forEach(([ns, name]) => {
  const c = cfg.collections.findOne({_id: ns});
  const g = cfg.chunks.aggregate([{$match: {uuid: c.uuid}}, {$group: {_id: '$shard', n: {$sum: 1}}}]).toArray();
  print(name + ' 块分布: ' + JSON.stringify(g));
});
print('borrow_logs getShardDistribution: ' + JSON.stringify(
  db.getSiblingDB('library').borrow_logs.getShardDistribution()));
print('books getShardDistribution: ' + JSON.stringify(
  db.getSiblingDB('library').books.getShardDistribution()));
"""

ROUTE_JS = """
function shardsOf(q, coll) {
  const ex = db.getSiblingDB('library')[coll].find(q).explain();
  const s = (ex.queryPlanner.winningPlan.shards || []).map(x => x.shardName);
  return s.length ? s.join(',') : '(1 个分片)';
}
print('① 带分片键 reader_card=R20240001 → ' + shardsOf({reader_card: 'R20240001'}, 'borrow_logs'));
print('② 不带分片键 status=逾期        → ' + shardsOf({status: '逾期'}, 'borrow_logs'));
print('③ 带分片键 isbn=9787115428028  → ' + shardsOf({isbn: '9787115428028'}, 'books'));
"""

PERF_JS = """
const d = db.getSiblingDB('library');
function run(label, q, hint) {
  const ex = d.borrow_logs.find(q, hint ? {hint: hint} : {});
  const p = ex.explain('executionStats');
  const s = p.executionStats;
  print(label + ': 返回 ' + s.nReturned + ' 条, 扫描文档 ' + s.totalDocsExamined
        + ', 扫描索引项 ' + s.totalKeysExamined + ', 耗时 ' + s.executionTimeMillis + ' ms');
}
run('走 idx_book_isbn（借阅日志按 ISBN 查）', {book_isbn: '9787115428028'});
run('走 idx_card_hashed（按借阅证查）', {reader_card: 'R20240001'});
"""


def main() -> None:
    log: list[str] = []

    def conn(name: str) -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[name], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        return cli

    def sh(host: str, cmd: str, timeout: int = 180) -> None:
        cli = conn(host)
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        log.append(f"[{host}] $ {cmd}")
        log.append((out.read() + err.read()).decode("utf-8", "replace").strip())
        log.append("")
        cli.close()

    def put(host: str, remote: str, text: str) -> None:
        cli = conn(host)
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    # 一、节点信息与实例端口
    for name in NODES:
        sh(name, "hostname; hostname -I | awk '{print $1}'; "
                "grep PRETTY_NAME /etc/os-release; uname -r; free -g | awk '/Mem/{print \"内存 \" $2 \" GB\"}'; "
                "ss -lntp | grep -E ':(2701[6-9]|2702[0-2])' | awk '{print $4, $6}' | sort -t: -k2 -n")

    # 二、单机环境
    sh("nosql01", f"mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet "
                  "--eval 'const d=db.getSiblingDB(\"library\");"
                  "print(\"单机 books=\"+d.books.countDocuments()+\" readers=\"+d.readers.countDocuments()"
                  "+\" borrow_logs=\"+d.borrow_logs.countDocuments()+\" fs.files=\"+d.fs.files.countDocuments()+\" fs.chunks=\"+d.fs.chunks.countDocuments());"
                  "print(\"索引: books=\"+d.books.getIndexes().length+\" readers=\"+d.readers.getIndexes().length"
                  "+\" borrow_logs=\"+d.borrow_logs.getIndexes().length)'")
    sh("nosql01", f"mongosh --port 27017 {MON} --quiet --eval 'const d=db.getSiblingDB(\"library\");"
                  "[\"books\",\"readers\",\"borrow_logs\"].forEach(c => print(c + \": \" + "
                  "d[c].getIndexes().map(i => i.name).join(\", \")));'")

    # 三、副本集
    sh("nosql01", f"mongosh --port 27018 {MON} --eval 'rs.status().members.forEach(m => print(m.name, m.stateStr, m.health))'")
    sh("nosql01", f"mongosh --port 27018 {MON} --eval 'rs.printSecondaryReplicationInfo()'")

    # 四、分片集群
    put("nosql01", "/data/lib/tmp/v_dist.js", DIST_JS)
    put("nosql01", "/data/lib/tmp/v_route.js", ROUTE_JS)
    put("nosql01", "/data/lib/tmp/v_perf.js", PERF_JS)
    sh("nosql01", f"mongosh --port 27022 {MON} /data/lib/tmp/v_dist.js")
    sh("nosql01", f"mongosh --port 27022 {MON} /data/lib/tmp/v_route.js")
    sh("nosql01", f"mongosh --port 27022 {MON} --eval 'const s=db.adminCommand({{listShards:1}}); "
                  "s.shards.forEach(x=>print(x._id, x.host))'")
    sh("nosql01", f"mongosh --port 27022 {MON} /data/lib/tmp/v_perf.js")

    # 五、三台机器上的进程总览
    for name in NODES:
        sh(name, "ps -o pid,etime,cmd -C mongod,mongos | grep -v PID | sed 's/  */ /g'")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "final_verify.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
