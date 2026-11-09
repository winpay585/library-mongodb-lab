"""用 guest 端脚本把真实命令与输出回显到 tty1（英文标签，避免控制台缺中文字形），逐张截图。

用法：python scripts\\lab_tty_shots3.py
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import paramiko

HOST = "192.168.121.134"
VMX = r"C:\Users\tttt\Documents\Virtual Machines\NOSQL01\NOSQL01.vmx"
VMRUN = r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "shots"

S1 = r"""clear
echo "== 1. Standalone 27017 : data size and indexes =="
echo '[root@nosql01 ~]# mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin'
mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet --eval '
const d = db.getSiblingDB("library");
print("books       = " + d.books.countDocuments());
print("readers     = " + d.readers.countDocuments());
print("borrow_logs = " + d.borrow_logs.countDocuments());
print("GridFS files= " + d.fs.files.countDocuments() + "   chunks= " + d.fs.chunks.countDocuments());
["books","readers","borrow_logs"].forEach(c => print(c + "  indexes = " + d[c].getIndexes().length));
'
echo '[root@nosql01 ~]# '
"""

S2 = r"""clear
echo "== 2. Replica set rs_lib : 27018 member states =="
echo '[root@nosql01 ~]# mongosh --port 27018 -u platform_admin -p Admin2026pwd --authenticationDatabase admin'
mongosh --port 27018 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet --eval '
rs.status().members.forEach(m => print(m.name + "   " + m.stateStr + "   health=" + m.health));
print("--- replication lag ---");
rs.printSecondaryReplicationInfo();
'
echo '[root@nosql01 ~]# '
"""

S3 = r"""clear
echo "== 3. Sharded cluster : chunks and query routing (mongos 27022) =="
echo '[root@nosql01 ~]# mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin'
mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet --eval '
const d = db.getSiblingDB("library");
const o = d.borrow_logs.getShardDistribution();
Object.keys(o).forEach(k => { if (k !== "Totals") print(k + "  docs=" + o[k].docs + "  chunks=" + o[k].chunks); });
print("total docs = " + o.Totals.docs + "   chunks = " + o.Totals.chunks);
print("--- routing ---");
print("with shard key reader_card=R20240001  -> " + JSON.stringify(
  d.borrow_logs.find({reader_card:"R20240001"}).explain().queryPlanner.winningPlan.shards.map(s=>s.shardName)));
print("no shard key   status=overdue         -> " + JSON.stringify(
  d.borrow_logs.find({status:"逾期"}).explain().queryPlanner.winningPlan.shards.map(s=>s.shardName)));
'
echo '[root@nosql01 ~]# '
"""

S4 = r"""clear
echo "== 4. Index effect : collection scan vs index scan (3000 docs) =="
echo '[root@nosql01 ~]# mongosh --port 27017 ... explain("executionStats")'
mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet --eval '
const d = db.getSiblingDB("library");
const a = d.borrow_logs.find({status:"逾期"}).hint({$natural:1}).explain("executionStats").executionStats;
const b = d.borrow_logs.find({status:"逾期"}).hint({status:1}).explain("executionStats").executionStats;
print("COLLSCAN : returned=" + a.nReturned + "  docsExamined=" + a.totalDocsExamined + "  time=" + a.executionTimeMillis + "ms");
print("IXSCAN   : returned=" + b.nReturned + "  docsExamined=" + b.totalDocsExamined + "  time=" + b.executionTimeMillis + "ms");
const c1 = d.borrow_logs.find({book_isbn:"9787115428028"}).hint({$natural:1}).explain("executionStats").executionStats;
const c2 = d.borrow_logs.find({book_isbn:"9787115428028"}).hint({book_isbn:1}).explain("executionStats").executionStats;
print("ISBN COLLSCAN : docsExamined=" + c1.totalDocsExamined + "  time=" + c1.executionTimeMillis + "ms");
print("ISBN IXSCAN   : docsExamined=" + c2.totalDocsExamined + "  time=" + c2.executionTimeMillis + "ms");
'
echo '[root@nosql01 ~]# '
"""

S5 = r"""clear
echo "== 5. GridFS : download and md5 verification =="
echo '[root@nosql01 ~]# md5sum /data/lib/tmp/data/gridfs_files/*  /data/lib/out/gridfs_dl/*'
md5sum /data/lib/tmp/data/gridfs_files/*.pdf /data/lib/tmp/data/gridfs_files/*.png 2>/dev/null | sed 's#/data/lib/tmp/data/gridfs_files/#SRC #'
echo '---'
md5sum /data/lib/out/gridfs_dl/* 2>/dev/null | sed 's#/data/lib/out/gridfs_dl/#DL  #'
echo '[root@nosql01 ~]# '
"""

FILES = [("t01_standalone", S1), ("t02_rs", S2), ("t03_shard", S3),
         ("t04_index", S4), ("t05_gridfs", S5)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log: list[str] = []

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)
    sftp = cli.open_sftp()

    for name, body in FILES:
        remote = f"/data/lib/tmp/{name}.sh"
        with sftp.open(remote, "w") as f:
            f.write(body)
        _, out, err = cli.exec_command(f"bash {remote} > /dev/tty1 2>&1", timeout=120)
        rc = out.channel.recv_exit_status()
        log.append(f"{name} rc={rc}")
        subprocess.run([VMRUN, "-T", "ws", "-gu", "root", "-gp", "111111",
                        "captureScreen", VMX, str(OUT / f"{name}.png")], capture_output=True)

    sftp.close()
    cli.close()
    (OUT / "tty_shot3.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
