"""副本集：补建索引 + 故障转移演练（踢主、测选举耗时、恢复、校验追平）。

用法：python scripts\\lab_replica_drill.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "linux"
PORT = 27018
MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

INDEX_JS = """
const d = db.getSiblingDB('library');
d.books.createIndex({isbn: 1}, {unique: true, name: 'uk_isbn'});
d.books.createIndex({category: 1}, {name: 'idx_category'});
d.books.createIndex({title: 'text'}, {name: 'idx_title_text'});
d.books.createIndex({category: 1, isbn: 1}, {name: 'idx_cat_isbn'});
d.readers.createIndex({card_no: 1}, {unique: true, name: 'uk_card_no'});
d.readers.createIndex({college: 1}, {name: 'idx_college'});
d.readers.createIndex({college: 1, card_no: 1}, {name: 'idx_college_card'});
d.borrow_logs.createIndex({reader_card: 'hashed'}, {name: 'idx_card_hashed'});
d.borrow_logs.createIndex({book_isbn: 1}, {name: 'idx_book_isbn'});
d.borrow_logs.createIndex({borrow_date: -1}, {name: 'idx_date_desc'});
d.borrow_logs.createIndex({book_isbn: 1, borrow_date: -1}, {name: 'idx_isbn_date'});
d.borrow_logs.createIndex({status: 1}, {name: 'idx_status'});
print('索引已建立');
"""


def main() -> None:
    log: list[str] = []

    def conn(name: str) -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[name], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        return cli

    def sh(host: str, cmd: str, timeout: int = 120) -> tuple[int, str]:
        cli = conn(host)
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"[{host}] $ {cmd}")
        log.append(text)
        log.append(f"[exit {rc}]")
        log.append("")
        return rc, text

    def put(host: str, remote: str, text: str) -> None:
        cli = conn(host)
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    # 1. 建索引（主节点执行，自动复制到从节点）
    put("nosql01", "/data/lib/tmp/rs_index.js", INDEX_JS)
    sh("nosql01", f"mongosh --port {PORT} {MON} /data/lib/tmp/rs_index.js")
    for node in NODES:
        sh(node, f"mongosh --port {PORT} {MON} --eval "
                 "'const d=db.getSiblingDB(\"library\");print(\"books=\"+d.books.getIndexes().length, "
                 "\"readers=\"+d.readers.getIndexes().length, \"borrow_logs=\"+d.borrow_logs.getIndexes().length)'")

    # 2. 定位当前主节点
    primary = None
    for node in NODES:
        _, text = sh(node, f"mongosh --port {PORT} {MON} --eval 'print(db.hello().isWritablePrimary)'")
        if text.strip() == "true":
            primary = node
            break
    log.append(f">>> 故障转移前主节点：{primary}")

    # 3. 杀掉主节点进程（模拟宕机）
    _, text = sh(primary, "ss -lntp | grep 27018 | grep -o 'pid=[0-9]*' | cut -d= -f2")
    pid = text.strip().splitlines()[0] if text.strip() else ""
    log.append(f">>> 主节点 mongod pid = {pid}")
    t_kill = time.time()
    sh(primary, f"kill -9 {pid}")

    # 4. 轮询新主（每 0.2 s 检查一次）
    new_primary, elapsed = None, None
    deadline = time.time() + 40
    while time.time() < deadline:
        for node in NODES:
            if node == primary:
                continue
            cli = conn(node)
            _, out, err = cli.exec_command(
                f"mongosh --port {PORT} {MON} --eval 'print(db.hello().isWritablePrimary)'", timeout=15)
            val = out.read().decode().strip()
            cli.close()
            if val == "true":
                new_primary = node
                elapsed = time.time() - t_kill
                break
        if new_primary:
            break
        time.sleep(0.2)
    log.append(f">>> 新主节点：{new_primary}，从杀进程到选出新主耗时 {elapsed:.2f} 秒" if new_primary
               else ">>> 40 秒内未选出新主")

    # 5. 新主可写 + 集群状态
    if new_primary:
        sh(new_primary, f"mongosh --port {PORT} {MON} --eval "
                        "'db.getSiblingDB(\"library\").books.insertOne({isbn:\"failover-probe\","
                        "title:\"故障转移写入探针\",category:\"测试\",price:0,stock:1});"
                        "print(\"新主写入成功，books=\" + db.getSiblingDB(\"library\").books.countDocuments())'")
        sh(new_primary, f"mongosh --port {PORT} {MON} --eval "
                        "'rs.status().members.forEach(m => print(m.name, m.stateStr, m.health))'")

    # 6. 原主恢复
    n = primary[-1]
    t_restart = time.time()
    sh(primary, f"mongod --config /data/lib/conf/rs{n}.conf")
    time.sleep(10)
    sh(primary, f"mongosh --port {PORT} {MON} --eval "
                "'print(\"原主节点当前角色：\" + (db.hello().isWritablePrimary ? \"PRIMARY\" : \"SECONDARY\"));"
                "print(\"books=\" + db.getSiblingDB(\"library\").books.countDocuments())'")
    sh("nosql01", f"mongosh --port {PORT} {MON} --eval "
                  "'rs.status().members.forEach(m => print(m.name, m.stateStr, m.health))'")
    sh("nosql01", f"mongosh --port {PORT} {MON} --eval 'rs.printSecondaryReplicationInfo()'")

    # 7. 探针清理
    sh(new_primary, f"mongosh --port {PORT} {MON} --eval "
                    "'db.getSiblingDB(\"library\").books.deleteMany({isbn:\"failover-probe\"});"
                    "print(\"探针已清理，books=\" + db.getSiblingDB(\"library\").books.countDocuments())'")

    log.append(f">>> 恢复耗时记录：{time.time() - t_restart:.0f} 秒（含 10 秒等待）")
    (OUT / "replica_drill.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
