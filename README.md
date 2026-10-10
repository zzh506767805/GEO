# AI 曝光专员（GEO 数字员工）第一版

版本 0.1.0 · 2026-10-09

这个目录里有四样东西：

| 路径 | 是什么 |
| --- | --- |
| `方案.md` | 产品方案 |
| `digital-employee/` | 技能包，结构和 `yzclaw/digital-employee` 仓库一致，可以整体拷进去 |
| `示例/` | 商家看到的工作台（麦的日尝 10 月 8 日的真实存档）和七张截图 |
| `tests/` | 本地测试，不联网 |

**现状：脚本在本机测过，还没有在真实的 Pod 里跑过。** 详见 `方案.md` 的“验证情况”。

## 先看效果

用浏览器打开 `示例/工作台-麦的日尝.html`。这就是商家拿到的工作台：左边导航，7 个页面。这家店的档案没有经过商家确认，按规则不能替它写内容，所以“内容”页是空的。

- 数据是 10 月 8 日那次真实体检的存档，按员工的正常流程重跑出来的（建档、开通工作台、体检、算分、判读、写小结和待办、同步）。只有一期，所以没有趋势。
- 店铺档案是从公开信息整理的，没有经过商家确认，页面上标着“档案待确认”；四类顾客的依据标的是“推测”。
- 示例里没有编的数据。多期才有的状态（趋势、上一期对比、待办打勾、三种类型的内容）用一份虚构的剧本做回归测试，见下面的 `make_demo.py`，它生成的页面顶部标着“演示数据”，不要对外用。

## 工作台和技能是怎么连起来的

员工每做一步，结果落在工作台的哪一页是定死的；数据一变，脚本就记下“工作台待同步”；同步只有一条命令。

```
建档 ──→ 店铺档案、顾客与问题库          ┐
体检 ──→ 首页、提及分析、内容来源          │  数据一变，脚本记一笔“待同步”
判读 ──→ 说错的信息、AI 怎么介绍你        ├─→ geo_report.py publish ─→ 生成网页 → 传云盘 → 固定链接
小结、待办 ──→ 首页                       │      返回 7 个页面的链接、这次同步了什么
写内容（按类型登记）──→ 内容              │
商家说“3 号我改好了”──→ 已处理           ┘
```

- 说明在 `geo-weekly/references/workbench.md`：每一步落在哪一页、员工要亲手写哪五样东西、商家从工作台上复制过来的话怎么接、什么时候同步、传不上去怎么办。
- `geo_state.py status`、`geo_report.py links`、`geo_report.py show` 都会说工作台是不是最新的（`pending` 是还没同步上去的变化）。
- 商家在工作台上看到的编号员工都对得上：问题是 Q3（`q03`），说错的信息是“3 号”（`mark-issue --no 3`），待办是“第 1 件”（`mark-todo --no 1`），内容是“第 4 篇”（`mark-content --no 4`）。

## 内容按类型登记

替商家写的东西分类型，稿子跟着类型走。公众号文章和小红书笔记不是同一份文字换个排版。

| 类型 | `type` | 标题上限 | 正文 | 登记时必须带 | 工作台上怎么展示 |
| --- | --- | --- | --- | --- | --- |
| 公众号文章 | `wechat` | 64 字 | 可以不带 | 排版预览链接 | “看排版预览”按钮；带了文字版就多一个“看文字版” |
| 小红书笔记 | `xhs` | 20 字 | 30 到 1000 字 | 正文 | 标题、正文、话题，一起复制 |
| 长文 | `text` | 60 字 | 80 到 6000 字 | 正文 | 全文，可复制 |

- 规格在 `geo_report.py` 的 `CONTENT_TYPES`，写法在 `geo-weekly/references/content-types.md`。加一种类型只动这两处。
- 账本在 `<数据目录>/profile/contents.json`。公共字段所有类型一样（序号、类型、标题、状态、放到了哪）；`previewUrl` 和 `ref` 是给“成品是带排版的页面”的类型用的，脚本不解析公众号的 HTML，也不认识公众号技能。
- 脚本卡住的规则：档案没确认不能登记；每期主动写的最多 2 篇；超出规格退回、不截断；没确认不能记成已放进草稿箱；确认后改稿变回等确认；两条内容不能共用一个预览链接。
- 每期收尾同步时，档案已确认却既没登记内容、也没写没写的原因，`publish` 会给 `warnings`。

