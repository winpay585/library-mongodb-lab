"""阶段一（GridFS 补跑）：带认证上传 6 个文件，下载后逐文件比对 MD5。"""

from __future__ import annotations

import os
from pathlib import Path

import paramiko

HOST = "192.168.121.134"
USER = os.environ.get("LAB_USER", "root")
PASS = os.environ.get("LAB_PASS", "111111")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "linux"
FILES = "ebook_1.pdf ebook_2.pdf ebook_3.pdf cover_1.png cover_2.png cover_3.png"
AUTH = "-u lib_admin -p lib2026pwd --authenticationDatabase library"


def main() -> None:
    log: list[str] = []
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, port=22, username=USER, password=PASS, timeout=10,
                allow_agent=False, look_for_keys=False)

    def sh(cmd: str, timeout: int = 180) -> int:
        _, out, err = cli.exec_command(cmd, timeout=timeout)
        rc = out.channel.recv_exit_status()
        log.append(f"$ {cmd}")
        log.append((out.read() + err.read()).decode("utf-8", "replace").strip())
        log.append(f"[exit {rc}]")
        log.append("")
        return rc

    sh(f"cd /data/lib/tmp/data/gridfs_files && for f in {FILES}; do "
       f"mongofiles --port 27017 {AUTH} -d library put $f; done; echo")
    list_js = ("db.getSiblingDB('library').fs.files.find({}, {filename:1, length:1, chunkSize:1, _id:0})"
               ".forEach(f => print(f.filename, f.length, f.chunkSize))")
    sh(f"cd /data/lib/tmp && printf '%s\\n' \"{list_js}\" > fslist.js && "
       f"mongosh --port 27017 {AUTH} --quiet /data/lib/tmp/fslist.js")
    sh(f"rm -rf /data/lib/out/gridfs_dl; mkdir -p /data/lib/out/gridfs_dl; cd /data/lib/out/gridfs_dl && "
       f"for f in {FILES}; do mongofiles --port 27017 {AUTH} -d library get $f >/dev/null; done; ls -l; md5sum * | sort -k2")
    sh("cd /data/lib/tmp/data/gridfs_files && md5sum *.pdf *.png | awk '{print $1}' | sort > /tmp/src.txt; "
       "cd /data/lib/out/gridfs_dl && md5sum * | awk '{print $1}' | sort > /tmp/dst.txt; "
       "diff /tmp/src.txt /tmp/dst.txt && echo 'GridFS 6 个文件字节与 MD5 与源文件逐一一致'")
    sh(f"mongosh --port 27017 {AUTH} --quiet --eval "
       "'const d=db.getSiblingDB(\"library\");print(\"fs.files=\"+d.fs.files.countDocuments()+\" fs.chunks=\"+d.fs.chunks.countDocuments()+\" 总字节=\"+d.fs.chunks.aggregate([{$group:{_id:null,n:{$sum:\"$data.length\"}}}]).toArray()[0].n)'")

    cli.close()
    (OUT / "gridfs.log").write_text("\n".join(log), encoding="utf-8")
    print("lines:", len(log))


if __name__ == "__main__":
    main()
