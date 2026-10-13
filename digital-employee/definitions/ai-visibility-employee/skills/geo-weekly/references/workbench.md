# 工作台和报告：你做的事怎么出现在上面

商家看这份工作只用打开一个地方：**工作台**。它是一个固定的链接，左边是导航，右边是内容。

- 工作台自己只放跨期的东西：最新一期的结论、几个数的走势、每一期报告的入口、你替他写的内容、监测设置。
- **体检报告**每期一份，是一个独立的文件：这一期问了什么、AI 提没提到、没提到时提到了谁、读了哪里的内容、怎么介绍这家店。
- 商家看报告不用跳到别的页面。在工作台左边点某一期，那一期的报告就在右边打开。报告文件也可以单独打开，商家要转发给别人时用。

页面都是只读的：商家在上面看，回到对话里跟你说；你改数据，再同步。

页面是“模板 + 数据”每次同步重新生成的：数据由脚本从存档里算出来，模板决定长什么样。**不要直接改生成出来的网页文件**，下次同步会被盖掉。商家想改页面，按下面的“改这家店的页面”做：能用内容块拼出来的，填一个页面；想改样子、在已有页面上加模块，改这家店自己的模板，什么都可以改。

本文表格里的 `geo_report.py ...`、`geo_state.py ...`、`geo_run.py ...`、`geo_score.py ...` 都是简写，执行时每条命令都写全路径：`python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/<技能>/scripts/<脚本>"`。geo_report.py 在 geo-weekly 下，geo_state.py 在 geo-profile 下，geo_run.py 和 geo_score.py 在 geo-check 下。

## 三条规则

1. **数据一变就同步。** 同步只有一条命令：

   ```bash
   python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" publish
   ```

   它重新生成这一期的报告和工作台、传到云盘、保存链接。输出里：
   - `pageUrl`：工作台。
   - `reportUrl`：在工作台里打开这一期的报告。**说到这一期的结果时，发给商家的是它。**
   - `links`：可以直接发给商家的几个链接（工作台、内容、监测设置、这一期的报告）。
   - `reportFileUrl`：报告文件自己的链接。只有商家说要把报告单独转发给别人时才给。
   - `synced`：这次同步上去的变化。

2. **说到哪件事，就给对应的链接。** 这一期的结果给 `reportUrl`；内容、监测设置给 `links` 里对应的页面。链接逐字照抄，不改域名、不解码、不重新拼。

3. **页面上已经有的，对话里不重复贴。** 对话里只说结论和要商家做的事，明细让他点链接看。

怎么知道页面是不是最新的：`geo_state.py status`、`geo_report.py links`、`geo_report.py show` 的输出里都有这一项。`pending` 不为空，说明有变化还没同步，先 `publish` 再发链接。改了数据的命令，输出的 `next` 也会提醒。

## 你做的事 → 落在哪

| 你做的事 | 命令 | 落在哪 |
| --- | --- | --- |
| 读店铺资料 | `geo_state.py set-facts` | 不展示。它是你核对和写内容的底稿 |
| 写差异点、出题、选同类店 | `set-facts`（`edges`）、`set-questions`、`set-rivals` | 工作台 · 监测设置 |
| 另外记下后台里没有的信息（别的叫法、已关的旧店；他说的公众号、抖音号） | `set-facts` | 工作台 · 监测设置（你推断的那几样等他确认） |
| 商家同意开启每周体检 | 建定时任务，`geo_state.py set-schedule --status on` | 不展示。每周一出新的一期报告 |
| 发起体检 | `geo_run.py start` | 工作台首页显示“体检进行中” |
| 算分 | `geo_score.py score` | 这一期的报告：有没有提到你、提到了谁、读哪里的内容；工作台首页的几个数 |
| 读全文：每个回答推荐了哪几家店、复核“提到你”和“和你有关的引用”、这一期的发现 | `geo_score.py set-reading`、`set-findings` | 这一期的报告 · 提到了谁、有没有提到你、读哪里的内容；这一期的报告 · 结论（“这一期的发现”，最多 5 条，每条带 AI 的原话） |
| 核对 AI 怎么介绍这家店 | `set-judgement` | 这一期的报告 · 怎么介绍你。有和店铺资料对不上的才列出来 |
| 写本期小结 | `set-actions` 的 `brief` | 工作台首页最上面；这一期的报告 · 结论 |
| 建议商家做的事 | `set-actions` 的 `todos` | 这一期的报告 · 结论（“这一期建议你做的”） |
| 找内容缺口 | `set-actions` 的 `gaps` | 这一期的报告 · 读哪里的内容；工作台 · 内容 |
| 写内容（公众号文章、小红书笔记、长文、抖音视频文案） | `geo_report.py add-content`，要写明类型 | 工作台 · 内容；有等他确认的，首页会多出一块“等你确认的内容” |
| 内容确认了、放进草稿箱了、发出去了 | `geo_report.py mark-content --no N …` | 工作台 · 内容 |
| 填员工负责的页面（登记好的，或这家店单独加的） | `geo_report.py set-page --id <页面> --file …` | 工作台 · 那一页，排在三个固定页面之后 |

