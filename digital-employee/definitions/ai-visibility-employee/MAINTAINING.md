# 维护和扩展 AI 曝光专员

这份是给改这个数字员工的人看的，员工自己不读。想改流程、加页面、加内容类型之前先看这里：大多数改动只用改一两个文件，不用碰模板和脚本。

## 东西都放在哪

| 层 | 文件 | 管什么 | 改它要不要动代码 |
| --- | --- | --- | --- |
| 角色和红线 | `prompt.md` | 员工是谁、什么能做什么不能做、对商家怎么说话、哪句话找哪个 Skill。每次对话都加载，Skill 里不再重复这里的规矩 | 不用 |
| 流程 | `skills/*/SKILL.md` | 每件事按什么顺序做、每一步跑哪个命令 | 不用 |
| 细则 | `skills/*/references/*.md` | 怎么出题、怎么核对、各类内容怎么写、页面上的东西从哪来 | 不用 |
| 每周体检 | `skills/geo-weekly/SKILL.md` 的“开启每周体检” | 商家同意后员工替他建的定时任务：每周几点、触发时对员工说什么 | 不用 |
| 页面清单 | `skills/geo-workbench/assets/pages.json` | 工作台导航里有哪些页面、什么顺序 | 不用 |
| 护栏 | `skills/*/scripts/*.py` | 数据格式、硬性的上限和顺序、给员工的 `next` 提示 | 要 |
| 页面样式 | `skills/geo-workbench/assets/page.html` | 标准模板：工作台和报告长什么样 | 要 |
| 每家店自己的页面 | `<会话工作区>/ai-visibility-employee/template/page.html` | 员工按商家的意思改出来的模板，有它就不用标准模板 | 员工自己改 |

流程写在文档里，脚本只管“错了就拦住”的那几件事。改流程时先看下面这张表：表里的规矩由脚本卡住，只改文档改不掉；其余规矩都只写在文档里，改文档就行。

| 脚本卡住的规矩 | 在哪 |
| --- | --- |
| 先问不带店名的问题，再问带店名的 | `geo_run.py` 的 `cmd_start` |
| 不带店名的问题里不能有店名；问题数量 6–12 加 1–3 | `geo_state.py` 的 `normalize_questions`、`OPEN_RANGE`、`BRAND_RANGE` |
| 资料不是后台读的、商家也没确认时，不能登记内容 | `geo_common.py` 的 `confirm_state` |
| 每期主动写的内容最多 2 篇 | `geo_report.py` 的 `WEEKLY_CONTENT_CAP` |
| 体检做到一半断掉时回到哪一步；写完小结后重新算分、数变了要重写：status 和 publish 按这一期做到哪了给 next 和提醒 | `geo_common.py` 的 `period_stage`、`summary_fingerprint` |
| 每种内容的标题、正文长度 | `geo_report.py` 的 `CONTENT_TYPES` |
| 核对时出处链接必须来自回答自己的引用 | `geo_score.py` 的 `cmd_set_judgement` |
| 读全文写回的店名必须出现在那个回答的原文里；没点名的回答一个都不能漏，漏了“提到了谁”不出数；复核的引用必须是这一期出现过的 | `geo_score.py` 的 `cmd_set_reading`、`count_shops` |
| 发现最多 5 条，每条至少一句能在原文里逐字找到的原话 | `geo_score.py` 的 `cmd_set_findings`、`FINDINGS_CAP` |
| 存草稿、记发布之前必须先确认 | `geo_report.py` 的 `cmd_mark_content` |
| 资料还不能写内容时不能登记官网；没登记过测试版，不能登记正式上线 | `geo_report.py` 的 `cmd_set_site` |
| 一家店单独加的页面最多 5 个；内容块的格式 | `geo_report.py` 的 `CUSTOM_PAGE_CAP`、`normalize_blocks` |

## 想改什么 → 改哪里

### 改每周的流程

例如“每周先写内容再出报告”“周报多加一行”“改成两周一次”。

1. 改 `skills/geo-weekly/SKILL.md` 的“每周出周报”（体检那一段在 `skills/geo-check/SKILL.md`）。
2. 触发时间、触发时的那段话改 `skills/geo-weekly/SKILL.md` 的“开启每周体检”。只对之后新建的任务生效，已经建好的任务不会跟着变。
3. 搜一下脚本里的 `next` 文案（`grep -n '"next"' skills/*/scripts/*.py`）。员工会照着 `next` 做，文档改了顺序而 `next` 还指旧的下一步，新员工会跟着 `next` 走。
4. 新的流程碰到上面那张表里的规矩时，才需要改脚本。

