#!/bin/bash
# 集群验收：把单机、副本集、分片三套环境的关键指标一次性打出来。
#
# 在哪跑：nosql01（能连到 27017 / 27018 / 27022 就行）
# 用法：bash 12_集群验收.sh

AUTH="-u platform_admin -p Admin2026pwd --authenticationDatabase admin --quiet"

echo "===== 一、单机 27017 ====="
mongosh --port 27017 $AUTH --eval '
const d = db.getSiblingDB("library");
print("books=" + d.books.countDocuments() + "  readers=" + d.readers.countDocuments()
      + "  borrow_logs=" + d.borrow_logs.countDocuments());
print("fs.files=" + d.fs.files.countDocuments() + "  fs.chunks=" + d.fs.chunks.countDocuments());
["books", "readers", "borrow_logs"].forEach(c =>
  print("[" + c + "] 索引 " + d[c].getIndexes().length + " 个：" + d[c].getIndexes().map(i => i.name).join(", ")));'

echo "===== 二、副本集 rs_lib 27018 ====="
mongosh --port 27018 $AUTH --eval '
rs.status().members.forEach(m => print(m.name + "  " + m.stateStr + "  health=" + m.health));
print("主节点：" + db.hello().primary);'
mongosh --port 27018 $AUTH --eval 'rs.printSecondaryReplicationInfo()'

echo "===== 三、分片集群 27022 ====="
mongosh --port 27022 $AUTH --eval '
db.adminCommand({listShards: 1}).shards.forEach(s => print(s._id + "  " + s.host));
const cfg = db.getSiblingDB("config");
["borrow_logs", "books"].forEach(n => {
  const c = cfg.collections.findOne({_id: "library." + n});
  const g = cfg.chunks.aggregate([{$match: {uuid: c.uuid}}, {$group: {_id: "$shard", n: {$sum: 1}}}]).toArray();
  print(n + " 块分布：" + JSON.stringify(g));
  print(n + " 文档数：" + db.getSiblingDB("library")[n].countDocuments());
});'

echo "===== 四、路由抽查 ====="
mongosh --port 27022 $AUTH --eval '
const d = db.getSiblingDB("library");
function shardsOf(q, coll) {
  const ex = d[coll].find(q).explain();
  const s = (ex.queryPlanner.winningPlan.shards || []).map(x => x.shardName);
  return s.length ? s.join(",") : "(单分片)";
}
print("reader_card=R20240001 → " + shardsOf({reader_card: "R20240001"}, "borrow_logs"));
print("status=逾期           → " + shardsOf({status: "逾期"}, "borrow_logs"));
print("isbn=9787115428028    → " + shardsOf({isbn: "9787115428028"}, "books"));'

echo "===== 五、本实例端口 ====="
ss -lntp | grep -E ':(2701[7-9]|2702[0-2])' | awk '{print $4}' | sort -t: -k2 -n