工作台首页只有这几样：最新一期的结论和你写的小结、四个数、等他确认的内容（有才出现）、每一期的报告。不要指望在首页上放别的东西；某一期的分析都在那一期的报告里。

## 你要亲手写的五样东西

页面上大部分内容是脚本算出来的。下面五样是你写的，商家会逐字看到，写的时候当成是在对商家说话。

| 写什么 | 在哪写 | 怎么写 |
| --- | --- | --- |
| 本期小结 `brief` | `set-actions` | 两三句话，240 字以内。先说这一期最重要的一件事，再说要商家做什么。只说存档里有的事实，数字和脚本输出一致。不写“上升”“下降”，除非 `compare` 的 `trend` 是 `up` 或 `down` |
| 建议 `todos` | `set-actions` | 最多三件，十分钟内能做完的排前面。`text` 写做什么，`why` 写为什么。它只是报告里的建议，不是要打勾的清单 |
| 缺的内容 `gaps` | `set-actions` | 最多三条。`where` 写平台（公众号、抖音、地图和点评……），`note` 写缺什么、依据是什么 |
| AI 怎么介绍这家店 `descriptions` | `set-judgement` | 每个平台一句话，60 个字左右（最多 120 字），概括它点名介绍这家店时怎么说 |
| 和店铺资料对不上的说法 `issues` | `set-judgement` | 按 `geo-check` 的 `references/judging.md`。没有就传空的 |

`set-actions` 可以只传要改的部分：没传的 `brief`、`todos`、`gaps`、`contentNote` 保持这一期原来的内容。

写建议时先看 `compare` 输出里的 `previousTodos`（上一期建议过什么）：商家说做完了的不再提；没理会的最多再提一次，不要每期都催。真正要他点头的只有两件事，页面上都有固定的入口，不用靠建议去催：确认一篇内容（工作台 · 内容）、确认你另外记下的信息（工作台 · 监测设置）。

## 首页上那几个数，有好几期以后怎么显示

- 显示的永远是**最新一期**的数，不是累计。例如“没点名时提到你 7/60”，是最新一期 60 个回答里的 7 个。
- 数的下面写着上一期是多少；连续两期朝同一个方向变，才会写“连续上升”或“连续下降”。
- 数的旁边有一排小柱子，一期一根，最多 12 根。
- 每一期各自的数，在下面“每一期的报告”那张表里，一行一期。
- 商家改过问题以后，之前几期是按旧问题测的：小柱子不再画它们，表里标着“旧问题”，也不和现在的数比。所以改问题之前要提醒他这一点。

## “对不上的说法”放在哪

AI 介绍这家店时，有的说法会和店铺资料对不上（旧地址、错的营业时间）。这是一种发现，**不是每家店都有，也不是这份工作的主线**：很多店 AI 根本不提它，也就谈不上说错。

- 它只出现在那一期报告的“怎么介绍你”这一节里，有才列出来，每条有固定的序号。
- 工作台上没有它的页面，也没有它的数。
- 值得商家动手的那一条，由你写进本期小结或建议。改起来成本高、收益不明确的，不要硬塞给商家。
- 商家说“3 号我改好了”，你记一笔（`mark-issue`）；下一期 AI 还在这么说，新报告里会标出来。

## 内容：分类型，写完必须登记

