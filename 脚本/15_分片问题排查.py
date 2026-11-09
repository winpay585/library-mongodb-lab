"""探查 shardCollection 报错原因。"""

from __future__ import annotations

import os
from pathlib import Path

import paramiko

HOST = "192.168.121.134"
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"
MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

JS = """
const r = db.adminCommand({shardCollection: 'library.borrow_logs', key: {reader_card: 'hashed'}});
printjson(r);
print('--- 用 sh 助手再试 ---');
try { printjson(sh.shardCollection('library.borrow_logs', {reader_card: 'hashed'})); }
catch (e) { print('助手报错: ' + e.message); }
print('--- 数据库分片状态 ---');
printjson(db.adminCommand({listDatabases: 1, filter: {name: 'library'}}).databases);
printjson(db.getSiblingDB('config').databases.find().toArray());
"""


def main() -> None:
    log: list[str] = []
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)
    sftp = cli.open_sftp()
    with sftp.open("/data/lib/tmp/probe_shard.js", "w") as f:
        f.write(JS)
    sftp.close()
    _, out, err = cli.exec_command(f"mongosh --port 27022 {MON} /data/lib/tmp/probe_shard.js", timeout=120)
    log.append((out.read() + err.read()).decode("utf-8", "replace"))
    cli.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "probe_shard.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
