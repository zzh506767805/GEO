#!/usr/bin/env python3
"""模拟云盘上传脚本（youzan-oss 的 upload.js），只给本地测试用。

和真脚本一样：收 --file-path，成功时在标准输出打印带 url 的 JSON；同一个文件每次给出同一个链接。
  MOCK_UPLOAD_FAIL=1   模拟上传失败
  MOCK_UPLOAD_LOG=<文件>  每上传一次往里记一行，测试用它数上传了几次
"""
import argparse
import json
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--file-path", required=True)
args = parser.parse_args()
if os.environ.get("MOCK_UPLOAD_FAIL"):
    sys.stderr.write("上传失败：云盘暂时不可用\n")
    sys.exit(1)
if not os.path.isfile(args.file_path):
    sys.stderr.write("文件不存在\n")
    sys.exit(1)
log = os.environ.get("MOCK_UPLOAD_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(args.file_path + "\n")
print(json.dumps({"url": "https://claw-cloud.youzan.com/f/mock/ai-visibility-employee/pages/" + os.path.basename(args.file_path)}))