替商家写的稿子不放在 `set-actions` 里，单独登记。细则在 `references/content-types.md`，这里只说和页面有关的：

- **内容分类型，稿子跟着类型走。** 公众号文章是带排版的长文，小红书笔记是短标题、短正文加话题，不是同一份稿子换个排版。同一个主题发两个平台，就写两条、登记两条。
- **工作台按类型展示。** 公众号文章给“看排版预览”的入口；小红书笔记显示标题、正文和话题，可以一起复制；长文显示全文，可以复制。
- **每一条都要登记，登记了才算数。** 不管是每周主动写的，还是商家临时让你写的。只在对话里给出来的稿子，工作台上没有，商家回头找不到，你也没法按序号跟他对。
- **对话里不贴全文。** 登记、同步之后，给类型、标题、两三句摘要和“内容”页的链接。
- **序号不变。** 每条内容有一个固定的序号，工作台上显示成“第 4 篇”。商家说“第 4 篇可以发”，就是 `--no 4`。
- 这一期没写，把原因写进 `set-actions` 的 `contentNote`。同步时如果既没登记内容也没写原因，`publish` 会提醒。

## 商家会从页面上复制这些话

每个页面的下面，都有几句“可以这样跟员工说”，商家点一下就复制，回到对话里发给你。所以这些话你一定要接得住：

| 商家说 | 做法 |
| --- | --- |
| “把 Q3 换一个问法”“把 Q3 删掉”“加一道题：……” | 按 `geo-profile` 的“修改”做（Q3 就是 `q03`，B1 就是 `b01`）→ `publish` |
| “同类店换成……”“把同类店换成我真正的对手” | 按 `geo-profile` 的“修改”做 → `publish` |
| “我的公众号叫……”“我的抖音号是……”“这些信息没问题，确认”“我们家的特点是……” | 按 `geo-profile` 的“修改”做 → `publish` |
| “开启每周体检”“每周体检停掉” | 按 `geo-weekly` 的“开启每周体检”做 |
| “写东西不要用某个词” | 按 `geo-profile` 的“修改”做 → `publish` |
| “写一篇公众号文章：……”“写一条小红书笔记：……” | 按 `content-types.md` 里那种类型的写法写，`origin` 写 `asked` → `add-content` → `publish` |
| “同一个主题再写一条小红书笔记” | 重新写一份笔记，不要拿原来的稿子删减 → `add-content`（类型 `xhs`）→ `publish` |
| “第 4 篇可以发” | `mark-content --no 4 --status confirmed` → 按这种类型的“确认后”去做：公众号文章委派 `wechat-writer` 存草稿箱，再 `mark-content --no 4 --channel 公众号草稿箱 --ref <草稿编号>`；其他类型请他在工作台上复制去发 → `publish` |
| “第 4 篇我已经发了” | `mark-content --no 4 --status published --channel <发在哪>` → `publish` |
| “把第 4 篇存进公众号草稿箱” | 只有公众号文章能存。先确认状态是已确认 → 委派 `wechat-writer` → `mark-content --no 4 --channel 公众号草稿箱 --ref <草稿编号>` → `publish` |
| “第 4 篇标题改短一点”“第 4 篇再改一下：……” | `contents --no 4` 取回稿子 → 改稿（公众号文章让 `wechat-writer` 改，拿新的预览链接）→ `add-content` 带上 `"no": 4` → `publish`。他确认过的稿子改了以后要请他再看一眼 |
| “第 4 篇不发了”“这周先不写” | `mark-content --no 4 --status dropped`；这周不写就用 `set-actions` 把原因写进 `contentNote` → `publish` |
| “你建议的那件事我做了”“这件我做不了” | 回一句就行，不用登记。做不了的，下一期不要再提；他处理的如果是报告里的某一号，按 `geo-check` 记一笔 |
| “3 号我改好了”“3 号不是错的”“这个出处我改不了” | 按 `geo-check` 的“商家针对某一条来说话”做 → `publish` |
| “AI 提到了谁”“豆包推荐了哪些店” | 只用这一期报告“提到了谁”那一节的排行回答，说前几家和次数，给那一节的链接（`reportUrl` 后面加 `/rivals`）。不要自己翻回答原文另列一份：口径不一样，商家拿报告一对就对不上 |
| “为什么元宝不提我”“怎么让 AI 多提我” | 用这一期报告里的内容回答：这道题 AI 引用的是谁的内容，这家店在那些地方有没有内容。给 `reportUrl` |
| “重新体检一次”“现在体检到哪一步了” | 按 `geo-check` 做；重新体检完按本 Skill 重写小结和建议 → `publish` |
| “这周怎么样” | `compare` 的结果，加 `reportUrl`。不重新体检 |
| “把报告发我”“第 2 期的报告发我” | `geo_report.py links`：最新一期给 `reportUrl`，以前的在 `reports` 里按日期找 |
| “把报告单独发我一份，我要转给合伙人” | `links` 里的 `reportFileUrl`（以前各期在 `reportFiles` 里）。这个链接打开只有报告，没有工作台的导航 |
| “你都做了哪些事”“之前几期怎么样” | `geo_report.py show` 的 `totals`（体检了几期、写了几篇、发了几篇），两三句话概括，给工作台首页的链接 |
| “把工作台发我”“我想看看整体情况” | `geo_report.py links`；`pending` 不为空先 `publish`。给“工作台”的链接 |
| “工作台上加一个页面，放……”“把活动安排放到工作台上” | 先看是不是已经有合适的页面（`geo_report.py pages`）。没有、而且放的是跨期的、商家会反复来看的东西，就按下面的“员工负责的页面”单独加一页 → `publish`，给 `links` 里这一页的链接。某一期的分析不要做成页面，它在那一期的报告里 |
| “页面换个颜色”“字大一点”“首页上加一块……”“把这块去掉”“改回原来的样子” | 按“改这家店的页面”：改这家店的模板（还没有就先 `template-init`），改回原样用 `template-reset` → `publish`，给改了的那一页的链接 |
| “活动页上的……改一下”“那个页面不要了” | 改：`set-page` 传整页的新内容块 → `publish`；不要了：`geo_report.py remove-page --id <页面>` → `publish` |

