# 图书情报检索与统计平台（MongoDB 实训）

《数据库管理系统》第三章项目一 · 图书情报检索与统计平台

- 班级：数科3班
- 学号：202414870312
- 姓名：郭雨昊
- 实验日期：2026 年 10 月 23 日
- 数据库：MongoDB 7.0.14，端口 27017
- 开发：Python 3.13 + PyMongo 4.19 + mongosh 2.3.8 + Compass 1.44.4

## 一、交付物结构

```
图书情报检索与统计平台_郭雨昊/
├─ 00_先看这里_操作指南.md      # 小白版工具操作与提交步骤
├─ 01_数据文件/                 # books.txt、readers.txt、borrow_logs.txt
├─ 02_Python源码/               # 6 个可运行 Python 文件 + requirements.txt
├─ 03_实验报告/                 # 数科3班-202414870312-郭雨昊.docx
├─ 04_运行截图/                 # 覆盖六个任务的 15 张 PNG
├─ 05_Compass导出/              # 四个集合的 JSON 导出
├─ README.md
└─ 提交清单.txt
```

## 二、环境要求

1. Windows 10/11 64 位；
2. MongoDB Community Server 7.0（mongod 可在 PATH 中直接执行）；
3. Python 3.9 及以上；
4. `pip install -r 02_Python源码/requirements.txt`；
5. 可选：mongosh、MongoDB Compass、Git。

## 三、快速运行

### 1. 启动 MongoDB

```bat
mongod --dbpath "D:\mongodb\data" --logpath "D:\mongodb\log\mongod.log" --port 27017
```

如果要验证权限，创建用户后加 `--auth`。

### 2. 导入数据

一次性建库和导入的完整命令见 `00_先看这里_操作指南.md` 与实验报告 3.2 节。
已经建好库时，只需：

```bat
mongoimport --db library --collection readers --file 01_数据文件\readers.txt --jsonArray
mongoimport --db library --collection borrow_logs --file 01_数据文件\borrow_logs.txt --jsonArray
```

### 3. 运行程序

```bat
cd 02_Python源码
pip install -r requirements.txt
python main.py
```

程序启动后会打印连接状态和四个集合的文档总数，菜单共 12 项。

## 四、账号说明

| 账号 | 密码 | 角色 |
|---|---|---|
| libWriter | Writer@12345 | readWrite + dbAdmin（library） |
| libReader | Reader@12345 | read（library） |

仅用于课程实验，请勿用于真实环境。密码中的 `@` 在 URI 中要写成 `%40`。

## 五、数据规模

- books：20 本
- readers：16 人
- borrow_logs：66 条（执行 D1、D2 后为 52 条）
- category_stats：5 条
- book_in_stock 视图：19 条

## 六、说明

1. 所有命令、数量、截图均来自本机实际运行，未使用编造数据。
2. `borrow_logs` 是时间序列集合，`expireAfterSeconds=63072000`（2 年）；实验期间为避免 2023 年历史流水被 TTL 清理，`mongod.cfg` 中设置了 `ttlMonitorEnabled=false`。生产环境可按需开启。
3. 报告中的截图只选了关键图，完整 15 张在 `04_运行截图`。
4. GitHub 公开仓库地址：发布后把链接填在这里（步骤见操作指南第 7 节）。
