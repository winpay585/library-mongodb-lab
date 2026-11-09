"""副本集收尾（二）：用 platform_admin 建业务账号、导入数据、校验主从。

用法：python scripts\\lab_replica_fix2.py
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
PORT = 27018

USERS_JS = """
const lib = db.getSiblingDB('library');
function mk(name, pwd, roles) {
  const exists = lib.getUser(name);
  if (exists) { print(name + ' 已存在，跳过'); return; }
  lib.createUser({user: name, pwd: pwd, roles: roles});
  print(name + ' 已创建');
}
mk('lib_admin', 'lib2026pwd', [{role: 'dbOwner', db: 'library'}]);
mk('lib_editor', 'lib2026pwd', [{role: 'readWrite', db: 'library'}]);
mk('lib_reader', 'lib2026pwd', [{role: 'read', db: 'library'}]);
print('当前账号：' + lib.getUsers().users.map(u => u.user).join(', '));
"""

CHECK_JS = """
db.getMongo().setReadPref('secondaryPreferred');
const d = db.getSiblingDB('library');
print('本节点 ' + db.hello().me + ' 角色 ' + (db.hello().isWritablePrimary ? 'PRIMARY' : 'SECONDARY'));
['books', 'readers', 'borrow_logs'].forEach(c => print('  ' + c + '=' + d[c].countDocuments()));
print('  books 索引=' + d.books.getIndexes().length + '  borrow_logs 索引=' + d.borrow_logs.getIndexes().length);
"""

MON = f"-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"


def main() -> None:
    log: list[str] = []

    def conn(name_or_ip: str) -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES.get(name_or_ip, name_or_ip), port=22, username=USER, password=PASS,
                    timeout=10, allow_agent=False, look_for_keys=False)
        return cli

    def sh(host: str, cmd: str, timeout: int = 180) -> int:
        cli = conn(host)
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"[{host}] $ {cmd}")
        log.append(text)
        log.append(f"[exit {rc}]")
        log.append("")
        return rc

    def put(host: str, remote: str, text: str) -> None:
        cli = conn(host)
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    for node in NODES:
        put(node, "/data/lib/tmp/rs_users.js", USERS_JS)
        put(node, "/data/lib/tmp/rs_check.js", CHECK_JS)

    # 1. 业务账号
    sh("nosql01", f"mongosh --port {PORT} {MON} /data/lib/tmp/rs_users.js")

    # 2. 导入数据
    for col in ("books", "readers", "borrow_logs"):
        sh("nosql01", f"mongoimport --port {PORT} -u lib_admin -p lib2026pwd --authenticationDatabase library "
                      f"--db library --collection {col} --file /data/lib/tmp/data/{col}.txt --jsonArray --drop")

    # 3. 三台一致性
    for node in NODES:
        sh(node, f"mongosh --port {PORT} {MON} /data/lib/tmp/rs_check.js")

    # 4. 状态与延迟
    sh("nosql01", f"mongosh --port {PORT} {MON} --eval 'rs.status().members.forEach(m => print(m.name, m.stateStr, m.health))'")
    sh("nosql01", f"mongosh --port {PORT} {MON} --eval 'rs.printSecondaryReplicationInfo()'")

    (OUT / "replica_fix2.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