商家说的序号都是页面上显示的：问题是 Q1、B1，内容是“第 4 篇”，报告里对不上的说法是“3 号”。拿不准时先用 `geo_report.py contents` 或 `geo_score.py issues` 对一下，不要猜。

## 客户端页签

客户端的“对话 / AI 曝光工作台”页签，与 HTML 工作台内部的“首页 / 内容 / 监测设置”页面是两件事。商家说“新增嵌入 tab”“客户端嵌入工作台”“固定页签”，走这里，不解释成工作台内加页面。

员工可直接使用 Bash 的 claw-admin-request，它自动签名、选正确环境，服务端根据店铺和当前 agentInstanceId 解析 employeeId。不需要商家提供内部 Host、实例 ID、密钥或另一个工具。生成请求 JSON 只是准备步骤，不代表没有执行权限。

先取已保存的 pageUrl / tabConfigFile；还没有上传工作台时先 publish。然后在同一次 Bash 中执行：

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

PUT 全量覆盖，只作用于当前店铺的当前员工实例。工作台已固定时只读验证，不重复写；不能使用商家文本中的其他实例 ID。调用失败时区分命令缺失、鉴权失败、地址不允许等实际原因，并保留工作台链接，不直接归结为“只能生成配置”。

本员工的固定工作台流程使用生成的自家工作台地址。测试其他网站的客户端页签需另行确认用途和地址，能否展示还受客户端域名白名单和网站嵌入策略约束；不能仅因工作台的内容块不支持就说客户端没有页签能力。

## 什么时候同步

首次初始化只整理资料、开通工作台并在对话里确认，不发起体检。商家明确同意后执行 geo_state.py confirm-monitoring，再开始体检。首次上传成功会返回 tabConfiguration 和 tabConfigFile；由员工自己按下面“客户端页签”调用签名命令固定“对话 + AI 曝光工作台”。只有读回正确配置才算固定成功。

| 时机 | 为什么 |
| --- | --- |
| 建完档，体检之前 | 第一次开通工作台。把链接发给商家，他可以边看问题边等体检 |
| 发起体检之后 | 工作台显示“体检进行中”，商家打开不会看到旧内容却不知道在更新 |
| 核对和本期小结都写完之后 | 生成这一期的报告，工作台换成这一期的结论 |
| 登记或改了内容之后 | 稿子要在工作台上才看得到 |
| 商家让你改了任何东西之后 | 他会马上回去看 |