### 给所有店的工作台加一个页面

不用写代码。在 `skills/geo-workbench/assets/pages.json` 里加一项：

```json
{"id": "events", "title": "活动", "icon": "clock", "subtitle": "这个月店里的活动",
 "guide": "放这个月店里的活动：时间、内容、怎么参加。每周出周报时看一眼，有新活动就更新"}
```

- `id`：小写英文，2 到 24 个字符，不能用 `report`、`embed`。它也是链接的末尾（`#/events`）。
- `guide`：写给员工看的。这一页放什么、数据从哪来、什么时候更新。员工执行 `geo_report.py pages` 时会看到它，`show` 也会提醒“这几页还没填”。
- 页面的内容由员工用 `geo_report.py set-page` 填，用的是固定的几种内容块（文字、列表、表格、几个数、链接、可以复制的话），怎么填写在 `skills/geo-workbench/references/pages.md` 的“员工负责的页面”。
- 员工还没填的页面不会出现在导航里。

只有内容块拼不出来的页面（要画图、要从体检存档里算数）才需要写代码：在 `pages.json` 里把它标成 `"builtin": true`，在 `page.html` 的 `PAGES` 里加一个画它的函数，在 `geo_report.py` 的 `workbench_data` 里准备它要的数据。测试会核对每个内置页面在模板里都有画它的函数。

去掉一个页面：从 `pages.json` 里删掉那一项。员工以前填的内容还留在存档里，不显示。

### 加一种内容块

在 `geo_report.py` 的 `BLOCK_TYPES` 和 `normalize_blocks` 里加上这种块的格式和检查，在 `page.html` 的 `customBlock` 里加上怎么画，在 `skills/geo-workbench/references/pages.md` 的块表里加一行。

### 加一种内容类型（比如抖音脚本）

`geo_report.py` 的 `CONTENT_TYPES` 里加一行规格（标题上限、正文上下限、要不要话题、成品是不是带排版的页面），`skills/geo-content/references/writing.md` 里加一节写法、登记字段、确认后怎么交，`skills/geo-content/SKILL.md` 的类型表和“定类型”里各加一行。工作台的“内容”页按类型自动展示，不用改模板。

### 官网

官网由员工调用平台的“应用”能力做，流程在 `skills/geo-site/SKILL.md`。SKILL.md 本身是索引，细则在它的 `references/` 下：

- 长什么样：`design-index.md` 写三个设计参考各适合什么店、怎么挑，员工挑一个，再读对应的 `design-qiaomu.md`、`design-frontend.md`、`design-uiux.md`。这三份是从 GitHub 上的设计 Skill 收的做法要点，来源和版本记在 `design-index.md` 末尾；要加或换参考，在那张表和“怎么挑”里一起改。三种方向的效果样例在仓库根目录 `官网对比/`。
- 让搜索引擎和 AI 读得到：`seo-geo.md`，包括交给“应用”能力的页面要求、测试版的检查命令、上线以后的事。规则来自 Google 的 AI 优化指南和几个开源 SEO/GEO Skill，来源也记在文件末尾，规则变了改这一份。

脚本只记官网在哪、到了哪一步：

- 记录在 `<数据目录>/profile/site.json`，`geo_report.py set-site` 写，`site-brief` 把做官网要用的资料一次给全。
- “官网过时了”看 `geo_common.py` 的 `SITE_PARTS`（店名和品类、门店、招牌商品、怎么买）：做测试版那一刻的这几样和现在的店铺资料不一样，就算过时。想多比一样，在 `site_facts` 和 `SITE_PARTS` 里加，三份 `geo_common.py` 一起改。
- AI 引用了已上线的官网算本店自己的内容：`geo_score.py` 的 `_with_site` 和 `classify_ref`，按正式链接的前缀认，绑了独立域名的按域名认。
- 工作台上是“内容”页最上面一块：`page.html` 的 `siteCard`，数据是 `workbench_data` 里的 `site`。

### 加报告的小节

`geo_report.py` 的 `REPORT_SECTIONS`、`page.html` 的 `SECTIONS` 和画这一节的函数、`skills/geo-workbench/SKILL.md` 的小节表，四处一起改，测试会核对。注意下面“报告嵌在工作台里”的约定。

### 加或换 AI 平台

