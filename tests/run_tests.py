#!/usr/bin/env python3
"""三个技能脚本和工作台网页的本地测试，不联网。

  python3 tests/run_tests.py

用模拟的“问 AI”脚本（mock_ai_query.py）和模拟的云盘上传（mock_upload.py），跑通
“建档 → 开通工作台 → 发起 → 等待 → 算分 → 核对 → 小结和待办 → 同步（出报告）”全过程，
并核对每一步之后“工作台是不是最新的”这个状态。
如果上一级目录里有 2026-10-08 麦的日尝的真实存档，还会回放一遍，核对算出来的数和当时人工统计的是否一致，
并重新生成 示例/麦的日尝/ 里的工作台和第一期报告。
本机有 node 时，再用 page_smoke.cjs 把各种状态下的工作台和报告都渲染一遍。
"""
import hashlib
import json
import os
import re
import shutil
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
REPORT = SKILLS / "geo-workbench" / "scripts" / "geo_report.py"
TEMPLATE = SKILLS / "geo-workbench" / "assets" / "page.html"
ARCHIVE = ROOT.parent / "GEO实测" / "2026-10-08-麦的日尝" / "结果"
SAMPLE = ROOT / "示例" / "麦的日尝"  # 工作台和这一期的报告放在同一个文件夹里，本机打开时能互相跳转
DATE = "2026-10-08"

results = []
PAGES = []  # (状态说明, 网页文件)，最后统一逐页渲染检查
KEEP = Path(tempfile.mkdtemp(prefix="geo-pages-"))


def keep_page(label, file_path):
    target = KEEP / ("%02d.html" % len(PAGES))
    shutil.copyfile(file_path, target)
    PAGES.append((label, target))


def page_json(file_path):
    html = Path(file_path).read_text(encoding="utf-8")
    block = re.search(r'<script type="application/json" id="geo-data">(.*?)</script>', html, re.S)
    return html, block, (json.loads(block.group(1)) if block else {})


def render_fixture(data, out):
    """把一份页面数据直接套进标准模板，不读体检存档。只给测试和演示数据用。"""
    data = json.loads(Path(data).read_text(encoding="utf-8")) if isinstance(data, (str, Path)) else data
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for raw, safe in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        text = text.replace(raw, safe)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(TEMPLATE.read_text(encoding="utf-8").replace("__GEO_DATA__", text), encoding="utf-8")
    return {"file": str(out)}


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(("通过  " if condition else "失败  ") + name + ("" if condition else "  ← " + str(detail)))


def call(script, *args, env, expect=0):
    proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **env))
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"_raw": proc.stdout, "_err": proc.stderr}
    if proc.returncode != expect:
        raise AssertionError("%s %s 退出码 %s，期望 %s：%s" % (script.name, args, proc.returncode, expect, proc.stdout[:300] + proc.stderr[:300]))
    return data


def write(folder, name, data):
    path = Path(folder) / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


MOCK_SHOPS = ("甲记面包", "乙家烘焙", "丙记吐司坊", "手工面包")


def read_all(env, tmp, date, only="", shops=MOCK_SHOPS):
    """模拟读全文的子 Agent：每个平台取回全文，按名字找出推荐的店，写成文件，一次写回。"""
    files = []
    for provider in ("hunyuan", "doubao", "deepseek"):
        out = call(SCORE, "answers", "--provider", provider, "--date", date, *(["--only", only] if only else []), env=env)
        answers = {a["answer"]: [n for n in shops if n in a["text"] and n != "手工面包"] for a in out["answers"] if a["listShops"]}
        files += ["--file", write(tmp, "reading-%s.json" % provider, {"provider": provider, "answers": answers})]
    return call(SCORE, "set-reading", "--date", date, *files, env=env)


def wait_all(env, date):
    for _ in range(40):
        progress = call(RUN, "wait", "--date", date, "--max-seconds", "5", env=env)
        if not progress["running"]:
            return progress
    raise AssertionError("等待超时")


def base_env(tmp, **extra):
    env = {
        "GEO_DATA_ROOT": str(Path(tmp) / "data"),
        "MOCK_STATE": str(Path(tmp) / "mock-state.json"),
        "GEO_AI_QUERY_CMD": "%s %s" % (sys.executable, HERE / "mock_ai_query.py"),
        "GEO_POLL_INTERVAL": "0.3",
        "GEO_UPLOAD_CMD": "%s %s" % (sys.executable, HERE / "mock_upload.py"),
        "MOCK_UPLOAD_LOG": str(Path(tmp) / "uploads.log"),
        "YOUZAN_AGENT_SESSION_TEMP": str(Path(tmp) / "temp"),
    }
    env.update(extra)
    return env


SYNTHETIC_FACTS = {
    "segment": "local",
    "brand": {"name": "示例小店", "aliases": ["Sample Shop"], "category": "面包", "city": "测试市"},
    "stores": [{"name": "测试路店", "address": "测试市测试路 1 号", "hours": "09:00-20:00", "status": "在营", "source": "有赞后台"}],
    "channels": {"wechatOfficial": "示例小店官方号"},
}
SYNTHETIC_QUESTIONS = [
    {"id": "q01", "kind": "open", "tag": "品类", "text": "测试市哪家面包店好吃？", "audience": "附近居民", "worry": "口碑"},
    {"id": "q02", "kind": "open", "tag": "地段", "text": "测试路附近有什么面包店？", "audience": "不存在的人群"},
    {"id": "q03", "kind": "open", "tag": "场景", "text": "这是一道用来测同名的题目"},
    {"id": "q04", "kind": "open", "tag": "场景", "text": "这道题会在某个平台挂起不返回"},
    {"id": "q05", "kind": "open", "tag": "场景", "text": "这道题会在某个平台失败返回"},
    {"id": "q06", "kind": "open", "tag": "单品", "text": "测试市哪家的吐司好吃？"},
    {"id": "q07", "kind": "open", "tag": "单品", "text": "测试市哪家的可颂好吃？"},
    {"id": "q08", "kind": "open", "tag": "渠道", "text": "测试市有能外卖的面包店吗？"},
    {"id": "q09", "kind": "open", "tag": "渠道", "text": "测试市有能小程序下单的面包店吗？"},
    {"id": "q10", "kind": "open", "tag": "品类", "text": "测试市面包店推荐几家"},
    {"id": "b01", "kind": "brand", "tag": "口碑", "text": "示例小店这家面包店怎么样？"},
    {"id": "b02", "kind": "brand", "tag": "门店", "text": "示例小店在哪，几点开门？"},
]


