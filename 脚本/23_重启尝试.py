"""重启后按节点拉起全部 mongod/mongos 实例，并复验集群。

用法：python scripts\\lab_restart_all.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
START = {
    "nosql01": ["standalone-auth", "rs1", "cfg1", "shard1"],
    "nosql02": ["rs2", "cfg2", "shard1", "shard2"],
    "nosql03": ["rs3", "cfg3", "shard2"],
}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"


def main() -> None:
    log: list[str] = []

    def run(host: str, cmd: str, timeout: int = 180) -> str:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[host], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"[{host}] $ {cmd}")
        log.append(text)
        log.append("")
        return text

    for host, confs in START.items():
        for c in confs:
            run(host, f"mongod -f /data/lib/conf/{c}.conf >/dev/null 2>&1; sleep 1; echo '{c} 已启动'")
    run("nosql01", "mongos -f /data/lib/conf/mongos.conf >/dev/null 2>&1; echo 'mongos 已启动'")

    time.sleep(15)
    for host in NODES:
        run(host, "ss -lntp | grep -E ':(2701[7-9]|2702[0-2])' | awk '{print $4}' | sort -t: -k2 -n")

    (OUT / "restart_all.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
