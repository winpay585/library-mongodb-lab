"""副本集收尾：建账号（走 127.0.0.1 localhost 例外）、导入数据、主从校验。

用法：python scripts\\lab_replica_fix.py
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

USERS_JS = """
const admin = db.getSiblingDB('admin');
admin.createUser({user:'platform_admin', pwd:'Admin2026pwd', roles:[{role:'root', db:'admin'}]});
const lib = db.getSiblingDB('library');
lib.createUser({user:'lib_admin', pwd:'lib2026pwd', roles:[{role:'dbOwner', db:'library'}]});
lib.createUser({user:'lib_editor', pwd:'lib2026pwd', roles:[{role:'readWrite', db:'library'}]});
lib.createUser({user:'lib_reader', pwd:'lib2026pwd', roles:[{role:'read', db:'library'}]});
print('副本集账号创建完成');
"""

MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

CHECK_JS = """
db.getMongo().setReadPref('secondaryPreferred');
const d = db.getSiblingDB('library');
print('本节点：' + db.hello().me + '  角色：' + (db.hello().isWritablePrimary ? 'PRIMARY' : 'SECONDARY'));
['books', 'readers', 'borrow_logs'].forEach(c => print('  ' + c + ' = ' + d[c].countDocuments()));
print('  books 索引数 = ' + d.books.getIndexes().length);
print('  borrow_logs 索引数 = ' + d.borrow_logs.getIndexes().length);
"""


def conn(name: str) -> paramiko.SSHClient:
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(NODES[name], port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)
    return cli


def main() -> None:
    log: list[str] = []

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

    # 1. 建账号（显式 127.0.0.1）
    cli = conn("nosql01")
    sftp = cli.open_sftp()
    with sftp.open("/data/lib/tmp/rs_users.js", "w") as f:
        f.write(USERS_JS)
    with sftp.open("/data/lib/tmp/rs_check.js", "w") as f:
        f.write(CHECK_JS)
    sftp.close()
    cli.close()
    sh("nosql01", "mongosh 'mongodb://127.0.0.1:27018/?directConnection=true' --quiet /data/lib/tmp/rs_users.js")

    # 2. 导入三份数据
    for col in ("books", "readers", "borrow_logs"):
        sh("nosql01", f"mongoimport --port 27018 -u lib_admin -p lib2026pwd --authenticationDatabase library "
                      f"--db library --collection {col} --file /data/lib/tmp/data/{col}.txt --jsonArray --drop")

    # 3. 主从一致性（同一份 JS 在三台上执行，从节点按 secondary 优先读）
    for node in ("nosql01", "nosql02", "nosql03"):
        if node != "nosql01":
            cli = conn(node)
            sftp = cli.open_sftp()
            with sftp.open("/data/lib/tmp/rs_check.js", "w") as f:
                f.write(CHECK_JS)
            sftp.close()
            cli.close()
        sh(node, f"mongosh --port 27018 {MON} --quiet /data/lib/tmp/rs_check.js")

    # 4. 状态与延迟
    sh("nosql01", f"mongosh --port 27018 {MON} --eval 'rs.status().members.forEach(m => "
                  "print(m.name, m.stateStr, m.health))'")
    sh("nosql01", f"mongosh --port 27018 {MON} --eval 'rs.printSecondaryReplicationInfo()'")

    (OUT / "replica_fix.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