def test_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp, MOCK_HANG="deepseek:挂起", MOCK_FAIL="hunyuan:失败", GEO_DEADLINE_SECONDS="2")
        check("没建档时 status 给出提示", call(STATE, "status", env=env)["exists"] is False)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        facts = call(STATE, "set-facts", "--file", write(tmp, "facts.json", SYNTHETIC_FACTS), env=env)
        check("资料来自公开信息时：整份等商家确认，确认前不能写内容，并列出要确认的是哪几样",
              (facts["confirmed"], facts["factsFrom"], facts["pendingConfirm"], facts["canWrite"]) == (False, "public", True, False)
              and facts["segment"] == "local" and {"brand", "stores", "channels"} <= set(facts["toConfirm"]), facts)
        check("改了店铺资料就记下“待同步”，并提醒去同步",
              facts["workbench"]["pending"] == ["店铺资料"] and not facts["workbench"]["upToDate"] and "publish" in facts["next"], facts.get("workbench"))
        error = call(REPORT, "links", env=env, expect=2)
        check("工作台没开通时要不到链接", "publish" in error.get("error", ""), error)

        bad = [dict(SYNTHETIC_QUESTIONS[0], text="示例小店附近还有什么面包店？")] + SYNTHETIC_QUESTIONS[1:]
        error = call(STATE, "set-questions", "--file", write(tmp, "bad.json", bad), env=env, expect=2)
        check("不带店名的问题里出现店名会被拒绝", "店名" in error.get("error", ""), error)

        saved = call(STATE, "set-questions", "--file", write(tmp, "questions.json", SYNTHETIC_QUESTIONS), env=env)
        check("问题库 10 加 2 写入成功", (saved["openQuestions"], saved["brandQuestions"], saved["questionsVersion"]) == (10, 2, 1), saved)
        check("没写差异点、题没写替谁问，都会提醒；不再按顾客类型数题",
              any("不一样" in w for w in saved["warnings"]) and any("Q03" in w and "Q10" in w and "Q02" not in w for w in saved["warnings"])
              and not any("顾客" in w for w in saved["warnings"]), saved["warnings"])
        shown = call(STATE, "show", "--part", "questions", env=env)["questions"]["items"]
        check("替谁问是出题时顺手写的，原样保留，不用先归纳顾客类型", shown[1]["audience"] == "不存在的人群" and shown[0]["audience"] == "附近居民")
        relabel = [dict(q, tag="改标签") if q["id"] == "q06" else q for q in SYNTHETIC_QUESTIONS]
        again = call(STATE, "set-questions", "--file", write(tmp, "relabel.json", relabel), env=env)
        check("只改标注不算口径变化", again["questionsVersion"] == 1 and again["changed"] is True, again)
        call(STATE, "set-rivals", "--file", write(tmp, "rivals.json", [{"name": "甲记面包"}, {"name": "乙家烘焙"}, {"name": "示例小店"}]), env=env)
        check("竞品里的本店会被去掉", call(STATE, "status", env=env)["rivals"] == ["甲记面包", "乙家烘焙"])

        first = call(REPORT, "publish", env=env)
        check("没体检过也能开通工作台", first["published"] and first["firstTime"] and first["periods"] == 0
              and first["pageUrl"].endswith("/ai-visibility.html"), first)
        check("还没体检时，同步后给出工作台三个页面的链接，没有报告", list(first["links"]) == ["工作台", "内容", "监测设置"]
              and first["links"]["监测设置"] == first["pageUrl"] + "#/settings" and first["reportUrl"] == "" and first["reportFiles"] == [], first["links"])
        check("同步结果里写明这次同步了什么", first["synced"] == ["店铺资料", "问题库", "同类店"], first["synced"])
        status = call(STATE, "status", env=env)
        check("同步后工作台是最新的，不再提醒", status["workbench"]["upToDate"] and "next" not in status, status)
        keep_page("刚建档", first["file"])

        check("页签输出告诉员工用签名命令固定并读回", "claw-admin-request" in first["tabSetup"] and "读回" in first["tabSetup"], first["tabSetup"])
        blocked = call(RUN, "start", "--phase", "open", "--date", DATE, env=env, expect=2)
        check("首次初始化未经确认不发查询", "商家确认" in blocked.get("error", "") and not Path(env["MOCK_STATE"]).exists(), blocked)
        early = call(STATE, "set-schedule", "--status", "on", env=env, expect=2)
        check("商家确认之前不能开启每周体检", "确认" in early.get("error", ""), early)
        consent = call(STATE, "confirm-monitoring", env=env)
        check("监测方向确认与第三方账号确认分开", consent["firstCheckPending"] is False and consent["confirmed"] is False, consent)
        check("工作台页签配置保留对话和真实工作台链接", first["tabConfiguration"]["tabs"][0]["tabKey"] == "conversation"
              and first["tabConfiguration"]["tabs"][1]["tabUrl"] == first["pageUrl"] + "#/overview", first["tabConfiguration"])

        started = call(RUN, "start", "--date", DATE, env=env)
        check("一次发出全部 36 条查询：不带店名的 30 条和带店名的 6 条一起",
              started["started"] == 36 and started["running"] == 36 and not started["finished"]
              and started["phases"]["open"]["total"] == 30 and started["phases"]["brand"]["total"] == 6, started)
        waiting = call(RUN, "status", "--date", DATE, env=env)
        check("运行中的提示写明“不要当成出错”", "不要把它当成出错" in waiting["next"], waiting["next"])
        check("发起体检后工作台又变成待同步", call(STATE, "status", env=env)["workbench"]["pending"] == ["体检进度"])
        running = call(REPORT, "publish", env=env)
        check("体检进行中同步一次，工作台上是进度而不是旧结果",
              running["progress"].get("running") == 36 and running["periods"] == 0 and running["firstTime"] is False, running)
        keep_page("体检进行中", running["file"])
        progress = wait_all(env, DATE)
        check("挂起的查询到时限后记为缺失，失败的查询也记为缺失",
              sorted(progress["missing"]) == ["q04_deepseek", "q05_hunyuan"] and progress["done"] == 34, progress)
        check("全部返回，整轮结束，下一步算分", progress["finished"] is True and "score" in progress["next"], progress)
        noop = call(RUN, "start", "--date", DATE, env=env)
        check("重复发起不会重复提问", noop["started"] == 0, noop)

        digest = call(SCORE, "score", "--date", DATE, env=env)
        check("提及统计：按名字算，同名的也先算进去（豆包 3/20），其余为 0",
              digest["mention"]["byProvider"] == {"元宝": "0/18", "豆包": "3/20", "DeepSeek": "0/18"} and "memoryFlagged" not in digest, digest["mention"])
        check("本店公众号被引用 12 次，门店页 12 次", (digest["refs"]["own"], digest["refs"]["storePages"]) == (12, 12), digest["refs"])
        check("还没读全文时，同类店次数都是 0，不按名字另算", [r["count"] for r in digest["rivals"]] == [0, 0], digest["rivals"])
        check("对照表里没有的网站，被引用两次以上的单独成一行；天眼查归到企业信息",
              {"测试论坛", "企业信息"} <= {x["type"] for x in json.loads(
                  (Path(env["GEO_DATA_ROOT"]) / "runs" / DATE / "summary.json").read_text(encoding="utf-8"))["sources"]["all"]})
        check("算分输出的“读哪里”按平台给，没有几个平台合起来的数",
              "topSources" not in digest and sorted(digest["sourcesByProvider"]) == sorted(["元宝", "豆包", "DeepSeek"]), digest.get("sourcesByProvider"))
        check("缺失 2 条不到四分之一，数据算完整", digest["complete"] is True and len(digest["missing"]) == 2)
        check("还没读全文时：提到了谁不出数，next 让员工派子 Agent 读全部题",
              digest["shops"] == [] and digest["shopsPending"] == 56 and "读全部题" in digest["next"], digest.get("next"))
        full = call(SCORE, "answers", "--provider", "doubao", "--date", DATE, env=env)
        check("给子 Agent 的全文：带店铺资料、同类店、每个回答的全文，标明哪些要写店名",
              full["store"]["name"] == "示例小店" and [r["name"] for r in full["rivals"]] == ["甲记面包", "乙家烘焙"]
              and any(a["listShops"] for a in full["answers"]) and any(a["withBrandName"] and not a["listShops"] for a in full["answers"])
              and all(a["text"] for a in full["answers"]), [a["answer"] for a in full["answers"]][:4])
        tag = next(a["answer"] for a in full["answers"] if a["listShops"])
        bad = call(SCORE, "set-reading", "--date", DATE, "--file", write(tmp, "bad-shops.json", {"answers": {tag: ["丁记面包"]}}), env=env, expect=2)
        check("写回的店名原文里找不到，整份退回", "找不到" in bad.get("error", ""), bad)
        own = call(SCORE, "set-reading", "--date", DATE, "--file", write(tmp, "own-shops.json", {"answers": {tag: ["示例小店"]}}), env=env, expect=2)
        check("本店不能写进“提到了谁”", "本店" in own.get("error", ""), own)
        partial = call(SCORE, "set-reading", "--date", DATE, "--file", write(tmp, "part-shops.json", {"answers": {tag: ["甲记面包"]}}), env=env)
        check("只写了一部分：保存，并列出还没写的回答", partial["stillMissing"] and "补齐" in partial["next"], partial.get("next"))
        merged = call(SCORE, "set-reading", "--date", DATE, "--file", write(tmp, "alias-shops.json",
                      {"answers": {tag: ["甲记"]}, "names": {"甲记": ["甲记面包"]}}), env=env)
        check("同一家店的不同写法：在 names 里写上原文的写法就能对上", merged["ok"], merged)
        done = read_all(env, tmp, DATE)
        check("三个平台都写回后，没有漏读的回答", done["stillMissing"] == [] and "score" in done["next"], done)
        same = next(a for a in full["answers"] if "养老服务站" in a["text"])
        elder = next(r for r in same["refs"] if "养老" in r["title"])
        bakery = next(r for r in same["refs"] if "工商信息" in r["title"])
        check("给子 Agent 的全文里标明哪些回答按名字算作提到你、哪些引用按标题算作和你有关",
              same["mentionedByName"] and elder["relation"] == "about" and bakery["relation"] == "", same["refs"])
        wrong = call(SCORE, "set-reading", "--date", DATE, "--file", write(tmp, "wrong.json", {"notUs": [tag], "refsNotUs": ["https://nowhere.cn/x"]}), env=env, expect=2)
        check("复核写错了：没算作提到你的回答、这一期没有的引用，都退回", "不用写进 notUs" in wrong.get("error", "") and "没有这条引用" in wrong.get("error", ""), wrong)
        call(SCORE, "set-reading", "--date", DATE, "--file", write(tmp, "review.json",
             {"notUs": [same["answer"]], "refsNotUs": [elder["url"]], "refsAboutUs": [bakery["url"]]}), env=env)
        digest = call(SCORE, "score", "--date", DATE, env=env)
        check("复核后：同名的不算提到你（豆包 2/20），并在 notes 里说明", digest["mention"]["byProvider"]["豆包"] == "2/20"
              and digest["notUs"] == [same["answer"]] and any("同名" in n for n in digest["notes"]), digest["mention"])
        about = json.loads((Path(env["GEO_DATA_ROOT"]) / "runs" / DATE / "summary.json").read_text(encoding="utf-8"))["refs"]["aboutItems"]
        check("复核后：同名的引用不算和你有关，没写店名但写的是你的算进来",
              [x["title"] for x in about] == ["测试路面包店工商信息"], [x["title"] for x in about])
        check("同类店次数和“提到了谁”用同一份店名", digest["rivals"][0] == {"name": "甲记面包", "count": 56}, digest["rivals"])
        shops = {x["name"]: x["count"] for x in digest["shops"]}
        check("提到了谁：按员工读出来的店计数，不只是同类店；不含本店，不含不是店的词",
              shops.get("甲记面包") == 56 and shops.get("丙记吐司坊") == 6 and "示例小店" not in shops and "手工面包" not in shops, digest["shops"])
        tag_brand = next(a["answer"] for a in full["answers"] if a["withBrandName"])
        quote = next(a["text"] for a in full["answers"] if a["answer"] == tag_brand).split("\n")[1][:12]
        finding = {"kind": "misread", "title": "豆包把你和别的店放在一起介绍", "detail": "带着店名问豆包时，它先推荐了别的店，再说到你。",
                   "action": "在门店页写清招牌", "evidence": [{"answer": tag_brand, "quote": quote}]}
        too_many = call(SCORE, "set-findings", "--date", DATE, "--file", write(tmp, "f6.json", {"items": [finding] * 6}), env=env, expect=2)
        check("发现最多 5 条", "最多 5 条" in too_many.get("error", ""), too_many)
        fake = call(SCORE, "set-findings", "--date", DATE, "--file", write(tmp, "fx.json",
                    {"items": [dict(finding, evidence=[{"answer": tag_brand, "quote": "这句话回答里没有"}])]}), env=env, expect=2)
        check("发现的原话在回答里找不到，整份退回", "找不到这句原话" in fake.get("error", ""), fake)
        saved = call(SCORE, "set-findings", "--date", DATE, "--file", write(tmp, "f1.json", {"items": [finding]}), env=env)
        check("发现保存成功", saved["findings"] == 1, saved)

        material = call(SCORE, "brand-digest", "--date", DATE, env=env)
        tags = [row["answer"] for row in material["answers"]]
        check("核对材料包含全部带店名的回答和提到本店的回答", "b01_hunyuan#1" in tags and "q02_doubao#1" in tags and len(tags) == 15, tags)
        issue = {"id": "hours-wrong", "fact": "hours", "aiSays": "营业到 20:00", "truth": "营业到 21:00", "fix": "改门店页的营业时间",
                 "evidence": ["b01_hunyuan#1"], "sourceType": "map", "sourceTitle": "示例小店(测试路店)", "sourceUrl": "https://m.dianping.com/shop/1"}
        error = call(SCORE, "set-judgement", "--date", DATE, "--file",
                     write(tmp, "j-bad.json", {"issues": [dict(issue, sourceUrl="https://example.com/made-up")]}), env=env, expect=2)
        check("编造的出处链接会被拒绝", "不在这些回答的引用列表里" in error.get("error", ""), error)
        error = call(SCORE, "set-judgement", "--date", DATE, "--file",
                     write(tmp, "j-bad2.json", {"issues": [dict(issue, evidence=["b09_hunyuan#1"])]}), env=env, expect=2)
        check("不存在的证据编号会被拒绝", "证据编号不存在" in error.get("error", ""), error)
        judged = call(SCORE, "set-judgement", "--date", DATE, "--file",
                      write(tmp, "j.json", {"descriptions": {"hunyuan": "一家社区面包店"}, "issues": [issue]}), env=env)
        check("记下 1 条和店铺资料对不上的说法", judged["issuesOpen"] == 1)
        listed = call(SCORE, "issues", env=env)
        check("每条对不上的说法有一个固定序号", [(row["no"], row["id"], row["status"]) for row in listed["items"]] == [(1, "hours-wrong", "open")], listed)
        error = call(SCORE, "mark-issue", "--no", "9", "--status", "done", env=env, expect=2)
        check("不存在的序号会被拒绝", "没有这一条" in error.get("error", ""), error)
        marked = call(SCORE, "mark-issue", "--no", "1", "--status", "done", env=env)
        check("按序号标记已改，并提醒同步工作台", marked["id"] == "hours-wrong" and marked["issuesOpen"] == 0 and "publish" in marked["next"], marked)
        reopened = call(SCORE, "set-judgement", "--date", DATE, "--file", write(tmp, "j.json", {"issues": [issue]}), env=env)
        check("标记已改后 AI 仍这么说，会重新打开", reopened["reopened"] == ["hours-wrong"] and reopened["issuesOpen"] == 1, reopened)
        call(SCORE, "mark-issue", "--no", "1", "--status", "dismissed", env=env)
        check("核实后不算错的，不再待处理", call(SCORE, "issues", "--status", "open", env=env)["items"] == [])
        again = call(SCORE, "set-judgement", "--date", DATE, "--file", write(tmp, "j.json", {"issues": [issue]}), env=env)
        check("下一期还对不上时回到待处理，序号不变",
              again["issuesOpen"] == 1 and again["reopened"] == [] and call(SCORE, "issues", env=env)["items"][0]["no"] == 1, again)

        compared = call(REPORT, "compare", "--date", DATE, env=env)
        check("第一期没有可比的上一期", compared["previous"] == "" and compared["trend"] == "observe", compared)
        check("对比结果只带给员工的提示，不带页面上给商家看的说明；也不把“还有几处对不上”当成一项来报",
              compared["notes"] and "readerNotes" not in compared and "issuesOpen" not in compared, sorted(compared))
        error = call(REPORT, "set-actions", "--date", DATE, "--file",
                     write(tmp, "a-old.json", {"brief": "x", "article": {"status": "preview", "title": "测试文章"}}), env=env, expect=2)
        check("写好的内容不能再塞进本期动作里，要单独登记", "add-content" in error.get("error", ""), error)
        error = call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a-long.json", {
            "brief": "长" * 241, "todos": [{"text": "一"}, {"text": "二"}, {"text": "三"}, {"text": "四"}]}), env=env, expect=2)
        check("小结超长、建议超过三件会整份退回，不从中间截断",
              "本期小结最多 240 字" in error.get("error", "") and "建议最多三件" in error.get("error", "")
              and not (Path(env["GEO_DATA_ROOT"]) / "runs" / DATE / "actions.json").exists(), error)
        acted = call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a.json", {
            "brief": "本期小结：只有豆包提到你。",
            "todos": [{"text": "一"}, {"text": "二"}, {"text": "三"}]}), env=env)
        check("写了小结就没有提醒", acted["brief"] is True and acted["warnings"] == [], acted)
        gone = subprocess.run([sys.executable, str(REPORT), "mark-todo", "--no", "1"], capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **env))
        check("建议不是要打勾的清单：没有给待办打勾的命令了", gone.returncode != 0 and "mark-todo" in gone.stderr, gone.stderr[-120:])
        call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a2.json", {"gaps": [{"where": "公众号", "note": "没有文章被引用"}]}), env=env)
        shown = call(REPORT, "show", env=env)
        check("问“写什么、往哪发”时有数可答：show 的各平台读哪里和算分输出的一样",
              shown["sourcesByProvider"] == call(SCORE, "score", "--date", DATE, env=env)["sourcesByProvider"]
              and set(shown["refs"]) == {"total", "own", "storePages", "aboutStore"}, shown.get("sourcesByProvider"))
        check("只传要改的部分，其余保持不变（小结、建议都在）；建议只有做什么和为什么",
              shown["brief"].startswith("本期小结") and [sorted(t) for t in shown["todos"]] == [["text", "why"]] * 3
              and [t["text"] for t in shown["todos"]] == ["一", "二", "三"] and len(shown["gaps"]) == 1 and shown["contents"] == [], shown)

        # ── 内容：按类型登记，稿子跟着类型走 ──
        long_text = "# 测试市哪家的吐司好吃\r\n\r\n第一段  \n\n\n\n第二段 <b>不是标签</b>\n\n" + "示例小店在测试市测试路 1 号，每天 9 点到 20 点营业。" * 4
        clean_text = "# 测试市哪家的吐司好吃\n\n第一段\n\n第二段 <b>不是标签</b>\n\n" + "示例小店在测试市测试路 1 号，每天 9 点到 20 点营业。" * 4
        body_file = Path(tmp) / "draft.md"
        body_file.write_text(long_text, encoding="utf-8")
        text_item = {"type": "text", "title": "测试市哪家的吐司好吃", "reason": "这道题没有平台提到你", "forQuestion": "Q06",
                     "whereToPost": "知乎", "bodyFile": str(body_file)}
        error = call(REPORT, "add-content", "--file", write(tmp, "c-text.json", text_item), env=env, expect=2)
        check("资料不是后台读的、商家也没确认时，不能登记内容", "确认" in error.get("error", ""), error)
        call(STATE, "confirm", env=env)
        warned = call(REPORT, "publish", "--date", DATE, env=env)
        check("这一期收尾了，却既没登记内容也没写原因，同步时会提醒",
              any("add-content" in w for w in warned.get("warnings", [])), warned.get("warnings"))
        error = call(REPORT, "add-content", "--file", write(tmp, "c-notype.json", dict(text_item, type="")), env=env, expect=2)
        check("登记内容要写明类型", "wechat" in error.get("error", "") and "小红书笔记" in error.get("error", ""), error)
        error = call(REPORT, "add-content", "--file", write(tmp, "c-short.json", {"type": "text", "title": "只有标题", "body": "太短"}), env=env, expect=2)
        check("长文正文太短会退回，并说清至少几个字", "至少 80 字" in error.get("error", ""), error)
        error = call(REPORT, "add-content", "--file", write(tmp, "c-nobody.json", {"type": "text", "title": "只有标题"}), env=env, expect=2)
        check("长文必须带上稿子", "必须带上稿子正文" in error.get("error", ""), error)
        added = call(REPORT, "add-content", "--file", write(tmp, "c-text.json", text_item), env=env)
        check("登记长文：有固定序号、带全文、等商家确认，并提醒别在对话里再贴一遍",
              (added["no"], added["type"], added["typeName"], added["status"], added["origin"], added["period"], added["forQuestion"]) == (1, "text", "长文", "preview", "weekly", DATE, "q06")
              and added["bodyChars"] == len(clean_text) and "不要在对话里再贴一遍" in added["next"], added)
        error = call(REPORT, "add-content", "--file", write(tmp, "c-text.json", text_item), env=env, expect=2)
        check("同一类型同一标题不会重复登记", "已经登记过" in error.get("error", ""), error)

        note = {"type": "xhs", "origin": "asked", "title": "测试市吐司｜我只认这一家", "tags": ["#测试市美食", "吐司", "吐司", " 探 店 "],
                "tip": "配三张图", "body": "吐司控看过来👇\n\n#测试市 这家每天现烤\n✅ 全麦粉排配料表第一\n📍测试路 1 号，9 点到 20 点"}
        error = call(REPORT, "add-content", "--file", write(tmp, "c-xhs-long.json", dict(note, title="这个标题一共有二十一个字所以小红书是放不下去的")), env=env, expect=2)
        check("小红书笔记的标题超过 20 个字会被退回，不悄悄截断", "最多 20 个字" in error.get("error", ""), error)
        error = call(REPORT, "add-content", "--file", write(tmp, "c-xhs-body.json", dict(note, body="长" * 1001)), env=env, expect=2)
        check("小红书笔记的正文超过 1000 字会被退回", "最多 1000 字" in error.get("error", ""), error)
        xhs = call(REPORT, "add-content", "--file", write(tmp, "c-xhs.json", note), env=env)
        check("登记小红书笔记：话题去掉 # 和重复的，商家点名要的不占每期名额",
              (xhs["no"], xhs["typeName"], xhs["origin"], xhs["tags"], xhs["tip"]) == (2, "小红书笔记", "asked", ["测试市美食", "吐司", "探店"], "配三张图"), xhs)

        wechat = {"type": "wechat", "title": "测试市哪家的吐司好吃", "previewUrl": "https://claw-cloud.youzan.com/f/x/output/geo-3-preview.html"}
        error = call(REPORT, "add-content", "--file", write(tmp, "c-wx-none.json", {"type": "wechat", "title": "只有标题"}), env=env, expect=2)
        check("公众号文章要带排版预览链接", "previewUrl" in error.get("error", "") and "长文" in error.get("error", ""), error)
        error = call(REPORT, "add-content", "--file", write(tmp, "c-wx-http.json", dict(wechat, previewUrl="http://x/y.html")), env=env, expect=2)
        check("预览链接必须是 https", "https" in error.get("error", ""), error)
        wx = call(REPORT, "add-content", "--file", write(tmp, "c-wx.json", wechat), env=env)
        check("登记公众号文章：同一个标题可以有不同类型的稿子，公众号这篇不用带文字稿",
              (wx["no"], wx["typeName"], wx["bodyChars"], wx["previewUrl"]) == (3, "公众号文章", 0, wechat["previewUrl"]), wx)
        error = call(REPORT, "add-content", "--file", write(tmp, "c-wx2.json", dict(wechat, title="另一篇公众号文章")), env=env, expect=2)
        check("两篇用了同一个预览链接会被退回（新的预览把上一篇盖掉了）", "盖掉了" in error.get("error", ""), error)
        error = call(REPORT, "add-content", "--file", write(tmp, "c-cap.json", {"type": "text", "title": "这一期的第三篇", "body": clean_text}), env=env, expect=2)
        check("每期主动写的最多两篇", "每期最多 2 篇" in error.get("error", ""), error)

        error = call(REPORT, "mark-content", "--no", "3", "--channel", "公众号草稿箱", env=env, expect=2)
        check("没确认的内容不能记成已放进草稿箱", "还没有经过商家确认" in error.get("error", ""), error)
        call(REPORT, "mark-content", "--no", "3", "--status", "confirmed", env=env)
        placed = call(REPORT, "mark-content", "--no", "3", "--channel", "公众号草稿箱", "--ref", "media-123", env=env)
        check("确认后可以记下放到了哪和对方给的编号，状态不变",
              (placed["status"], placed["channels"], placed["ref"]) == ("confirmed", ["公众号草稿箱"], "media-123") and "publish" in placed["next"], placed)
        call(REPORT, "mark-content", "--no", "1", "--status", "confirmed", env=env)
        edited = call(REPORT, "add-content", "--file", write(tmp, "c-edit.json", {"no": 1, "title": "测试市吐司哪家好"}), env=env)
        check("确认后又改稿，变回等商家确认，没传的部分不变",
              edited["status"] == "preview" and "note" in edited and edited["title"] == "测试市吐司哪家好" and edited["bodyChars"] == len(clean_text), edited)
        error = call(REPORT, "add-content", "--file", write(tmp, "c-retype.json", {"no": 1, "type": "xhs"}), env=env, expect=2)
        check("不能把一种类型改成另一种，稿子不一样要另外登记", "不能改成别的类型" in error.get("error", ""), error)
        call(REPORT, "mark-content", "--status", "dropped", "--no", "2", env=env)
        shown = call(REPORT, "show", env=env)
        ledger = json.loads(Path(shown["contentsFile"]).read_text(encoding="utf-8"))
        check("员工直接读内容账本就能拿到全文，show 告诉它账本在哪和下一篇的序号",
              next(a for a in ledger["items"] if a["no"] == 1)["body"] == clean_text and shown["nextNo"] == 4
              and [(a["no"], a["status"]) for a in shown["contents"]] == [(3, "confirmed"), (2, "dropped"), (1, "preview")], shown.get("contents"))
        gone = subprocess.run([sys.executable, str(REPORT), "contents"], capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **env))
        check("没有 contents 命令了，内容直接读账本", gone.returncode != 0, gone.stderr[-120:])
        check("show 里能看到工作台还有哪些变化没同步", "内容" in shown["workbench"]["pending"])

        built = call(REPORT, "publish", "--date", DATE, env=env)
        check("再次同步：链接不变，不再算第一次开通，这一期登记过内容就不再提醒",
              built["published"] and built["pageUrl"] == first["pageUrl"] and built["firstTime"] is False
              and "内容" in built["synced"] and "warnings" not in built, built)
        check("同步后没有待同步的变化", call(REPORT, "links", env=env)["upToDate"] is True)
        keep_page("一期（合成数据）", built["file"])
        check("这一期的报告是独立的文件、有自己的链接；发给商家的是在工作台里打开它的地址",
              built["reportFileUrl"].endswith("/report-%s.html" % DATE) and built["reportUrl"] == first["pageUrl"] + "#/report/" + DATE
              and built["links"]["这一期的报告"] == built["reportUrl"]
              and [Path(f).name for f in built["reportFiles"]] == ["report-%s.html" % DATE] and "reportUrl" in built["next"], built)
        listed = call(REPORT, "links", env=env)
        check("要链接时：每一期都有“在工作台里打开”的地址，报告文件自己的链接另外给",
              listed["reports"] == {DATE: built["reportUrl"]} and listed["reportFiles"] == {DATE: built["reportFileUrl"]}
              and listed["reportUrl"] == built["reportUrl"] and listed["reportFileUrl"] == built["reportFileUrl"], listed)
        keep_page("一期的报告（合成数据）", built["reportFiles"][0])
        asked = call(STATE, "status", env=env)
        check("第一份报告出来后，提醒问商家要不要开启每周体检", asked["schedule"] == "" and "每周体检" in asked.get("next", ""), asked)
        turned_on = call(STATE, "set-schedule", "--status", "on", env=env)
        check("商家同意后记下每周体检已开启，不再提醒", turned_on["schedule"] == "on" and "每周体检" not in turned_on.get("next", ""), turned_on)
        html, block, data = page_json(built["file"])
        check("工作台生成成功，占位符已替换", "__GEO_DATA__" not in html and data.get("kind") == "workbench" and data.get("runDate") == DATE)
        check("网页里的数据块不含能提前结束标签的字符", block is not None and "<" not in block.group(1))
        check("建议最多保留三件", len(data["actions"]["todos"]) == 3)
        check("工作台数据里有小结，体检做完后不再显示进行中",
              data["actions"]["brief"].startswith("本期小结") and data["progress"] == {}, data["actions"])
        check("工作台上的内容：按类型带各自的东西，不发了的不带稿子",
              [(c["no"], c["typeName"], c["status"], bool(c["body"]), bool(c["previewUrl"])) for c in data["contents"]]
              == [(3, "公众号文章", "confirmed", False, True), (2, "小红书笔记", "dropped", False, False), (1, "长文", "preview", True, False)]
              and data["periods"][-1]["content"]["count"] == 2 and data["contentTypes"]["xhs"] == "小红书笔记", data["contents"])
        period = data["periods"][-1]
        check("工作台只放跨期的东西：每期一行，带报告的链接，不带回答原文和逐题明细",
              len(data["periods"]) == 1 and (period["no"], period["reportFile"], period["reportUrl"]) == (1, "report-%s.html" % DATE, built["reportFileUrl"])
              and "answers" not in data and "dots" not in period and "issues" not in data and data["latest"]["rivals"][0]["name"] == "甲记面包", period)
        check("监测设置：问题、同类店，和员工另外记下的信息",
              len(data["settings"]["questions"]) == 12 and [r["name"] for r in data["settings"]["rivals"]] == ["甲记面包", "乙家烘焙"]
              and data["settings"]["extras"]["wechatOfficial"] == "示例小店官方号" and data["settings"]["from"] == "public", data["settings"]["extras"])
        check("工作台首页只留跨期的几样：不带工作记录、不带某一期的说明；汇总数只有期数和内容篇数",
              "log" not in data and "notes" not in data and not (Path(env["GEO_DATA_ROOT"]) / "log.json").exists()
              and data["totals"] == {"periods": 1, "contents": 2, "contentsWaiting": 1, "contentsPublished": 0}, data["totals"])
        check("问“你都做了哪些事”时有数可答：几期、几篇内容、几篇等确认", shown["totals"]["periods"] == 1 and call(REPORT, "show", env=env)["totals"]["contents"] == 2)
        _, _, report = page_json(built["reportFiles"][0])
        check("报告带这一期的全部证据：逐题圆点、回答原文、同类店、内容来源",
              report["kind"] == "report" and report["period"] == {"date": DATE, "no": 1, "latest": True}
              and report["dots"]["q02"]["doubao"] == "hh" and report["dots"]["q03"]["doubao"] == "nn"
              and len(report["answers"]["q02_doubao"]) == 2 and report["rivals"][0]["name"] == "甲记面包" and report["sources"]["doubao"]
              and {(x["name"], x["rival"]) for x in report["shops"]} >= {("甲记面包", True), ("乙家烘焙", True), ("丙记吐司坊", False)}
              and report["shopsPending"] == 0 and report["findings"][0]["kindName"] == "认错了你"
              and report["findings"][0]["evidence"][0]["provider"] == "doubao", report["period"])
        check("缺失的查询在报告的圆点里留空", report["dots"].get("q04", {}).get("deepseek", "") == "")
        check("和店铺资料对不上的说法只出现在报告里，带固定序号",
              [(i["no"], i["id"]) for i in report["issues"]] == [(1, "hours-wrong")] and report["workbenchUrl"] == first["pageUrl"], report["issues"])
        check("报告里有这一期的小结、建议和写的内容", report["actions"]["brief"].startswith("本期小结") and len(report["actions"]["todos"]) == 3
              and [c["no"] for c in report["contents"]] == [1, 3], report["contents"])
        check("网页文件名是英文", Path(built["file"]).name == "ai-visibility.html")

        call(STATE, "set-rivals", "--file", write(tmp, "rivals2.json", [{"name": "甲记面包"}, {"name": "乙家烘焙"}]), env=env)
        failed = call(REPORT, "publish", env=dict(env, MOCK_UPLOAD_FAIL="1"))
        check("上传失败时如实返回，不给新链接，并说明退路",
              failed["published"] is False and failed["pageUrl"] == first["pageUrl"] and "工作台" in failed["reason"] and "报告" in failed["reason"]
              and "youzan-oss" in failed["next"] and "不要编链接" in failed["next"], failed)
        stale = call(REPORT, "links", env=env)
        check("没同步上去的变化会一直提醒", stale["upToDate"] is False and stale["pending"] == ["同类店"] and "publish" in stale["next"], stale)
        error = call(REPORT, "set-page-url", "--url", "http://claw-cloud.youzan.com/f/x", env=env, expect=2)
        check("非 https 的链接会被拒绝", "https" in error.get("error", ""))
        saved = call(REPORT, "set-page-url", "--url", "https://claw-cloud.youzan.com/f/abc/ai-visibility.html", env=env)
        check("手动补上链接后，工作台算已同步", "warning" not in saved and call(REPORT, "links", env=env)["upToDate"] is True
              and call(STATE, "status", env=env)["pageUrl"].endswith("ai-visibility.html"))
        uploads = Path(env["MOCK_UPLOAD_LOG"]).read_text(encoding="utf-8").splitlines()
        names = [Path(u).name for u in uploads]
        check("每次同步传的都是固定的两个文件（链接才能固定）：没体检时只传工作台，有了结果先传报告再传工作台",
              names == ["ai-visibility.html", "ai-visibility.html", "report-%s.html" % DATE, "ai-visibility.html", "report-%s.html" % DATE, "ai-visibility.html"]
              and len(set(uploads)) == 2, names)
        fixed = call(REPORT, "set-page-url", "--report", DATE, "--url", "https://claw-cloud.youzan.com/f/abc/report-%s.html" % DATE, env=env)
        relisted = call(REPORT, "links", env=env)
        check("报告文件的链接也能手动补；在工作台里打开它的地址不变",
              fixed["report"] == DATE and relisted["reportFiles"][DATE].endswith("/f/abc/report-%s.html" % DATE)
              and relisted["reports"][DATE] == relisted["pageUrl"] + "#/report/" + DATE, relisted)

        changed = [dict(q, text="测试市哪家的贝果好吃？") if q["id"] == "q06" else q for q in SYNTHETIC_QUESTIONS]
        bumped = call(STATE, "set-questions", "--file", write(tmp, "changed.json", changed), env=env)
        check("改了问题原文才算口径变化", bumped["questionsVersion"] == 2, bumped)
        restart = call(RUN, "start", "--phase", "open", "--date", DATE, "--only", "q06", env=env)
        check("改过的问题会重新提问", restart["started"] == 3, restart)
        wait_all(env, DATE)
        rerun = call(SCORE, "score", "--date", DATE, env=env)
        check("只重跑了一道题：只要补读这一道，之前读过的保留",
              rerun["shopsPending"] == 6 and "只读这几道题：q06" in rerun["next"], rerun.get("next"))
        read_all(env, tmp, DATE, only="q06")
        check("补读之后，提到了谁重新出数", call(SCORE, "score", "--date", DATE, env=env)["shopsPending"] == 0)
        confirmed = call(STATE, "confirm", env=env)
        check("确认后状态变为已确认", confirmed["confirmed"] is True)


