// 索引：books 4 个、readers 3 个、borrow_logs 5 个（不含默认的 _id_）
//
// 在哪跑：单机 27017
//   mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 02_建索引.js
//
// 重复执行不会报错：同样的名字和字段，MongoDB 直接返回已存在。

const d = db.getSiblingDB('library');

// books：ISBN 唯一、按分类查、标题全文索引、分类+ISBN 组合
d.books.createIndex({isbn: 1}, {unique: true, name: 'uk_isbn'});
d.books.createIndex({category: 1}, {name: 'idx_category'});
d.books.createIndex({title: 'text'}, {name: 'idx_title_text'});
d.books.createIndex({category: 1, isbn: 1}, {name: 'idx_cat_isbn'});

// readers：借阅证唯一、按学院查、学院+证号组合
d.readers.createIndex({card_no: 1}, {unique: true, name: 'uk_card_no'});
d.readers.createIndex({college: 1}, {name: 'idx_college'});
d.readers.createIndex({college: 1, card_no: 1}, {name: 'idx_college_card'});

// borrow_logs：证号散列（分片阶段要用的键）、按书查、按日期倒序、书+日期、按状态
d.borrow_logs.createIndex({reader_card: 'hashed'}, {name: 'idx_card_hashed'});
d.borrow_logs.createIndex({book_isbn: 1}, {name: 'idx_book_isbn'});
d.borrow_logs.createIndex({borrow_date: -1}, {name: 'idx_date_desc'});
d.borrow_logs.createIndex({book_isbn: 1, borrow_date: -1}, {name: 'idx_isbn_date'});
d.borrow_logs.createIndex({status: 1}, {name: 'idx_status'});

print('索引清单：');
['books', 'readers', 'borrow_logs'].forEach(c => {
  print('[' + c + '] 共 ' + d[c].getIndexes().length + ' 个');
  d[c].getIndexes().forEach(i => print('   ' + i.name + '  ' + JSON.stringify(i.key)));
});
