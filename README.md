# 图书情报检索与统计平台（MongoDB 实训）

《数据库管理系统》第三章项目一 · 图书情报检索与统计平台

* 班级：数科3班
* 学号：202414870312
* 姓名：郭雨昊
* 实验日期：2026 年 10 月 23 日
* 数据库：MongoDB 7.0.14，端口 27017
* 开发：Python 3.13 + PyMongo 4.19 + mongosh 2.3.8 + Compass 1.44.4

## 一、交付物结构

```
图书情报检索与统计平台\_郭雨昊/
├─ 01\_数据文件/                 # books.txt、readers.txt、borrow\_logs.txt
├─ 02\_Python源码/               # 6 个可运行 Python 文件 + requirements.txt
├─ 03\_实验报告/                 # 数科3班-202414870312-郭雨昊.docx
├─ 04\_运行截图/                 # 覆盖六个任务的 15 张 PNG
├─ 05\_Compass导出/              # 四个集合的 JSON 导出
├─ README.md
└─ 提交清单.txt
```

## 二、环境要求

1. Windows 10/11 64 位；
2. MongoDB Community Server 7.0（mongod 可在 PATH 中直接执行）；
3. Python 3.9 及以上；
4. `pip install -r 02\_Python源码/requirements.txt`；
5. 可选：mongosh、MongoDB Compass、Git。

## 三、快速运行

### 1\. 启动 MongoDB

```bat
mongod --dbpath "D:\\mongodb\\data" --logpath "D:\\mongodb\\log\\mongod.log" --port 27017
```

如果要验证权限，创建用户后加 `--auth`。

### 2\. 导入数据

一次性建库和导入的完整命令见 `00\_先看这里\_操作指南.md` 与实验报告 3.2 节。
已经建好库时，只需：

```bat
mongoimport --db library --collection readers --file 01\_数据文件\\readers.txt --jsonArray
mongoimport --db library --collection borrow\_logs --file 01\_数据文件\\borrow\_logs.txt --jsonArray
```

### 3\. 运行程序

```bat
cd 02\_Python源码
pip install -r requirements.txt
python main.py
```

程序启动后会打印连接状态和四个集合的文档总数，菜单共 12 项。

## 四、账号说明

|账号|密码|角色|
|-|-|-|
|libWriter|Writer@12345|readWrite + dbAdmin（library）|
|libReader|Reader@12345|read（library）|



## 五、数据规模

* books：20 本
* readers：16 人
* borrow\_logs：66 条（执行 D1、D2 后为 52 条）
* category\_stats：5 条
* book\_in\_stock 视图：19 条

## 六、说明

1. `borrow\_logs` 是时间序列集合，`expireAfterSeconds=63072000`（2 年）。
2. 报告中的截图只选了关键图，完整 15 张在 `04\_运行截图`。
3. GitHub 公开仓库：https://github.com/winpay585/library-mongodb-lab