def test_resume_mid_check():
    """会话在体检中途断掉：status 把员工带回没做完的那一步，不会误判成“第一份报告出来了”；
    中途同步的报告会被提醒“还没做完”；隔几天改了一道题，重问的题算进最近一期，不另开一期。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp, GEO_FAKE_NOW="2026-10-09T10:00:00+08:00")  # 体检是前一天（DATE）发起的，隔天接着做
        stage = lambda: call(STATE, "status", env=env)  # noqa: E731
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)
        questions = [q for q in SYNTHETIC_QUESTIONS if q["id"] not in ("q04", "q05")]
        call(STATE, "set-questions", "--file", write(tmp, "q.json", questions), env=env)
        call(STATE, "set-rivals", "--file", write(tmp, "r.json", [{"name": "甲记面包"}, {"name": "乙家烘焙"}]), env=env)
        call(REPORT, "publish", env=env)
        call(STATE, "confirm-monitoring", env=env)
        call(RUN, "start", "--phase", "open", "--date", DATE, env=env)
        call(REPORT, "publish", env=env)  # 照 geo-check：第一次 start 之后同步一次
        now = stage()
        check("第一次体检刚发起就断：status 让员工接着等，不说“第一份报告出来了”",
              now["period"]["stage"] == "asking" and "wait" in now["next"] and "每周体检" not in now["next"], now.get("next"))
        wait_all(env, DATE)
        now = stage()
        check("只问了不带店名的（旧的分段写法）：status 让员工把带店名的补上，并带上这一期的日期",
              now["period"]["stage"] == "asking" and "带店名" in now["next"] and "geo_run.py start --date " + DATE in now["next"], now.get("next"))
        call(RUN, "start", "--phase", "brand", "--date", DATE, env=env)
        wait_all(env, DATE)
        check("问完还没算分：status 让员工算分", stage()["period"]["stage"] == "scoring")
        call(SCORE, "score", "--date", DATE, env=env)
        now = stage()
        check("算完分还没读全文：status 让员工读全文", now["period"]["stage"] == "reading" and "读全文" in now["next"], now.get("next"))
        half = call(REPORT, "publish", env=env)
        check("没读全文就同步：会提醒这一期还没做完，不让员工把报告当成结果发出去",
              half["unfinished"]["stage"] == "reading" and any("还没做完" in w for w in half.get("warnings", []))
              and "这一期的结果给 reportUrl" not in half["next"], half.get("next"))
        read_all(env, tmp, DATE)
        call(SCORE, "score", "--date", DATE, env=env)
        check("读完还没核对：status 让员工核对", stage()["period"]["stage"] == "judging")
        call(SCORE, "set-judgement", "--date", DATE, "--file", write(tmp, "j.json", {"descriptions": {"hunyuan": "一家面包店"}, "issues": []}), env=env)
        check("核对完还没写小结：status 让员工按 geo-weekly 收尾", "geo-weekly" in stage()["next"] and stage()["period"]["stage"] == "wrapup")
        call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a.json", {"brief": "小结", "contentNote": "这一期先不写"}), env=env)
        done = call(REPORT, "publish", env=env)
        now = stage()
        check("这一期做完了才问开不开每周体检；同步输出里有报告各节的链接，照抄就行",
              now["period"]["done"] and "每周体检" in now["next"] and "unfinished" not in done
              and done["reportSections"]["rivals"] == done["reportUrl"] + "/rivals"
              and list(done["reportSections"]) == ["summary", "mentions", "rivals", "sources", "says"], (now.get("next"), done.get("reportSections")))
        check("links 和 show 也给报告各节的链接",
              call(REPORT, "links", env=env)["reportSections"] == done["reportSections"]
              and call(REPORT, "show", env=env)["reportSections"] == done["reportSections"])

        # 换了同类店、重新算分，数变了：小结过时，要重写
        call(STATE, "set-rivals", "--file", write(tmp, "r2.json", [{"name": "甲记面包"}]), env=env)
        call(SCORE, "score", "--date", DATE, env=env)
        now = stage()
        check("写完小结后重新算分、数变了：status 让员工重写小结", now["period"]["stage"] == "wrapup" and "重写" in now["next"], now.get("next"))
        call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a-gap.json", {"gaps": [{"where": "公众号", "note": "x"}]}), env=env)
        check("只改缺口不算重写小结，还是提醒", stage()["period"]["stage"] == "wrapup")
        call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a2.json", {"brief": "新的小结"}), env=env)
        call(SCORE, "score", "--date", DATE, env=env)
        check("重写了小结，再重跑一次算分、数没变，不算过时", stage()["period"]["done"])

        # 隔几天商家改了一道题：只重问这一道，算进最近一期
        changed = [dict(q, text="测试市哪家的贝果好吃？") if q["id"] == "q06" else q for q in questions]
        call(STATE, "set-questions", "--file", write(tmp, "changed.json", changed), env=env)
        env["GEO_FAKE_NOW"] = "2026-10-11T10:00:00+08:00"
        rerun = call(RUN, "start", "--phase", "open", "--only", "q06", env=env)
        runs = lambda: sorted(p.name for p in (Path(env["GEO_DATA_ROOT"]) / "runs").iterdir() if p.is_dir())  # noqa: E731
        check("改了题只重问这一道：算进最近一期，不另开一期", rerun["date"] == DATE and runs() == [DATE], (rerun.get("date"), runs()))
        wait_all(env, DATE)
        now = stage()
        check("重问之后还没重新算分：status 让员工重新算分", now["period"]["stage"] == "scoring", now.get("period"))
        call(SCORE, "score", "--date", DATE, env=env)
        read_all(env, tmp, DATE, only="q06")
        call(SCORE, "score", "--date", DATE, env=env)
        call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a3.json", {"brief": "改题后的小结"}), env=env)

        # 最近一期是好几周前的：改了题不往那一期里补
        env["GEO_FAKE_NOW"] = "2026-10-30T10:00:00+08:00"
        stale = call(RUN, "start", "--phase", "open", "--only", "q06", env=env, expect=2)
        check("最近一期超过 7 天：只重问几道题会被拦下，让员工问商家要不要整轮重测",
              "超过 7 天" in stale.get("error", "") and runs() == [DATE], stale)

        # 新一期刚发起就同步：报告还是上一期的，不能当成这一期的结果
        call(RUN, "start", "--phase", "open", env=env)
        early = call(REPORT, "publish", env=env)
        check("新一期还在提问时同步：提示报告是上一期的，先别发",
              early["unfinished"]["stage"] == "asking" and "上一期（%s）" % DATE in early["next"]
              and "这一期的结果给 reportUrl" not in early["next"], early.get("next"))

    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp, MOCK_RUN_ERROR="1")
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-questions", "--file", write(tmp, "q.json", SYNTHETIC_QUESTIONS), env=env)
        call(STATE, "confirm-monitoring", env=env)
        call(RUN, "start", "--phase", "open", "--date", DATE, env=env, expect=2)
        now = call(STATE, "status", env=env)
        check("一条都没问成功：status 让员工重新发起，不说“第一份报告出来了”",
              now["period"]["stage"] == "asking" and "--retry" in now["next"] and "每周体检" not in now["next"], now.get("next"))


def test_environment_error():
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp, MOCK_RUN_ERROR="1")
        call(STATE, "init", "--segment", "ecom", "--brand", "示例小店", env=env)
        call(STATE, "set-questions", "--file", write(tmp, "q.json", SYNTHETIC_QUESTIONS), env=env)
        call(STATE, "confirm-monitoring", env=env)
        error = call(RUN, "start", "--phase", "open", "--date", DATE, env=env, expect=2)
        check("一条都发不出去时给出明确原因", "一条都没有发起成功" in error.get("error", ""), error)
        env2 = dict(env)
        env2.pop("GEO_AI_QUERY_CMD")
        env2["YOUZAN_GLOBAL_SKILLS_PATH"] = str(Path(tmp) / "no-skills")
        error = call(RUN, "start", "--phase", "open", "--date", "2026-10-09", env=env2, expect=2)
        check("没有“问 AI”能力时用业务语言报错", "还没有开通“问 AI”能力" in error.get("error", ""), error)


def test_replay():
    if not ARCHIVE.is_dir():
        print("跳过  真实存档回放（没有找到 %s）" % ARCHIVE)
        return
    fixtures = HERE / "fixtures" / "mai"
    with tempfile.TemporaryDirectory() as tmp:
        # 存档文件是 10 月 8 日 21:50 落盘的，工作记录里的时间按这个时间记
        env = base_env(tmp, MOCK_ARCHIVE=str(ARCHIVE), MOCK_QUESTIONS=str(ARCHIVE / "questions.tsv"), MOCK_POLLS="1",
                       GEO_FAKE_NOW="2026-10-08T21:50:00+08:00")
        call(STATE, "init", "--segment", "local", "--brand", "麦的日尝", env=env)
        call(STATE, "set-facts", "--file", str(fixtures / "facts.json"), env=env)
        call(STATE, "set-questions", "--file", str(fixtures / "questions.json"), env=env)
        call(STATE, "set-rivals", "--file", str(fixtures / "rivals.json"), env=env)
        call(REPORT, "publish", env=env)  # 和员工的真实顺序一样：建完档先开通工作台
        call(STATE, "confirm-monitoring", env=env)
        call(RUN, "start", "--phase", "open", "--date", DATE, env=env)
        wait_all(env, DATE)
        call(RUN, "start", "--phase", "brand", "--date", DATE, env=env)
        wait_all(env, DATE)
        digest = call(SCORE, "score", "--date", DATE, env=env)
        # 那次实测豆包还开着记忆，有 3 个回答是记忆带出来的提及；现在不再单独剔除，由员工读全文时复核
        check("回放：元宝 0/24、DeepSeek 0/24，豆包 24 个回答都计入",
              digest["mention"]["byProvider"]["元宝"] == "0/24" and digest["mention"]["byProvider"]["DeepSeek"] == "0/24"
              and digest["mention"]["byProvider"]["豆包"].endswith("/24"), digest["mention"])
        check("回放：留下附近那道题提到了本店", "q11" in digest["questionsMentioned"], digest["questionsMentioned"])
        check("回放：被提到最多的同类店是 Cycle & Cycle，17 次", digest["rivals"][0] == {"name": "Cycle & Cycle", "count": 17}, digest["rivals"])
        check("回放：主理人账号的抖音视频被引用 1 次", digest["refs"]["own"] == 1, digest["refs"])
        summary = json.loads((Path(env["GEO_DATA_ROOT"]) / "runs" / DATE / "summary.json").read_text(encoding="utf-8"))
        top = {p: v[0]["type"] for p, v in summary["sources"]["byProvider"].items()}
        check("回放：元宝最常读公众号，豆包最常读抖音", top["hunyuan"] == "微信公众号" and top["doubao"] == "抖音", top)
        check("回放：DeepSeek 丢了开头一个字的回答仍算提到本店", summary["cells"]["b02"]["deepseek"]["hits"] == 2, summary["cells"]["b02"])
        call(SCORE, "set-judgement", "--date", DATE, "--file", str(fixtures / "judgement.json"), env=env)
        call(REPORT, "set-actions", "--date", DATE, "--file", str(fixtures / "actions.json"), env=env)
        built = call(REPORT, "publish", "--date", DATE, env=env)
        _, _, data = page_json(built["file"])
        _, _, report = page_json(built["reportFiles"][0])
        check("回放：工作台和报告都同步成功，数据来自真实存档（没有演示标记）",
              built["published"] and data["store"]["demo"] is False and data["store"]["name"] == "麦的日尝"
              and report["store"]["demo"] is False and Path(built["reportFiles"][0]).stat().st_size > 100000, built)
        check("回放：工作台上是 1 期、14 个问题；报告里是 84 个回答的原话",
              (data["totals"]["periods"], len(data["settings"]["questions"]), sum(len(v) for v in report["answers"].values())) == (1, 14, 84), data["totals"])
        check("回放：报告里对不上的说法按序号排列，资料来源标的是公开信息",
              [i["no"] for i in report["issues"]] == [1, 2, 3, 4] and report["factsFrom"] == "public" and data["settings"]["pending"] is True, report["factsFrom"])
        keep_page("工作台（麦的日尝真实存档）", built["file"])
        keep_page("第 1 期报告（麦的日尝真实存档）", built["reportFiles"][0])
        SAMPLE.mkdir(parents=True, exist_ok=True)
        for source in (built["file"], built["reportFiles"][0]):
            shutil.copyfile(source, SAMPLE / Path(source).name)
        print("      示例已更新：" + str(SAMPLE))


def test_public_empty_accounts():
    """公开信息整理的资料里，空着的公众号、抖音号不列进“等商家确认的”：列进去，员工会以为要去问商家要账号。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        created = call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        check("刚建档时：要商家确认的只有店名这些，不列空着的账号和购买入口",
              created["pendingConfirm"] is True and set(created["toConfirm"]) == {"brand"}, created.get("toConfirm"))
        empty = dict(SYNTHETIC_FACTS, channels={"wechatOfficial": "", "douyin": "", "ownHosts": [], "ownContentKeys": []})
        saved = call(STATE, "set-facts", "--file", write(tmp, "f.json", empty), env=env)
        check("资料来自公开信息、账号都空着：整份仍要商家确认，但要确认的不含账号",
              saved["factsFrom"] == "public" and saved["pendingConfirm"] is True and saved["canWrite"] is False
              and {"brand", "stores"} <= set(saved["toConfirm"]) and "channels" not in saved["toConfirm"], saved.get("toConfirm"))


