#!/usr/bin/env python3
"""演示数据的剧本：一家虚构的社区面包店“禾木烘焙”用了五期以后的样子。

店铺、同类店、地址、文章全部是编的，只给 make_demo.py 生成演示页面用。
剧本大意：
  第 1 期  刚上岗。AI 几乎不提这家店；元宝和 DeepSeek 还把已经关掉的河畔店当成在营门店；DeepSeek 把营业时间说错。
  第 2 期  商家确认了档案，发了门店信息说明。
  第 3 期  元宝开始引用商家自己的公众号文章，并改了口；DeepSeek 还在说旧地址（商家标记过已改，被重新打开）。
  第 4 期  旧地址不再出现。第二篇文章被引用。
  第 5 期  提到本店的回答继续变多；只剩营业时间这一处没改过来。
"""

BRAND = "禾木烘焙"
WEEKS = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05"]

# 第几期 → 平台 → {问题里的关键词: 第几个回答提到本店}
HITS = {
    1: {"doubao": {"运河边": [1]}},
    2: {"doubao": {"运河边": [1, 2]}},
    3: {"doubao": {"运河边": [1, 2]}, "hunyuan": {"拱墅区": [1]}},
    4: {"doubao": {"运河边": [1, 2]}, "hunyuan": {"拱墅区": [1], "全麦吐司": [1]}, "deepseek": {"全麦吐司": [1]}},
    5: {"doubao": {"运河边": [1, 2], "贝果": [1]}, "hunyuan": {"拱墅区": [1, 2], "全麦吐司": [1]}, "deepseek": {"全麦吐司": [1]}},
}
KEYWORDS = ("运河边", "拱墅区", "全麦吐司", "贝果", "小程序下单", "带孩子", "坐下来喝咖啡", "礼盒", "提前预订", "城西")
MEMORY = {2: ("doubao", "坐下来喝咖啡", 2)}            # 这一期豆包有一个回答带着之前对话的痕迹
OLD_ADDRESS = {"hunyuan": (1, 2), "deepseek": (1, 2, 3)}  # 哪几期还在说已经关掉的河畔店
WRONG_HOURS = {"deepseek": (1, 2, 3, 4, 5)}                # 哪几期把营业时间说成到 22:00

OLD_STORE = {"url": "https://m.dianping.com/shop/demo-hemu-riverside", "host": "m.dianping.com", "title": "禾木烘焙(河畔店)", "source": "大众点评"}
NEW_STORE = {"url": "https://m.dianping.com/shop/demo-hemu-gongshu", "host": "m.dianping.com", "title": "禾木烘焙(拱墅店)", "source": "大众点评"}
OLD_NOTE = {"url": "https://www.demo-notes.cn/p/hemu-late-night", "host": "www.demo-notes.cn", "title": "禾木烘焙探店：晚上十点还亮着灯的面包店", "source": "本地生活笔记"}
OWN_INFO = {"url": "https://mp.weixin.qq.com/s?demo=hemu-store-info", "host": "mp.weixin.qq.com", "title": "禾木烘焙门店信息（2026 年 9 月更新）", "source": "禾木烘焙"}
OWN_TOAST = {"url": "https://mp.weixin.qq.com/s?demo=hemu-wholewheat", "host": "mp.weixin.qq.com", "title": "拱墅区哪里能买到现烤的全麦吐司", "source": "禾木烘焙"}
GENERIC = {
    "hunyuan": [
        {"url": "https://mp.weixin.qq.com/s?demo=a1", "host": "mp.weixin.qq.com", "title": "杭州社区面包店地图：这 8 家值得专门去", "source": "杭城吃喝指南"},
        {"url": "https://mp.weixin.qq.com/s?demo=a2", "host": "mp.weixin.qq.com", "title": "麦田工坊十周年：一家社区店的坚持", "source": "麦田工坊"},
        {"url": "https://mp.weixin.qq.com/s?demo=a3", "host": "mp.weixin.qq.com", "title": "带娃友好的 5 家面包店", "source": "亲子周末"},
        {"url": "https://www.sohu.com/a/demo-bread", "host": "www.sohu.com", "title": "杭州面包店推荐合集", "source": "搜狐"},
        {"url": "https://baike.baidu.com/item/demo", "host": "baike.baidu.com", "title": "全麦面包", "source": "百度百科"},
    ],
    "doubao": [
        {"url": "https://www.iesdouyin.com/share/video/demo1", "host": "www.iesdouyin.com", "title": "杭州面包脑袋必吃的 6 家店 #杭州美食", "source": "www.iesdouyin.com"},
        {"url": "https://www.iesdouyin.com/share/video/demo2", "host": "www.iesdouyin.com", "title": "运河边散步顺路买面包 #探店", "source": "www.iesdouyin.com"},
        {"url": "https://www.iesdouyin.com/share/video/demo3", "host": "www.iesdouyin.com", "title": "暖炉面包新品测评", "source": "www.iesdouyin.com"},
        {"url": "https://www.iesdouyin.com/share/video/demo4", "host": "www.iesdouyin.com", "title": "巷口烘焙的贝果到底值不值", "source": "www.iesdouyin.com"},
        {"url": "https://m.ctrip.com/webapp/you/demo", "host": "m.ctrip.com", "title": "杭州周末吃喝路线", "source": "携程旅行"},
    ],
    "deepseek": [
        {"url": "https://www.zhihu.com/question/demo1", "host": "www.zhihu.com", "title": "杭州有哪些值得去的面包店？", "source": "知乎"},
        {"url": "https://www.zhihu.com/question/demo2", "host": "www.zhihu.com", "title": "全麦吐司怎么挑？", "source": "知乎"},
        {"url": "https://www.amap.com/place/demo-maitian", "host": "www.amap.com", "title": "麦田工坊(拱墅店)", "source": "高德地图"},
        {"url": "https://baijiahao.baidu.com/s?id=demo", "host": "baijiahao.baidu.com", "title": "杭州烘焙店盘点", "source": "百家号"},
        {"url": "https://www.demo-food.cn/list", "host": "www.demo-food.cn", "title": "本地面包店榜单", "source": "吃喝榜"},
    ],
}
LEAD = {
    "hunyuan": "先说结论，下面几家口碑比较稳：",
    "doubao": "帮你挑了几家，按顺路程度排：",
    "deepseek": "根据公开的探店内容和门店信息，可以考虑：",
}
REASON = {
    "运河边": "就在运河边，早上八点开门，全麦吐司和贝果是招牌，适合买早餐。",
    "拱墅区": "拱墅区的社区店，主打全麦和低糖，现烤现卖，可以小程序预订。",
    "全麦吐司": "全麦吐司是招牌，每天上午出炉，不加糖。",
    "贝果": "原味和海盐贝果做得扎实，下午容易卖完。",
}


