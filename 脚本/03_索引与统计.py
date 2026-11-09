"""阶段一（续）：索引、统计查询、GridFS、账号与权限——全部在 nosql01:27017 上。

用法：python scripts\\lab_stage_standalone2.py
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
GRID = ROOT / "交付" / "智慧图书馆数字资源平台_郭雨昊" / "01_数据文件" / "gridfs_files"
OUT = ROOT / "runtime" / "linux"
OUT.mkdir(parents=True, exist_ok=True)

INDEX_JS = r"""
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
print('--- 索引清单 ---');
['books', 'readers', 'borrow_logs'].forEach(c => {
  print('[' + c + '] 共 ' + d[c].getIndexes().length + ' 个索引');
  d[c].getIndexes().forEach(i => print('   ' + i.name + '  ' + JSON.stringify(i.key)));
});
"""

STATS_JS = r"""
const d = db.getSiblingDB('library');
print('== Q1 分类统计 ==');
d.books.aggregate([
  {$group: {_id: '$category', 图书数: {$sum: 1}, 均价: {$round: [{$avg: '$price'}, 2]}, 总借阅: {$sum: '$borrow_count'}}},
  {$sort: {图书数: -1}}
]).forEach(r => print(JSON.stringify(r)));

print('== Q2 学院读者数 Top5 ==');
d.readers.aggregate([
  {$group: {_id: '$college', 人数: {$sum: 1}}},
  {$sort: {人数: -1}}, {$limit: 5}
]).forEach(r => print(JSON.stringify(r)));

print('== Q3 月度借阅（36 个月） ==');
const m = d.borrow_logs.aggregate([
  {$group: {_id: {$substrCP: ['$borrow_date', 0, 7]}, 借阅量: {$sum: 1}}},
  {$sort: {_id: 1}}
]).toArray();
print('月份总数: ' + m.length);
print('首月 ' + m[0]._id + ' = ' + m[0].借阅量 + '，末月 ' + m[m.length-1]._id + ' = ' + m[m.length-1].借阅量);
print('全期合计: ' + m.reduce((s, x) => s + x.借阅量, 0));

print('== Q4 借阅 Top10 图书 ==');
d.borrow_logs.aggregate([
  {$group: {_id: '$book_isbn', 次数: {$sum: 1}}},
  {$sort: {次数: -1}}, {$limit: 10},
  {$lookup: {from: 'books', localField: '_id', foreignField: 'isbn', as: 'b'}},
  {$project: {_id: 0, isbn: '$_id', 书名: {$arrayElemAt: ['$b.title', 0]}, 分类: {$arrayElemAt: ['$b.category', 0]}, 次数: 1}}
]).forEach(r => print(JSON.stringify(r)));