def _relations(env, urls):
    """用体检算分的那套规则，看这几个链接被认成什么：own 是本店自己的内容，空串是和本店无关。"""
    code = ("import json, sys; sys.path.insert(0, %r); import geo_score as s; p = s.load_profile(); "
            "names = s.gc.brand_aliases(p['facts']); "
            "print(json.dumps([s.classify_ref({'url': u, 'title': '一篇文章'}, p['facts'], names)['relation'] for u in sys.argv[1:]]))"
            % str(SKILLS / "geo-check" / "scripts"))
    proc = subprocess.run([sys.executable, "-c", code, *urls], capture_output=True, text=True,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **env))
    return json.loads(proc.stdout) if proc.returncode == 0 else proc.stderr[-300:]


def test_site():
    """官网：资料不能用时不让登记；先有测试版才能登记上线；店铺资料改了提示过时；AI 引用了已上线的官网算本店自己的内容。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "public.json", SYNTHETIC_FACTS), env=env)
        brief = call(REPORT, "site-brief", env=env)
        check("资料是公开信息整理的、商家还没确认：site-brief 说现在不能做官网", brief["canWrite"] is False and "不能做官网" in brief.get("next", ""), brief.get("next"))
        error = call(REPORT, "set-site", "--status", "test", "--test-url", "https://pages.example.com/t/official-site", env=env, expect=2)
        check("资料还没确认时，不能登记官网", "不能把它放上官网" in error.get("error", ""), error)
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        old_store = {"name": "老街店", "address": "测试市老街 9 号", "status": "已关闭", "source": "有赞后台"}
        facts = dict(SYNTHETIC_FACTS, **{"from": "backend", "channels": {},
                                         "stores": SYNTHETIC_FACTS["stores"] + [old_store],
                                         "products": [{"name": "全麦吐司", "spec": "450 克", "priceRange": "18-25 元"}],
                                         "buyEntry": {"miniProgram": "示例小店", "shopUrl": "https://shop1.youzan.com/v2/showcase/homepage"}})
        call(STATE, "set-facts", "--file", write(tmp, "f1.json", facts), env=env)
        call(STATE, "set-questions", "--file", write(tmp, "q.json", SYNTHETIC_QUESTIONS), env=env)
        brief = call(REPORT, "site-brief", env=env)
        check("site-brief：在营门店和已关的门店分开给，商品带价格带，没确认的别名不放，顾客常问用全部监测问题，给出页面标题",
              brief["canWrite"] is True and [x["name"] for x in brief["stores"]] == ["测试路店"] and [x["name"] for x in brief["oldStores"]] == ["老街店"]
              and brief["products"][0].get("priceRange") == "18-25 元" and brief["aliases"] == [] and len(brief["faq"]) == len(SYNTHETIC_QUESTIONS)
              and brief["pageTitle"] == "示例小店 · 测试市面包店" and brief["site"] == {"exists": False}, brief)
        error = call(REPORT, "set-site", "--status", "published", "--url", "https://pages.example.com/s/official-site", env=env, expect=2)
        check("没出过测试版，不能登记正式上线", "没有等商家确认的测试版" in error.get("error", ""), error)
        check("还没体检过：site-brief 不给商城被引用的次数", brief["shopCited"] == {}, brief.get("shopCited"))
        error = call(REPORT, "set-site", "--status", "test", "--test-url", "http://pages.example.com/t", env=env, expect=2)
        check("测试版链接不是 https 的完整链接，退回", "https" in error.get("error", ""), error)
        error = call(REPORT, "set-site", "--status", "test", "--test-url", "https://pages.example.com/t", "--page-name", "Site", env=env, expect=2)
        check("页面标识不合规，退回", "页面标识" in error.get("error", ""), error)
        tested = call(REPORT, "set-site", "--status", "test", "--test-url", "https://pages.example.com/t/official-site?v=1", "--page-name", "official-site", env=env)
        check("登记测试版：等商家确认，还没上线，提醒先同步再把链接发给商家",
              (tested["site"]["status"], tested["site"]["live"], tested["site"]["outdated"]) == ("test", False, False) and "publish" in tested["next"], tested)
        published = call(REPORT, "publish", env=env)
        _, _, data = page_json(published["file"])
        check("工作台数据里带着官网的测试版", data["site"]["status"] == "test" and data["site"]["testUrl"].endswith("v=1"), data.get("site"))
        keep_page("工作台（官网测试版等确认）", published["file"])
        check("官网还没上线时，链接不算本店自己的内容", _relations(env, ["https://pages.example.com/s/official-site"]) == [""])
        live = call(REPORT, "set-site", "--status", "published", "--url", "https://pages.example.com/s/official-site", env=env)
        check("登记正式上线", (live["site"]["status"], live["site"]["live"], live["site"]["url"]) == ("published", True, "https://pages.example.com/s/official-site"), live)
        check("AI 引用了已上线的官网（带参数也认），算本店自己的内容；同一个网站的别的页面不算",
              _relations(env, ["https://pages.example.com/s/official-site?from=ai", "https://pages.example.com/s/official-site/", "https://pages.example.com/s/other-site"]) == ["own", "own", ""])
        check("官网下面的页面算本店的，名字相近的别的页面不算",
              _relations(env, ["https://pages.example.com/s/official-site/menu", "https://pages.example.com/s/official-site-2"]) == ["own", ""])
        error = call(REPORT, "set-site", "--status", "published", "--url", "https://pages.example.com/s/official-site", env=env, expect=2)
        check("已经上线、没有新的测试版：不能再登记一次上线", "没有等商家确认的测试版" in error.get("error", ""), error)
        call(REPORT, "set-site", "--domain", "www.sample-shop.com", env=env)
        check("绑了独立域名：这个域名下的页面都算本店自己的内容，名字相近的别的域名不算",
              _relations(env, ["https://www.sample-shop.com/about", "https://notsample-shop.com/x"]) == ["own", ""])
        hours = dict(facts, stores=[dict(SYNTHETIC_FACTS["stores"][0], hours="09:00-21:00"), old_store])
        call(STATE, "set-facts", "--file", write(tmp, "f2.json", hours), env=env)
        status = call(STATE, "status", env=env)
        check("官网上线后门店的营业时间改了：status 说官网过时了，改的是门店",
              status["site"]["outdated"] is True and status["site"]["changed"] == ["门店"], status.get("site"))
        check("show 里也看得到官网过时了", call(REPORT, "show", env=env)["site"]["outdated"] is True)
        published = call(REPORT, "publish", env=env)
        keep_page("工作台（官网已上线、店铺资料改过）", published["file"])
        again = call(REPORT, "set-site", "--status", "test", "--test-url", "https://pages.example.com/t/official-site?v=2", env=env)
        check("改过的一版出了测试版：官网还在线，新的一版跟上了店铺资料",
              (again["site"]["status"], again["site"]["live"], again["site"]["outdated"]) == ("test", True, False), again)
        published = call(REPORT, "publish", env=env)
        keep_page("工作台（官网在线、改过的一版等确认）", published["file"])
        edges = call(STATE, "set-facts", "--file", write(tmp, "f3.json", {"edges": [{"text": "测试路上唯一一家现烤面包", "basis": "门店位置"}]}), env=env)
        stale = call(REPORT, "set-site", "--status", "published", "--url", "https://pages.example.com/s/official-site", env=env)
        check("测试版做好后改了这家店的特点：上线时提醒官网已经跟不上",
              stale["site"]["changed"] == ["这家店的特点"] and "跟不上" in stale["next"], stale)
        dropped = call(REPORT, "set-site", "--status", "dropped", env=env)
        check("官网不要了：不再算在线，它的链接也不再算本店自己的内容",
              dropped["site"]["live"] is False and _relations(env, ["https://pages.example.com/s/official-site"]) == [""], dropped)
        error = call(REPORT, "set-site", "--status", "published", "--url", "https://pages.example.com/s/official-site", env=env, expect=2)
        check("不要了以后，不出新的测试版不能直接上线", "没有等商家确认的测试版" in error.get("error", ""), error)
        remade = call(REPORT, "set-site", "--status", "test", "--test-url", "https://pages.example.com/t/new-site", env=env)
        check("不要了以后重做：是新的官网，旧的正式链接、域名、页面标识都清掉",
              (remade["site"]["live"], remade["site"]["url"], remade["site"]["domain"], remade["site"]["pageName"]) == (False, "", "", "")
              and _relations(env, ["https://pages.example.com/s/official-site", "https://www.sample-shop.com/about"]) == ["", ""], remade)
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        facts = dict(SYNTHETIC_FACTS, **{"from": "backend", "products": [{"name": "全麦吐司", "spec": "450 克", "priceRange": "18-25 元"}]})
        call(STATE, "set-facts", "--file", write(tmp, "f1.json", facts), env=env)
        call(REPORT, "set-site", "--status", "test", "--test-url", "https://pages.example.com/t/official-site", env=env)
        site_file = Path(env["GEO_DATA_ROOT"]) / "profile" / "site.json"
        site = json.loads(site_file.read_text(encoding="utf-8"))
        for product in site["testBasis"]["products"]:
            product.pop("priceRange")  # 以前登记的官网，商品没记价格带
        site_file.write_text(json.dumps(site, ensure_ascii=False), encoding="utf-8")
        check("以前登记的官网商品没记价格带：不因此算过时", call(STATE, "status", env=env)["site"]["outdated"] is False)
        call(REPORT, "set-site", "--status", "test", "--test-url", "https://pages.example.com/t/official-site?v=2", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f2.json", dict(facts, products=[{"name": "全麦吐司", "spec": "450 克", "priceRange": "20-28 元"}])), env=env)
        status = call(STATE, "status", env=env)
        check("官网上有价格：商品的价格带改了，官网算过时，改的是招牌商品",
              status["site"]["outdated"] is True and status["site"]["changed"] == ["招牌商品"], status.get("site"))


def test_backend_source():
    """店铺后台读来的资料不用商家确认；只有员工另外记下的那几样要确认。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        facts = dict(SYNTHETIC_FACTS, **{"from": "backend", "channels": {}})
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        saved = call(STATE, "set-facts", "--file", write(tmp, "f1.json", dict(facts, brand={"name": "示例小店", "category": "面包", "city": "测试市"})), env=env)
        check("资料全部来自店铺后台时，不用商家确认就能替他写内容",
              (saved["factsFrom"], saved["confirmed"], saved["pendingConfirm"], saved["canWrite"]) == ("backend", False, False, True)
              and saved["toConfirm"] == {}, saved)
        call(STATE, "set-questions", "--file", write(tmp, "q.json", SYNTHETIC_QUESTIONS), env=env)
        text = "示例小店在测试市测试路 1 号，每天 9 点到 20 点营业。" * 4
        added = call(REPORT, "add-content", "--file", write(tmp, "c.json", {"type": "text", "title": "测试市哪家的吐司好吃", "body": text}), env=env)
        check("后台来的资料可以直接登记内容", added["no"] == 1 and added["status"] == "preview", added)
        extra = call(STATE, "set-facts", "--file", write(tmp, "f2.json", dict(facts, channels={"douyin": "示例小店的抖音号"})), env=env)
        check("员工另外记下了后台里没有的信息：标成等商家确认，但不挡写内容；要确认的只列别名和抖音号，不列后台的门店",
              (extra["pendingConfirm"], extra["canWrite"]) == (True, True)
              and extra["toConfirm"] == {"aliases": ["Sample Shop"], "channels": {"douyin": "示例小店的抖音号"}}, extra)
        call(STATE, "confirm", env=env)
        hours = dict(facts, channels={"douyin": "示例小店的抖音号"},
                     stores=[dict(SYNTHETIC_FACTS["stores"][0], hours="09:00-21:00")])
        refreshed = call(STATE, "set-facts", "--file", write(tmp, "f3.json", hours), env=env)
        check("从后台重读带来的变化（营业时间改了）不用商家再确认", refreshed["changed"] is True and refreshed["confirmed"] is True, refreshed)
        changed = call(STATE, "set-facts", "--file", write(tmp, "f4.json", dict(hours, channels={"douyin": "另一个抖音号"})), env=env)
        check("要确认的那部分变了（换了一个抖音号），才重新请商家确认", changed["confirmed"] is False and changed["pendingConfirm"] is True, changed)
        published = call(REPORT, "publish", env=env)
        _, _, data = page_json(published["file"])
        check("监测设置里只列员工另外记下的，不抄店铺后台的门店",
              data["settings"]["from"] == "backend" and data["settings"]["extras"]["douyin"] == "另一个抖音号" and data["settings"]["extras"]["stores"] == [], data["settings"]["extras"])
        call(STATE, "set-facts", "--file", write(tmp, "edges.json", {"edges": [{"text": "测试路上唯一一家现烤面包", "basis": "门店位置"}]}), env=env)
        published = call(REPORT, "publish", env=env)
        _, _, data = page_json(published["file"])
        check("差异点显示在监测设置上，商家看得到、能让员工改",
              data["settings"]["edges"] == [{"text": "测试路上唯一一家现烤面包", "basis": "门店位置"}], data["settings"].get("edges"))
        keep_page("工作台（资料来自店铺后台，还没体检）", published["file"])


