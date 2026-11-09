"""清掉故障转移探针数据并复核三节点条数。"""

from __future__ import annotations

import os
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"
MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"


def main() -> None:
    log: list[str] = []

    def sh(host: str, cmd: str) -> None:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[host], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        _, out, err = cli.exec_command(cmd, timeout=90)
        rc = out.channel.recv_exit_status()
        log.append(f"[{host}] $ {cmd}")
        log.append((out.read() + err.read()).decode("utf-8", "replace").strip())
        log.append(f"[exit {rc}]")
        log.append("")
        cli.close()

    # 找主节点执行删除
    for host in NODES:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[host], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        _, out, _ = cli.exec_command(f"mongosh --port 27018 {MON} --eval 'print(db.hello().isWritablePrimary)'", timeout=30)
        is_primary = out.read().decode().strip() == "true"
        cli.close()
        if is_primary:
            sh(host, f"mongosh --port 27018 {MON} --eval "
                     "'const d=db.getSiblingDB(\"library\");"
                     "const r=d.books.deleteMany({isbn:\"failover-probe\"});"
                     "print(\"已删探针 \" + r.deletedCount + \" 条，books=\" + d.books.countDocuments())'")
            break

    for host in NODES:
        sh(host, f"mongosh --port 27018 {MON} --eval "
                 "'const d=db.getSiblingDB(\"library\");print(db.hello().me+\" \"+(db.hello().isWritablePrimary?\"PRIMARY\":\"SECONDARY\")"
                 "+\" books=\"+d.books.countDocuments()+\" readers=\"+d.readers.countDocuments()"
                 "+\" borrow_logs=\"+d.borrow_logs.countDocuments())'")

    (OUT / "replica_cleanup.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
