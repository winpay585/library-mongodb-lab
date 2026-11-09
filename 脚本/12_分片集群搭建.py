"""阶段三（A）：分片集群骨架——配置服务器副本集、两组分片副本集、mongos。

布局：
  配置服务器 cfgrs：nosql01/02/03:27019
  分片一 shard1rs：nosql01:27020(priority 2) + nosql02:27020
  分片二 shard2rs：nosql03:27021(priority 2) + nosql02:27021
  mongos：nosql01:27022

用法：python scripts\\lab_stage_shard.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import paramiko

NODES = {"nosql01": "192.168.121.134", "nosql02": "192.168.121.135", "nosql03": "192.168.121.136"}
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
OUT = Path(__file__).resolve().parents[1] / "runtime" / "linux"

CFG_CONF = """systemLog:
  destination: file
  path: /data/lib/log/cfg{n}.log
  logAppend: true
storage:
  dbPath: /data/lib/cfg{n}
  wiredTiger:
    engineConfig:
      cacheSizeGB: 0.25
net:
  port: 27019
  bindIp: 0.0.0.0
security:
  keyFile: /data/lib/key/mongo.key
  authorization: enabled
replication:
  replSetName: cfgrs
sharding:
  clusterRole: configsvr
processManagement:
  fork: true
  timeZoneInfo: /usr/share/zoneinfo
"""

SHARD_CONF = """systemLog:
  destination: file
  path: /data/lib/log/shard{n}.log
  logAppend: true
storage:
  dbPath: /data/lib/shard{n}
  wiredTiger:
    engineConfig:
      cacheSizeGB: 0.25
net:
  port: {port}
  bindIp: 0.0.0.0
security:
  keyFile: /data/lib/key/mongo.key
  authorization: enabled
replication:
  replSetName: {rs}
sharding:
  clusterRole: shardsvr
processManagement:
  fork: true
  timeZoneInfo: /usr/share/zoneinfo
"""

MONGOS_CONF = """systemLog:
  destination: file
  path: /data/lib/log/mongos.log
  logAppend: true
net:
  port: 27022
  bindIp: 0.0.0.0
security:
  keyFile: /data/lib/key/mongo.key
sharding:
  configDB: cfgrs/nosql01:27019,nosql02:27019,nosql03:27019
processManagement:
  fork: true
  timeZoneInfo: /usr/share/zoneinfo
"""

CFG_INIT = ("rs.initiate({_id:'cfgrs',configsvr:true,members:["
            "{_id:0,host:'nosql01:27019'},{_id:1,host:'nosql02:27019'},"
            "{_id:2,host:'nosql03:27019'}]})")

SHARD1_INIT = ("rs.initiate({_id:'shard1rs',members:["
               "{_id:0,host:'nosql01:27020',priority:2},"
               "{_id:1,host:'nosql02:27020',priority:1}]})")

SHARD2_INIT = ("rs.initiate({_id:'shard2rs',members:["
               "{_id:0,host:'nosql03:27021',priority:2},"
               "{_id:1,host:'nosql02:27021',priority:1}]})")


def main() -> None:
    log: list[str] = []

    def conn(name: str) -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(NODES[name], port=22, username=USER, password=PASS, timeout=10,
                    allow_agent=False, look_for_keys=False)
        return cli

    def sh(host: str, cmd: str, timeout: int = 180) -> tuple[int, str]:
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

    # 1. 配置服务器（三台）
    for name in NODES:
        n = name[-1]
        put(name, f"/data/lib/conf/cfg{n}.conf", CFG_CONF.format(n=n))
        sh(name, f"rm -rf /data/lib/cfg{n}; mkdir -p /data/lib/cfg{n}; "
                f"mongod --config /data/lib/conf/cfg{n}.conf || tail -n 15 /data/lib/log/cfg{n}.log")
    time.sleep(4)
    for name in NODES:
        sh(name, "ss -lntp | grep 27019")

    sh("nosql01", f"mongosh --port 27019 --quiet --eval \"{CFG_INIT}\"")
    time.sleep(6)
    sh("nosql01", "mongosh --port 27019 --quiet --eval 'rs.status().members.forEach(m => print(m.name, m.stateStr, m.health))'")

    # 2. 两组分片副本集
    put("nosql01", "/data/lib/conf/shard1.conf", SHARD_CONF.format(n=1, port=27020, rs="shard1rs"))
    put("nosql02", "/data/lib/conf/shard1.conf", SHARD_CONF.format(n=1, port=27020, rs="shard1rs"))
    put("nosql02", "/data/lib/conf/shard2.conf", SHARD_CONF.format(n=2, port=27021, rs="shard2rs"))
    put("nosql03", "/data/lib/conf/shard2.conf", SHARD_CONF.format(n=2, port=27021, rs="shard2rs"))

    for name, port in (("nosql01", 27020), ("nosql02", 27020), ("nosql02", 27021), ("nosql03", 27021)):
        n = 1 if port == 27020 else 2
        sh(name, f"rm -rf /data/lib/shard{n}; mkdir -p /data/lib/shard{n}; "
                f"mongod --config /data/lib/conf/shard{n}.conf || tail -n 15 /data/lib/log/shard{n}.log")
    time.sleep(5)
    for name, port in (("nosql01", 27020), ("nosql02", 27020), ("nosql02", 27021), ("nosql03", 27021)):
        sh(name, f"ss -lntp | grep {port}")

    sh("nosql01", f"mongosh --port 27020 --quiet --eval \"{SHARD1_INIT}\"")
    sh("nosql03", f"mongosh --port 27021 --quiet --eval \"{SHARD2_INIT}\"")
    time.sleep(6)
    sh("nosql01", "mongosh --port 27020 --quiet --eval 'rs.status().members.forEach(m => print(m.name, m.stateStr))'")
    sh("nosql03", "mongosh --port 27021 --quiet --eval 'rs.status().members.forEach(m => print(m.name, m.stateStr))'")

    # 3. mongos
    put("nosql01", "/data/lib/conf/mongos.conf", MONGOS_CONF)
    sh("nosql01", "mongos --config /data/lib/conf/mongos.conf || tail -n 15 /data/lib/log/mongos.log")
    time.sleep(5)
    sh("nosql01", "ss -lntp | grep 27022")
    sh("nosql01", "mongosh --port 27022 --quiet --eval 'db.adminCommand({listShards:1})'")

    (OUT / "shard_bootstrap.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
