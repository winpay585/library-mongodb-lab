"""清理三台机器上遗留的副本集实例（27018）及其数据目录。

把清理脚本先传到远端再执行，避免 pkill -f 匹配到 SSH 会话自身的命令行。
"""

from __future__ import annotations

import os
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "linux"

CLEAN = """#!/bin/bash
# 停掉占用 27018 的进程，清空副本集数据目录
for port in 27018 27019 27020 27021 27022; do
  for pid in $(ss -lntp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $6}' | grep -o 'pid=[0-9]*' | cut -d= -f2); do
    echo "kill pid=$pid (port $port)"
    kill -9 "$pid" 2>/dev/null
  done
done
sleep 3
echo "-- 剩余 mongod 进程 --"
ps -o pid,etime,cmd -C mongod
echo "-- 清理数据目录 --"
rm -rf /data/lib/rs1 /data/lib/rs2 /data/lib/rs3
echo "-- 端口占用检查 --"
ss -lntp | grep -E '2701[7-9]|2702[0-4]' || echo "27017-27024 全部空闲"
"""


def main() -> None:
    log: list[str] = []
    for name, ip in NODES.items():
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(ip, port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        sftp = cli.open_sftp()
        with sftp.open("/tmp/clean_rs.sh", "w") as f:
            f.write(CLEAN)
        sftp.close()
        _, out, err = cli.exec_command("bash /tmp/clean_rs.sh", timeout=60)
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        log.append(f"===== {name} ({ip}) =====")
        log.append(text)
        log.append("")
        cli.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reset.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
