"""实验室三台 CentOS 节点的远程操作底座（paramiko）。

用法：
  python scripts\\lab_remote.py discover                 # 扫描网段，识别三台节点的 IP/主机名
  python scripts\\lab_remote.py run <host> "<command>"    # 在指定节点执行命令
  python scripts\\lab_remote.py all "<command>"           # 三台依次执行
  python scripts\\lab_remote.py put <host> <local> <remote>

凭据通过环境变量传入：LAB_USER / LAB_PASS（默认 root / 111111）。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
SUBNET = os.environ.get("LAB_SUBNET", "192.168.121")
CANDIDATES = [f"{SUBNET}.{i}" for i in range(128, 141)]


def connect(host: str, timeout: float = 8.0) -> paramiko.SSHClient | None:
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(host, port=22, username=USER, password=PASS,
                    timeout=timeout, auth_timeout=timeout, banner_timeout=timeout,
                    allow_agent=False, look_for_keys=False)
        return cli
    except Exception:
        cli.close()
        return None


def run(cli: paramiko.SSHClient, cmd: str, timeout: float = 60) -> tuple[int, str]:
    _, out, err = cli.exec_command(cmd, timeout=timeout, get_pty=False)
    code = out.channel.recv_exit_status()
    text = (out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")).strip()
    return code, text


def discover() -> None:
    found = []
    for host in CANDIDATES:
        cli = connect(host)
        if not cli:
            continue
        _, hn = run(cli, "hostname")
        _, osr = run(cli, "cat /etc/centos-release 2>/dev/null || cat /etc/os-release | head -2")
        _, ip = run(cli, "hostname -I")
        _, mongo = run(cli, "command -v mongod || echo NONE")
        _, df = run(cli, "df -h / | tail -1")
        _, mem = run(cli, "free -m | head -2 | tail -1")
        found.append((host, hn, osr.splitlines()[0] if osr else "", ip, mongo, df, mem))
        cli.close()
    for f in found:
        print("=" * 60)
        print(f"IP={f[0]}  HOST={f[1]}  OS={f[2]}")
        print(f"  hostname -I : {f[3]}")
        print(f"  mongod      : {f[4]}")
        print(f"  disk        : {f[5]}")
        print(f"  mem         : {f[6]}")
    if len(found) != 3:
        print(f"\n!! 只识别到 {len(found)} 台，期望 3 台")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    action = sys.argv[1]
    if action == "discover":
        discover()
        return
    if action == "run":
        host, cmd = sys.argv[2], sys.argv[3]
        cli = connect(host)
        if not cli:
            raise SystemExit(f"无法连接 {host}")
        code, text = run(cli, cmd)
        print(text)
        print(f"[exit {code}]")
        cli.close()
        return
    if action == "all":
        cmd = sys.argv[2]
        for host in CANDIDATES:
            cli = connect(host, timeout=4)
            if not cli:
                continue
            _, hn = run(cli, "hostname")
            code, text = run(cli, cmd)
            print(f"===== {hn} ({host}) =====")
            print(text)
            print(f"[exit {code}]")
            cli.close()
        return
    if action == "put":
        host, local, remote = sys.argv[2], sys.argv[3], sys.argv[4]
        cli = connect(host)
        if not cli:
            raise SystemExit(f"无法连接 {host}")
        sftp = cli.open_sftp()
        sftp.put(local, remote)
        sftp.close()
        cli.close()
        print(f"uploaded {local} -> {remote}")
        return
    print(__doc__)


if __name__ == "__main__":
    main()
