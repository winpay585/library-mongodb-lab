"""在远端用后台脚本方式拉起各节点实例，然后检查端口与进程。

用法：python scripts\\lab_boot_instances.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
CONFS = {
    "nosql01": ["standalone-auth", "rs1", "cfg1", "shard1"],
    "nosql02": ["rs2", "cfg2", "shard1", "shard2"],
    "nosql03": ["rs3", "cfg3", "shard2"],
}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"

BOOT = """#!/bin/bash
for c in {confs}; do
  port=$(grep -oP 'port:\\s*\\K\\d+' /data/lib/conf/$c.conf)
  if ss -lnt | grep -q ":$port "; then echo "$c ($port) 已在运行，跳过"; continue; fi
  setsid mongod -f /data/lib/conf/$c.conf </dev/null >/data/lib/log/$c.boot.log 2>&1 &
  echo "$c ($port) 启动"
  sleep 2
done
"""

MONGOS_BOOT = """#!/bin/bash
if ss -lnt | grep -q ":27022 "; then echo "mongos 已在运行，跳过"; exit 0; fi
setsid mongos -f /data/lib/conf/mongos.conf </dev/null >/data/lib/log/mongos.boot.log 2>&1 &
echo "mongos 启动"
"""


def main() -> None:
    log: list[str] = []

    def conn(host: str) -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[host], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        return cli

    def run(host: str, cmd: str, timeout: int = 120) -> str:
        cli = conn(host)
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"[{host}] $ {cmd}")
        log.append(text)
        log.append("")
        return text

    def put(host: str, remote: str, text: str) -> None:
        cli = conn(host)
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    for host, confs in CONFS.items():
        put(host, "/tmp/boot_instances.sh", BOOT.format(confs=" ".join(confs)))
        run(host, "bash /tmp/boot_instances.sh 2>&1")

    put("nosql01", "/tmp/boot_mongos.sh", MONGOS_BOOT)
    run("nosql01", "bash /tmp/boot_mongos.sh 2>&1")

    time.sleep(25)
    for host in NODES:
        run(host, "ss -lnt | grep -E ':270(17|18|19|20|21|22) ' | awk '{print $4}' | sort -t: -k2 -n")

    (OUT / "boot_instances.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
