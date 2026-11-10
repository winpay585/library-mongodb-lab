// 账号与自定义角色。跑完这四个账号再开认证（security.authorization: enabled）。
//
// 在哪跑：单机 27017，用 platform_admin 连接
//   mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 04_账号与角色.js
//
// 重复执行安全：账号已存在就跳过，只更新角色绑定。

const admin = db.getSiblingDB('admin');
const lib = db.getSiblingDB('library');

function ensureUser(dbRef, user, pwd, roles) {
  const exists = dbRef.getUsers().users.some(u => u.user === user);
  if (exists) {
    dbRef.updateUser(user, {roles: roles});
    print(user + ' 已存在，角色已更新为 ' + roles.map(r => r.role).join('/'));
    return;
  }
  dbRef.createUser({user: user, pwd: pwd, roles: roles});
  print(user + ' 已创建，角色 ' + roles.map(r => r.role).join('/'));
}

ensureUser(admin, 'platform_admin', 'Admin2026pwd', [{role: 'root', db: 'admin'}]);
ensureUser(lib, 'lib_admin', 'lib2026pwd', [{role: 'dbOwner', db: 'library'}]);
ensureUser(lib, 'lib_reader', 'lib2026pwd', [{role: 'read', db: 'library'}]);

// 自定义角色：能增删改查文档，但不能删集合（内置 readWrite 允许 dropCollection）
try { lib.dropRole('library_editor'); } catch (e) {}
lib.createRole({
  role: 'library_editor',
  privileges: [{resource: {db: 'library', collection: ''}, actions: ['find', 'insert', 'update', 'remove']}],
  roles: []
});
print('自定义角色 library_editor 已建立：find/insert/update/remove，不含 dropCollection');
ensureUser(lib, 'lib_editor', 'lib2026pwd', [{role: 'library_editor', db: 'library'}]);

print('当前 library 库账号：' + lib.getUsers().users.map(u => u.user + '(' + u.roles.map(r => r.role).join('/') + ')').join('  '));
