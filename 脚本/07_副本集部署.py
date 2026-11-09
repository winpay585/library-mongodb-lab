"""阶段二：三台机器组副本集 rs_lib（27018），含故障转移演练与计时。

用法：python scripts\\lab_stage_replica.py [drill]
不带参数：建副本集 + 建账号 + 导入数据 + 校验
带 drill：踢掉主节点，测选举耗时，恢复后校验同步
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "linux"
OUT.mkdir(parents=True, exist_ok=True)
PORT = 27018

CONF = """systemLog:
  destination: file
  path: /data/lib/log/rs{n}.log
  logAppend: true
storage:
  dbPath: /data/lib/rs{n}
  wiredTiger:
    engineConfig:
      cacheSizeGB: 0.8
net:
  port: {port}
  bindIp: 0.0.0.0
security:
  keyFile: /data/lib/key/mongo.key
  authorization: enabled
replication:
  replSetName: rs_lib
processManagement:
  fork: true
  timeZoneInfo: /usr/share/zoneinfo
"""


def conn(host: str) -> paramiko.SSHClient:
    host = NODES.get(host, host)
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(host, port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)
    return cli


def main() -> None:
    drill = len(sys.argv) > 1 and sys.argv[1] == "drill"
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

    def sh_text(host: str, cmd: str, timeout: int = 180) -> str:
        cli = conn(host)
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        code = out.channel.recv_exit_status()
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        cli.close()
        log.append(f"[{host}] $ {cmd}")
        log.append(text)
        log.append(f"[exit {code}]")
        log.append("")
        return text

    def put(host: str, remote: str, text: str) -> None:
        cli = conn(host)
        sftp = cli.open_sftp()
        with sftp.open(remote, "w") as f:
            f.write(text)
        sftp.close()
        cli.close()

    MON = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

    if not drill:
        # 1. 配置并启动三个副本集节点（先停旧进程再清目录，避免删除运行中实例的 dbPath）
        for name, ip in NODES.items():
            n = name[-1]
            put(ip, f"/data/lib/conf/rs{n}.conf", CONF.format(n=n, port=PORT))
            sh(ip, f"rm -rf /data/lib/rs{n}; mkdir -p /data/lib/rs{n}; "
                   f"mongod --config /data/lib/conf/rs{n}.conf || tail -n 20 /data/lib/log/rs{n}.log")
        time.sleep(5)
        for name, ip in NODES.items():
            sh(ip, f"ss -lntp | grep {PORT}")

        # 2. 初始化副本集（第一个节点上执行）
        init_js = (
            "rs.initiate({_id:'rs_lib',members:["
            "{_id:0,host:'nosql01:27018',priority:2},"
            "{_id:1,host:'nosql02:27018',priority:1},"
            "{_id:2,host:'nosql03:27018',priority:1}]})"
        )
        sh("nosql01", f"mongosh --port {PORT} --quiet --eval \"{init_js}\"")
        time.sleep(6)

        # 3. 主节点身份与状态
        sh("nosql01", f"mongosh --port {PORT} --quiet --eval 'rs.status().members.forEach(m => "
                      "print(m.name, m.stateStr, m.health))'")
        sh("nosql01", f"mongosh --port {PORT} --quiet --eval 'print(\"PRIMARY=\" + db.hello().primary, "
                      "\" isWritablePrimary=\" + db.hello().isWritablePrimary)'")

        # 4. 建账号（无用户时本地连接可免认证，正好建立第一个用户）
        users_js = """
