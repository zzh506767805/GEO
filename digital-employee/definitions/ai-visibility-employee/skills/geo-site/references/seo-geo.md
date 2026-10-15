# 官网的 SEO 和 GEO

官网做出来，要先被搜索引擎和 AI 读到、读懂，才可能被引用。这份写的是：交给“应用”能力时要提哪些页面要求，测试版出来以后怎么查，上线以后还能做什么。

## 先弄清三件事

1. **给 AI 看的和给搜索引擎看的是同一件事。** Google 的官方说法是：为生成式 AI 搜索做优化，就是为搜索做优化，“仍然是 SEO”。AI 联网回答问题时，先用搜索找到网页再读。所以没有一套单独“给 AI 的写法”：不用另写一版给 AI 看的内容，不用把内容切成小段，不用堆长尾关键词。
2. **很多 AI 的爬虫不运行 JavaScript。** 它们只读服务器返回的 HTML。页面上的字要直接写在 HTML 里，不能等脚本去取数据再显示（SKILL.md 第 4 步“文字直接写在页面里”就是为这个）。
3. **国内的 AI 各用各的搜索源。** 元宝、豆包、DeepSeek 联网时用哪家搜索、哪些站点，没有公开说明。能做的是让主流搜索引擎的爬虫都能读到这个页面，再让别处多一些指向它的链接。

## 交给“应用”能力的页面要求

下面每一条都写进需求里。“应用”能力做不到的（比如平台不让改页面头部），记下是哪几条，测试版出来后告诉商家，不要假装做了。

### 页面头部

| 项 | 写什么 |
| --- | --- |
| 语言 | `<html lang="zh-CN">` |
| 页面标题 `<title>` | `site-brief` 的 `pageTitle`；格式是“店名 · 在哪个城市卖什么”，30 个字以内 |
| 页面描述 `<meta name="description">` | 一句话说清这家店是谁、在哪、卖什么，80 个字以内，用页面上已有的事实 |
| 规范链接 `<link rel="canonical">` | 正式链接；绑了独立域名就用域名。测试版先不填，正式发布时填 |
| 分享卡片 | `og:title`、`og:description`、`og:type`（`website`）、`og:url`；有店里真实的门头或商品图就填 `og:image` |
| 视口 | `<meta name="viewport" content="width=device-width, initial-scale=1">`，不禁止缩放 |
| 不要 | `noindex`、`nofollow`；正式版上不能有 |

### 正文结构

- **只有一个 `<h1>`，里面要有店名。** 例如“〈店名〉 · 〈城市〉〈品类〉”。不要把一句问话、一句口号当 `h1`。
- 第一段 40–60 个字直接回答“这家店是谁”，用“〈店名〉是〈城市〉的〈品类〉，……”这样的句式。AI 引用最多的是页面前三分之一。
- 各块用 `<h2>`，块里的小项用 `<h3>`，不跳级。块标题尽量用顾客会问的说法：“门店在哪、几点开门”“怎么买”。
- 用语义标签：`<header>`、`<main>`、`<section>`、`<footer>`；门店地址可以放在 `<address>` 里。
- **顾客常问平铺写出来，不折叠、不放进标签页。** 一问一答，问题用 `<h3>`，回答紧跟在下面。
- 门店信息每家一样的写法：名字、地址、营业时间、电话（有才写），用文字写，不做成图片。
- 页面最下面写“信息更新于 X 年 X 月 X 日”。资料新，被引用的机会更大。
- 图片都有替代文字（`alt`），写清是什么：“〈门店名〉门头”“〈招牌商品名〉”。
- 不用外部字体和外部脚本：国内打开慢，还可能加载失败。系统字体就够。

### 结构化数据（JSON-LD）

放在页面里一段 `<script type="application/ld+json">`。**每个值都必须是页面上看得到的事实**，看不到的不写。不写价格（`priceRange`、`offers` 都不写），不写评分（`aggregateRating`）、评价。

- 每家门店一个 `LocalBusiness`（品类更具体的用子类型：面包店 `Bakery`、咖啡馆 `CafeOrCoffeeShop`、餐厅 `Restaurant`、商店 `Store`），写 `name`、`address`、`openingHours`、`telephone`（有才写）、`url`（官网链接）。纯网店没有门店，用一个 `Organization`。
- 顾客常问写一个 `FAQPage`，问和答与页面上的文字一字不差。
- 一个 `WebSite`，写 `name` 和 `url`。

