#!/bin/bash
# GridFS：6 个电子书/封面文件存进 library 库的 fs 集合，再下载回来比对 MD5。
#
# 在哪跑：nosql01。文件放在 /data/lib/tmp/data/gridfs_files（数据/gridfs 里那 6 个）。
# 关键点：上传前先 cd 到目录，用文件名本身上传，别用绝对路径——mongofiles 会把整条路径
#        当成 filename 存进 fs.files。
#
# 用法：bash 06_电子书存取.sh [端口]
#       DB=library_probe bash 06_电子书存取.sh 27017    # 存到临时库里试

PORT=${1:-27017}
DB=${DB:-library}
DIR=${GRID_DIR:-/data/lib/tmp/data/gridfs_files}
DL=${DL_DIR:-/data/lib/out/gridfs_dl}
FILES="ebook_1.pdf ebook_2.pdf ebook_3.pdf cover_1.png cover_2.png cover_3.png"
U=${MONGO_USER:-lib_admin}
P=${MONGO_PASS:-lib2026pwd}
ADB=${MONGO_AUTHDB:-$DB}
AUTH="--port $PORT -d $DB -u $U -p $P --authenticationDatabase $ADB"

mkdir -p "$DL"
cd "$DIR" || exit 1
echo "== 源文件 MD5 =="
md5sum $FILES

echo "== 上传到 GridFS =="
for f in $FILES; do
  mongofiles $AUTH put "$f"
done

echo "== fs.files 里的记录 =="
mongosh --port "$PORT" -u "$U" -p "$P" --authenticationDatabase "$ADB" --quiet --eval "
const f = db.getSiblingDB('$DB').fs.files;
f.find({}, {filename: 1, length: 1, chunkSize: 1, _id: 0}).forEach(x =>
  print(x.filename + '  ' + x.length + ' 字节  chunkSize=' + x.chunkSize));
print('共 ' + f.countDocuments() + ' 个文件');
"

echo "== 下载回来比对 =="
rm -rf "$DL"
mkdir -p "$DL"
cd "$DL" || exit 1
for f in $FILES; do
  mongofiles $AUTH get "$f" >/dev/null
done
md5sum $FILES
(cd "$DIR" && md5sum $FILES | awk '{print $1}' | sort) > /tmp/gridfs_src.md5
(cd "$DL" && md5sum $FILES | awk '{print $1}' | sort) > /tmp/gridfs_dst.md5
if diff -q /tmp/gridfs_src.md5 /tmp/gridfs_dst.md5 >/dev/null; then
  echo "6 个文件 MD5 与源文件一致"
else
  echo "MD5 不一致，见 /tmp/gridfs_src.md5 与 /tmp/gridfs_dst.md5"
  diff /tmp/gridfs_src.md5 /tmp/gridfs_dst.md5
  exit 1
fi