const admin = db.getSiblingDB('admin');
admin.createUser({user:'platform_admin', pwd:'Admin2026pwd', roles:[{role:'root', db:'admin'}]});
const lib = db.getSiblingDB('library');
lib.createUser({user:'lib_admin', pwd:'lib2026pwd', roles:[{role:'dbOwner', db:'library'}]});
lib.createUser({user:'lib_editor', pwd:'lib2026pwd', roles:[{role:'readWrite', db:'library'}]});
lib.createUser({user:'lib_reader', pwd:'lib2026pwd', roles:[{role:'read', db:'library'}]});
print('副本集账号已创建');
"""
        put("nosql01", "/data/lib/tmp/rs_users.js", users_js)
        sh("nosql01", f"mongosh --port {PORT} --quiet /data/lib/tmp/rs_users.js")

        # 5. 导入数据（主节点）
        for name in ("books", "readers", "borrow_logs"):
            sh("nosql01", f"mongoimport --port {PORT} -u lib_admin -p lib2026pwd --authenticationDatabase library "
                          f"--db library --collection {name} --file /data/lib/tmp/data/{name}.txt --jsonArray --drop")

        # 6. 主/从数据一致性
        sh("nosql01", f"mongosh --port {PORT} {MON} --eval 'const d=db.getSiblingDB(\"library\");"
                      "[\"books\",\"readers\",\"borrow_logs\"].forEach(c=>print(c,d[c].countDocuments()))'")
        sh("nosql02", f"mongosh --port {PORT} {MON} --eval 'db.getMongo().setReadPref(\"secondary\");"
                      "const d=db.getSiblingDB(\"library\");"
                      "[\"books\",\"readers\",\"borrow_logs\"].forEach(c=>print(c,d[c].countDocuments()))'")
        sh("nosql03", f"mongosh --port {PORT} {MON} --eval 'db.getMongo().setReadPref(\"secondary\");"
                      "const d=db.getSiblingDB(\"library\");"
                      "const s=d.books.countDocuments({}, {hint:{\"$natural\":1}});"
                      "print(\"nosql03 读到 books=\" + s)'")
        sh("nosql01", f"mongosh --port {PORT} {MON} --eval 'printjson(rs.printReplicationInfo()); "
                      "printjson(rs.printSecondaryReplicationInfo())'")

    else:
        # 故障转移演练：找到当前主节点，踢掉它
        r = sh("nosql01", f"mongosh --port {PORT} {MON} --eval 'print(db.hello().primary)'")
        # 从主节点探测结果中解析出主机名
        primary = "nosql01"
        for line in reversed(log[-4:]):
            if line.startswith("nosql0") and ":" in line:
                primary = line.split(":")[0].strip()
                break
        log.append(f"当前主节点: {primary}")
        start = time.time()
        sh(primary, f"ps -o pid,cmd -C mongod | grep {PORT} | awk '{{print $1}}' | xargs -r kill -9")
        killed = time.time()
        # 轮询新主节点
        new_primary, elapsed = None, None
        for _ in range(120):
            cli = conn("nosql01")
            _, out, _ = cli.exec_command(f"mongosh --port {PORT} --quiet --eval 'db.hello().isWritablePrimary'", timeout=20)
            val = out.read().decode().strip()
            rc = out.channel.recv_exit_status()
            cli.close()
            if rc == 0 and val == "true":
                new_primary = "nosql01"
                elapsed = time.time() - killed
                break
            for other in ("nosql02", "nosql03"):
                cli = conn(other)
                _, out, _ = cli.exec_command(f"mongosh --port {PORT} --quiet --eval 'db.hello().isWritablePrimary'", timeout=20)
                v2 = out.read().decode().strip()
                rc2 = out.channel.recv_exit_status()
                cli.close()
                if rc2 == 0 and v2 == "true":
                    new_primary = other
                    elapsed = time.time() - killed
                    break
            if new_primary:
                break
            time.sleep(0.2)
        log.append(f"新主节点: {new_primary}  选举耗时: {elapsed:.2f} s" if elapsed else "未选出新主")

        # 新主可写测试
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        sh(new_primary, f"mongosh --port {PORT} {MON} --eval 'db.getSiblingDB(\"library\").books.insertOne("
                        "{{isbn:\"failover-probe-{ts}\",title:\"故障转移写入探针\",category:\"测试\",price:0,stock:1}});"
                        "print(\"新主写入成功, books=\" + db.getSiblingDB(\"library\").books.countDocuments())'")
        sh(new_primary, f"mongosh --port {PORT} {MON} --eval 'rs.status().members.forEach(m => "
                        "print(m.name, m.stateStr))'")

        # 恢复旧主
        n = primary[-1]
        sh(primary, f"mongod --config /data/lib/conf/rs{n}.conf")
        time.sleep(8)
        sh("nosql01", f"mongosh --port {PORT} {MON} --eval 'rs.status().members.forEach(m => "
                      "print(m.name, m.stateStr, m.health))'")
        sh("nosql01", f"mongosh --port {PORT} {MON} --eval 'rs.printSecondaryReplicationInfo()'")
        # 清理探针数据
        sh(new_primary, f"mongosh --port {PORT} {MON} --eval 'db.getSiblingDB(\"library\").books.deleteMany("
                        "{{isbn:/failover-probe/}}); print(\"探针已清理, books=\" + "
                        "db.getSiblingDB(\"library\").books.countDocuments())'")

    (OUT / ("replica_drill.log" if drill else "replica.log")).write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log[-30:]))


if __name__ == "__main__":
    main()