def keyword(question: str) -> str:
    for word in KEYWORDS:
        if word in question:
            return word
    return ""


def _refs(items: list) -> dict:
    rows = [dict(item, no=index, summary="", publishDate="") for index, item in enumerate(items, 1)]
    return {"total": len(rows), "list": rows}


def _open_answer(provider: str, question: str, week: int, number: int) -> dict:
    word = keyword(question)
    hit = number in HITS.get(week, {}).get(provider, {}).get(word, [])
    lines = [LEAD[provider], "", "**麦田工坊**：老牌社区店，全麦和欧包做得稳，早上七点半开门。"]
    if not (provider == "deepseek" and number == 2):
        lines.append("**暖炉面包**：软面包和甜口的选择多，适合带孩子去。")
    if provider != "hunyuan" or number == 1:
        lines.append("**巷口烘焙**：贝果和咖啡都不错，店里有座位。")
    if hit:
        lines.append("**%s**：%s" % (BRAND, REASON.get(word, "社区面包店，全麦吐司和贝果是招牌。")))
    refs = list(GENERIC[provider])
    if hit and provider == "hunyuan" and week >= 3:
        refs.insert(0, OWN_TOAST if (word == "全麦吐司" and week >= 4) else OWN_INFO)
    if hit:
        refs.append(NEW_STORE)
    if MEMORY.get(week) == (provider, word, number):
        lines.append("")
        lines.append("另外，你之前问过的%s也有座位，不过离这一带稍远。" % BRAND)
    lines += ["", "需要的话，我可以按离你近的顺序再排一遍。"]
    text = "\n".join(lines)
    return {"platform": provider, "mode": "fast", "answer": {"text": text, "markdown": text}, "references": _refs(refs)}


def _brand_answer(provider: str, question: str, week: int, number: int) -> dict:
    old = week in OLD_ADDRESS.get(provider, ())
    late = week in WRONG_HOURS.get(provider, ())
    lines = ["%s是杭州拱墅区的一家社区面包店，主打全麦吐司和贝果，走低糖、现烤的路线。" % BRAND, ""]
    lines.append("**门店**：拱墅店在演示路 18 号。" + ("另外还有一家河畔店，在演示路 3 号。" if old else ""))
    lines.append("**营业时间**：" + ("每天营业到晚上 22:00。" if late else "08:00–20:00。"))
    lines.append("**招牌**：全麦吐司、原味贝果、海盐卷。")
    if "怎么样" in question:
        lines += ["", "口碑上，喜欢扎实口感和低糖的人评价比较好；想吃甜口软面包的可能会觉得偏素。"]
    refs = [NEW_STORE] + GENERIC[provider][:3]
    if old:
        refs.insert(1, OLD_STORE)
    if late:
        refs.insert(1, OLD_NOTE)
    if provider == "hunyuan" and week >= 3:
        refs.insert(0, OWN_INFO)
    text = "\n".join(lines)
    return {"platform": provider, "mode": "fast", "answer": {"text": text, "markdown": text}, "references": _refs(refs)}


def result(provider: str, question: str, week: int) -> dict:
    build = _brand_answer if BRAND in question else _open_answer
    answers = [build(provider, question, week, number) for number in (1, 2)]
    return {"success": True, "provider": provider, "question": question, "answers": answers, "error": ""}