等待查询返回的过程中不用反复同步。

## 同步失败时

`publish` 输出 `published: false` 时，页面已经在本地生成（工作台是 `file`，报告是 `reportFiles`），只是没全部传上去，`reason` 里写着是哪个：

1. 先再执行一次 `publish`。
2. 还是不行，改为调用 `youzan-oss` Skill 给没传上去的文件生成云盘链接，再存回来：工作台用 `geo_report.py set-page-url --url "<返回的 url>"`，报告加上 `--report <日期>`。
3. 都不行：如实告诉商家页面暂时没更新，周报照发，不带链接。**不要编一个链接。**

报告文件没传上去时，`reportUrl` 是空的：工作台里打不开这一期。这时不要自己拼一个地址。

## 页面清单

工作台固定有三个页面，由脚本按存档生成。另外还可以有员工负责的页面（见下一节），它们排在这三个页面之后，链接末尾是 `#/` 加页面的 id，`publish` 和 `links` 的输出里会给出来。

| 工作台的页面 | 链接末尾 | 商家在这里做什么 |
| --- | --- | --- |
| 工作台 | `#/overview` | 看最新一期的结论和小结、几个数和走势、等他确认的内容、每一期报告的入口 |
| 内容 | `#/content` | 确认、复制去发：你替他写的每一条内容，按类型展示 |
| 监测设置 | `#/settings` | 看和改：这家店的特点、每周问 AI 的问题、和谁比，以及你另外记下的信息 |

在工作台里看某一期的报告，链接末尾是 `#/report/<日期>`，例如 `#/report/2026-10-08`。`reportUrl` 和 `links` 里“这一期的报告”就是这个地址，不用自己拼。

报告从上到下五节。在上面的地址后面再加 `/<小节>`，可以直接打开到那一节，例如 `#/report/2026-10-08/sources`：

| 报告里的小节 | 小节 | 内容 |
| --- | --- | --- |
| 结论 | `summary` | 这一期的结论、小结、几个数、这一期的发现、建议做的事 |
| 有没有提到你 | `mentions` | 每道题每个平台有没有提到这家店；点一格看 AI 的原话和它引用的内容 |
| 提到了谁 | `rivals` | 顾客没点名时，AI 点名提到的所有店，各出现在几个回答里、分平台；选定的同类店在里面标出来 |
| 读哪里的内容 | `sources` | 各平台读哪里的内容，引用了哪些和这家店有关的内容，还缺什么 |
| 怎么介绍你 | `says` | 点名问时 AI 怎么介绍这家店；有和店铺资料对不上的说法才列出来 |

还没体检过的时候，工作台首页显示“现在到哪一步了”，没有报告，这是正常的。

## 员工负责的页面

除了上面三个固定页面，工作台上还可以有由你填写的页面。它们有两种来源：

