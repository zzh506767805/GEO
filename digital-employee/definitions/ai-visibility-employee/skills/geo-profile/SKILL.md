---
name: geo-profile
description: 数字员工首次初始化时必须调用。商家要求查看或修改监测设置（每周问 AI 的问题、顾客类型、同类店、他的公众号和抖音号、写内容的要求）时也使用，包括“把 Q3 换一个问法”“加一道题”“同类店换成……”“我的公众号叫……”“确认”这类话。读取店铺资料，判断是本地门店还是电商，归纳顾客类型、出好问题，开通工作台，跑第一次体检。
---

# 建档和监测设置

本 Skill 负责两样东西：

- **店铺资料**：从店铺后台读来的店名、门店、营业时间、商品、小程序。体检时拿它核对 AI 说得对不对，替商家写内容也只用它里面的事实。它是你的工作底稿，**不在工作台上展示**：这些是商家自己在后台维护的，抄一份给他看只会抄不全。
- **监测设置**：每周替商家问 AI 的问题、这些问题是替哪几类顾客问的、和哪几家同类店比，以及你另外记下的、店铺后台里没有的几样信息。商家在工作台的“监测设置”页上看得到。

监测设置每改一次，都要同步一次工作台（同步的命令在 `geo-weekly` Skill 里，下面用 `publish` 指代）：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" publish
```

## 开始前

- 脚本一律用绝对路径执行，工作目录保持在当前会话工作目录：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-profile/scripts/geo_state.py" status
```

- 入参先写成 JSON 文件，放在会话临时目录 `$YOUZAN_AGENT_SESSION_TEMP/geo/` 下，再用 `--file` 传入。不要把 JSON 写在命令行里。
- 先执行 `status`。返回 `exists: false` 走“首次建档”，否则走“修改”。
- `status` 里的 `workbench` 是工作台的情况：`pending` 不为空，说明有变化还没同步上去，做完手上的事要 `publish`。
- 脚本返回 `ok: false` 时，`error` 是可以直接转述的原因；按原因修正后重试，不要绕过脚本直接改存档文件。

## 哪些要商家确认，哪些不用

| 信息 | 从哪来 | 要不要商家确认 |
| --- | --- | --- |
| 店名、门店、营业时间、商品、小程序 | 店铺后台 | **不用**。那是他自己填的，以后台为准 |
| 别的叫法、他的公众号、他的抖音号、后台里没有的门店（比如已经关掉的旧店） | 你搜到的或推断的 | **要**。可能认错 |
| 顾客类型、问题、同类店 | 你归纳的 | 不用确认，但他随时可以改 |

- 从店铺后台读到的资料，`set-facts` 时写 `"from": "backend"`。这样不用等商家确认，就可以替他写内容。
- 查不到店铺后台、资料是从公开信息里整理的，写 `"from": "public"`。这时整份资料都要商家看过才算数，确认之前脚本不让你登记内容。
- `status` 里的 `pendingConfirm` 为 true，说明有你另外记下的信息还没经过商家确认，`toConfirm` 里列着具体是哪几样。没确认的信息不能写进内容。

## 首次建档

顺序不能变：先读资料、出题，开通工作台，再体检。不要先问商家一堆问题再干活。

### 1. 判断客群类型

通过 `youzan-data-analyst` Skill 查店铺名称、主营类目、店铺类型、门店列表和配送方式。

- 有线下门店、顾客主要到店或同城下单：`local`（本地门店）。
- 没有门店，或主要全国发货：`ecom`（电商）。
- 两样都有：按主要收入来源选一套，再从另一套里补 2 个问题。

然后只读对应的一份说明：`references/segment-local.md` 或 `references/segment-ecom.md`。它规定了资料里多记什么、怎么出题。

### 2. 读店铺资料

能从店铺后台查到的不要问商家。查不到的字段留空，**禁止推测或编造**；留空不会出错，写错会让后面的核对全错。

