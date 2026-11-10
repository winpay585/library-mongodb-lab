#!/bin/bash
# 三个业务账号的权限验证：只读账号写不进去、编辑账号能改文档但不能删集合、库管理员能删集合。
# 脚本只对 tmp 探针集合操作，跑完自己清理，不影响 books / readers / borrow_logs。
#
# 在哪跑：nosql01，认证已打开的 27017
# 用法：bash 05_权限验证.sh

PORT=${1:-27017}

echo "== lib_reader：应该只能读 =="
mongosh --port "$PORT" -u lib_reader -p lib2026pwd --authenticationDatabase library --quiet --eval '
const c = db.getSiblingDB("library").books;
try { c.insertOne({isbn: "perm-test-reader"}); print("插入成功（不应该）"); }
catch (e) { print("写入被拒绝：" + e.codeName); }
print("可读条数 books=" + c.countDocuments());'

echo "== lib_editor：能增改删文档，不能删集合 =="
mongosh --port "$PORT" -u lib_editor -p lib2026pwd --authenticationDatabase library --quiet --eval '
const d = db.getSiblingDB("library");
d.perm_probe.insertOne({probe: 1, name: "editor"});
d.perm_probe.updateOne({probe: 1}, {$set: {ok: true}});
print("插入并更新成功，条数=" + d.perm_probe.countDocuments());
d.perm_probe.deleteMany({});
print("删除文档成功，条数=" + d.perm_probe.countDocuments());
try { d.perm_probe.drop(); print("drop 成功（不应该）"); }
catch (e) { print("删集合被拒绝：" + e.codeName); }'

echo "== lib_admin：能删集合 =="
mongosh --port "$PORT" -u lib_admin -p lib2026pwd --authenticationDatabase library --quiet --eval '
const d = db.getSiblingDB("library");
d.perm_probe.drop();
print("删集合成功，现有集合：" + d.getCollectionNames().sort().join(","));'

echo "== platform_admin：认证状态 =="
mongosh --port "$PORT" -u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet --eval '
const d = db.getSiblingDB("library");
print("角色：" + JSON.stringify(db.runCommand({connectionStatus: 1}).authInfo.authenticatedUserRoles));
["books", "readers", "borrow_logs"].forEach(c => print(c + " " + d[c].countDocuments()));
print("fs.files " + d.fs.files.countDocuments());'
