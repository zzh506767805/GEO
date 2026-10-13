---
name: geo-weekly
description: 出每期的体检报告、维护商家的“AI 曝光工作台”、替商家写内容：把体检和核对的结果做成这一期的报告，同步工作台，写本期小结和建议，找内容缺口，按类型写内容（公众号文章、小红书笔记、长文）并登记，给商家发周报和链接；第一份报告出来后问商家要不要开启每周体检，并替他开启。第一次体检和每周体检之后接在 geo-check 之后使用；商家说“开启每周体检”“每周体检停掉”时使用；任何时候数据有变化需要同步页面时使用；商家说“把工作台发我”“把报告发我”“这周怎么样”“你都做了哪些事”“写一篇公众号文章”“写一条小红书笔记”“第 2 篇可以发”“新增嵌入 tab”“固定工作台到客户端”“查看客户端页签”时也使用。
---

# 报告、工作台和内容

商家看这份工作只用打开一个地方：**工作台**，一个固定的链接，一直是最新的。

- 工作台自己只放跨期的东西：最新一期的结论、几个数的走势、每一期报告的入口、你替他写的内容、监测设置。
- **体检报告**每期一份，是一个独立的文件：这一期问了什么、AI 提没提到、提到了谁、读了哪里的内容、怎么介绍这家店。
- 商家看报告不用跳到别的页面：在工作台里点某一期，报告就在右边打开。周报里发的就是这个地址。

页面都是只读的。商家在上面看到什么，回到对话里跟你说，你改数据，再同步。

完整的对应关系见 `references/workbench.md`：你做的事落在哪、你要亲手写哪几样东西、商家从页面上复制过来的话怎么接、怎么填员工负责的页面。**每次用本 Skill 之前先读它**（每周的定时任务通常是一个新的会话，你上次读过的不会留下来）。

替商家写内容的规则在 `references/content-types.md`：内容分类型，稿子跟着类型走，写完必须登记。**每次要写内容之前先读它。**

## 开始前

- 本 Skill 负责整体流程里的第 4、5 步（流程见 `geo-profile`）：第一份报告出来后汇报、问商家要不要开启每周体检；以后每周出周报。`geo_state.py status` 返回 `firstCheckPending` 为 true 时，还在等商家确认第一次体检，这时不出报告、不写内容。

- **每条命令都写全路径**：本 Skill 的脚本是 `python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py"`，店铺资料的脚本是 `python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-profile/scripts/geo_state.py"`。不要先定义 `REPORT=...` 这类变量、在后面的命令里再用：两次命令之间 shell 变量不一定保留，变量丢了命令就会去执行一个空路径。下文表格里写的 `geo_report.py ...`、`geo_state.py ...` 都是全路径的简写。工作目录保持在当前会话工作目录。
- 入参先写成 JSON 文件，放在 `$YOUZAN_AGENT_SESSION_TEMP/geo/` 下，再用 `--file` 传入。

每个命令的输出里都有 `next`，写着下一步该做什么，照着做。

## 同步：只有一条命令

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" publish
```

它重新生成这一期的报告和工作台、传到云盘、保存链接。**不要直接改生成出来的网页文件**，下次同步会被盖掉。商家想改页面的样子、加模块、加页面，按 `references/workbench.md` 的“改这家店的页面”做：内容块填一个页面，或者改这家店自己的页面模板。

- `published: true`：同步成功。`pageUrl` 是工作台，`reportUrl` 是在工作台里打开这一期的报告（发给商家的是它），`links` 是可以直接发给商家的几个链接，`synced` 是这次同步上去的变化。`reportFileUrl` 是报告文件自己的链接，商家要单独转发给别人时才给。
- `firstTime: true`：第一次开通。把 `pageUrl` 发给商家，告诉他以后都在这个链接看。
- `published: false`：没全部传上去，按 `references/workbench.md` 的“同步失败时”处理，不要编链接。

什么时候同步：建完档、发起体检之后、这一期的核对和动作都写完之后、登记或改了内容之后、商家让你改了任何东西之后。拿不准页面是不是最新的，执行 `python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" links`，`pending` 不为空就先同步。

## 第一份报告（整体流程第 4 步）

商家确认后跑完第一次体检（`geo-check` 的算分和核对都做完），按下面“每周出周报”的第 1 到第 5 步做：对比（第一期没有可比的）、找内容缺口、写第一篇内容、写小结和建议、同步。然后给商家发一条消息，六行以内：

