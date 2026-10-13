---
name: geo-check
description: 给店铺做一次“AI 曝光体检”：按问题库向元宝、豆包、DeepSeek 提问，保存每个回答的原文和引用来源，统计提没提到本店、提到了谁、读了哪里的内容，再核对 AI 是怎么介绍这家店的。商家确认开始第一次体检后、每周体检时、商家说“重新体检”“重新测一下”“现在体检到哪一步了”时使用；商家针对报告里某一条对不上的说法说“3 号我改好了”“3 号不是错的”“这个出处我改不了”时也使用。
---

# 体检

一轮体检分四步：提问和等待、算分、读全文、核对。前两步由脚本完成；读全文和核对由你做（读全文派子 Agent），结果都交给脚本校验。

每一期体检的结果做成**一份体检报告**：有没有提到这家店、没提到时提到了谁、AI 读哪里的内容、AI 怎么介绍这家店。报告每期一份，是独立的文件；商家在工作台里点开看，不用跳到别的页面。工作台首页只显示最新一期的结论和每一期报告的入口。

**体检不会自己变成报告。** 报告由 `geo-weekly` Skill 里的同步命令生成（下面用 `publish` 指代）：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-weekly/scripts/geo_report.py" publish
```

## 开始前

- 先执行 `geo_state.py status`：没有建档先按 `geo-profile` 建档；`firstCheckPending` 为 true 说明商家还没同意体检，回到 `geo-profile` 的第 3 步。
- 每周体检之前，按 `geo-profile` 的“每期体检前”重新读一遍店铺资料。核对用的是它，旧了会对错。
- 两个脚本是 `python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_run.py"` 和 `python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py"`。下文表格里写的 `geo_run.py ...`、`geo_score.py ...` 都是全路径的简写，执行时写全。
- 每个命令的输出里都有 `next`，写着下一步该做什么，照着做。

## 第一步：提问和等待

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_run.py" start --phase open     # 先问全部不带店名的问题
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_run.py" wait                   # 等结果，可以反复执行
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_run.py" start --phase brand    # 不带店名的全部返回后，再问带店名的问题
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_run.py" wait
```

顺序不能反：取数账号万一带着记忆，先问带店名的问题，后面的回答会凭空提到这家店。脚本会拦住错误的顺序。

第一次 `start` 之后执行一次 `publish`：工作台会显示“体检进行中”，商家这时打开不会以为看到的是最新结果。之后等待的过程中不用再同步。

**等待：**

- 一轮通常要 5 到 10 分钟。`wait` 每次最多等 90 秒就返回进度，`running` 不为 0 时再执行一次，直到 `next` 让你进入下一步。查询还在运行是正常的，继续 `wait`，不要重新 `start`。
- 超过 15 分钟还没返回的查询，脚本会自动记为缺失，这一期该题该平台不计分，不用补救。
- `start` 返回 `ok: false` 时按 `error` 处理。如果是“还没有开通问 AI 能力”，告诉商家暂时不能体检。

只想重跑个别问题（例如商家改了某道题）：`python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_run.py" start --phase open --only q03,q07`。改过原文的题会重新问，没改的不会。

**接着上一次，和重新测一次，是两回事：**

- 不带 `--fresh` 的 `start` 是“接着上一次”：这一天已经有回答的题不会重新问。同一天再执行，输出里 `started` 是 0，`next` 会说明用的是已有的回答。
- 商家说“重新体检”“重新测一下”，要的是重新问一遍：`python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_run.py" start --phase open --fresh`。上一次的回答、算分和核对会挪进这一天目录下的 `old-<时间>/` 留底，然后从头问；等不带店名的全部返回，再 `start --phase brand`，接着照常算分、核对。还有查询在运行时不能重新测，先等它们返回。
- 商家删掉的题不用重跑：重新 `score`，最新一期就不再算它（输出的 `notes` 会列出来）。以前各期按当时问的题算，不变。

