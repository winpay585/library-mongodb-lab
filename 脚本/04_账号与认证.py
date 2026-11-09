"""阶段一（修正）：统计聚合、GridFS 文件名、编辑器角色与权限验证。

用法：python scripts\\lab_fix_standalone.py
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
OUT = ROOT / "runtime" / "linux"
OUT.mkdir(parents=True, exist_ok=True)

STATS_JS = r"""
const d = db.getSiblingDB('library') || connect('mongodb://127.0.0.1:27017/library');
"""

STATS = r"""
const lib = db.getSiblingDB('library');
print('== Q1 分类统计（图书数 / 均价 / 总借阅） ==');
lib.books.aggregate([
  {$group: {_id: '$category', n: {$sum: 1}, avgPrice: {$avg: '$price'}, totalBorrow: {$sum: '$borrow_count'}}},
  {$project: {_id: 0, 分类: '$_id', 图书数: '$n', 均价: {$round: ['$avgPrice', 2]}, 总借阅: '$totalBorrow'}},
  {$sort: {图书数: -1}}
]).forEach(r => print(JSON.stringify(r)));

print('== Q2 学院读者数 Top5 ==');
lib.readers.aggregate([
  {$group: {_id: '$college', 人数: {$sum: 1}}},
  {$sort: {人数: -1}}, {$limit: 5}
]).forEach(r => print(JSON.stringify(r)));

print('== Q3 月度借阅（按月聚合） ==');
const m = lib.borrow_logs.aggregate([
  {$group: {_id: {$substrCP: ['$borrow_date', 0, 7]}, 借阅量: {$sum: 1}}},
  {$sort: {_id: 1}}
]).toArray();
print('月份总数: ' + m.length);
print('首月 ' + m[0]._id + ' = ' + m[0].借阅量 + '；末月 ' + m[m.length - 1]._id + ' = ' + m[m.length - 1].借阅量);
print('全期合计: ' + m.reduce((s, x) => s + x.借阅量, 0));

print('== Q4 借阅 Top10 图书 ==');
lib.borrow_logs.aggregate([
  {$group: {_id: '$book_isbn', 次数: {$sum: 1}}},
  {$sort: {次数: -1}}, {$limit: 10},
  {$lookup: {from: 'books', localField: '_id', foreignField: 'isbn', as: 'b'}},
  {$project: {_id: 0, isbn: '$_id', 书名: {$arrayElemAt: ['$b.title', 0]}, 分类: {$arrayElemAt: ['$b.category', 0]}, 次数: 1}}
]).forEach(r => print(JSON.stringify(r)));

