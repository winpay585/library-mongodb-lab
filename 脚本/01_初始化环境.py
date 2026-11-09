"""三台 CentOS 节点的基础准备：统一主机名、hosts、项目目录、keyfile。

用法：python scripts\\lab_setup_base.py
凭据：LAB_USER / LAB_PASS 环境变量（默认 root / 111111）。
"""

from __future__ import annotations

import os
from pathlib import Path

import paramiko

NODES = {
    "nosql01": "192.168.121.134",
    "nosql02": "192.168.121.135",
    "nosql03": "192.168.121.136",
}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
ROOT = Path(__file__).resolve().parents[1]
LOGDIR = ROOT / "runtime" / "linux"

HOSTS_BLOCK = """127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
::1         localhost localhost.localdomain localhost6 localhost6.localdomain6
192.168.121.134 nosql01
192.168.121.135 nosql02
192.168.121.136 nosql03"""

DIRS = ["/data/lib/log", "/data/lib/conf", "/data/lib/key", "/data/lib/tmp",
        "/data/lib/standalone", "/data/lib/rs1", "/data/lib/rs2", "/data/lib/rs3",
        "/data/lib/cfg1", "/data/lib/cfg2", "/data/lib/cfg3",
        "/data/lib/shard1", "/data/lib/shard2", "/data/lib/out"]


def connect(host: str) -> paramiko.SSHClient:
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(host, port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)
    return cli


def run(cli, cmd, timeout=90):
    _, out, err = cli.exec_command(cmd, timeout=timeout)
    code = out.channel.recv_exit_status()
    return code, (out.read() + err.read()).decode("utf-8", "replace").strip()


def main() -> None:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    log = []
    # keyfile：三台内容一致，权限 400/600，供副本集与分片内部认证
    key = os.urandom(32).hex()
    key_b64 = key.encode()
    for name, ip in NODES.items():
        cli = connect(ip)
        steps = []
        steps.append(run(cli, f"hostnamectl set-hostname {name} && hostname"))
        # hosts 整块重写（保留原有注释行外的前两行）
        hosts_tmp = "/data/lib/tmp/hosts.new"
        run(cli, "mkdir -p /data/lib/tmp")
        sftp = cli.open_sftp()
        with sftp.open(hosts_tmp, "w") as f:
            f.write(HOSTS_BLOCK + "\n")
        sftp.close()
        steps.append(run(cli, f"cat {hosts_tmp} > /etc/hosts && cat /etc/hosts | tail -3"))
        steps.append(run(cli, "mkdir -p " + " ".join(DIRS) + " && ls -d /data/lib/*"))
        # keyfile
        sftp = cli.open_sftp()
        with sftp.open("/data/lib/key/mongo.key", "w") as f:
            f.write(key_b64.decode())
        sftp.close()
        steps.append(run(cli, "chmod 400 /data/lib/key/mongo.key && ls -l /data/lib/key/mongo.key"))
        steps.append(run(cli, "systemctl disable --now firewalld 2>/dev/null; getenforce || true"))
        # 保留旧实例，但确认它只在 27016 上
        steps.append(run(cli, "ss -lntp | grep -E '2701|2702' || echo 'no 2701x/2702x listener'"))
        log.append(f"===== {name} ({ip}) =====")
        log += [f"  {s}" for s in steps]
        cli.close()
        print(f"{name} done")
    (LOGDIR / "setup_base.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