## 第二步：算分

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" score
```

输出里重点看：

- `mention`：顾客没点名时，多少个回答提到了本店，分平台。
- `rivals`：选定的同类店各被几个回答推荐（读全文写回以后才有数）。
- `refs`：本店账号的内容、以本店命名的门店页、别人写本店的内容，各被引用多少次。
- `topSources`：AI 这一期最常读哪里的内容。
- `shopsPending`：还没读过的回答数。不为 0 时，`next` 会让你先做第三步。
- `notes`：需要在周报里说明的情况。

AI 推荐了哪些店、有什么值得商家知道的，脚本算不出来，要读回答全文，这是第三步。

## 第三步：读全文

派子 Agent 把这一期每个平台的回答全部读一遍，看 AI 推荐了哪些店、有什么值得商家知道的。怎么派、派几个、怎么交代，你自己定；子 Agent 交回文字就行，整理成下面的格式是你的事。

取一个平台回答全文的命令（只重跑了几道题时，`score` 的 `next` 会写明是哪几道，加 `--only`）：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" answers --provider doubao
```

脚本有几个数是按“名字出现在文字里”算的，同名的店、同名的养老院都会混进来。读全文时一起复核，收回来以后整理成一份写回：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" set-reading --file "$YOUZAN_AGENT_SESSION_TEMP/geo/reading.json"
```

```json
{"answers": {"q01_doubao#1": ["储缘蛋糕", "馋嘴蛋糕"], "q01_doubao#2": []},
 "names": {"储缘蛋糕": ["储缘生日蛋糕(留下镇店)"]},
 "notUs": ["q05_doubao#2"],
 "refsNotUs": ["https://..."],
 "refsAboutUs": ["https://..."]}
```

| 写什么 | 对应 `answers` 输出里的 | 要求 |
| --- | --- | --- |
| `answers`：每个回答推荐了哪几家店 | `listShops` 为 true 的回答 | **每个都要写**，没推荐店的写空列表。只写店（门店、品牌、网店、连锁），不写品类、商圈、平台，不写本店。同一家店的不同写法，在 `names` 里写上原文的写法 |
| `notUs`：算作“提到你”、其实说的不是这家店的回答 | `mentionedByName` 为 true 的回答 | 只写说错了的，比如说的是同名的养老院、别的城市的同名店 |
| `refsNotUs`：标题里有店名、其实不是这家店的引用 | 引用的 `relation` 不为空的 | 只写不是的 |
| `refsAboutUs`：标题里没店名、其实写的就是这家店的引用 | 引用的 `relation` 为空的 | 只写有把握的，例如地址、招牌都对得上 |

后三样没有就不写。可以一次传，也可以按平台分几个文件传（`--file` 写多次）。脚本会核对：店名或原文写法必须出现在那个回答里，要写店名的回答不能漏，引用必须是这一期出现过的。对不上的整份退回，按 `error` 改；`stillMissing` 里是还没写店名的回答，漏了就让子 Agent 补。复核过的引用以后各期都算数。

再写这一期的发现，**最多 5 条，宁缺毋滥**，没有值得说的就传空列表，不要凑：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" set-findings --file "$YOUZAN_AGENT_SESSION_TEMP/geo/findings.json"
```

```json
{"items": [{"kind": "misread", "title": "", "detail": "", "action": "",
            "evidence": [{"answer": "b01_doubao#1", "quote": "回答里的一句原话"}]}]}
```

`kind`：`misread` 认错了你、`lead` 线索（比如疑似你家、但没写店名的内容）、`against` 对你不利的说法、`rivals` 同行的做法、`other` 其他。每条至少一句原话，脚本会逐字核对；数字只用脚本算出来的，子 Agent 自己数的次数不要写进去。

写完重新算分。“提到了谁”和同类店的次数这时才有数，“提到你”和“和你有关的引用”也按复核过的算：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" score
```

如果输出里有 `candidates`（这时 `next` 也会让你先选同类店），说明同类店还没定：从里面挑 3 家和本店同品类、同区域的店，带上常见的别名，用 `geo-profile` 的 `set-rivals` 保存，再执行一次 `score`。

## 第四步：核对 AI 怎么介绍这家店

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" brand-digest
```

