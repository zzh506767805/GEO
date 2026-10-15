# 员工负责的页面和这家店自己的模板

## 员工负责的页面

除了工作台固定的三个页面（首页、内容、监测设置），工作台上还可以有由你填写的页面。它们有两种来源：

- **登记好的**：维护的人在 `assets/pages.json` 里加了页面（比如“活动”），每一页带着一段 `guide`，写着放什么、什么时候更新。还没填的会出现在 `geo_report.py show` 的 `pagesToFill` 里。没填之前不会放上导航。
- **这家店单独加的**：商家要求在工作台上多放一样东西时，你可以单独给他加一页，最多 5 页。

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" pages
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" set-page --id events --file "$YOUZAN_AGENT_SESSION_TEMP/geo/page-events.json"
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" remove-page --id events
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
| `say` | 顶栏右上角“跟员工说”里的话，商家点开、点一句就能复制。写上他在这一页最可能想让你做的两三件事 |

规矩：

- 页面上的每一个事实都要有出处：店铺资料、店铺数据、体检存档，或者商家亲口说的。不编造，不写“第一”“最好”。
- 放跨期的、商家会反复来看的东西。某一期的分析在那一期的报告里，不要做成页面。
- 页面也是只读的：商家在上面看，回到对话里跟你说，你改了再 `set-page` → `publish`。
- 块不够用（要特别的样子、要放进已有的页面里），改这家店的模板，见下面的“改这家店的页面”。

## 改这家店的页面：自己的模板

商家想改页面的样子、在首页或别的页面上加一个模块、调整布局，都可以。做法是给这家店复制一份模板，改这一份：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" template-init
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
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" template-diff
```

它给出标准模板自你复制（或上次合并）以来改了什么，只含标准模板的改动，不含这家店自己的。把这些改动合进这家店的模板；和这家店的改动冲突时，以这家店的为准，除非标准模板的改动是在修错。合完 `publish` 检查页面正常，再执行 `template-rebase` 记一笔，以后就只给之后的改动。