| 字段 | 内容 | 来源 |
| --- | --- | --- |
| `brand` | 店名、品类、城市；`aliases` 是别的叫法（英文名、简称），属于要确认的 | 店铺后台；别名是你推断的 |
| `stores` | 每家门店的名称、地址、营业时间、电话、状态（在营 / 已搬迁 / 已关闭） | 后台的门店 `source` 写“有赞后台”；从别处看到的写实际来源 |
| `products` | 核心商品的名称、规格、价格带、产地（电商必填，最多 10 个） | 店铺后台 |
| `buyEntry` | 小程序名称、店铺链接 | 店铺后台 |
| `channels` | 他的公众号、抖音号、他发过的内容的编号 | 第 5 步查到的，属于要确认的 |
| `writingRules` | 口吻、不用的词、每篇必须带的信息 | 商家说过才填 |
| `audience` | 顾客类型，见第 3 步 | 评价、订单等 |

### 3. 归纳顾客类型

写 2 到 4 类顾客。这一步决定问题出得准不准：问题要替真实的顾客问，不是替店铺问。

依据按这个顺序找，前面的找得到就不用后面的：

1. 商品评价（通过 `youzan-item` Skill 查评价）：顾客自己写的场合和顾虑，例如“给孩子当早餐”“送长辈”“怕太甜”。
2. 订单和热销商品：谁在买、买什么、怎么收货（到店、同城、快递）。
3. 客服对话（当前环境查得到时）：顾客下单前反复问的问题。
4. 商家自己说过的。
5. 以上都没有时才推测。

每一类写五项：

- `name`：这类人的叫法，12 个字以内，例如“附近的上班族”。
- `who`：他们是谁。
- `scene`：什么时候会去问 AI。
- `worry`：最在意或最担心什么。
- `basis`：依据，写“商品评价”“订单”“客服对话”“商家说明”或“推测”。没有数据支撑的必须写“推测”。

### 4. 出题

按客群说明里的配比出 10 个不带店名的问题和 2 个带店名的问题。

- 每类顾客至少 2 道题，在题目上写明 `audience`（替哪类顾客问）和 `worry`（他在意什么）。
- 用这类顾客的口气和他会用的词，把他在意的事写进问题里。例如控糖的人不会问“哪家面包店好”，会问“有没有适合控糖的人吃的面包店”。
- 不带店名的问题里不能出现店名和别名，否则结果虚高，脚本会拒绝。
- 多出具体的问题：具体街区、具体单品、具体场合、具体价位。“全国哪个牌子好”这类大问题，小店赢不了，最多留 1 个当参照。
- 带店名的 2 个固定为“某某怎么样”和“某某在哪、几点开门、有什么招牌”。
- 同类店这一步先不定，第一次体检后从 AI 实际提到的店里挑。

### 5. 查他在别处的账号和内容

通过 `youzan-ai-search` Skill 查，每项只查一次：

- 公众号搜索：有没有同名公众号。
- 抖音团购门店搜索：有没有门店页。
- 抖音作品搜索：他的账号发过的视频。把这些视频的作品编号记进 `channels.ownContentKeys`。抖音的引用不带作者，只有记了编号，才能认出“AI 引用的是你自己发的视频”。
- 小红书实时搜索：有没有顾客写的笔记。

搜到的账号是不是他的，你没法确定，所以这些都属于要商家确认的信息。查询需要等待时按 `youzan-ai-search` 的要求等；查不到就如实记“没有找到”。

### 6. 写入

```bash
S="$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-profile/scripts/geo_state.py"
python3 "$S" init --segment local --brand "店名"
python3 "$S" set-facts --file "$YOUZAN_AGENT_SESSION_TEMP/geo/facts.json"
python3 "$S" set-questions --file "$YOUZAN_AGENT_SESSION_TEMP/geo/questions.json"
python3 "$S" set-assets --file "$YOUZAN_AGENT_SESSION_TEMP/geo/assets.json"
```

`facts.json`：

```json
{
  "from": "backend",
  "segment": "local",
  "brand": {"name": "", "aliases": [], "category": "", "city": ""},
  "audience": [{"name": "", "who": "", "scene": "", "worry": "", "basis": "商品评价"}],
  "stores": [{"name": "", "address": "", "hours": "", "phone": "", "status": "在营", "source": "有赞后台"}],
  "products": [{"name": "", "spec": "", "priceRange": "", "origin": ""}],
  "buyEntry": {"miniProgram": "", "shopUrl": ""},
  "channels": {"wechatOfficial": "", "douyin": "", "ownHosts": [], "ownContentKeys": []},
  "writingRules": {"tone": "", "bannedWords": [], "mustInclude": []}
}
```

`questions.json`（`kind` 为 `open` 表示不带店名，编号用 q01 起；`brand` 表示带店名，编号用 b01 起）：