print('== Q5 未归还借阅分布 ==');
d.borrow_logs.aggregate([
  {$group: {_id: '$status', 笔数: {$sum: 1}, 平均借期: {$round: [{$avg: '$duration_days'}, 1]}}},
  {$sort: {笔数: -1}}
]).forEach(r => print(JSON.stringify(r)));
"""

USERS_JS = r"""
const admin = db.getSiblingDB('admin');
admin.createUser({user: 'platform_admin', pwd: 'Admin2026pwd', roles: [{role: 'root', db: 'admin'}]});
const lib = db.getSiblingDB('library');
lib.createUser({user: 'lib_admin', pwd: 'lib2026pwd', roles: [{role: 'dbOwner', db: 'library'}]});
lib.createUser({user: 'lib_editor', pwd: 'lib2026pwd', roles: [{role: 'readWrite', db: 'library'}]});
lib.createUser({user: 'lib_reader', pwd: 'lib2026pwd', roles: [{role: 'read', db: 'library'}]});
print('账号清单:');
printjson(lib.getUsers().users.map(u => ({user: u.user, roles: u.roles.map(r => r.role)})));
"""

CONF_AUTH = """systemLog:
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
security:
  authorization: enabled
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
    cli = connect()
    sftp = cli.open_sftp()

    def put(remote: str, text: str) -> None:
        with sftp.open(remote, "w") as f:
            f.write(text)

    def sh(cmd: str, timeout: int = 180) -> int:
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        text = (out.read() + err.read()).decode("utf-8", "replace").strip()
        log.append(f"$ {cmd}")
        log.append(text)
        log.append(f"[exit {rc}]")
        log.append("")
        return rc

    # 1. 索引
    put("/data/lib/tmp/index2.js", INDEX_JS)
    sh("mongosh --port 27017 --quiet /data/lib/tmp/index2.js")

    # 2. 统计查询
    put("/data/lib/tmp/stats.js", STATS_JS)
    sh("mongosh --port 27017 --quiet /data/lib/tmp/stats.js")

    # 3. GridFS：上传 6 个文件并核对 MD5
    sh("mkdir -p /data/lib/tmp/data/gridfs_files")
    for f in sorted(GRID.iterdir()):
        if f.is_file():
            sftp.put(str(f), f"/data/lib/tmp/data/gridfs_files/{f.name}")
            log.append(f"sftp put {f.name}")
    log.append("")
    sh("cd /data/lib/tmp/data/gridfs_files && md5sum *.pdf *.png | sort -k2")
    sh("for f in ebook_1.pdf ebook_2.pdf ebook_3.pdf cover_1.png cover_2.png cover_3.png; do "
       "mongofiles --port 27017 -d library put /data/lib/tmp/data/gridfs_files/$f; done")
    sh("mongosh --port 27017 --quiet --eval '"
       "db.getSiblingDB(\"library\").fs.files.find({}, {filename:1, length:1, md5:1, _id:0}).forEach(f => print(f.filename, f.length, f.md5))'")
    sh("mkdir -p /data/lib/out/gridfs_dl && for f in ebook_1.pdf ebook_2.pdf ebook_3.pdf cover_1.png cover_2.png cover_3.png; do "
       "mongofiles --port 27017 -d library get $f --local /data/lib/out/gridfs_dl/$f >/dev/null; done; "
       "cd /data/lib/out/gridfs_dl && md5sum * | sort -k2")
    sh("cd /data/lib/tmp/data/gridfs_files && md5sum * | awk '{print $1}' | sort > /tmp/src.txt; "
       "cd /data/lib/out/gridfs_dl && md5sum * | awk '{print $1}' | sort > /tmp/dst.txt; "
       "diff /tmp/src.txt /tmp/dst.txt && echo 'MD5 全部一致（6/6）'")

    # 4. 导出统计结果 JSON
    sh("mongosh --port 27017 --quiet --eval '"
       "const d=db.getSiblingDB(\"library\");"
       "const r=d.books.aggregate([{$group:{_id:\"$category\",n:{$sum:1},avg:{$round:[{$avg:\"$price\"},2]}}},{$sort:{n:-1}}]).toArray();"
       "print(JSON.stringify(r))' > /data/lib/out/library.category_stats.json && wc -c /data/lib/out/library.category_stats.json")

    # 5. 建账号 + 开认证
    put("/data/lib/tmp/users.js", USERS_JS)
    sh("mongosh --port 27017 --quiet /data/lib/tmp/users.js")
    conf_local = OUT / "standalone_auth.conf"
    conf_local.write_text(CONF_AUTH, encoding="utf-8")
    sftp.put(str(conf_local), "/data/lib/conf/standalone-auth.conf")
    sh("mongod --config /data/lib/conf/standalone.conf --shutdown")
    time.sleep(2)
    sh("mongod --config /data/lib/conf/standalone-auth.conf")
    time.sleep(5)
    sh("ss -lntp | grep 27017")

    # 6. 权限验证
    sh("mongosh --port 27017 -u lib_reader -p lib2026pwd --authenticationDatabase library --quiet --eval '"
       "try { db.getSiblingDB(\"library\").books.insertOne({isbn:\"x\"}); print(\"插入成功(不应该)\") } "
       "catch(e) { print(\"lib_reader 写入被拒绝: \" + e.codeName) }; "
       "print(\"lib_reader 可读条数: \" + db.getSiblingDB(\"library\").books.countDocuments())'")
    sh("mongosh --port 27017 -u lib_editor -p lib2026pwd --authenticationDatabase library --quiet --eval '"
       "const c=db.getSiblingDB(\"library\").tmp_probe;"
       "c.insertOne({probe:1}); print(\"lib_editor 插入成功, 条数=\" + c.countDocuments());"
       "try { c.drop(); print(\"删除成功(不应该)\") } catch(e) { print(\"lib_editor 删除被拒绝: \" + e.codeName) }'")
    sh("mongosh --port 27017 -u lib_admin -p lib2026pwd --authenticationDatabase library --quiet --eval '"
       "const d=db.getSiblingDB(\"library\"); d.tmp_probe.drop();"
       "print(\"lib_admin 集合删除成功, 剩余集合: \" + d.getCollectionNames().join(\",\"))'")
    sh("mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet --eval '"
       "print(\"platform_admin 角色: \" + JSON.stringify(db.getSiblingDB(\"admin\").runCommand({connectionStatus:1}).authInfo.authenticatedUserRoles))'")

    # 7. 认证后复核数据量
    sh("mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet --eval '"
       "const d=db.getSiblingDB(\"library\"); "
       "[\"books\",\"readers\",\"borrow_logs\"].forEach(c => print(c, d[c].countDocuments())); "
       "print(\"fs.files\", d.fs.files.countDocuments())'")

    sftp.close()
    cli.close()
    (OUT / "standalone2.log").write_text("\n".join(log), encoding="utf-8")
    print("log lines:", len(log))


if __name__ == "__main__":
    main()
