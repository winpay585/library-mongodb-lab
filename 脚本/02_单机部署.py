"""阶段一：nosql01 上的单机环境（27017）——建库、导入、索引、统计、GridFS、权限。

全部操作通过 SSH 在 CentOS 上执行（等价于 Xshell 里手工敲），命令与输出落盘到
runtime/linux/standalone.log，供报告与截图取材。

用法：python scripts\\lab_stage_standalone.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

HOST = "192.168.121.134"
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "交付" / "智慧图书馆数字资源平台_郭雨昊" / "01_数据文件"
OUT = ROOT / "runtime" / "linux"
OUT.mkdir(parents=True, exist_ok=True)

CONF = """systemLog:
  destination: file
  path: /data/lib/log/standalone.log
  logAppend: true
storage:
  dbPath: /data/lib/standalone
  wiredTiger:
    engineConfig:
      cacheSizeGB: 0.8
net:
  port: 27017
  bindIp: 0.0.0.0
processManagement:
  fork: true
  timeZoneInfo: /usr/share/zoneinfo
"""


def connect() -> paramiko.SSHClient:
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)
    return cli


def main() -> None:
    log: list[str] = []

    def rec(title: str, code: int, text: str) -> None:
        log.append(f"$ {title}")
        log.append(text)
        log.append(f"[exit {code}]")
        log.append("")

    cli = connect()
    # SELinux 放行（本项目 dbPath 在 /data/lib，非标准目录）
    _, out, err = cli.exec_command("setenforce 0; getenforce; sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config; grep '^SELINUX=' /etc/selinux/config")
    rc = out.channel.recv_exit_status()
    rec("setenforce 0", rc, (out.read() + err.read()).decode("utf-8", "replace").strip())

    # 上传数据文件
    sftp = cli.open_sftp()
    cli.exec_command("mkdir -p /data/lib/tmp/data")[1].channel.recv_exit_status()
    for f in sorted(DATA.iterdir()):
        if f.is_file():
            sftp.put(str(f), f"/data/lib/tmp/data/{f.name}")
            log.append(f"sftp put {f.name} -> /data/lib/tmp/data/{f.name}")
    sftp.close()
    log.append("")

    # 写入配置
    conf_local = OUT / "standalone.conf"
    conf_local.write_text(CONF, encoding="utf-8")
    sftp = cli.open_sftp()
    sftp.put(str(conf_local), "/data/lib/conf/standalone.conf")
    sftp.close()

    def sh(cmd: str, timeout: int = 120) -> None:
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        rec(cmd, rc, (out.read() + err.read()).decode("utf-8", "replace").strip())

    sh("ls -l /data/lib/conf/standalone.conf /data/lib/tmp/data")
    sh("rm -rf /data/lib/standalone/*; mongod --config /data/lib/conf/standalone.conf")
    time.sleep(4)
    sh("ss -lntp | grep 27017")
    sh("mongosh --port 27017 --quiet --eval 'db.runCommand({ping:1})'")

    # 导入三张集合
    for name in ("books", "readers", "borrow_logs"):
        sh(f"mongoimport --port 27017 --db library --collection {name} "
           f"--file /data/lib/tmp/data/{name}.txt --jsonArray --drop")
    sh("mongosh --port 27017 --quiet --eval 'db.getSiblingDB(\"library\").getCollectionNames().forEach("
       "c => print(c, db.getSiblingDB(\"library\")[c].countDocuments()))'")

    # 建索引（16 个）
    idx_js = """
const d = db.getSiblingDB('library');
d.books.createIndex({isbn:1},{unique:true,name:'uk_isbn'});
d.books.createIndex({category:1,name:'idx_category'});
d.books.createIndex({title:'text'},{name:'idx_title_text'});
d.books.createIndex({category:1,isbn:1},{name:'idx_cat_isbn'});
d.readers.createIndex({card_no:1},{unique:true,name:'uk_card_no'});
d.readers.createIndex({college:1,name:'idx_college'});
d.readers.createIndex({college:1,card_no:1},{name:'idx_college_card'});
d.borrow_logs.createIndex({reader_card:'hashed'},{name:'idx_card_hashed'});
d.borrow_logs.createIndex({book_isbn:1,name:'idx_book_isbn'});
d.borrow_logs.createIndex({borrow_date:-1},{name:'idx_date_desc'});
d.borrow_logs.createIndex({isbn:1,borrow_date:-1},{name:'idx_isbn_date'});
d.borrow_logs.createIndex({returned:1,name:'idx_returned'});
print('索引统计:');
d.getCollectionNames().forEach(c=>{ const n=d[c].getIndexes().length; print(' ',c,n,'个') });
"""
    sftp = cli.open_sftp()
    with sftp.open("/data/lib/tmp/index.js", "w") as f:
        f.write(idx_js)
    sftp.close()
    sh("mongosh --port 27017 --quiet /data/lib/tmp/index.js")

    # Compass 导出（JSON 数组）
    for name in ("books", "readers", "borrow_logs"):
        sh(f"mongoexport --port 27017 --db library --collection {name} --jsonArray "
           f"--out /data/lib/out/library.{name}.json && wc -c /data/lib/out/library.{name}.json")

    (OUT / "standalone.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log[-25:]))
    cli.close()


if __name__ == "__main__":
    main()
