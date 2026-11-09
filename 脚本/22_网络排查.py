"""查看三台虚拟机的网卡与 NetworkManager 连接配置（为切桥接做准备）。"""

from __future__ import annotations

import os

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
CMD = (
    "nmcli -t -f NAME,DEVICE,TYPE con show; echo ---; "
    "nmcli -t -f CONNECTION,ipv4.method,ipv4.addresses ip 2>/dev/null; echo ---; "
    "ip -br addr show | grep -v 'lo '"
)


def main() -> None:
    for name, ip in NODES.items():
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(ip, port=22, username=os.environ.get("LAB_USER", "root"),
                    password=os.environ.get("LAB_PASS", "111111"), timeout=10,
                    allow_agent=False, look_for_keys=False)
        _, out, err = cli.exec_command(CMD, timeout=30)
        print(f"=== {name} ({ip})")
        print((out.read() + err.read()).decode("utf-8", "replace"))
        cli.close()


if __name__ == "__main__":
    main()