def test_facts_merge():
    """每周从后台重读资料时只传后台读得到的几样：员工另外记下的不能被悄悄清空。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        first = call(STATE, "set-facts", "--file", write(tmp, "f0.json", {k: v for k, v in SYNTHETIC_FACTS.items() if k != "segment"}), env=env)
        check("资料没写 from 时提醒：后台读来的要写 backend", any("from" in w for w in first["warnings"]), first["warnings"])
        full = dict(SYNTHETIC_FACTS, **{"from": "backend", "edges": [{"text": "测试路上唯一一家现烤面包", "basis": "门店位置"}],
                    "channels": {"wechatOfficial": "示例小店官方号", "douyin": "示例抖音", "ownContentKeys": ["1234567890"]},
                    "writingRules": {"bannedWords": ["网红"]},
                    "stores": SYNTHETIC_FACTS["stores"] + [{"name": "旧店", "address": "测试市旧路 2 号", "status": "已关闭", "source": "大众点评"}]})
        call(STATE, "set-facts", "--file", write(tmp, "f1.json", full), env=env)
        weekly = {"from": "backend", "segment": "local", "brand": {"name": "示例小店", "category": "面包", "city": "测试市"},
                  "stores": [dict(SYNTHETIC_FACTS["stores"][0], hours="09:00-21:00")]}
        merged = call(STATE, "set-facts", "--file", write(tmp, "f2.json", weekly), env=env)
        facts = call(STATE, "show", "--part", "facts", env=env)["facts"]
        check("只传后台的几样：别名、账号、作品编号、差异点、写作要求、后台以外的门店都保留，并列出保留了哪些",
              facts["brand"]["aliases"] == ["Sample Shop"] and facts["channels"]["ownContentKeys"] == ["1234567890"]
              and facts["edges"] and facts["writingRules"]["bannedWords"] == ["网红"]
              and [s["name"] for s in facts["stores"]] == ["测试路店", "旧店"] and facts["stores"][0]["hours"] == "09:00-21:00"
              and "brand.aliases" in merged.get("kept", []) and "channels" in merged.get("kept", []), (facts, merged.get("kept")))
        cleared = call(STATE, "set-facts", "--file", write(tmp, "f3.json", {"channels": {"douyin": ""}}), env=env)
        facts = call(STATE, "show", "--part", "facts", env=env)["facts"]
        check("要删掉某一项就把它传成空值；只传一样也行", facts["channels"]["douyin"] == "" and facts["channels"]["wechatOfficial"] == "示例小店官方号"
              and cleared["changed"] is True, facts["channels"])
        call(STATE, "set-facts", "--replace", "--file", write(tmp, "f4.json", weekly), env=env)
        facts = call(STATE, "show", "--part", "facts", env=env)["facts"]
        check("--replace 整份覆盖：没传的都清空", facts["brand"]["aliases"] == [] and facts["edges"] == [] and len(facts["stores"]) == 1, facts)
        chain = [{"name": "第 %d 家店" % i, "address": "测试市测试路 %d 号" % i, "source": "有赞后台"} for i in range(1, 206)]
        big = call(STATE, "set-facts", "--file", write(tmp, "f5.json", {"stores": chain}), env=env)
        facts = call(STATE, "show", "--part", "facts", env=env)["facts"]
        check("连锁店：门店能记 200 家，超出的不悄悄丢，告诉员工传了几家、记了几家",
              len(facts["stores"]) == 200 and any("传了 205 条，只记了前 200 条" in w for w in big["warnings"]), big["warnings"])
        error = call(STATE, "set-rivals", "--file", write(tmp, "r6.json", [{"name": "同类店%d" % i} for i in range(6)]), env=env, expect=2)
        check("同类店超过 5 家会退回，不只留前 5 家", "最多 5 家" in error.get("error", ""), error)


def test_edited_page():
    """员工直接改了工作台网页：同步只换数据块，员工加的、改的都保留。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)
        first = call(REPORT, "publish", env=env)
        page = Path(first["file"])
        _, _, data = page_json(str(page))
        data["nav"].append({"id": "keywords", "title": "关键词监控", "icon": "doc", "subtitle": ""})
        data["customPages"] = {"keywords": {"blocks": [{"type": "text", "text": "员工加的"}]}}
        edited = page.read_text(encoding="utf-8").replace("<style>", "<style>/* 商家要的橙色 */", 1)
        edited = re.sub(r'(<script type="application/json" id="geo-data">).*?(</script>)',
                        lambda m: m.group(1) + json.dumps(data, ensure_ascii=False) + m.group(2), edited, flags=re.S)
        page.write_text(edited, encoding="utf-8")
        call(STATE, "set-rivals", "--file", write(tmp, "r2.json", [{"name": "甲记面包"}]), env=env)
        again = call(REPORT, "publish", env=env)
        html, _, data = page_json(again["file"])
        check("员工改过的页面：同步后改动都在，数据换成了新的，员工加的页面和数据也在",
              "/* 商家要的橙色 */" in html and [r["name"] for r in data["settings"]["rivals"]] == ["甲记面包"]
              and [p["id"] for p in data["nav"]][-1] == "keywords" and "keywords" in data["customPages"],
              (data["settings"]["rivals"], [p["id"] for p in data["nav"]]))
        call(STATE, "set-rivals", "--file", write(tmp, "r2b.json", [{"name": "丙记吐司坊"}]), env=env)
        call(REPORT, "publish", env=env)
        html, _, data = page_json(again["file"])
        check("员工改过的页面连续同步两次，改动还在（只同步一次时测不出来）",
              "/* 商家要的橙色 */" in html and [r["name"] for r in data["settings"]["rivals"]] == ["丙记吐司坊"]
              and "keywords" in data["customPages"], data["settings"]["rivals"])
        page.write_text(html.replace('id="geo-data"', 'id="geo-data-gone"'), encoding="utf-8")
        broken = page.read_text(encoding="utf-8")
        error = call(REPORT, "publish", env=env, expect=2)
        check("改过的页面把数据块弄丢了：不同步也不覆盖，告诉员工怎么办",
              "找不到放数据的地方" in error.get("error", "") and page.read_text(encoding="utf-8") == broken, error)
        page.unlink()
        call(REPORT, "publish", env=env)
        check("删掉页面再同步，恢复标准样子", "/* 商家要的橙色 */" not in page.read_text(encoding="utf-8"))
        plain = page.read_text(encoding="utf-8")
        call(STATE, "set-rivals", "--file", write(tmp, "r3.json", [{"name": "乙家烘焙"}]), env=env)
        call(REPORT, "publish", env=env)
        check("没改过的页面照标准模板整页重写", page.read_text(encoding="utf-8") != plain
              and [r["name"] for r in page_json(str(page))[2]["settings"]["rivals"]] == ["乙家烘焙"])

    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)
        page = Path(call(REPORT, "publish", env=env)["file"])
        root = Path(env["GEO_DATA_ROOT"])
        (root / "pages" / ".generated.json").unlink()
        (root / "template").mkdir()
        (root / "template" / "page.html").write_text("旧版这家店自己的模板", encoding="utf-8")
        page.write_text(page.read_text(encoding="utf-8").replace("<style>", "<style>/* 旧模板的样子 */", 1), encoding="utf-8")
        call(REPORT, "publish", env=env)
        check("以前用这家店自己模板生成的页面，升级后第一次同步也只换数据", "/* 旧模板的样子 */" in page.read_text(encoding="utf-8"))

    # 61d9a0e 之前的老页面：记录是整页的指纹，员工改过的页面也这样记（线上星光之家碰到过）
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)
        page = Path(call(REPORT, "publish", env=env)["file"])
        record_file = Path(env["GEO_DATA_ROOT"]) / "pages" / ".generated.json"
        whole = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]  # noqa: E731
        edited = page.read_text(encoding="utf-8").replace("<style>", "<style>/* 升级前就改过 */", 1)
        page.write_text(edited, encoding="utf-8")
        record_file.write_text(json.dumps({page.name: whole(edited)}), encoding="utf-8")
        call(STATE, "set-rivals", "--file", write(tmp, "r4.json", [{"name": "甲记面包"}]), env=env)
        call(REPORT, "publish", env=env)
        check("升级前改过、记录是整页指纹的页面：升级后同步，改动还在", "/* 升级前就改过 */" in page.read_text(encoding="utf-8"))
        legacy = subprocess.run(["git", "show", "3c92769:digital-employee/definitions/ai-visibility-employee/skills/geo-workbench/assets/page.html"],
                                cwd=str(ROOT), capture_output=True, text=True)
        if legacy.returncode:
            print("跳过  老版标准模板生成的页面能跟着升级（这里没有 git 历史）")
        else:
            block = re.search(r'<script type="application/json" id="geo-data">(.*?)</script>', page.read_text(encoding="utf-8"), re.S).group(1)
            old_page = legacy.stdout.replace("__GEO_DATA__", block)
            for label, record in (("没有记录", {}), ("记录是整页指纹", {page.name: whole(old_page)})):
                page.write_text(old_page, encoding="utf-8")
                record_file.write_text(json.dumps(record), encoding="utf-8")
                call(REPORT, "publish", env=env)
                check("老版标准模板生成、没改过的页面（%s）：同步时换成现在的标准模板" % label,
                      page.read_text(encoding="utf-8").split('id="geo-data">')[0] == TEMPLATE.read_text(encoding="utf-8").split('id="geo-data">')[0])


