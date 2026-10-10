#!/usr/bin/env python3
"""多期回归：一家虚构的面包店连用五期，把工作台上只有用久了才出现的状态都跑出来。
内容按类型登记：公众号文章带排版预览链接，长文和小红书笔记带文字稿；三种类型都会跑到。

  python3 tests/make_demo.py [输出目录]

真实数据目前只有一期，趋势、上一期对比、标记已改后又被重新打开、文章从备稿到存草稿、
待办打勾这些状态没法用真实数据验证，所以保留这份虚构的剧本做回归。
**它不是示例**：店铺和内容全是编的，生成的页面顶部标着“演示数据”，不要拿给商家或对外展示。

全程走真实的脚本（建档、同步工作台、发起、等待、算分、判读、周报），只有“问 AI”和云盘上传是模拟的，
回答内容来自 demo_scenario.py。产物：tests/fixtures/ 里的 page-data.demo.json（工作台）和 report-data.demo.json（最后一期的报告）；
给了输出目录时，再把工作台和五期的报告网页都写进去。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILLS = ROOT / "digital-employee" / "definitions" / "ai-visibility-employee" / "skills"
STATE = SKILLS / "geo-profile" / "scripts" / "geo_state.py"
RUN = SKILLS / "geo-check" / "scripts" / "geo_run.py"
SCORE = SKILLS / "geo-check" / "scripts" / "geo_score.py"
REPORT = SKILLS / "geo-weekly" / "scripts" / "geo_report.py"
sys.path.insert(0, str(HERE))
import demo_scenario as demo  # noqa: E402

FACTS = {
    "from": "backend",
    "segment": "local",
    "brand": {"name": demo.BRAND, "aliases": ["禾木面包", "HEMU BAKERY"], "category": "面包烘焙", "city": "杭州"},
    "audience": [
        {"name": "附近的年轻家庭", "who": "住在拱墅区、家里有小孩的住户", "scene": "想找一家能放心给孩子买早餐的面包店", "worry": "配料干不干净、甜不甜", "basis": "商品评价"},
        {"name": "附近的上班族", "who": "在运河一带上班的人", "scene": "上班路上买早餐，或者提前订好到店取", "worry": "几点开门、能不能提前订", "basis": "订单"},
        {"name": "面包爱好者", "who": "冲着全麦吐司和贝果专门来的人", "scene": "想找某一种面包做得好的店", "worry": "这一款做得扎不扎实", "basis": "商品评价"},
    ],
    "stores": [
        {"name": "拱墅店", "address": "杭州市拱墅区演示路 18 号", "hours": "08:00–20:00", "phone": "", "status": "在营", "source": "有赞后台"},
        {"name": "河畔店", "address": "杭州市拱墅区演示路 3 号", "hours": "", "phone": "", "status": "已关闭", "source": "有赞后台"},
    ],
    "buyEntry": {"miniProgram": "禾木烘焙", "shopUrl": ""},
    "channels": {"wechatOfficial": "禾木烘焙", "douyin": "禾木烘焙"},
    "writingRules": {"tone": "像店主在跟街坊说话，不夸张", "bannedWords": ["第一", "最好", "网红"], "mustInclude": ["门店地址和营业时间", "小程序名称"]},
}
QUESTIONS = [
    ("q01", "open", "地段", "杭州城西有什么好吃的面包店？", "面包爱好者", "哪几家值得去"),
    ("q02", "open", "地段", "运河边附近有没有适合买早餐面包的店？", "附近的上班族", "几点开门"),
    ("q03", "open", "地段", "杭州拱墅区哪家社区面包店值得去？", "附近的年轻家庭", "离家近不近"),
    ("q04", "open", "场合", "杭州有哪些适合带孩子去的面包店？", "附近的年轻家庭", "配料干不干净"),
    ("q05", "open", "场合", "周末想找个能坐下来喝咖啡的面包店，杭州有推荐吗？", "面包爱好者", "有没有座位"),
    ("q06", "open", "场合", "杭州哪里能买到适合送人的面包礼盒？", "附近的年轻家庭", "拿得出手"),
    ("q07", "open", "单品", "杭州哪家的全麦吐司好吃？", "面包爱好者", "是不是真全麦"),
    ("q08", "open", "单品", "杭州哪家的贝果值得买？", "面包爱好者", "做得扎不扎实"),
    ("q09", "open", "渠道", "杭州有没有可以小程序下单、当天送到的面包店？", "附近的上班族", "能不能当天送"),
    ("q10", "open", "渠道", "杭州哪家面包店可以提前预订、到店自取？", "附近的上班族", "能不能提前订"),
    ("b01", "brand", "口碑", "杭州的禾木烘焙这家店怎么样？", "", ""),
    ("b02", "brand", "门店", "禾木烘焙在哪里，几点开门，有什么招牌？", "", ""),
]
RIVALS = [{"name": "麦田工坊"}, {"name": "暖炉面包"}, {"name": "巷口烘焙"}]
ASSETS = {"items": [
    {"platform": "抖音门店", "found": True, "note": "拱墅店有门店页，评价 86 条，团购 2 个；河畔店的旧门店页还在。"},
    {"platform": "公众号", "found": True, "note": "有同名公众号“禾木烘焙”，上岗前最近一篇文章是三个月前发的。"},
    {"platform": "小红书", "found": True, "note": "能搜到顾客写的笔记 20 多篇。"},
]}
DESCRIPTIONS = {
    "hunyuan": "拱墅区的社区面包店，主打全麦吐司和贝果，走低糖、现烤的路线。",
    "doubao": "运河边的社区店，全麦和贝果是招牌，适合买早餐。",
    "deepseek": "主打低糖全麦的社区面包店，喜欢扎实口感的人评价比较好。",
}
BRIEFS = {
    1: "顾客没点名的时候，只有豆包提到你 1 次。点名问的时候，元宝和 DeepSeek 还把已经关掉的河畔店当成在营业，DeepSeek 把关门时间说成了晚上 10 点。先请你确认档案。",
    2: "这一期和上一期差不多。河畔店的旧地址还在被提起，我备了一篇门店信息说明，等你确认。",
    3: "元宝开始引用你公众号上的门店信息，也不再提河畔店了。DeepSeek 还在说旧地址，你标记过已改的那一条我重新打开了。",
    4: "旧地址这一期没有再出现。全麦吐司那篇文章被元宝和 DeepSeek 引用了，这道题第一次有平台提到你。",
    5: "提到你的回答比上一期又多了一些，连续两期往上走。现在只剩营业时间这一处还没改过来。",
}
BODY = """# 带孩子买面包，配料表该怎么看

