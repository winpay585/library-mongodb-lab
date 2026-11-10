// 五组统计查询，对应任务书里的五个统计需求。
//
// 在哪跑：单机 27017，只读，不写数据
//   mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 03_检索与统计.js

const d = db.getSiblingDB('library');

print('== Q1 各分类的图书数、均价、总借阅 ==');
d.books.aggregate([
  {$group: {_id: '$category', 图书数: {$sum: 1}, 均价: {$avg: '$price'}, 总借阅: {$sum: '$borrow_count'}}},
  {$project: {_id: 0, 分类: '$_id', 图书数: 1, 均价: {$round: ['$均价', 2]}, 总借阅: 1}},
  {$sort: {图书数: -1}}
]).forEach(r => print(JSON.stringify(r)));

print('== Q2 读者数最多的前 5 个学院 ==');
d.readers.aggregate([
  {$group: {_id: '$college', 人数: {$sum: 1}}},
  {$sort: {人数: -1}}, {$limit: 5}
]).forEach(r => print(JSON.stringify(r)));

print('== Q3 按月借阅量 ==');
const m = d.borrow_logs.aggregate([
  {$group: {_id: {$substrCP: ['$borrow_date', 0, 7]}, 借阅量: {$sum: 1}}},
  {$sort: {_id: 1}}
]).toArray();
print('月份数: ' + m.length);
print('首月 ' + m[0]._id + ' = ' + m[0].借阅量 + '，末月 ' + m[m.length - 1]._id + ' = ' + m[m.length - 1].借阅量);
print('合计: ' + m.reduce((s, x) => s + x.借阅量, 0));

print('== Q4 借阅次数最多的 10 本书 ==');
d.borrow_logs.aggregate([
  {$group: {_id: '$book_isbn', 次数: {$sum: 1}}},
  {$sort: {次数: -1}}, {$limit: 10},
  {$lookup: {from: 'books', localField: '_id', foreignField: 'isbn', as: 'b'}},
  {$project: {_id: 0, isbn: '$_id', 书名: {$arrayElemAt: ['$b.title', 0]}, 分类: {$arrayElemAt: ['$b.category', 0]}, 次数: 1}}
]).forEach(r => print(JSON.stringify(r)));

print('== Q5 借阅状态分布 ==');
d.borrow_logs.aggregate([
  {$group: {_id: '$status', 笔数: {$sum: 1}, 平均借期: {$avg: '$duration_days'}}},
  {$project: {_id: 0, 状态: '$_id', 笔数: 1, 平均借期: {$round: ['$平均借期', 1]}}},
  {$sort: {笔数: -1}}
]).forEach(r => print(JSON.stringify(r)));
