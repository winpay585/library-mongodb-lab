// 分片键到底切没切、块落在哪、要不要手动搬——都在 mongos 上看。
//
// 在哪跑：mongos 27022，用 platform_admin
//   mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 10_分片与块迁移.js
//
// 重复执行安全：已经有多个块、两个分片都有数据时，脚本只打印分布，不再切分和迁移。

const cfg = db.getSiblingDB('config');

function chunksOf(ns) {
  const c = cfg.collections.findOne({_id: ns});
  return cfg.chunks.find({uuid: c.uuid}).sort({'min.reader_card': 1, 'min.isbn': 1}).toArray();
}

function perShard(ns) {
  const c = cfg.collections.findOne({_id: ns});
  return cfg.chunks.aggregate([
    {$match: {uuid: c.uuid}},
    {$group: {_id: '$shard', n: {$sum: 1}}}
  ]).toArray();
}

// 1. 块太少时先按散列值切几刀，均衡器才有东西可搬
let bl = chunksOf('library.borrow_logs');
if (bl.length < 4) {
  ['-6917529027641081856', '-4611686018427387904', '-2305843009213693952',
   '0', '2305843009213693952', '4611686018427387904', '6917529027641081856'].forEach(p => {
    try {
      db.adminCommand({split: 'library.borrow_logs', middle: {reader_card: NumberLong(p)}});
    } catch (e) {
      print('切分跳过 ' + p + '：' + e.codeName);
    }
  });
  try { db.adminCommand({split: 'library.books', middle: {isbn: NumberLong('0')}}); } catch (e) {}
  db.adminCommand({balancerStart: 1});
  print('已切分 borrow_logs，并启动均衡器');
} else {
  print('borrow_logs 已有 ' + bl.length + ' 个块，不再切分');
}

// 2. 数据都堆在一个分片时，手动搬一半过去
if (perShard('library.borrow_logs').length < 2) {
  bl = chunksOf('library.borrow_logs');
  bl.slice(0, Math.floor(bl.length / 2)).forEach((c, i) => {
    const r = db.adminCommand({moveChunk: 'library.borrow_logs', bounds: [c.min, c.max], to: 'shard2'});
    print('  borrow_logs 第 ' + (i + 1) + ' 块 → ' + (r.ok === 1 ? 'OK' : '失败：' + r.errmsg));
  });
  const bk = chunksOf('library.books');
  const r2 = db.adminCommand({moveChunk: 'library.books', bounds: [bk[0].min, bk[0].max], to: 'shard2'});
  print('  books 第 1 块 → ' + (r2.ok === 1 ? 'OK' : '失败：' + r2.errmsg));
} else {
  print('两个分片都已有块，跳过手动迁移');
}

// 3. 分布
['borrow_logs', 'books'].forEach(n => {
  print('== ' + n + ' ==');
  print('  块数：' + JSON.stringify(perShard('library.' + n)));
  // getShardDistribution 返回的是 mongosh 包装对象，真实数据在 .value 里
  const o = db.getSiblingDB('library')[n].getShardDistribution().value;
  Object.keys(o).forEach(k => {
    if (k === 'Totals') return;
    const v = o[k];
    const short = k.replace(/ at .*/, '');          // "Shard shard1 at ..." → "Shard shard1"
    const pct = o.Totals[short] ? o.Totals[short][0] : '';
    print('  ' + short + '：文档 ' + v.docs + '，块 ' + v.chunks + '，' + v.data + '，' + pct);
  });
  print('  合计：文档 ' + o.Totals.docs + '，块 ' + o.Totals.chunks + '，' + o.Totals.data);
});

print('== 库的主分片 ==');
db.getSiblingDB('config').databases.find({_id: 'library'}).forEach(d => print('  primaryShard=' + d.primary));