这是禾木烘焙写给街坊的一篇说明，信息更新于 2026 年 10 月。

## 先看前三位
配料表按用量从多到少排。给孩子买的面包，前三位最好是面粉、水、鸡蛋或牛奶，而不是白砂糖和植物油。

## 我们店里哪几款合适
**全麦吐司**：全麦粉排在配料表第一位，不额外加糖浆。
**原味贝果**：只有面粉、水、酵母、盐和少量糖。

## 在哪买
拱墅店在杭州市拱墅区演示路 18 号，每天 08:00–20:00。也可以在微信小程序“禾木烘焙”提前订，到店自取。
"""
ARTICLES = {
    2: ("禾木烘焙门店信息（2026 年 9 月更新）", "", "AI 还在说已经关掉的河畔店，原文改不了，先发一篇带日期的门店信息说明。"),
    3: ("拱墅区哪里能买到现烤的全麦吐司", "q07", "“哪家的全麦吐司好吃”这道题，三个平台都没提到你，而这是你的招牌。"),
    4: ("运河边上班，早餐面包可以在哪订", "q10", "“提前预订、到店自取”这道题没提到你，而你的小程序支持预订。"),
    5: ("带孩子买面包，配料表该怎么看", "q04", "“适合带孩子去的面包店”这道题没提到你，评价里家长最在意配料。"),
}


def call(script, *args, now, extra=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", GEO_FAKE_NOW=now, **BASE, **(extra or {}))
    proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise SystemExit("%s %s 失败：%s%s" % (script.name, " ".join(args), proc.stdout[:400], proc.stderr[:400]))
    return json.loads(proc.stdout)


def write(name, data):
    path = Path(TMP) / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def judgement(week):
    issues = []
    old = [p for p in ("hunyuan", "deepseek") if week in demo.OLD_ADDRESS[p]]
    if old:
        issues.append({
            "id": "address-old-store", "fact": "address",
            "aiSays": "说还有一家“河畔店”，在演示路 3 号。",
            "truth": "店铺档案里河畔店的状态是已关闭，现在只有拱墅店一家。",
            "evidence": ["b02_%s#1" % p for p in old],
            "sourceType": "map", "sourceTitle": demo.OLD_STORE["title"], "sourceUrl": demo.OLD_STORE["url"],
            "fix": "这是大众点评上还没下线的旧门店页。在大众点评的商家后台把河畔店标记为“已关闭”；高德上如果也有，同样处理。",
        })
    if week in demo.WRONG_HOURS["deepseek"]:
        issues.append({
            "id": "hours-closing-time", "fact": "hours",
            "aiSays": "DeepSeek 说每天营业到晚上 22:00。",
            "truth": "店铺档案里拱墅店的营业时间是 08:00–20:00。",
            "evidence": ["b02_deepseek#1", "b02_deepseek#2"],
            "sourceType": "note", "sourceTitle": demo.OLD_NOTE["title"], "sourceUrl": demo.OLD_NOTE["url"],
            "fix": "这是一篇两年前的探店笔记，原文改不了。门店信息说明里已经写了现在的营业时间；再把抖音和点评门店页上的营业时间补全，让 AI 有更多一致的依据。",
        })
    return {"descriptions": DESCRIPTIONS, "issues": issues}


SHORT_BODY = """这是禾木烘焙写给街坊的一篇说明，信息更新于 2026 年 9 月。