def test_no_silent_caps():
    """几百篇内容、一年以上的期次：工作台上每一篇都带全文，每一期都有入口。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)
        root = Path(env["GEO_DATA_ROOT"])
        days = ["2026-%02d-%02d" % (1 + i // 4, 1 + (i % 4) * 7) for i in range(40)]
        summary = {"mention": {"hits": 1, "valid": 2, "byProvider": {}, "byQuestion": {}}, "refs": {"total": 0, "own": 0, "storePages": 0, "aboutStore": 0},
                   "expected": 2, "returned": 2, "complete": True, "buyEntry": {}}
        for day in days:
            (root / "runs" / day).mkdir(parents=True)
            (root / "runs" / day / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        items = [{"no": n, "type": "text", "title": "第 %d 篇" % n, "body": "正文" * 400, "status": "published" if n < 290 else "preview",
                  "origin": "asked", "period": days[-1]} for n in range(1, 301)]
        (root / "profile" / "contents.json").write_text(json.dumps({"items": items, "nextNo": 301}, ensure_ascii=False), encoding="utf-8")
        from_lib = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import geo_report as r, json; "
                                   "d = r.workbench_data(); print(json.dumps([len(d['periods']), len(d['contents']), "
                                   "sum(1 for c in d['contents'] if c['body'])]))" % str(REPORT.parent)],
                                  capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **env))
        counts = json.loads(from_lib.stdout or "null") if from_lib.returncode == 0 else from_lib.stderr[-300:]
        check("40 期、300 篇内容：每一期都在工作台上，每一篇都带全文", counts == [40, 300, 300], counts)
        shown = call(REPORT, "show", env=env)
        check("show 只带最近几篇，不把几百篇全塞给员工", len(shown["contents"]) == 5 and shown["nextNo"] == 301, len(shown["contents"]))


def test_new_agent_guards():
    """一个新员工照着 next 做，不会跳过选同类店；先写了“这期不写”后来又写了内容，会被提醒。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)
        questions = [q for q in SYNTHETIC_QUESTIONS if q["id"] not in ("q04", "q05")]
        call(STATE, "set-questions", "--file", write(tmp, "q.json", questions), env=env)
        call(STATE, "confirm-monitoring", env=env)
        call(RUN, "start", "--phase", "open", "--date", DATE, env=env)
        wait_all(env, DATE)
        call(RUN, "start", "--phase", "brand", "--date", DATE, env=env)
        wait_all(env, DATE)
        scored = call(SCORE, "score", "--date", DATE, env=env)
        check("没读全文时，next 先让员工读全文，而不是选同类店", "读全文" in scored["next"] and "set-rivals" not in scored["next"], scored.get("next"))
        read_all(env, tmp, DATE)
        scored = call(SCORE, "score", "--date", DATE, env=env)
        check("同类店没定时，next 让员工先选同类店，而不是直接去核对",
              scored.get("candidates") and "set-rivals" in scored["next"] and "brand-digest" not in scored["next"], scored.get("next"))
        call(STATE, "set-rivals", "--file", write(tmp, "r.json", [{"name": "甲记面包"}, {"name": "乙家烘焙"}]), env=env)
        scored = call(SCORE, "score", "--date", DATE, env=env)
        check("同类店定了以后，next 才是去核对", "brand-digest" in scored["next"] and "candidates" not in scored, scored.get("next"))
        call(SCORE, "set-judgement", "--date", DATE, "--file", write(tmp, "j.json", {"descriptions": {"hunyuan": "一家面包店"}, "issues": []}), env=env)
        call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a.json", {"brief": "小结", "contentNote": "这一期先不写"}), env=env)
        body = "示例小店在测试市测试路 1 号，每天 9 点到 20 点营业。" * 4
        call(REPORT, "add-content", "--file", write(tmp, "c.json", {"type": "text", "title": "测试市哪家的吐司好吃", "body": body}), env=env)
        published = call(REPORT, "publish", "--date", DATE, env=env)
        check("登记了内容、contentNote 却还写着没写的原因：同步时提醒清掉",
              any("contentNote" in w and "清掉" in w for w in published.get("warnings", [])), published.get("warnings"))
        call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a2.json", {"contentNote": ""}), env=env)
        check("清掉以后不再提醒", "warnings" not in call(REPORT, "publish", "--date", DATE, env=env))