`geo_common.py` 的 `PROVIDERS` 和 `PROVIDER_NAMES`。这个文件在三个技能目录里各有一份，三份要一样（测试会查）。`prompt.md` 和几个 SKILL.md 里写着平台名字的地方一起改。

### 调上限和数量

| 想调的 | 在哪 |
| --- | --- |
| 每期主动写几篇 | `geo_report.py` 的 `WEEKLY_CONTENT_CAP`，同时改 `skills/geo-content/SKILL.md`、`prompt.md`、上面“脚本卡住的规矩”表里写的数，以及 `tests/run_tests.py` 里“第三篇被拒”那条检查 |
| 一家店能单独加几个页面 | `geo_report.py` 的 `CUSTOM_PAGE_CAP` |
| 问题的数量 | `geo_state.py` 的 `OPEN_RANGE`、`BRAND_RANGE`、`RECOMMENDED`，同时改 `skills/geo-profile/SKILL.md`（“出题”和“判断是本地门店还是电商”里写的 10 道、2 道）和 `references/segment-*.md` 的配比表 |
| 改了题只重问几道时，最近一期多旧就不往里补 | `geo_run.py` 的 `STALE_PERIOD_DAYS` |
| 一条查询等多久算缺失 | `geo_run.py` 的 `DEADLINE_SECONDS` |
| 工作台保留几期 | `geo_report.py` 的 `PERIOD_LIMIT` |

### 每家店自己的页面

员工可以按商家的意思改页面，什么都能改：`geo_report.py template-init` 把标准模板复制到这家店的数据目录，员工改这一份，以后同步都用它。数据还是脚本放进去的（模板里唯一不能删的是 `__GEO_DATA__`）。员工怎么做写在 `skills/geo-workbench/references/pages.md` 的“改这家店的页面”。

这对改标准模板有两个影响：

- **标准模板的改动不会自动到达这些店。** 员工在 `publish` 的输出里看到 `templateNotice`，用 `template-diff` 拿到标准模板自他复制以来的增量，自己合进去。所以改标准模板时尽量一次只改一件事、改动集中，增量才好合；数据的格式（`geo-data` 里的字段）只加不改，改了字段名，改过模板的店会读不到。
- **存量不处理**：以前各期的报告不重新生成；改过模板的店，旧改动和标准模板的差异也不回头去对齐。

### 改样式

标准模板只改 `assets/page.html`，工作台和报告共用这一个模板，数据里的 `kind` 决定出哪一种。

- 颜色只用文件开头定义的变量，取值和有赞龙虾客户端一致，深色模式有另一套值。
- 不引用任何外部资源。数据只放在 `<script type="application/json" id="geo-data">` 里，页面上的文字一律用 `textContent` 写入。
- 模板里动态拼出来的类名要加前缀，免得和布局用的类名撞上。
- 模板不要挪到 `references/` 或 `scripts/` 下面。
- 报告嵌在工作台里靠两个约定：工作台给报告的地址带 `#embed`（报告据此不显示自己的标题）；报告显示出来以后向外发一条 `report-ready` 的消息（工作台等不到，就在上面给一个“单独打开”的入口）。**以前各期的报告文件生成后不再更新，所以这两个约定以后只能加、不能改**，否则旧报告在新工作台里会显示不对。
- 只想看样式：`geo_report.py render --data <页面数据.json> --out <输出.html>`。数据样例是 `tests/fixtures/page-data.demo.json`（工作台）和 `tests/fixtures/report-data.demo.json`（报告），都是虚构的多期数据，页面上会标“演示数据”。

### 改商家在报告上看到的说明

脚本里 `readerNotes` 和报告里追加的 `notes` 会原样出现在商家的报告上。它们要用对商家说话的口吻，称呼用“你”，不能写给员工看的提示；给员工的提示放在命令输出的 `notes` 和 `next` 里。测试会查。

## 改完怎么验证

```bash
python3 tests/run_tests.py
```

不联网，十几秒跑完。它用模拟的“问 AI”和云盘把建档、体检、核对、周报、内容、页面整个走一遍，再把生成的每个页面在一个假的浏览器环境里渲染一遍，查有没有报错、有没有把 `undefined` 显示给商家。

改了文档里的流程，最好再用一个没看过这些文件的新会话，照 SKILL.md 从头走一遍。新员工只看得到文档和命令输出，文档和 `next` 说法不一致的地方，它多半会跟着 `next` 走。