## 现在营业的门店
拱墅店在杭州市拱墅区演示路 18 号，每天 08:00–20:00。

## 怎么买
到店，或者在微信小程序“禾木烘焙”提前订、到店自取。
"""


# 每一期写什么类型：稿子跟着类型走，三种类型都跑到
TYPES = {2: "wechat", 3: "text", 4: "wechat", 5: "text"}
XHS_NOTE = {
    "type": "xhs", "origin": "asked", "title": "拱墅区带娃买面包｜配料表我是这么看的",
    "reason": "你点名要一条小红书笔记，用的是同一个主题。",
    "tip": "配 3 到 4 张图：门头、全麦吐司切面、配料表特写。",
    "tags": ["#杭州面包店", "拱墅区探店", "全麦吐司", "带娃吃什么"],
    "body": "带娃买面包，我只看配料表前三位👇\n\n✅ 面粉、水、鸡蛋或牛奶排前面\n❌ 白砂糖、植物油排前面的先放下\n\n我们家全麦吐司：全麦粉排第一，不额外加糖浆。\n原味贝果：面粉、水、酵母、盐，加一点点糖。\n\n📍拱墅区演示路 18 号，每天 08:00–20:00\n小程序搜“禾木烘焙”可以提前订，到店自取。",
}


def content(week):
    """这一期要登记的内容。类型不同，稿子和要带的东西也不同。"""
    title, question, reason = ARTICLES[week]
    kind = TYPES[week]
    item = {"type": kind, "title": title, "forQuestion": question, "reason": reason, "origin": "weekly",
            "summary": "用顾客的问法起标题，开头两句直接给答案，写清地址、营业时间和小程序名称。"}
    if kind == "wechat":
        # 公众号文章的成品是带排版的页面：登记的是公众号技能给的预览链接，每一篇一个文件名
        item["previewUrl"] = "https://claw-cloud.youzan.com/f/demo/output/geo-%d-preview.html" % week
        item["body"] = "# %s\n\n%s" % (title, SHORT_BODY)
    else:
        item["whereToPost"] = "知乎，同一篇也可以发头条号"
        item["body"] = BODY if week == 5 else "# %s\n\n%s" % (title, SHORT_BODY)
    return item


def actions(week):
    todos = {
        1: [("确认店铺档案：门店、营业时间和三类顾客说得对不对", "确认以后才会开始替你写文章"),
            ("在大众点评把“河畔店”标记为已关闭", "元宝和 DeepSeek 还在把它当成营业中的门店"),
            ("把抖音门店页的营业时间补上", "豆包主要读抖音，门店页上现在没有营业时间")],
        2: [("看一下《禾木烘焙门店信息》这篇文章，没问题就回复“确认”", "发出去以后，AI 介绍你时就有新的依据"),
            ("在大众点评把“河畔店”标记为已关闭", "这一期 AI 还在提这家店")],
        3: [("再检查一下高德上有没有河畔店的门店页", "你标记过已改，但 DeepSeek 这一期还在说河畔店"),
            ("看一下《拱墅区哪里能买到现烤的全麦吐司》，没问题就回复“确认”", "全麦吐司是你的招牌，这道题还没有平台提到你")],
        4: [("把抖音和点评门店页上的营业时间改成 08:00–20:00", "DeepSeek 还在说你营业到晚上 22:00"),
            ("看一下《运河边上班，早餐面包可以在哪订》，没问题就回复“确认”", "这道题还没有平台提到你")],
        5: [("看一下《带孩子买面包，配料表该怎么看》，没问题就回复“确认”", "“适合带孩子去的面包店”这道题还没有平台提到你"),
            ("把抖音和点评门店页上的营业时间改成 08:00–20:00", "这是现在唯一还没改过来的一处")],
    }[week]
    gaps = [{"where": "抖音", "note": "豆包八成的引用来自抖音。你的抖音号最近一个月没有发过视频。"},
            {"where": "知乎", "note": "DeepSeek 常读知乎，这几道题下面还没有提到你的回答。"}]
    payload = {"brief": BRIEFS[week], "todos": [{"text": t, "why": w} for t, w in todos], "gaps": gaps}
    if week not in ARTICLES:
        payload["contentNote"] = "店铺档案还没有确认，先不写内容。"
    return payload


def run_week(week, date):
    day = lambda clock, offset=0: "%sT%s:00+08:00" % (shift(date, offset), clock)  # noqa: E731
    mock = {"MOCK_DEMO_WEEK": str(week), "MOCK_STATE": str(Path(TMP) / ("mock-%d.json" % week)), "MOCK_POLLS": "1"}
    call(RUN, "start", "--phase", "open", "--date", date, now=day("09:04"), extra=mock)
    call(REPORT, "publish", now=day("09:05"))  # 让工作台显示“体检进行中”
    call(RUN, "wait", "--date", date, "--max-seconds", "5", now=day("09:09"), extra=mock)
    call(RUN, "start", "--phase", "brand", "--date", date, now=day("09:10"), extra=mock)
    call(RUN, "wait", "--date", date, "--max-seconds", "5", now=day("09:13"), extra=mock)
    call(SCORE, "score", "--date", date, now=day("09:14"))
    if week == 1:
        call(STATE, "set-rivals", "--file", write("rivals.json", RIVALS), now=day("09:15"))
        call(SCORE, "score", "--date", date, now=day("09:15"))
    call(SCORE, "set-judgement", "--date", date, "--file", write("j%d.json" % week, judgement(week)), now=day("09:18"))
    if week in ARTICLES:
        call(REPORT, "add-content", "--file", write("c%d.json" % week, content(week)), now=day("09:19"))
    call(REPORT, "set-actions", "--date", date, "--file", write("a%d.json" % week, actions(week)), now=day("09:20"))
    published = call(REPORT, "publish", "--date", date, now=day("09:21"))
    assert "warnings" not in published, published
    assert published["published"] and not call(STATE, "status", now=day("09:21"))["workbench"]["pending"], published
    return day


def shift(date, days):
    import datetime as dt
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def main():
    first = demo.WEEKS[0]
    at = lambda clock: "%sT%s:00+08:00" % (first, clock)  # noqa: E731
    call(STATE, "init", "--segment", "local", "--brand", demo.BRAND, now=at("09:01"))
    call(STATE, "set-facts", "--file", write("facts.json", FACTS), now=at("09:02"))
    questions = [{"id": q[0], "kind": q[1], "tag": q[2], "text": q[3], "audience": q[4], "worry": q[5]} for q in QUESTIONS]
    call(STATE, "set-questions", "--file", write("questions.json", questions), now=at("09:03"))
    call(STATE, "set-assets", "--file", write("assets.json", ASSETS), now=at("09:03"))
    first_publish = call(REPORT, "publish", now=at("09:03"))  # 建档后先开通工作台，再去体检
    assert first_publish["firstTime"] and first_publish["periods"] == 0, first_publish
    for week, date in enumerate(demo.WEEKS, 1):
        day = run_week(week, date)
        if week == 1:
            call(STATE, "confirm", now=day("10:30", 2))
            call(REPORT, "mark-todo", "--no", "1", now=day("10:30", 2))
            call(REPORT, "publish", now=day("10:31", 2))
        if week in (2, 3, 4):  # 商家确认；公众号文章存进草稿箱再发，长文由商家自己复制去发
            call(REPORT, "mark-content", "--status", "confirmed", now=day("14:05", 1))
            if TYPES[week] == "wechat":
                call(REPORT, "mark-content", "--channel", "公众号草稿箱", "--ref", "demo-media-%d" % week, now=day("14:10", 1))
            call(REPORT, "mark-content", "--status", "published", "--channel", "公众号" if TYPES[week] == "wechat" else "知乎", now=day("18:30", 1))
            call(REPORT, "mark-todo", "--no", "1" if week == 2 else "2", now=day("14:10", 1))
            call(REPORT, "publish", now=day("18:31", 1))
        if week == 2:
            call(SCORE, "mark-issue", "--no", "1", "--status", "done", now=day("16:40", 3))
            call(REPORT, "publish", now=day("16:41", 3))
        if week == 4:
            listed = call(SCORE, "issues", "--status", "open", now=day("15:19", 1))
            number = next(row["no"] for row in listed["items"] if row["id"] == "address-old-store")
            call(SCORE, "mark-issue", "--no", str(number), "--status", "done", now=day("15:20", 1))
            call(REPORT, "publish", now=day("15:21", 1))
    last = demo.WEEKS[-1]
    # 最后一期商家又点名要了一条小红书笔记：同一个主题，但稿子是另一份
    call(REPORT, "add-content", "--file", write("xhs.json", XHS_NOTE), now="%sT11:40:00+08:00" % last)
    # 带着“演示数据”的标记把最后一期的报告和工作台重新生成一遍（前四期的报告是当时生成的，留着不动）
    built = call(REPORT, "publish", "--date", last, now="%sT11:41:00+08:00" % last, extra={"GEO_DEMO": "1"})
    assert built["published"] and len(built["links"]) == 4, built
    pages = Path(built["file"]).parent

    def embedded(path):
        block = re.search(r'<script type="application/json" id="geo-data">(.*?)</script>', Path(path).read_text(encoding="utf-8"), re.S)
        return json.loads(block.group(1))

    data, report = embedded(built["file"]), embedded(built["reportFiles"][0])
    assert data["store"]["demo"] is True and report["store"]["demo"] is True
    assert sorted(f.name for f in pages.glob("report-*.html")) == ["report-%s.html" % d for d in demo.WEEKS], "每期都要有一份报告"
    (HERE / "fixtures").mkdir(exist_ok=True)
    (HERE / "fixtures" / "page-data.demo.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "fixtures" / "report-data.demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        target.mkdir(parents=True, exist_ok=True)
        for source in pages.glob("*.html"):
            (target / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        print("回归页面（演示数据，不对外）：%s，工作台 1 份、报告 %d 份" % (target, len(demo.WEEKS)))
    print("各期提到本店：" + "、".join("%d/%d" % (p["mention"]["hits"], p["mention"]["valid"]) for p in data["periods"]))
    print("各期本店内容被引用：" + "、".join(str(p["refs"]["own"]) for p in data["periods"]))
    print("最后一期报告里和店铺资料对不上的说法：%d 处" % len(report["issues"]))
    print("工作记录 %d 条，内容 %d 篇：%s" % (len(data["log"]), len(data["contents"]), "、".join("%s（%s）" % (c["typeName"], c["status"]) for c in data["contents"])))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as TMP:
        BASE = {
            "GEO_DATA_ROOT": str(Path(TMP) / "data"),
            "GEO_AI_QUERY_CMD": "%s %s" % (sys.executable, HERE / "mock_ai_query.py"),
            "GEO_POLL_INTERVAL": "0.2",
            "GEO_UPLOAD_CMD": "%s %s" % (sys.executable, HERE / "mock_upload.py"),
            "YOUZAN_AGENT_SESSION_TEMP": str(Path(TMP) / "temp"),
        }
        main()