1. 一句结论：顾客没点名时，多少个回答里有几个提到了他。
2. AI 点名介绍他时是怎么说的，一两句话。
3. 这一期的报告（`publish` 输出的 `reportUrl`）。
4. 写了的第一篇内容：类型、标题和“内容”页的链接，请他看一眼；没写就说为什么。
5. 问他要不要开启每周体检：“以后每周一上午我自动问一遍、出报告、备好一篇内容，要开启吗？”

报告里有的不要再贴一遍。商家回复后按下一节做。

## 开启每周体检

每周体检由你替商家开启，不是一上岗就有。**只在商家明确同意后开启**，只问一次；商家没回、说再看看，就不开，以后在周报里也不催。

商家同意后，用运行时提供的创建定时任务的能力，建一个这样的任务：

| 项 | 填什么 |
| --- | --- |
| 名称 | 每周 AI 曝光体检 |
| 时间 | 每周一 9:00，时区 Asia/Shanghai（cron：`0 9 * * 1`） |
| 每次触发时对你说的话 | 下面这一段，原样填 |

```text
每周 AI 曝光体检：先执行 geo-profile 的 status。firstCheckPending 为 true 时只提醒商家确认，不体检；schedule 不是 on 时说明商家已经关掉了每周体检，不体检，结束。
否则按 geo-profile 重读店铺资料，再依次用 geo-check 和 geo-weekly 完成本周体检和周报，直接执行，不询问确认。
这一期写的内容先登记到工作台，等商家确认后再发；现在不能替商家写内容时不写，只请商家看一眼工作台的“监测设置”。
结束时用一句话总结：“本周体检完成：Y 个回答里有 X 个提到本店，本周内容：待确认 / 未写。”
```

建好以后读回确认任务存在、时间对，再记下来，并告诉商家每周一上午会收到周报：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-profile/scripts/geo_state.py" set-schedule --status on
```

其他情况：

| 情况 | 做法 |
| --- | --- |
| 商家说先不开 | `set-schedule --status declined`。告诉他想做的时候说一声“开启每周体检”，或者随时说“重新体检” |
| 商家后来说“开启每周体检” | 照上面建任务，`set-schedule --status on` |
| 商家说“每周体检停掉” | 用运行时的能力停掉或删掉这个任务，`set-schedule --status off` |
| 当前环境没有创建定时任务的能力，或者建了读不回来 | `set-schedule --status unavailable`。如实告诉商家暂时开不了自动体检，他想看新结果时说“重新体检”。不要说已经开启 |

## 每周出周报（整体流程第 5 步）

前提：当期已经按 `geo-check` Skill 完成体检（算分和核对都做完）。没做完时先去做。

### 1. 和上一期对比

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" compare
```

`notes` 里的话要照办：第一期没有可比的上一期；没有连续两期同方向变化时，只能写“继续观察”，不能写“上升”或“下降”；数据不全时不和上一期比。

### 2. 找内容缺口

看这一期各平台最常读哪里的内容（`geo-check` 算分输出的 `topSources`），和其中有多少是这家店的（`refs`）。AI 常读、而这家店的内容没被引用的地方，就是缺口。最多写 3 条，每条说清是哪个平台、缺什么。

例如：元宝三分之一的引用来自公众号，而这家店没有公众号文章被引用。

### 3. 这一期的内容

先看现在能不能写：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-profile/scripts/geo_state.py" status
```

- `canWrite` 为 false：**这一期不写**。这说明资料不是从店铺后台读的，还没经过商家确认；在周报里请他看一眼“监测设置”。脚本也不会让你登记。
- `canWrite` 为 true：按 `references/content-types.md` 定类型、选题、写稿。每期主动写 1 篇，最多 2 篇。`pendingConfirm` 为 true 时，`toConfirm` 里列着的那几样信息还没经过商家确认，不能写进稿子。

内容分类型，稿子跟着类型走：

| 类型 | 谁写 | 登记时带什么 |
| --- | --- | --- |
| 公众号文章 `wechat` | 委派 `wechat-writer` 子 Agent，只让它出排版预览 | 标题、排版预览链接 |
| 小红书笔记 `xhs` | 你自己写 | 标题（20 字以内）、正文（1000 字以内）、话题 |
| 长文 `text` | 你自己写 | 标题、全文、建议发在哪 |

写完马上登记，再接着做下一步：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" add-content --file "$YOUZAN_AGENT_SESSION_TEMP/geo/content.json"
```

