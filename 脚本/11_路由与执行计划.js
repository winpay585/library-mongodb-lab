// 查询落点与执行计划：证明分片键和索引确实起作用。
//
// 在哪跑：mongos 27022，用 platform_admin（只读）
//   mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 11_路由与执行计划.js

const d = db.getSiblingDB('library');

function shardsOf(q, coll) {
  const ex = d[coll].find(q).explain();
  const s = (ex.queryPlanner.winningPlan.shards || []).map(x => x.shardName);
  return s.length ? s.join(',') : '(只有一个分片)';
}

print('== 查询落点 ==');
print('带分片键 reader_card=R20240001   → ' + shardsOf({reader_card: 'R20240001'}, 'borrow_logs'));
print('不带分片键 status=逾期           → ' + shardsOf({status: '逾期'}, 'borrow_logs'));
print('带分片键 isbn=9787115428028      → ' + shardsOf({isbn: '9787115428028'}, 'books'));
print('空条件全表扫                      → ' + shardsOf({}, 'borrow_logs'));

print('== 执行计划（扫描量对比）==');
function run(label, q) {
  const p = d.borrow_logs.find(q).explain('executionStats');
  const s = p.executionStats;
  print(label + '：返回 ' + s.nReturned + ' 条，扫描文档 ' + s.totalDocsExamined
        + '，扫描索引项 ' + s.totalKeysExamined + '，耗时 ' + s.executionTimeMillis + ' ms');
}
run('按 ISBN 查（走 idx_book_isbn）', {book_isbn: '9787115428028'});
run('按借阅证查（走 idx_card_hashed）', {reader_card: 'R20240001'});
run('按状态查（走 idx_status）', {status: '逾期'});
