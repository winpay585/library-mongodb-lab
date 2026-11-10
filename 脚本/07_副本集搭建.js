// 副本集 rs_lib 初始化（nosql01/02/03:27018）
//
// 在哪跑：只在一个节点上执行一次，一般在 nosql01
//   mongosh --port 27018 -f 07_副本集搭建.js
//   已经建过账号、开了认证的话要带上账号：
//   mongosh --port 27018 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 07_副本集搭建.js
//
// 顺序：实例启动（还没开认证）→ 跑本脚本建 rs → 跑 04 建账号 → 加认证重启。
// 重复执行安全：已经是 rs_lib 就只打印成员状态，不会再 initiate。

const setName = db.hello().setName || '';

if (setName === 'rs_lib') {
  print('已经是 rs_lib，不重复初始化。当前成员：');
  try {
    rs.status().members.forEach(m => print('  ' + m.name + '  ' + m.stateStr + '  health=' + m.health));
  } catch (e) {
    print('  （读不到 rs.status，通常是没带账号：' + e.codeName + '）');
  }
  print('当前主节点：' + db.hello().primary);
} else {
  if (setName) {
    print('这个实例已经属于别的副本集：' + setName + '，停下来先确认配置。');
  } else {
    printjson(rs.initiate({
      _id: 'rs_lib',
      members: [
        {_id: 0, host: 'nosql01:27018', priority: 2},
        {_id: 1, host: 'nosql02:27018', priority: 1},
        {_id: 2, host: 'nosql03:27018', priority: 1}
      ]
    }));
    sleep(8000);
    rs.status().members.forEach(m => print('  ' + m.name + '  ' + m.stateStr + '  health=' + m.health));
    print('当前主节点：' + db.hello().primary);
  }
}