print('== Q5 借阅状态分布 ==');
lib.borrow_logs.aggregate([
  {$group: {_id: '$status', 笔数: {$sum: 1}, 平均借期: {$avg: '$duration_days'}}},
  {$project: {_id: 0, 状态: '$_id', 笔数: '$笔数', 平均借期: {$round: ['$平均借期', 1]}}},
  {$sort: {笔数: -1}}
]).forEach(r => print(JSON.stringify(r)));
"""

CATEGORY_JSON = r"""
const lib = db.getSiblingDB('library');
const r = lib.books.aggregate([
  {$group: {_id: '$category', n: {$sum: 1}, avgPrice: {$avg: '$price'}, totalBorrow: {$sum: '$borrow_count'}}},
  {$project: {category: '$_id', count: '$n', avg_price: {$round: ['$avgPrice', 2]}, total_borrow: '$totalBorrow'}},
  {$sort: {count: -1}}
]).toArray();
print(JSON.stringify(r, null, 2));
"""

ROLE_JS = r"""
const lib = db.getSiblingDB('library');
try { lib.dropRole('library_editor'); } catch (e) {}
lib.createRole({
  role: 'library_editor',
  privileges: [
    {resource: {db: 'library', collection: ''}, actions: ['find', 'insert', 'update', 'remove']}
  ],
  roles: []
});
lib.updateUser('lib_editor', {roles: [{role: 'library_editor', db: 'library'}]});
print('自定义角色 library_editor 已建立，仅 find/insert/update/remove，不含 dropCollection');
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

    def sh(cmd: str, timeout: int = 180) -> int:
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        log.append(f"$ {cmd}")
        log.append((out.read() + err.read()).decode("utf-8", "replace").strip())
        log.append(f"[exit {rc}]")
        log.append("")
        return rc

    def put(remote: str, text: str) -> None:
        with sftp.open(remote, "w") as f:
            f.write(text)

    AUTH = "-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

    # 1. 修正统计
    put("/data/lib/tmp/stats2.js", STATS)
    sh(f"mongosh --port 27017 {AUTH} /data/lib/tmp/stats2.js")

    # 2. 分类统计 JSON
    put("/data/lib/tmp/category.js", CATEGORY_JSON)
    sh(f"mongosh --port 27017 {AUTH} /data/lib/tmp/category.js > /data/lib/out/library.category_stats.json; "
       "wc -c /data/lib/out/library.category_stats.json; head -6 /data/lib/out/library.category_stats.json")

    # 3. GridFS 重新入库：切到文件目录，用相对文件名
    sh(f"mongosh --port 27017 {AUTH} --eval 'db.getSiblingDB(\"library\").fs.files.drop(); "
       "db.getSiblingDB(\"library\").fs.chunks.drop(); print(\"fs 集合已清空\")'")
    sh("cd /data/lib/tmp/data/gridfs_files && for f in ebook_1.pdf ebook_2.pdf ebook_3.pdf "
       "cover_1.png cover_2.png cover_3.png; do mongofiles --port 27017 -d library put $f; done")
    sh(f"mongosh --port 27017 {AUTH} --eval 'db.getSiblingDB(\"library\").fs.files.find({{}}, "
       "{{filename:1, length:1, chunkSize:1, _id:0}}).forEach(f => print(f.filename, f.length, f.chunkSize))'")
    sh("rm -rf /data/lib/out/gridfs_dl; mkdir -p /data/lib/out/gridfs_dl; cd /data/lib/out/gridfs_dl && "
       "for f in ebook_1.pdf ebook_2.pdf ebook_3.pdf cover_1.png cover_2.png cover_3.png; do "
       "mongofiles --port 27017 -d library get $f >/dev/null; done; md5sum * | sort -k2")
    sh("cd /data/lib/tmp/data/gridfs_files && md5sum *.pdf *.png | awk '{print $1}' | sort > /tmp/src.txt; "
       "cd /data/lib/out/gridfs_dl && md5sum * | awk '{print $1}' | sort > /tmp/dst.txt; "
       "diff /tmp/src.txt /tmp/dst.txt && echo 'GridFS 6 个文件 MD5 与源文件逐一一致'")

    # 4. 自定义编辑器角色
    put("/data/lib/tmp/role.js", ROLE_JS)
    sh(f"mongosh --port 27017 {AUTH} /data/lib/tmp/role.js")

    # 5. 权限验证（三类账号）
    sh("mongosh --port 27017 -u lib_reader -p lib2026pwd --authenticationDatabase library --quiet --eval '"
       "const c=db.getSiblingDB(\"library\").books;"
       "try{c.insertOne({isbn:\"x\"});print(\"lib_reader 插入成功(不应该)\")}catch(e){print(\"lib_reader 写入被拒绝: \"+e.codeName)};"
       "print(\"lib_reader 可读: books=\"+c.countDocuments())'")
    sh("mongosh --port 27017 -u lib_editor -p lib2026pwd --authenticationDatabase library --quiet --eval '"
       "const d=db.getSiblingDB(\"library\");"
       "d.perm_probe.insertOne({probe:1,name:\"editor\"});"
       "d.perm_probe.updateOne({probe:1},{$set:{ok:true}});"
       "print(\"lib_editor 增改成功, 条数=\"+d.perm_probe.countDocuments());"
       "d.perm_probe.deleteMany({}); print(\"lib_editor 删除文档成功, 条数=\"+d.perm_probe.countDocuments());"
       "try{d.perm_probe.drop();print(\"drop 成功(不应该)\")}catch(e){print(\"lib_editor 删集合被拒绝: \"+e.codeName)}'")
    sh("mongosh --port 27017 -u lib_admin -p lib2026pwd --authenticationDatabase library --quiet --eval '"
       "const d=db.getSiblingDB(\"library\"); d.perm_probe.drop();"
       "print(\"lib_admin 删集合成功, 现有集合: \"+d.getCollectionNames().sort().join(\",\"))'")
    sh(f"mongosh --port 27017 {AUTH} --eval 'const d=db.getSiblingDB(\"library\");"
       "[\"books\",\"readers\",\"borrow_logs\"].forEach(c=>print(c,d[c].countDocuments()));"
       "print(\"fs.files\", d.fs.files.countDocuments(), \"| fs.chunks\", d.fs.chunks.countDocuments())'")

    sftp.close()
    cli.close()
    (OUT / "standalone3_fix.log").write_text("\n".join(log), encoding="utf-8")
    print("lines:", len(log))


if __name__ == "__main__":
    main()