它输出店铺资料（`facts`）、之前记过的对不上的说法（`knownIssues`），以及全部带店名的回答和提到本店的回答，每个回答带着它引用的内容。

读完后按 `references/judging.md` 写两样东西，存成 JSON 文件后交给脚本：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" set-judgement --file "$YOUZAN_AGENT_SESSION_TEMP/geo/judgement.json"
```

```json
{
  "descriptions": {"hunyuan": "", "doubao": "", "deepseek": ""},
  "issues": [
    {
      "id": "address-old-store",
      "fact": "address",
      "aiSays": "",
      "truth": "",
      "evidence": ["b01_hunyuan#1"],
      "sourceType": "note",
      "sourceTitle": "",
      "sourceUrl": "",
      "fix": ""
    }
  ]
}
```

- `descriptions`：每个平台一句话，AI 点名介绍这家店时怎么说。**每一期都要写**，它是报告“怎么介绍你”这一节的正文。
- `issues`：AI 的说法里和店铺资料对不上的具体事实。**没有就传空数组，这是最常见的正常结果**，不要为了有东西可写去凑。

脚本会拒绝两种情况：`evidence` 里的回答编号不存在；`sourceUrl` 不在这些回答自己的引用列表里。被拒绝时回到 `brand-digest` 的输出里核对；找不到出处就留空。

这两样商家会在报告里逐字看到，写的时候当成是在对商家说话。

### 对不上的说法怎么对待

它是体检顺带的一种发现，不是这份工作的主线：很多店 AI 根本不提，也就谈不上说错；提到了，也多半没有错。

- 它只出现在那一期报告的“怎么介绍你”一节里，有才列出来。工作台上没有它的页面，也没有它的数。
- 每条有一个固定的序号（1 号、2 号……），以后每一期都是这个号。
- 周报里不把它当成固定的一项来汇报。只有改得动、值得改的那一条，才由你在 `geo-weekly` 里写进本期小结或建议。例如地图上一个没下线的旧门店页，商家十分钟能标成已关闭，这值得说；一篇三年前的探店笔记写了旧地址，商家改不了原文，就不要当成一件事塞给他。
- 资料是从公开信息整理的、还没经过商家确认时，对不上不一定是 AI 错，也可能是你的资料不全。报告上会自动标明这一点；你在 `fix` 里也不要把话说死，写“如果确实……，可以……”。

## 商家针对某一条来说话

商家说的序号是报告上显示的。拿不准时先看清单，序号和报告上的一致：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" issues --status open
```

| 商家说 | 做法 |
| --- | --- |
| “3 号我改好了” | `python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" mark-issue --no 3 --status done` → `publish`。告诉他下一期体检会复查：AI 如果还在这么说，新的报告里会标出来 |
| “3 号不是错的” | 问清实际情况 → 按 `geo-profile` 把店铺资料改对（`--confirmed-by-merchant`），并提醒他店铺后台里也要是对的 → `python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" mark-issue --no 3 --status dismissed` → `publish` |
| “这个出处我改不了，怎么办” | 按 `references/judging.md`：别人写的内容改不了原文，可以发一篇带日期的信息说明，让 AI 有新的依据；地图和点评上的旧门店页可以标记为已关闭。他不想管也可以，不要反复提 |
| “我标错了，3 号还没改” | `python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-check/scripts/geo_score.py" mark-issue --no 3 --status open` → `publish` |

## 体检之后

核对写完，这一期的数据就齐了，但报告还没有生成，工作台上也还是旧的。接着按 `geo-weekly` Skill 写本期小结和建议，然后 `publish`：

- 第一次体检（商家刚确认）：按 `geo-weekly` 的“第一份报告”走完，汇报结果并问他要不要开启每周体检。
- 每周体检：按 `geo-weekly` 的“每周出周报”走完，发周报。
- 商家临时要求重新体检（用 `--fresh`，见第一步）：同样按 `geo-weekly` 重写小结和建议、`publish`，然后用两三句话说结果（没点名时多少个回答提到了他、和上一期比怎么样），给 `publish` 输出的 `reportUrl`。不用发完整周报。

## 对外表达

数字只用脚本输出里的，不估算，不凑整。