登记了，工作台“内容”页才有它。不登记，它就只存在于对话里，商家在工作台上看不到，你也没法按序号跟他对。

### 4. 写本期小结、建议，保存

这一步写的东西商家会逐字看到：

- `brief`：本期小结，显示在工作台最上面和这一期报告的开头。两三句话：这一期最重要的一件事，和要商家做什么。只说存档里有的事实。
- `todos`：建议商家做的事，最多三件，列在这一期报告的结论里。它只是建议，不是要打勾的清单。十分钟内能做完的排前面，每件写清做什么、为什么；核对出来的问题，只挑改得动、值得改的那一条。先看第 1 步输出里的 `previousTodos`（上一期建议过什么）：商家做了的不再提，没理会的最多再提一次。
- `gaps`：第 2 步找到的缺口。
- `contentNote`：这一期没有写内容时，写一句原因。写了就留空。

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" set-actions --file "$YOUZAN_AGENT_SESSION_TEMP/geo/actions.json"
```

```json
{
  "brief": "",
  "todos": [{"text": "", "why": ""}],
  "gaps": [{"where": "公众号", "note": ""}],
  "contentNote": ""
}
```

以后只改其中一样时，只传那一样，其余保持不变。

另外看一眼 `geo_report.py show` 输出里有没有 `pagesToFill`：那是工作台上登记了、还没填的页面。有的话执行 `geo_report.py pages` 看每一页放什么，按 `references/workbench.md` 的“员工负责的页面”填好。以前填过的页面，内容过时了也在这一步更新。

### 5. 同步

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" publish
```

这一步会生成这一期的报告，并把工作台换成这一期的结论。`reportUrl` 是在工作台里打开这一期报告的地址。

输出里有 `warnings` 时照着处理。最常见的两条：“这一期既没有登记内容，也没有写没写的原因”：内容写了就补登记，没写就补原因；“已经登记了内容，但 contentNote 里还写着没写的原因”：用 `set-actions` 传 `{"contentNote": ""}` 清掉，并看看小结要不要跟着改。

### 6. 给商家发周报

四行以内。明细都在报告里，不要贴在对话里：

1. 一句结论：顾客没点名时，多少个回答提到了他；和上一期怎么比，按第 1 步的 `notes` 说。
2. 这一期最值得他知道的一件事，一两句话。
3. 这一期的报告：`reportUrl`。
4. 要他做的一件事：有内容等他确认，就给工作台“内容”页的链接；有你另外记下的信息等他确认，就给“监测设置”的链接；都没有，就说建议里的第一件。

每周定时任务触发的这一轮结束时，再按任务里的要求输出那一句总结。

## 客户端页签

“新增嵌入 tab”“客户端里固定工作台”是管理客户端页签，不是给 HTML 工作台加页面。由员工自己通过 Bash 调 claw-admin-request，按 references/workbench.md 的“客户端页签”执行和读回验证。没有尝试实际命令前，不要说没有能力或需要平台代操作。

## 商家平时来问

商家的话很多是从工作台上点“可以这样跟员工说”复制过来的，会带着页面上的编号（Q3、第 4 篇、3 号）。**完整的对照表只有一份，在 `references/workbench.md` 的“商家会从页面上复制这些话”**，照那张表做。

涉及问题、同类店、账号的话按 `geo-profile` 处理，涉及体检和核对结果的话按 `geo-check` 处理，处理完都要回到这里 `publish`。

## 不可违反的规则

- 数字只用脚本输出里的。
- 不承诺 AI 一定推荐、排第几或多久见效。
- 内容只写店铺资料里有的事实和店铺数据里查得到的内容；你另外记下、商家还没确认的信息不写进稿子。细则见 `references/content-types.md`。
- 每一篇替商家写的内容都要登记到工作台，不管是哪种类型、是每周主动写的还是商家临时要的。不要只在对话里给。
- 存草稿和发布之前，必须得到商家对这一篇的明确确认。
- 工作台和报告的链接只用脚本输出里的，逐字照抄；没有拿到链接就如实说，不要编。
- 不向商家展示脚本、命令、文件路径和内部报错。
