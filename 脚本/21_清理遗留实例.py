"""清理遗留实例（27016）+ 核实分片真实文档数 + 索引扫描量对比。

用法：python scripts\\lab_cleanup_legacy.py
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
MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

SHARD_COUNT_JS = """
const d = db.getSiblingDB('library');
print('本分片 ' + db.adminCommand({hostInfo: 1}).system.hostname + ' 上：books=' + d.books.countDocuments()
      + ' borrow_logs=' + d.borrow_logs.countDocuments());
"""

PERF_JS = """
const d = db.getSiblingDB('library');
function stat(label, q, hint) {
  const p = d.borrow_logs.find(q).hint(hint).explain('executionStats');
  const s = p.executionStats;
  print(label + ': 返回 ' + s.nReturned + ' 条 | 扫描文档 ' + s.totalDocsExamined
        + ' | 扫描索引项 ' + s.totalKeysExamined + ' | 耗时 ' + s.executionTimeMillis + ' ms');
}
stat('无索引 + 全表扫描 (status=逾期)', {status: '逾期'}, {$natural: 1});
stat('走 idx_status  (status=逾期)', {status: '逾期'}, {status: 1});
stat('无索引 + 全表扫描 (book_isbn)', {book_isbn: '9787115428028'}, {$natural: 1});
stat('走 idx_book_isbn', {book_isbn: '9787115428028'}, {book_isbn: 1});
"""


def main() -> None:
    log: list[str] = []

    def conn(name: str) -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[name], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        return cli

    def sh(host: str, cmd: str, timeout: int = 180) -> str:
        cli = conn(host)
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"[{host}] $ {cmd}")
        log.append(text)
        log.append(f"[exit {rc}]")
        log.append("")
        return text

    def put(host: str, remote: str, text: str) -> None:
        cli = conn(host)
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    # 一、停用并删除遗留 27016 实例（systemd 服务 + /etc/mongod.conf + /var/lib/mongo）
    for name in NODES:
        sh(name, "systemctl disable --now mongod; sleep 1; systemctl is-active mongod; "
                "cp -a /etc/mongod.conf /data/lib/tmp/legacy_mongod.conf.bak 2>/dev/null; "
                "rm -f /etc/mongod.conf; du -sh /var/lib/mongo 2>/dev/null; rm -rf /var/lib/mongo; "
                "echo '遗留数据目录已删除'; ss -lntp | grep 27016 || echo '27016 端口已释放'")

    # 二、分片真实文档数（先在各分片本机建一个只读核查账号，走 localhost 例外）
    for name, port in (("nosql01", 27020), ("nosql03", 27021)):
        put(name, "/data/lib/tmp/shard_probe_user.js", """
const a = db.getSiblingDB('admin');
try { a.createUser({user: 'shard_probe', pwd: 'probe2026', roles: [{role: 'readAnyDatabase', db: 'admin'}]});
      print('shard_probe 已建'); } catch (e) { print('已存在'); }
""")
        sh(name, f"mongosh --port {port} --quiet /data/lib/tmp/shard_probe_user.js")
        put(name, "/data/lib/tmp/shard_count.js", SHARD_COUNT_JS)
        sh(name, f"mongosh --port {port} -u shard_probe -p probe2026 --authenticationDatabase admin --quiet "
                 "/data/lib/tmp/shard_count.js")

    # 三、索引扫描量对比（单机 27017）
    put("nosql01", "/data/lib/tmp/perf_cmp.js", PERF_JS)
    sh("nosql01", f"mongosh --port 27017 {MON} --quiet /data/lib/tmp/perf_cmp.js")

    # 四、清理后端口总览
    for name in NODES:
        sh(name, "ss -lntp | grep -E ':(2701[6-9]|2702[0-2])' | awk '{print $4}' | sort -t: -k2 -n")

    (OUT / "cleanup_legacy.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