def _quick_round(env, tmp, date, questions):
    call(STATE, "confirm-monitoring", env=env)
    call(RUN, "start", "--phase", "open", "--date", date, env=env)
    wait_all(env, date)
    call(RUN, "start", "--phase", "brand", "--date", date, env=env)
    wait_all(env, date)


def test_data_reliability():
    """同一天重新体检要真的重新问；删掉的问题不再算进这一期；数据不全的期次不拿来判断涨跌。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp, GEO_FAKE_NOW=DATE + "T10:00:00+08:00")
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)
        questions = [q for q in SYNTHETIC_QUESTIONS if q["id"] not in ("q04", "q05")]
        call(STATE, "set-questions", "--file", write(tmp, "q.json", questions), env=env)
        call(STATE, "set-rivals", "--file", write(tmp, "r.json", [{"name": "甲记面包"}]), env=env)
        _quick_round(env, tmp, DATE, questions)
        call(SCORE, "score", "--date", DATE, env=env)
        call(SCORE, "set-judgement", "--date", DATE, "--file", write(tmp, "j.json", {"descriptions": {"hunyuan": "旧的介绍"}, "issues": []}), env=env)

        again = call(RUN, "start", "--phase", "open", "--date", DATE, env=env)
        check("指定了这一期再发起：说清没有重新问，并告诉怎么开新的一期",
              again["started"] == 0 and "开新的一期" in again["next"], again.get("next"))
        run_dir = Path(env["GEO_DATA_ROOT"]) / "runs" / DATE
        second = call(RUN, "start", env=env)
        check("同一天、问题没变，再体检一次也是新的一期：编号 日期-2，全部问题一起问，上一期原样留着",
              second["newPeriod"] == DATE + "-2" and second["started"] == 30 and second["phases"]["brand"]["started"] is True
              and (run_dir / "summary.json").exists() and (run_dir / "judgement.json").exists(), second)
        resumed = call(RUN, "start", env=env)
        check("今天这一期还没问完时再 start：接着这一期，不另开", resumed["date"] == DATE + "-2" and resumed["started"] == 0, resumed)
        blocked = call(RUN, "start", "--fresh", env=env, expect=2)
        check("上一期还有查询在运行时不能另开一期", "还有查询在运行" in blocked.get("error", ""), blocked)
        done = wait_all(env, DATE + "-2")
        check("新的一期整轮结束", done["finished"] is True and done["done"] == 30, done)
        call(SCORE, "score", env=env)
        call(SCORE, "set-judgement", "--file", write(tmp, "j-2.json", {"descriptions": {"hunyuan": "第二期的介绍"}, "issues": []}), env=env)
        call(REPORT, "set-actions", "--file", write(tmp, "a-2.json", {"brief": "第二期"}), env=env)
        published = call(REPORT, "publish", env=env)
        _, _, page = page_json(published["file"])
        check("工作台上两期都在，最新的是第 2 期；两份报告各是各的文件",
              [p["date"] for p in page["periods"]] == [DATE, DATE + "-2"] and page["latest"]["no"] == 2
              and (Path(env["GEO_DATA_ROOT"]) / "pages" / ("report-%s.html" % DATE)).exists()
              and (Path(env["GEO_DATA_ROOT"]) / "pages" / ("report-%s-2.html" % DATE)).exists(), [p["date"] for p in page["periods"]])
        third = call(RUN, "start", "--fresh", env=env)
        check("--fresh 也是开新的一期，编号接着往下排", third["newPeriod"] == DATE + "-3", third)
        wait_all(env, DATE + "-3")

        call(STATE, "set-questions", "--file", write(tmp, "q2.json", [q for q in questions if q["id"] != "q01"]), env=env)
        latest = DATE + "-3"  # 删题只影响最新一期，以前各期按当时的问题算
        scored = call(SCORE, "score", "--date", latest, env=env)
        summary = json.loads((run_dir.parent / latest / "summary.json").read_text(encoding="utf-8"))
        check("删掉 q01 后重新算分：这一期不再算它，问题数和回答数跟着变",
              "q01" not in summary["mention"]["byQuestion"] and "q01" not in summary["cells"] and summary["expected"] == 27
              and scored["mention"]["valid"] < 48, (sorted(summary["mention"]["byQuestion"]), summary["expected"]))
        call(SCORE, "set-judgement", "--date", latest, "--file", write(tmp, "j2.json", {"descriptions": {"hunyuan": "新的介绍"}, "issues": []}), env=env)
        built = call(REPORT, "publish", "--date", latest, env=env)
        _, _, data = page_json(next(f for f in built["reportFiles"] if f.endswith(latest + ".html")))
        check("报告里的问题清单也没有 q01，和监测设置一致", "q01" not in [q["id"] for q in data["questions"]], [q["id"] for q in data["questions"]])


def test_trend_skips_incomplete():
    """三期里中间一期数据不全：不判断涨跌，并说明为什么不能比。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        root = Path(env["GEO_DATA_ROOT"])
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)

        def period(day, hits, complete):
            bucket = {"hits": hits, "valid": 40}
            summary = {"questionsVersion": 1, "expected": 36, "returned": 36 if complete else 20, "missing": [], "complete": complete,
                       "notUs": [], "answers": {}, "cells": {},
                       "mention": dict(bucket, byProvider={p: {"hits": 0, "valid": 0} for p in ("hunyuan", "doubao", "deepseek")},
                                       byQuestion={"q01": bucket}),
                       "refs": {"total": 0, "own": 0, "storePages": 0, "aboutStore": 0, "ownItems": [], "storePageItems": [], "aboutItems": []},
                       "sources": {"all": [], "byProvider": {}}, "rivals": [], "buyEntry": None}
            folder = root / "runs" / day
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

        period("2026-09-21", 9, True)
        period("2026-09-28", 5, False)
        period("2026-10-05", 2, True)
        compared = call(REPORT, "compare", "--date", "2026-10-05", env=env)
        check("中间一期数据不全：不判断涨跌，不拿它当上一期，并说明不能比",
              compared["trend"] == "observe" and compared["previous"] == ""
              and any("不全" in n and "比" in n for n in compared["notes"]), compared)
        period("2026-09-28", 5, True)
        compared = call(REPORT, "compare", "--date", "2026-10-05", env=env)
        check("三期都完整、连续两期下降，才写下降", compared["trend"] == "down" and compared["previous"] == "2026-09-28", compared)


def test_copies():
    copies = [(SKILLS / name / "scripts" / "geo_common.py").read_bytes() for name in ("geo-profile", "geo-check", "geo-workbench")]
    check("三个技能里的 geo_common.py 内容一致", copies[0] == copies[1] == copies[2])