## 本地测试

需要 Python 3.11 以上。有 node 时会多跑一项“工作台逐页渲染”检查。

```bash
python3 tests/run_tests.py
```

共 106 项。它用 `mock_ai_query.py` 模拟“问 AI”、用 `mock_upload.py` 模拟云盘上传，跑通全过程，并逐步核对工作台的同步状态和内容按类型登记的规则。

如果上一级目录里有 `GEO实测/2026-10-08-麦的日尝/结果`，还会回放那次真实存档，核对算出来的数，并重新生成 `示例/工作台-麦的日尝.html`。

```bash
python3 tests/make_demo.py [输出的网页路径]
```

多期回归：按 `demo_scenario.py` 里一家虚构面包店的剧本连跑五期，更新 `tests/fixtures/page-data.demo.json`。给了路径时再写一份网页，方便看多期的样子。**这是测试数据，不是示例。**

```bash
node tests/page_smoke.cjs <工作台.html>
```

不用浏览器，把工作台的每个页面、每一期都渲染一遍，再把能点的都点一遍；有报错或者页面上出现 `undefined` 这类空值就失败。它查不了样式和排版。

## 装进仓库

1. 把 `digital-employee/definitions/ai-visibility-employee/` 和 `digital-employee/tasks/timer/geo-weekly-check.yaml` 拷到 `yzclaw/digital-employee` 仓库的同名位置。
2. 提交说明里带上 `[sync-tasks:geo-weekly-check]`，任务模板会自动同步到后端。
3. `youzan-business-assistant` 更新 `employees` 子模块指针，发版。
4. 运营后台建员工档案，把任务模板关联到员工，加白名单。

运行时主干的员工定义加载器已经能加载这份定义（目录名、字段、技能名都符合校验）。

## 在 Pod 里联调要看的事

按顺序：

1. **问 AI 能不能调通**。`geo_run.py` 调的是 `$YOUZAN_GLOBAL_SKILLS_PATH/youzan-ai-search/scripts/ai-data-query.mjs` 的 `run` 和 `get` 两个命令，参数是 `provider`、`question`、`concurrency`。Pod 里要有 `AI_DATA_API_KEY` 和 `CLAW_TYPE` 两个环境变量，测试店（43729418）目前没有。
2. **工作台能不能同步上去**。`geo_report.py publish` 生成 `<会话工作区>/ai-visibility-employee/pages/ai-visibility.html`，然后直接调 `$YOUZAN_GLOBAL_SKILLS_PATH/youzan-oss/scripts/upload.js --file-path <文件>`，取输出里的 `url`。要确认三件事：脚本里这样调行不行；重复上传链接是否不变；网页会不会被上传前的安全检查拦下。调不通时脚本会返回 `published: false`，说明里写了退路（员工改为调用 `youzan-oss` 技能，再执行 `set-page-url`）。
3. **首次初始化**。提示词里写的是“数字员工首次初始化时，必须立即调用 geo-profile”，和客户运营专员的写法一样。触发指令从哪发出来，没有在代码里找到，要确认。
4. **员工会不会照着同步**。看三个时点工作台有没有更新：建完档、发起体检后、这一期做完后。再看周报里给的是不是对应页面的链接。
5. **员工会不会老实等**。一轮体检要 5 到 10 分钟，`wait` 每次最多等 90 秒。看员工会不会中途放弃、提交问题反馈或改用别的办法。
6. **商家的话接不接得住**。从工作台上复制几句发给员工：“确认档案”“1 号我改好了”“第 1 件我做完了”“把 Q3 换一个问法”“第 1 篇可以发”，看它有没有改对数据并同步工作台。
7. **写内容**。看四件事：员工写之前有没有先定类型；写完有没有先登记再告诉商家（对话里不贴全文）；公众号文章是不是委派给 `wechat-writer`、只出预览、按序号起了文件名（它默认每次写 `output/article.html` 和 `output/preview.html`，新的会盖掉旧的）；商家在对话里临时说“写一条小红书笔记”，工作台的“内容”页有没有多出一条。

运行时的命令沙箱：技能脚本在沙箱里执行，出站域名不限，只能写会话工作区、会话临时目录和 `/tmp`。这套脚本只往 `<会话工作区>/ai-visibility-employee/` 里写。

## 脚本命令

