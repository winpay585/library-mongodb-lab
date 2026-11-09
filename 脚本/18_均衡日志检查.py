"""检查均衡器为何没有迁移块：mongos 日志 + 均衡器运行状态。"""

from __future__ import annotations

import os
from pathlib import Path

import paramiko

HOST = "192.168.121.134"
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"

JS = """
print('getBalancerState=' + sh.getBalancerState());
print('isBalancerRunning=' + (typeof sh.isBalancerRunning === 'function' ? sh.isBalancerRunning() : 'n/a'));
printjson(db.adminCommand({balancerStatus: 1}));
"""


def main() -> None:
    log: list[str] = []
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)

    def sh(cmd: str) -> None:
        _, out, err = cli.exec_command(cmd, timeout=120)
        log.append(f"$ {cmd}")
        log.append((out.read() + err.read()).decode("utf-8", "replace").strip())
        log.append("")

    sftp = cli.open_sftp()
    with sftp.open("/data/lib/tmp/bal.js", "w") as f:
        f.write(JS)
    sftp.close()

    sh("mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet /data/lib/tmp/bal.js")
    sh("grep -iE 'balanc|migrat|moveChunk' /data/lib/log/mongos.log | tail -n 25")
    sh("grep -icE 'error|abort' /data/lib/log/mongos.log")

    cli.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "balancer_probe.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
