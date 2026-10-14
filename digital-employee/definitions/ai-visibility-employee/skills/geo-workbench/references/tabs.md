# 客户端页签

客户端的“对话 / AI 曝光工作台”页签，与 HTML 工作台内部的“首页 / 内容 / 监测设置”页面是两件事。商家说“新增嵌入 tab”“客户端嵌入工作台”“固定页签”，走这里，不解释成工作台内加页面。

用 Bash 里的 `claw-admin-request` 设置，它自动签名、按当前店铺和员工找到要改的页签。页签配置是 `publish` 生成的 `tabConfigFile`，还没开通工作台时先 `publish`。在同一次 Bash 中执行：

```bash
python3 - <<'PY'
import json, os, re, subprocess
from pathlib import Path
match = re.fullmatch(r"claw-chat:([A-Za-z0-9_-]{1,64}):employee", os.environ.get("YOUZAN_AGENT_SESSION_KEY", ""))
if not match:
    raise SystemExit("当前会话不是数字员工会话，不能设置页签")
endpoint = "/api/claw-chat/employees/" + match.group(1) + "/tabs"
workspace = Path(os.environ["YOUZAN_AGENT_SESSION_WORKSPACE"])
payload = json.loads((workspace / "ai-visibility-employee/profile/employee-tabs.json").read_text())
def request(method, body=None):
    command = ["claw-admin-request", method, endpoint]
    if body is not None:
        command += ["--json", json.dumps(body, ensure_ascii=False)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    response = json.loads(result.stdout)
    if result.returncode or response.get("success") is not True or response.get("data", {}).get("code") != 0:
        raise SystemExit("签名页签请求未成功，请查看实际失败原因，不声称已固定")
    return response["data"]["data"]
before = request("get")
expected = [(t["tabName"], t["tabUrl"], t["render_source"]) for t in payload["tabs"]]
actual = [(t["tabName"], t["tabUrl"], t["render_source"]) for t in before["tabs"]]
if actual != expected:
    request("put", payload)
after = request("get")
if after["employeeId"] != before["employeeId"] or [(t["tabName"], t["tabUrl"], t["render_source"]) for t in after["tabs"]] != expected:
    raise SystemExit("页签读回不一致，不能声称已固定")
print(json.dumps({"verified": True, "employeeId": after["employeeId"], "tabs": after["tabs"]}, ensure_ascii=False))
PY
```

它先读，配置不对才写（PUT 全量覆盖），写完再读回核对。没成功就告诉商家页签暂时没加上，照样给工作台链接。

## 设置成功了，商家那边没马上看到

读回正确只说明配置存好了。客户端只在进入这个伙伴页面时读取页签配置，在页面里切换页签不会重新读取，新加的页签要返回伙伴列表、再重新进入这个伙伴页面才看得到。所以：

- 第一次固定成功后，告诉商家一句：“上面加了一个「AI 曝光工作台」页签。如果还没看到，请返回伙伴列表，再重新进入这个伙伴页面。”同时照样给工作台链接，他在手机上或者转发时用得着。
- 商家说还是看不到：再执行一次上面的命令（配置是对的就只读不写）。读回正确，就请他返回伙伴列表，再重新进入这个伙伴页面看。
- 之后每次同步完，商家在页签里看到的可能还是旧的内容。说到这一期的结果时，加一句“页签里如果还是旧的，切一下再回来”，并照样给 `reportUrl`。