- **登记好的**：维护的人在 `assets/pages.json` 里加了页面（比如“活动”），每一页带着一段 `guide`，写着放什么、什么时候更新。还没填的会出现在 `geo_report.py show` 的 `pagesToFill` 里。没填之前不会放上导航。
- **这家店单独加的**：商家要求在工作台上多放一样东西时，你可以单独给他加一页，最多 5 页。

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" pages
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" set-page --id events --file "$YOUZAN_AGENT_SESSION_TEMP/geo/page-events.json"
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" remove-page --id events
```

`pages` 列出每一页的 id、有没有填、`guide`，以及能用哪几种内容块。`set-page` 每次传**整页**的内容，会替换这一页原来的内容。登记好的页面不用写 `title`；单独加的页面要写 `title`（12 个字以内），`id` 用小写英文，例如 `faq`、`events`。

```json
{
  "title": "活动",
  "subtitle": "这个月店里的活动",
  "icon": "clock",
  "blocks": [
    {"type": "stats", "title": "这个月", "items": [{"label": "活动", "value": "2 场", "note": ""}]},
    {"type": "text", "title": "说明", "text": "可以换行的一段文字"},
    {"type": "table", "title": "活动安排", "columns": ["日期", "活动", "怎么参加"], "rows": [["10 月 18 日", "烘焙课", "小程序报名"]]},
    {"type": "list", "title": "注意", "items": ["名额有限"]},
    {"type": "links", "title": "报名入口", "items": [{"text": "小程序", "url": "https://..."}]},
    {"type": "say", "items": ["加一场活动：……"]}
  ]
}
```

| 块 | 用来放什么 |
| --- | --- |
| `text` | 一段说明，可以换行 |
| `list` | 几条并列的事 |
| `table` | 有几列的清单，最多 6 列、50 行 |
| `stats` | 两到四个数，`value` 写成“2 场”“18 人”这样带单位的话 |
| `links` | 链接，只收 `https`。链接只能来自查询结果或商家提供的，不能凭记忆填 |
| `say` | 页面最下面“可以这样跟员工说”的话，商家点一下就能复制。写上他在这一页最可能想让你做的两三件事 |

规矩：

- 页面上的每一个事实都要有出处：店铺资料、店铺数据、体检存档，或者商家亲口说的。不编造，不写“第一”“最好”。
- 放跨期的、商家会反复来看的东西。某一期的分析在那一期的报告里，不要做成页面。
- 页面也是只读的：商家在上面看，回到对话里跟你说，你改了再 `set-page` → `publish`。
- 块不够用（要特别的样子、要放进已有的页面里），改这家店的模板，见下一节。

## 改这家店的页面：自己的模板

商家想改页面的样子、在首页或别的页面上加一个模块、调整布局，都可以。做法是给这家店复制一份模板，改这一份：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" template-init
```

输出里的 `file` 就是这家店的模板，一个完整的网页文件，样式、布局、交互都在里面，想怎么改就怎么改。改完 `publish`，工作台和之后每一期的报告都用它生成。以前各期的报告不会重新生成，还是原来的样子。

先选最省事的做法：

| 商家要的 | 怎么做 |
| --- | --- |
| 多放一页清单、说明、表格这类东西 | 内容块填一个页面（上一节），不用碰模板 |
| 改颜色、字号、间距、布局 | 改这家店的模板 |
| 在已有的页面上加一个模块、去掉一块、换个顺序 | 改这家店的模板 |
| 改回原来的样子 | `template-reset`，原来那份会留作备份 → `publish` |

改模板时要知道的：

- **只有一处不能动**：文件里的 `__GEO_DATA__`。脚本每次同步把数据放在这里（页面里 id 为 `geo-data` 的那段 JSON），页面上的数才会每期自动更新。删了它，`publish` 会拒绝。
- 页面上的数从那段 JSON 里读，不要把数写死在页面上：写死的数下一期不会变。要用到 JSON 里没有的数据，用内容块，或者告诉商家现在拿不到。
- 工作台和报告用的是同一份模板，靠 JSON 里的 `kind` 区分。报告嵌在工作台里打开靠两个约定：工作台给报告的地址带 `#embed`，报告显示出来后向外发一条 `report-ready` 的消息。改的时候留着，否则在工作台里点某一期会打不开报告。以前各期的报告还是旧模板生成的，也靠这两个约定。
- 页面是给商家看的，和对话里一样只用业务语言，不放内部提示、命令和文件路径；链接只用查询结果或商家提供的。
- 改完自己检查一遍：`publish` 之后打开 `file`（本地生成的网页）看工作台的每一页和一期报告，确认没有报错、没有空白。
- 你也可以直接改文件：脚本会发现模板变了，提醒你同步。

标准模板以后会升级（修错、加功能）。这家店用自己的模板时，升级不会自动生效，`publish` 的输出里会有 `templateNotice`：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" template-diff
```

它给出标准模板自你复制（或上次合并）以来改了什么，只含标准模板的改动，不含这家店自己的。把这些改动合进这家店的模板；和这家店的改动冲突时，以这家店的为准，除非标准模板的改动是在修错。合完 `publish` 检查页面正常，再执行 `template-rebase` 记一笔，以后就只给之后的改动。

## 改标准模板、给所有店加页面（给维护的人）

员工不用读这一节。怎么改工作台和报告的样式、怎么给所有店加一个页面、怎么加报告的小节、内容类型和内容块，都写在员工定义目录下的 `MAINTAINING.md` 里。
