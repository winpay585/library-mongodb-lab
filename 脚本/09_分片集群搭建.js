// 分片集群的业务侧配置：挂两个分片、library 库开启分片、给两张表定分片键。
//
// 在哪跑：mongos 27022，用 platform_admin
//   mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 09_分片集群搭建.js
//
// 前置：配置服务器 cfgrs(27019)、分片副本集 shard1rs(27020)/shard2rs(27021)、mongos 已经起来。
// 重复执行安全：已经挂过的分片、已经分片的集合会跳过。

const cfg = db.getSiblingDB('config');

function shardNames() {
  return db.adminCommand({listShards: 1}).shards.map(s => s._id);
}

function isSharded(ns) {
  const rows = cfg.collections.find({_id: ns, dropped: {$ne: true}}).toArray();
  return rows.length > 0;
}

if (shardNames().indexOf('shard1') === -1) {
  printjson(db.adminCommand({addShard: 'shard1rs/nosql01:27020,nosql02:27020', name: 'shard1'}));
} else {
  print('shard1 已在集群里');
}
if (shardNames().indexOf('shard2') === -1) {
  printjson(db.adminCommand({addShard: 'shard2rs/nosql03:27021,nosql02:27021', name: 'shard2'}));
} else {
  print('shard2 已在集群里');
}

const libDb = cfg.databases.find({_id: 'library'}).toArray();
if (libDb.length === 0 || !libDb[0].partitioned) {
  printjson(db.adminCommand({enableSharding: 'library'}));
} else {
  print('library 已开启分片');
}

if (!isSharded('library.borrow_logs')) {
  printjson(db.adminCommand({shardCollection: 'library.borrow_logs', key: {reader_card: 'hashed'}}));
} else {
  print('borrow_logs 已按 reader_card 散列分片');
}
if (!isSharded('library.books')) {
  printjson(db.adminCommand({shardCollection: 'library.books', key: {isbn: 'hashed'}}));
} else {
  print('books 已按 isbn 散列分片');
}

print('分片清单：');
db.adminCommand({listShards: 1}).shards.forEach(s => print('  ' + s._id + '  ' + s.host));
