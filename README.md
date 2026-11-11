# 智慧图书馆数字资源平台（MongoDB 三节点实验）

24数科3班 202414870312 郭雨昊

## 一、做了什么

在 VMware Workstation 上起三台 CentOS Stream 10 虚拟机（nosql01 / nosql02 / nosql03），
用 Xshell 通过 SSH 登进去，在三台上部署 MongoDB 8.0.34，按三个层次把"智慧图书馆数字资源平台"
的数据层做完：

1. 单机：27017 端口，导入图书 50 本、读者 30 人、借阅记录 3000 条，建索引、做五类查询统计、
   用 GridFS 存电子书与封面、建三层账号并开启认证。
2. 副本集：三台各起一个 27018 实例组成 rs_lib，keyfile 认证，做主节点宕机后的自动切换演练。
3. 分片集群：配置服务器副本集 cfgrs（27019）、两个分片副本集 shard1rs(27020) 与 shard2rs(27021)、
   路由 mongos（27022），对 books 和 borrow_logs 做哈希分片，验证数据分布与请求路由。

## 二、目录

- 文档/    技术文档，Word 和 PDF 各一份
- 程序/    Python 程序（pymongo 连库，做检索、统计与电子书存取）
- 脚本/    数据库这一层的脚本：建索引、统计查询、账号权限、GridFS、副本集、分片、验收
- 配置/    三台机器的主机名、hosts、目录划分、keyfile 做法
- 截图/    运行截图
- 数据/    导入用的源数据，以及 GridFS 用的电子书和封面
- 日志/    部署与排错时的命令输出，按执行先后编号

## 三、机器与端口

三台机器：nosql01 192.168.121.134、nosql02 192.168.121.135、nosql03 192.168.121.136，
4 GB 内存 / 2 核，MongoDB 8.0.34。

端口分配：27016 统一口径的独立单机实例，27017 单机，27018 副本集，27019 配置服务器，
27020 与 27021 两组分片，27022 mongos。

27016 这个实例是按第 3 章环境规范的写法单独建的：安装目录 `/export/servers/mongodb-8.3.8`、
数据目录 `/export/servers/standalone/dbs`、日志 `/export/servers/standalone/log/mongodb.log`、
配置文件 `/export/servers/standalone/mongod.conf`、账号 `itcastAdmin/123456`（admin 库，root 角色），
开启访问控制。它跟 27017 是两套独立数据目录，互不影响；环境规范里的命令可以直接在它上面跑通。

## 四、怎么跑

前置：三台机器按 `配置/说明.txt` 建好目录、写好 hosts，各实例用对应的 mongod 配置起起来
（单机 27017、副本集 27018、配置服务器 27019、分片 27020/27021、mongos 27022）。
脚本只管数据库里的活，不装机、不连 SSH。

| 顺序 | 命令 | 干什么 |
| --- | --- | --- |
| 1 | `bash 01_导入数据.sh 27017` | 三个集合导进 library（认证没开就不用带账号） |
| 2 | `mongosh --port 27017 -f 02_建索引.js` | 建 12 个业务索引 |
| 3 | `mongosh --port 27017 -f 03_检索与统计.js` | 五组统计查询 |
| 4 | `mongosh --port 27017 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 04_账号与角色.js` | 四个账号 + 自定义角色 |
| 5 | `bash 05_权限验证.sh` | 三类账号的权限边界 |
| 6 | `bash 06_电子书存取.sh` | 6 个文件进 GridFS 并比对 MD5 |
| 7 | `mongosh --port 27018 -f 07_副本集搭建.js` | 组 rs_lib（一个节点执行一次） |
| 8 | `bash 08_故障转移演练.sh` | 在当前主节点上测切换时间 |
| 9 | `mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 09_分片集群搭建.js` | 挂分片、开分片、定分片键 |
| 10 | `mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 10_分片与块迁移.js` | 切块、看分布、必要时 moveChunk |
| 11 | `mongosh --port 27022 -u platform_admin -p Admin2026pwd --authenticationDatabase admin -f 11_路由与执行计划.js` | 查询落点与扫描量 |
| 12 | `bash 12_集群验收.sh` | 一次打出三套环境的指标 |

除 01、05、06、08、12 是 shell（要用 mongoimport、mongofiles、kill、ss），其余都是 mongosh 脚本。
每个脚本开头都写了在哪台机器跑、要不要带账号；重复执行不会破坏已有数据。
01 的 `--drop` 会清空集合，所以它要排在 02 之前。

## 五、程序怎么跑

程序在 Windows 本机跑，连虚拟机上的库，默认连 27016 这个统一口径实例。

```bash
cd 程序
pip install -r requirements.txt
python run.py --demo          # 按固定顺序跑 12 项功能，输出可直接截图
python run.py                 # 菜单模式，13 个功能项按编号选
python run.py --profile replset   # 换成副本集，连 27018
```

连接串与账号都写在 `程序/config.ini`：单机用 lib_editor/lib2026pwd（library 库），
副本集和分片用 platform_admin。换机器只改这个文件。

## 六、账号

platform_admin（admin 库，root 权限）、lib_admin（library 库，dbOwner）、
lib_editor（library 库，只给增删改查）、lib_reader（library 库，只读）。
四个账号的密码见脚本 04。

27016 实例上另有一套对应的账号：itcastAdmin/123456（admin 库 root）、
lib_editor 与 lib_reader（library 库，读写与只读）。

## 七、说明

网络用 VMware 的 VMnet8，三台克隆机各自固定静态地址 192.168.121.134/135/136，
网关 192.168.121.2，DNS 223.5.5.5。宿主机按地址 SSH 直连，重启后地址不变。
网关与地址的配置写法在 `配置/说明.txt`，验证过程在技术文档第九章。