```json
[
  {"id": "q01", "kind": "open", "tag": "地段", "text": "", "audience": "", "worry": ""},
  {"id": "b01", "kind": "brand", "tag": "口碑", "text": ""}
]
```

`assets.json`（第 5 步查到的，你找内容缺口时用，不在工作台上展示）：

```json
{"items": [{"platform": "抖音门店", "found": true, "note": "", "url": ""}]}
```

脚本返回的 `warnings` 要处理：能补的补上，补不了的在第 9 步告诉商家。

### 7. 开通工作台

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" publish
```

这时还没有体检结果，工作台首页是“现在到哪一步了”，“监测设置”页上是你出的问题。输出里 `firstTime: true`，`pageUrl` 就是工作台的链接，以后一直是这一个。

先用两三句话告诉商家：问题出好了、工作台在这里（给 `pageUrl`，逐字照抄）、现在去做第一次体检、大约十分钟。然后**不等回复**，接着做下一步。

`published: false` 时按 `geo-weekly` 的 `references/workbench.md` 处理，体检照常进行。

### 8. 马上体检

立即按 `geo-check` Skill 跑第一次体检，再按 `geo-weekly` Skill 写本期小结和建议、同步工作台。这一期会生成第一份体检报告。

### 9. 告诉商家结果

这条消息控制在 6 行以内：

1. 一句结论：顾客没点名时，多少个回答里有几个提到了他。
2. AI 点名介绍他时是怎么说的，一两句话。
3. 这一期的报告（`publish` 输出的 `reportUrl`，点开是在工作台里看这一期的报告）。
4. `pendingConfirm` 为 true 时：把 `toConfirm` 里的那几样点出来（“我搜到一个叫某某的抖音号，是你的吗”），请他看一眼工作台的“监测设置”，回复“确认”或者直接说哪里不对。没有要确认的就不提这一条。

报告里有的不要再贴一遍。

## 每期体检前：重读一遍店铺资料

每周体检之前，重新从店铺后台读一遍资料，用 `set-facts` 写回（带 `"from": "backend"`，你另外记下的那几样原样保留）。营业时间改了、多了一家店，这样才能跟上。从后台重读带来的变化不用商家再确认。

## 修改

商家的话很多是从工作台上复制过来的。工作台和报告上问题的编号是 Q1、Q2、B1 这样，对应 `q01`、`q02`、`b01`。

| 商家说 | 做法 |
| --- | --- |
| “把 Q3 换一个问法”“把 Q3 删掉”“加一道题：……” | `show --part questions` → `set-questions`；提醒商家：改了问题原文，之前的数就不能和之后的比了。然后按 `geo-check` 只重跑改过的题、重新算分 → `publish` |
| “同类店换成……” | `set-rivals --file <文件>`（`[{"name": "", "aliases": []}]`，最多 5 家），按 `geo-check` 重新算分 → `publish` |
| “我的公众号叫……”“我的抖音号是……” | 记进 `channels`，`set-facts` 时加 `--confirmed-by-merchant`；抖音号还要按第 5 步查它的作品编号。然后按 `geo-check` 重新算分 → `publish` |
| “这些信息没问题，确认”“确认” | `confirm` → `publish` |
| “这个抖音号不是我的”“那家店早就关了” | 先 `show --part facts`，改好后 `set-facts --file <文件> --confirmed-by-merchant` → `publish` |
| “这类顾客说得不对，其实是……” | 改 `audience`，`set-facts --confirmed-by-merchant`；需要的话相应改问题 → `publish` |
| “写东西不要用某个词”“口吻随意一点” | 记进 `writingRules`，`set-facts --confirmed-by-merchant` → `publish` |
| “营业时间是……”“我们搬到……了” | 这是店铺后台里的资料。按他说的先记下（`--confirmed-by-merchant`），并提醒他把店铺后台也改掉，否则下一期重读时又会变回去 |

你自己改资料时不要加 `--confirmed-by-merchant`。要确认的那部分变了，脚本会自动标成“等商家确认”。

改完以后告诉商家哪里更新了，给“监测设置”页的链接。

## 对外表达

- 只说业务语言：店铺资料、顾客类型、问题、同类店、体检、报告、工作台。
- 不向商家展示脚本、命令、字段名、文件路径和内部报错。