def test_template():
    html = TEMPLATE.read_text(encoding="utf-8")
    check("默认模板不显示信息待确认侧栏提示", "有信息等你确认" not in html)
    check("工作台更新时间只展示一处", html.count("'更新于 ' + updatedAt()") == 1)
    check("模板里只有数据这一个占位符，龙虾图标已经内嵌", html.count("__GEO_DATA__") == 1 and "__MASCOT_B64__" not in html)
    check("模板不引用外部资源", not re.search(r'(?:src|href)\s*=\s*["\']https?://', html) and "@import" not in html and "url(http" not in html)
    urls = sorted(set(re.findall(r"https?://[^\s'\"<>)]+", html)))
    check("模板里唯一的外部文件是有赞官方的客户端接入脚本，只在嵌在网页版客户端里才加载",
          urls == ["http://www.w3.org/2000/svg", "https://b.yzcdn.cn/yzclaw/claw-host/0.0.1/claw-host.js"]
          and "script.src = HOST_SDK" in html and "if (!framed) { return; }" in html, urls)
    script = REPORT.read_text(encoding="utf-8")
    builtin = re.findall(r'\{"id": "([a-z]+)"', script.split("WORKBENCH_PAGES = (")[1].split(")\n")[0])
    renderers = re.findall(r"([a-z]+): page[A-Z]", html.split("var PAGES = {")[1].split("};")[0])
    fallback = re.findall(r"\{ id: '([a-z]+)'", html.split("var NAV_ITEMS")[1].split("]);")[0])
    check("页面清单里的内置页面，模板里都有画它的代码；旧数据没有 nav 时的默认导航也是这几页",
          builtin == ["overview", "content", "settings"] and sorted(renderers) == sorted(builtin) and fallback == builtin, (builtin, renderers, fallback))
    in_script = builtin
    sections_template = re.findall(r"\['([a-z]+)', '[^']+'\]", html.split("var SECTIONS = [")[1].split("];")[0])
    sections_script = re.findall(r'\("[^"]+", "([a-z]+)"\)', script.split("REPORT_SECTIONS = (")[1].split("REPORT_FILE")[0])
    check("报告里的小节，脚本和模板一致", len(sections_script) == 5 and sections_template == sections_script, (sections_template, sections_script))
    docs = (SKILLS / "geo-workbench" / "SKILL.md").read_text(encoding="utf-8")
    in_docs = re.findall(r"`#/([a-z]+)", docs)
    check("工作台说明里的页面和脚本里的页面一致，并写了“在工作台里打开报告”的地址",
          sorted(set(in_docs) - {"report"}) == sorted(in_script) and "report" in in_docs, (sorted(set(in_docs)), sorted(in_script)))
    check("工作台说明里列全了报告的小节", all("`%s`" % section in docs for section in sections_script), [x for x in sections_script if "`%s`" % x not in docs])
    check("首页没有“员工已经做了的工作”“现在该做的”这两块", "员工已经做了的工作" not in html and "现在该做的" not in html)
    check("报告嵌在工作台里打开：模板里有内嵌的入口、内嵌的标记和打不开时的退路",
          "rpt-frame" in html and "#embed" in html and "单独打开这份报告" in html and "report-ready" in html)
    draft = html.split("function openDraft(item)")[1].split("function siteCard")[0]
    check("稿子抽屉：公众号排版预览带手机框嵌在抽屉里，小红书画成笔记、封面占位写着配图建议，不挂状态和来历的小标签",
          "preview-frame" in draft and "phone-stage" in draft and "sameSite(item.previewUrl)" in draft and "xhsNote(item)" in draft
          and "statusText" not in draft and "你点名要的" not in draft and "item.tip" in html.split("function xhsNote(item)")[1].split("function copyLabel")[0])


def test_demo_fixture():
    """多期的状态（走势、上一期对比、打过勾的待办、三种类型的内容、多份报告）用虚构数据回归。"""
    fixtures = [HERE / "fixtures" / "page-data.demo.json", HERE / "fixtures" / "report-data.demo.json"]
    if not all(f.is_file() for f in fixtures):
        print("跳过  多期回归（没有 fixtures 里的两份演示数据，先运行 make_demo.py）")
        return
    workbench, report = (json.loads(f.read_text(encoding="utf-8")) for f in fixtures)
    check("多期样例标明是演示数据，工作台有五期、每期都有报告的链接",
          workbench["store"]["demo"] is True and report["store"]["demo"] is True and len(workbench["periods"]) >= 5
          and all(p["reportUrl"] for p in workbench["periods"]) and report["period"]["no"] == len(workbench["periods"]), workbench["periods"][-1])
    with tempfile.TemporaryDirectory() as tmp:
        for label, fixture in zip(("工作台（多期，演示数据）", "最新一期的报告（多期，演示数据）"), fixtures):
            rendered = render_fixture(fixture, Path(tmp) / (fixture.stem + ".html"))
            keep_page(label, rendered["file"])


READER_BANNED = ("商家", "周报", "publish", "set-", "geo_", "Skill", "技能", "员工要", "请执行")


def _smoke(paths):
    node = shutil.which("node")
    if not node:
        return None
    proc = subprocess.run([node, str(HERE / "page_smoke.cjs"), *[str(p) for p in paths]], capture_output=True, text=True)
    return json.loads(proc.stdout)["files"]


def test_many_periods():
    """有好几期报告以后，首页“没点名时提到你”怎么显示。"""
    fixture = HERE / "fixtures" / "page-data.demo.json"
    if not fixture.is_file() or not shutil.which("node"):
        print("跳过  多期首页的检查（没有演示数据或没有 node）")
        return
    data = json.loads(fixture.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        plain = render_fixture(fixture, Path(tmp) / "a.html")
        # 假设第 3 期起商家改过问题：前两期是按旧问题测的
        changed = json.loads(json.dumps(data))
        for period in changed["periods"][:2]:
            period["questionsVersion"] = 0
        reset = render_fixture(changed, Path(tmp) / "b.html")
        # 假设这一期刚改过问题：没有可比的上一期
        fresh = json.loads(json.dumps(data))
        for period in fresh["periods"][:-1]:
            period["questionsVersion"] = 0
        fresh["compare"] = {"previous": "", "mention": {}, "ownRefs": {}, "trend": "observe", "baselineReset": True}
        first = render_fixture(fresh, Path(tmp) / "c.html")
        a, b, c = _smoke([plain["file"], reset["file"], first["file"]])
    latest, before = data["periods"][-1]["mention"], data["periods"][-2]["mention"]
    # 页面不再写“上面的数不是累计”这类说明：首页标着第几期，数旁边是上一期的数，已经说清了
    check("多期时首页显示的是最新一期的数，带上一期的数和走势",
          not a["errors"] and "上一期 %d/%d，连续上升" % (before["hits"], before["valid"]) in a["homeText"]
          and "第 %d 期" % data["periods"][-1]["no"] in a["homeText"] and a["sparkBars"] == len(data["periods"]), (a["errors"], a["sparkBars"]))
    check("问题改过以后：小柱子只画新问题的那几期，旧的几期在表里标出来",
          not b["errors"] and b["sparkBars"] == len(data["periods"]) - 2 and b["homeText"].count("旧问题") >= 2 and "旧问题" not in a["homeText"],
          (b["errors"], b["sparkBars"]))
    check("刚改过问题的那一期：不和之前比，也不画走势", not c["errors"] and c["sparkBars"] == 0 and "问题改过了，从这一期重新比" in c["homeText"],
          (c["errors"], c["sparkBars"]))


def test_reader_voice():
    """商家在页面上逐字看到、由脚本写的文字只有一类：报告里“读这份报告前要知道的”。里面不能出现写给员工看的话。

    出过的事故：给员工的提示“周报里不要写成上升或下降”原样出现在了商家的报告里。
    """
    source = REPORT.read_text(encoding="utf-8")
    reader = re.findall(r'payload\["readerNotes"\]\.append\("([^"]+)"', source)
    reader += re.findall(r'\bnotes\.append\("([^"]+)"', source)  # 报告里另外追加的两条
    bad = [text for text in reader if any(word in text for word in READER_BANNED)]
    check("页面说明是写给商家看的，没有混进给员工的提示（共 %d 条）" % len(reader), len(reader) >= 6 and not bad, bad or reader)
    seen, bad = 0, []
    for label, path in PAGES:
        _, _, data = page_json(path)
        texts = list(data.get("notes") or [])
        seen += len(texts)
        bad += [(label, text) for text in texts if any(word in text for word in READER_BANNED)]
    # 真实存档回放会多生成一份报告；本机没有那份存档时少查一条
    least = 3 if ARCHIVE.is_dir() else 2
    check("生成出来的报告上，说明里没有写给员工看的话（查了 %d 条）" % seen, seen >= least and not bad, bad[:3])
    for script in (STATE, RUN, SCORE, REPORT):
        if "log_event" in script.read_text(encoding="utf-8"):
            check("脚本里不再记工作记录（页面上已经不显示了）", False, script.name)
            break
    else:
        check("脚本里不再记工作记录（页面上已经不显示了）", True)


def test_pages_render():
    node = shutil.which("node")
    if not node:
        print("跳过  工作台逐页渲染检查（本机没有 node）")
        return
    proc = subprocess.run([node, str(HERE / "page_smoke.cjs"), *[str(path) for _, path in PAGES]], capture_output=True, text=True)
    try:
        report = json.loads(proc.stdout)["files"]
    except (json.JSONDecodeError, KeyError):
        check("工作台逐页渲染检查能跑起来", False, proc.stdout[:200] + proc.stderr[:300])
        return
    clicks = {"workbench": 0, "report": 0}
    for (label, path), item in zip(PAGES, report):
        clicks[item["kind"]] = clicks.get(item["kind"], 0) + int(item.get("linkClicks") or 0)
        if item["kind"] == "report":
            check("报告能渲染，单独打开带标题、嵌在工作台里不带：%s" % label, not item["errors"] and item.get("embedded") is True, item["errors"][:3])
            continue
        _, _, data = page_json(path)
        dates = [p["date"] for p in data["periods"]]
        routes = item.get("routes") or []
        # 三个页面 + 每一期报告在工作台里打开的地址，再加一次“地址不对时回到首页”
        ok = not item["errors"] and item["pages"] == len(routes) + 1 and {"overview", "content", "settings"} <= set(routes) \
            and all("report/" + d in routes for d in dates[-6:]) and len(item.get("frames") or []) == sum(1 for r in routes if r.startswith("report/")) \
            and all("#embed" in src for src in item.get("frames") or [])
        check("工作台能渲染，每一期的报告都在工作台里打开：%s" % label, ok, item["errors"][:3] or (routes, item.get("frames")))
    check("外链真的点到了：工作台 %d 个、报告 %d 个，在客户端里都交给客户端打开，被拦下时都弹出了可复制的链接" % (clicks["workbench"], clicks["report"]),
          clicks["workbench"] > 0 and clicks["report"] > 0, clicks)


def test_douyin_and_sources():
    """抖音视频文案按自己的规格登记；算分输出给出每个 AI 各自最常读哪里，员工建议往哪发时照这个说。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp)
        call(STATE, "init", "--segment", "local", "--brand", "示例小店", env=env)
        call(STATE, "set-facts", "--file", write(tmp, "f.json", dict(SYNTHETIC_FACTS, **{"from": "backend"})), env=env)
        video = {"type": "douyin", "origin": "asked", "title": "测试路示例小店：每天现烤的全麦吐司",
                 "body": "（镜头：门头）我是示例小店，在测试市测试路 1 号。（镜头：出炉）每天早上 9 点现烤全麦吐司，晚上 8 点关门。",
                 "tags": ["测试市美食", "#吐司"], "tip": "早上出炉时拍"}
        error = call(REPORT, "add-content", "--file", write(tmp, "dy-long.json", dict(video, title="这是一个超过三十个字的抖音作品标题所以放不进作品描述的第一句里面")), env=env, expect=2)
        check("抖音视频文案的标题超过 30 个字会被退回", "最多 30 个字" in error.get("error", ""), error)
        added = call(REPORT, "add-content", "--file", write(tmp, "dy.json", video), env=env)
        check("登记抖音视频文案：类型名、话题去掉 #、带拍摄提示",
              (added["type"], added["typeName"], added["tags"], added["tip"]) == ("douyin", "抖音视频文案", ["测试市美食", "吐司"], "早上出炉时拍"), added)
        questions = [q for q in SYNTHETIC_QUESTIONS if q["id"] not in ("q04", "q05")]
        call(STATE, "set-questions", "--file", write(tmp, "q.json", questions), env=env)
        call(STATE, "confirm-monitoring", env=env)
        call(RUN, "start", "--phase", "open", "--date", DATE, env=env)
        wait_all(env, DATE)
        call(RUN, "start", "--phase", "brand", "--date", DATE, env=env)
        wait_all(env, DATE)
        digest = call(SCORE, "score", "--date", DATE, env=env)
        check("算分输出给出每个 AI 各自最常读哪里、各占多少",
              set(digest["sourcesByProvider"]) == {"元宝", "豆包", "DeepSeek"} and digest["sourcesByProvider"]["豆包"][0].startswith("抖音 "), digest["sourcesByProvider"])


if __name__ == "__main__":
    try:
        for test in (test_copies, test_template, test_synthetic, test_public_empty_accounts, test_backend_source, test_site, test_facts_merge, test_no_silent_caps, test_edited_page, test_new_agent_guards, test_resume_mid_check, test_data_reliability, test_trend_skips_incomplete, test_environment_error, test_replay, test_demo_fixture, test_many_periods, test_reader_voice, test_pages_render, test_douyin_and_sources):
            try:
                test()
            except AssertionError as exc:
                check(test.__name__ + " 中途出错", False, exc)
    finally:
        shutil.rmtree(KEEP, ignore_errors=True)
    failed = [name for name, ok in results if not ok]
    print("\n共 %d 项，失败 %d 项" % (len(results), len(failed)))
    sys.exit(1 if failed else 0)