样子（换成 `site-brief` 里的真实资料，用不上的字段删掉）：

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Bakery",
      "name": "〈门店名〉",
      "address": {"@type": "PostalAddress", "streetAddress": "〈地址〉", "addressLocality": "〈城市〉", "addressCountry": "CN"},
      "openingHours": "Mo-Su 08:00-20:00",
      "url": "〈正式链接〉"
    },
    {
      "@type": "FAQPage",
      "mainEntity": [
        {"@type": "Question", "name": "〈问题原文〉", "acceptedAnswer": {"@type": "Answer", "text": "〈回答原文〉"}}
      ]
    },
    {"@type": "WebSite", "name": "〈店名〉", "url": "〈正式链接〉"}
  ]
}
</script>
```

Google 说不必为了 AI 专门多加结构化数据。这里加这几种，是因为它们本来就是搜索引擎认门店和问答的标准写法，成本低。

## 测试版出来以后查一遍

拿到测试版链接后、发给商家之前，能联网就查。查的是服务器原样返回的 HTML，不是浏览器里看到的样子：

```bash
curl -sL "<测试版链接>" -o "$YOUZAN_AGENT_SESSION_WORKSPACE/site-check.html"
cd "$YOUZAN_AGENT_SESSION_WORKSPACE"
grep -c "<h1" site-check.html                       # 应该是 1
grep -o "<title>[^<]*</title>" site-check.html     # 有店名
grep -c 'name="description"' site-check.html       # 应该是 1
grep -c "application/ld+json" site-check.html      # 至少 1
grep -c "〈店名〉" site-check.html                   # 店名出现在正文里
grep -c "〈第一家门店的地址里的一段〉" site-check.html  # 门店地址是直接写在 HTML 里的
grep -ci "noindex" site-check.html                 # 正式版应该是 0
```

有一项不对，交给“应用”能力改，改好再发测试版。测试版本身带 `noindex` 是正常的，正式版不能有。环境里没法联网时，跳过这一步，在给商家的消息里不提。

## 上线以后

这几件不在页面里，在页面所在的站点上。员工改不了的，告诉商家能做什么，不替他去做：

- **robots.txt 不挡搜索爬虫。** 至少放行 `Baiduspider`、`Sogou web spider`、`360Spider`、`Bytespider`、`Googlebot`、`bingbot`，以及 AI 搜索用的 `OAI-SearchBot`、`Claude-SearchBot`、`PerplexityBot`。`GPTBot`、`ClaudeBot`、`CCBot` 这些是拿去训练模型的，放不放由商家定，和能不能被 AI 搜到无关。
- **提交给搜索引擎。** 绑了独立域名的，可以在百度搜索资源平台、Bing 网站管理员工具、Google Search Console 提交这个网址。
- **别处有链接指向它。** SKILL.md 第 6 步已经写了：建议商家在公众号菜单、小红书简介、抖音主页、大众点评这些他能改的地方放上官网链接。AI 认一家店，看的更多是各处提到它的地方，不只是官网本身。
- **资料变了就更新。** 过时的官网会让 AI 说错。按“改官网、更新官网”做。

## 不做的事

- 不做 `llms.txt`。Google 明确说不需要，也没有看到国内平台用它。
- 不堆关键词、不写给 AI 专门看的隐藏文字、不在页面里放和店铺无关的热门词。
- 不在结构化数据里写页面上没有的东西，不编评分和评价。
- 不去别的平台刷提及。

## 参考

做法综合自这几个 GitHub 上公开的 SEO / GEO Skill，以及它们引用的一手资料：

| 仓库 | 版本 | 许可 | 用了什么 |
| --- | --- | --- | --- |
| https://github.com/AgriciDaniel/claude-seo （`skills/seo-geo`） | `4b99de2` | MIT | Google AI 优化指南的结论（GEO 仍是 SEO、不需要 llms.txt）；可引用的写法（每块开头 40–60 字直接回答、问句式小标题、关键事实放在页面前三分之一）；AI 爬虫清单 |
| https://github.com/thevibegarage/geo-visibility-skill | `baffad0` | MIT | JSON-LD 模板（LocalBusiness、FAQPage、WebSite）、“结构化数据只写页面上看得到的事实” |
| https://github.com/zubair-trabzada/geo-seo-claude | `989cae0` | MIT | 不运行 JS 的 AI 爬虫要能读到正文、本地商家的结构化数据 |

一手资料：Google 搜索中心的 AI 优化指南 https://developers.google.com/search/docs/fundamentals/ai-optimization-guide ，各家爬虫说明：OpenAI https://platform.openai.com/docs/bots 、Anthropic https://support.anthropic.com/en/articles/8896518 。

这些规则会变。要更新，先看 Google 的指南和各家爬虫说明有没有改，再改这里。