脚本都要用绝对路径执行，入参写成 JSON 文件后用 `--file` 传。每个命令输出一段 JSON，`ok: false` 时 `error` 是原因，退出码是 2。输出里的 `next` 是下一步该做什么。

```
geo_state.py   status | init | show | set-facts | set-questions | set-rivals | set-assets | confirm
geo_run.py     start --phase open|brand [--only q01,q03] [--retry] | wait [--max-seconds 90] | status
geo_score.py   score | brand-digest | set-judgement | issues | mark-issue --no N --status done|dismissed|open
geo_report.py  publish | links | show | compare | set-actions | mark-todo --no N
               add-content | contents [--no N] | mark-content [--no N] [--status S] [--channel 去向] [--ref 凭据]
               build（只在本地生成）| set-page-url | render --data <json> --out <html>
```

测试用的环境变量：

| 变量 | 作用 |
| --- | --- |
| `GEO_DATA_ROOT` | 数据目录。不设时用 `$YOUZAN_AGENT_SESSION_WORKSPACE/ai-visibility-employee` |
| `GEO_AI_QUERY_CMD` | 把问 AI 的查询脚本换成别的命令，测试时指向模拟脚本 |
| `GEO_UPLOAD_CMD` | 把云盘上传脚本换成别的命令，测试时指向模拟脚本 |
| `GEO_DEADLINE_SECONDS` | 一段查询最长等多久，默认 900 |
| `GEO_POLL_INTERVAL` | 两次取结果之间隔多久，默认 15 秒 |
| `GEO_FAKE_NOW` | 指定“现在”的时间，只给测试用 |
| `GEO_DEMO` | 设了以后页面顶部标“演示数据”，只给多期回归用 |

## 改代码时要知道的

- `geo_common.py` 在三个技能目录里各有一份，内容必须完全一样。技能目录是独立安装的只读目录，不能跨目录 import。测试会校验三份一致。
- 改了数据的命令要调 `gc.mark_changed("变了什么")`，否则工作台不会被提醒同步。
- 工作台的样式、图标、交互全在 `geo-weekly/assets/page.html` 一个文件里。现在是 7 个页面。**加页面之前先问：商家要在上面做什么决定，或者它是哪个数字的证据。** 答不上来就放进现有页面。待办、历次体检、做过的工作都在首页，同类店对比在提及分析里，就是这么并掉的。
- 增减页面时，`geo_report.py` 的 `PAGES`、模板里的导航、`workbench.md` 里的页面表要一起改，测试会核对三处完全一致。
- 模板里动态拼出来的类名要加前缀。踩过两次：条形图的 `.bar` 和顶栏撞名；时间线图标直接用事件类型当类名，`content` 和页面容器撞名。这类问题逐页渲染检查抓不到，要看截图。
- 颜色用的是龙虾客户端的主题变量；页面里的龙虾形象取自客户端仓库的应用图标（`src/renderer/src/assets/images/app-icon.png`，缩到 88 像素后内嵌）。
- 网页模板放在 `geo-weekly/assets/`，不要挪到 `references/` 或 `scripts/`。运行时的安全检查会给内置技能这两个目录里的内容做指纹，照着模板生成的网页可能被当成泄露技能内容。
- 网页里的数据放在 `<script type="application/json">` 里，不要拼进脚本。云盘上传前会检查内联脚本的语法。
- 网页文件名用英文，而且位置固定。云盘按文件在工作区里的位置给链接，换了位置链接就变了。
- 日期一律按北京时间算，用 `geo_common.now()`。

## 已知的不足

- 工作台是只读的，确认、打勾都要回到对话里说。要做成能直接点，得等员工详情页的页签支持给员工发消息。
- 历史各期只保留数字和逐题的圆点，回答原文只有最新一期能点开看；内容的稿子只带最近 10 条，更早的只留标题和状态。
- 商家在对话里临时要的内容，员工没登记的话脚本发现不了，只靠规则约束。
- 小红书笔记的写法只有几条基本规格；抖音文案、视频脚本还没有对应的类型。
- 记忆痕迹只能认出明说“你之前问过”的回答。
- 抖音的引用不带作者，只有在档案里登记过作品编号的视频才能认出是本店的。
- “事实一致率”没有做成数字，只有“说错的信息”清单。
- 每家店的周任务都在周一 9 点触发，没有错峰。
- 真实数据只有一期，多期的展示只用虚构数据测过。
