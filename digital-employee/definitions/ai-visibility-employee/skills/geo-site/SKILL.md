---
name: geo-site
description: 用有赞的“应用”能力替商家做一个内容丰富、一直在线的官网，给 AI 和顾客一个这家店自己的出处；上线后店铺资料变了，提醒商家更新。商家说“帮我做个官网”“官网可以发布了”“官网上……改一下”“更新官网”“官网发我”“官网不要了”时使用；出周报时看到官网过时了也用它。
---

# 做官网

官网是这家店自己的网站，一直在线，AI 和顾客都能读到。页面由有赞的“应用”能力（`youzan-application` Skill）来做，按它的流程走；它的规矩（先给方案请商家确认、先出测试版、商家说发布才上线）一条不省，和这里冲突时以它为准。

本 Skill 只管“应用”能力不知道的几件事：

- 官网的内容要丰富，素材从哪拿。
- 做好以后登记到工作台，店铺资料变了提醒商家更新。

用到的脚本是工作台的 `geo_report.py`，下文的 `site-brief`、`set-site`、`publish` 都是它的子命令。

## 什么时候做

- 商家说要做，就做。
- 你主动提，只在下面两种情况，各提一次；商家没接，就不再提：
  1. 这一期报告“怎么介绍你”里，AI 点名介绍这家店时说法对不上，或者说不清门店、营业时间、卖什么。
  2. 商家问“怎么让 AI 更了解我”“怎么让 AI 把我的信息说对”。
- 首次初始化和第一次体检这一轮不提。
- 提的时候说清三件事：官网上放什么；要占用一个应用额度；先出测试版给他看，他说发布才上线。不说“做了官网 AI 就会推荐你”：AI 要先搜得到它才会引用，上线以后看后面几期报告里有没有引用它。

## 1. 先看能不能做

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" site-brief
```

- `canWrite` 为 false：店铺资料不是从店铺后台读的，商家也还没确认。这时不做，请他先看一眼工作台的“监测设置”，确认了再做。
- `site.exists` 为 true、`site.status` 不是 `dropped`：已经有官网了，按下面“改官网、更新官网”做，改的是同一个应用，不要再新建一个。

## 2. 先备齐素材

动手做页面之前，先把这家店的素材备齐，信息和图片都要。官网要让第一次来的人愿意看下去，看完就了解这家店：店铺资料（`site-brief`）、商品和评价（`youzan-item`）、素材中心（`youzan-material`）里查得到的都可以用，能用上的尽量用上；放什么、怎么组织、分几页，按这家店定。

最少要有：

- 这家店是谁，和别家哪里不一样
- 卖什么：主要商品，带图
- 在哪买：购买入口或门店
- 顾客常问的问题和回答（`site-brief` 的 `faq`）
- AI 说错过的事（`site-brief` 的 `issues`、`oldStores`），有就写清对的说法

图片先用店铺自己的：商品图、素材中心里的 Logo 和门店照片；不够的，委派 `youzan-image` 子 Agent 生成。

`site-brief` 输出里已经去掉了你另外记下、商家还没确认的信息。遵守 `writingRules`：口吻、不用的词、每次必须带的信息。页面标题可以用 `pageTitle`，商家想改就按他的。

## 3. 选一种风格，把素材组织成官网

从 `references/design-index.md` 的三个设计参考里选一个最适合这家店的，只读那一份，照着它把第 2 步的素材组织成官网。商家说了想要的感觉，就按他的选。选定的风格写进给“应用”能力的方案，商家看方案时一起确认。

## 4. 交给“应用”能力做

用 `Skill` 工具加载 `youzan-application`，按它的步骤走。**它要问商家的（发布渠道、空间类型、方案），你一个都不替商家答。** 它的方案里写明：这是店铺官网，店铺资料变了你会提醒商家更新。第 2 步备齐的素材和第 3 步选的风格一起交给它。

## 5. 测试版出来以后

“应用”能力部署好测试版、拿到测试版链接后，**先登记、同步，再把链接发给商家**（“应用”能力要求发出测试版链接后就停下来等商家）：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" set-site --status test --test-url "<测试版链接>" --page-name <页面标识>
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" publish
```

链接和页面标识照“应用”能力输出里的原样填。工作台“内容”页最上面会出现官网这一块，带“看测试版”。然后按“应用”能力的格式把测试版链接发给商家，停下来等他回复。

## 6. 商家确认发布以后

按“应用”能力正式发布，再用它给出的正式链接登记、同步：

```bash
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" set-site --status published --url "<正式链接>"
python3 "$YOUZAN_AGENT_SESSION_WORKSPACE/.claude/skills/geo-workbench/scripts/geo_report.py" publish
```

告诉商家官网上线了，给正式链接，并照 `set-site` 输出的 `next` 建议他把链接放到自己能填网址的地方：别处有链接指向它，搜索引擎和 AI 才更容易找到它。以后 AI 引用了这个官网，报告里会算进“你的内容被引用”。

## 改官网、更新官网

`site-brief` 或 `geo_state.py status` 输出的 `site.outdated` 为 true，说明官网用到的店铺资料改过了；`site.changed` 写着是哪几样，例如“门店”“这家店的特点”。

- 每周出周报时看到，就在建议里提一次：“官网上的门店信息过时了，要更新吗？”商家同意了再更新，没理会就不再提。
- 要更新，或者商家说“官网上……改一下”：重新执行 `site-brief` 拿最新的资料，按第 2 步备素材，交给“应用”能力改同一个应用，从第 5 步往下走。

## 商家说

| 商家说 | 做法 |
| --- | --- |
| “帮我做个官网” | 从第 1 步开始 |
| “官网可以发布了”“确认发布” | 按第 6 步；“应用”能力要求他确认的是这一轮看过的测试版，隔了几轮才说，按它的规矩先重出测试版 |
| “官网上……改一下”“更新官网” | 按“改官网、更新官网” |
| “官网发我” | `site-brief` 输出里的 `site.url`；还没上线，就说还在测试版，给 `site.testUrl` |
| “官网绑好域名了：……” | `set-site --domain <域名>` → `publish`。以后这个域名下的页面被 AI 引用，也算他自己的内容 |
| “官网不要了” | 按“应用”能力下线、删除的流程，商家明确确认后再做；做完 `set-site --status dropped` → `publish`。以后再要，就是从第 1 步重新做一个 |
