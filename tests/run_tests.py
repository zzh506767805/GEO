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
REPORT = SKILLS / "geo-weekly" / "scripts" / "geo_report.py"
TEMPLATE = SKILLS / "geo-weekly" / "assets" / "page.html"
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
    "audience": [{"name": "附近居民", "who": "住在周边的人", "scene": "想找一家常去的面包店", "worry": "离得近不近", "basis": "商品评价"}],
    "stores": [{"name": "测试路店", "address": "测试市测试路 1 号", "hours": "09:00-20:00", "status": "在营", "source": "有赞后台"}],
    "channels": {"wechatOfficial": "示例小店官方号"},
}
SYNTHETIC_QUESTIONS = [
    {"id": "q01", "kind": "open", "tag": "品类", "text": "测试市哪家面包店好吃？", "audience": "附近居民", "worry": "口碑"},
    {"id": "q02", "kind": "open", "tag": "地段", "text": "测试路附近有什么面包店？", "audience": "不存在的人群"},
    {"id": "q03", "kind": "open", "tag": "场景", "text": "这是一道用来测记忆标记的题目"},
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
        shown = call(STATE, "show", "--part", "questions", env=env)["questions"]["items"]
        check("不存在的顾客类型会被清空", shown[1]["audience"] == "" and shown[0]["audience"] == "附近居民")
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

        error = call(RUN, "start", "--phase", "brand", "--date", DATE, env=env, expect=2)
        check("带店名的问题不能先于不带店名的问题", "还没有跑完" in error.get("error", ""), error)
        started = call(RUN, "start", "--phase", "open", "--date", DATE, env=env)
        check("发起 30 条不带店名的查询", started["started"] == 30 and started["running"] == 30 and not started["finished"], started)
        waiting = call(RUN, "status", "--date", DATE, env=env)
        check("运行中的提示写明“不要当成出错”", "不要把它当成出错" in waiting["next"], waiting["next"])
        check("发起体检后工作台又变成待同步", call(STATE, "status", env=env)["workbench"]["pending"] == ["体检进度"])
        running = call(REPORT, "publish", env=env)
        check("体检进行中同步一次，工作台上是进度而不是旧结果",
              running["progress"].get("running") == 30 and running["periods"] == 0 and running["firstTime"] is False, running)
        keep_page("体检进行中", running["file"])
        progress = wait_all(env, DATE)
        check("挂起的查询到时限后记为缺失，失败的查询也记为缺失",
              sorted(progress["missing"]) == ["q04_deepseek", "q05_hunyuan"] and progress["done"] == 28, progress)
        check("两段没跑完时不算整轮结束", progress["finished"] is False and "start --phase brand" in progress["next"], progress)
        call(RUN, "start", "--phase", "brand", "--date", DATE, env=env)
        progress = wait_all(env, DATE)
        check("带店名的 6 条查询返回，整轮结束", progress["done"] == 34 and progress["finished"] is True, progress)
        noop = call(RUN, "start", "--phase", "open", "--date", DATE, env=env)
        check("重复发起不会重复提问", noop["started"] == 0, noop)

        digest = call(SCORE, "score", "--date", DATE, env=env)
        check("提及统计：豆包 2/19，其余为 0，带记忆的回答被剔除",
              digest["mention"]["byProvider"] == {"元宝": "0/18", "豆包": "2/19", "DeepSeek": "0/18"} and digest["memoryFlagged"] == 1, digest["mention"])
        check("本店公众号被引用 12 次，门店页 12 次", (digest["refs"]["own"], digest["refs"]["storePages"]) == (12, 12), digest["refs"])
        check("竞品次数按有效回答数", digest["rivals"][0] == {"name": "甲记面包", "count": 55}, digest["rivals"])
        check("缺失 2 条不到四分之一，数据算完整", digest["complete"] is True and len(digest["missing"]) == 2)

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
        error = call(REPORT, "set-actions", "--date", DATE, "--file",
                     write(tmp, "a-old.json", {"brief": "x", "article": {"status": "preview", "title": "测试文章"}}), env=env, expect=2)
        check("写好的内容不能再塞进本期动作里，要单独登记", "add-content" in error.get("error", ""), error)
        acted = call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a.json", {
            "brief": "本期小结：只有豆包提到你。",
            "todos": [{"text": "一"}, {"text": "二"}, {"text": "三"}, {"text": "四"}]}), env=env)
        check("写了小结就没有提醒", acted["brief"] is True and acted["warnings"] == [], acted)
        call(REPORT, "mark-todo", "--no", "2", env=env)
        error = call(REPORT, "mark-todo", "--no", "9", env=env, expect=2)
        check("没有的待办序号会被拒绝", "没有第 9 件" in error.get("error", ""), error)
        call(REPORT, "set-actions", "--date", DATE, "--file", write(tmp, "a2.json", {"gaps": [{"where": "公众号", "note": "没有文章被引用"}]}), env=env)
        shown = call(REPORT, "show", env=env)
        check("只传要改的部分，其余保持不变（小结、打过勾的待办都在）",
              shown["brief"].startswith("本期小结") and [t["done"] for t in shown["todos"]] == [False, True, False]
              and len(shown["gaps"]) == 1 and shown["contents"] == [], shown)

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
        full = call(REPORT, "contents", "--no", "1", env=env)
        check("能取回登记的全文", full["content"]["body"] == clean_text, full["content"]["body"][:60])
        listed = call(REPORT, "contents", env=env)
        check("内容清单：新的在前，告诉下一篇的序号和等确认的有几篇",
              [(a["no"], a["type"], a["status"]) for a in listed["items"]] == [(3, "wechat", "confirmed"), (2, "xhs", "dropped"), (1, "text", "preview")]
              and listed["waiting"] == 1 and listed["nextNo"] == 4, listed)
        check("show 里能看到工作台还有哪些变化没同步", "内容" in call(REPORT, "show", env=env)["workbench"]["pending"])

        built = call(REPORT, "publish", "--date", DATE, env=env)
        check("再次同步：链接不变，不再算第一次开通，这一期登记过内容就不再提醒",
              built["published"] and built["pageUrl"] == first["pageUrl"] and built["firstTime"] is False
              and "内容" in built["synced"] and "warnings" not in built, built)
        check("同步后没有待同步的变化", call(REPORT, "links", env=env)["upToDate"] is True)
        keep_page("一期（合成数据）", built["file"])
        check("这一期的报告单独一个文件，有自己的链接，和工作台的链接一起给出",
              built["reportUrl"].endswith("/report-%s.html" % DATE) and built["links"]["这一期的报告"] == built["reportUrl"]
              and [Path(f).name for f in built["reportFiles"]] == ["report-%s.html" % DATE] and "reportUrl" in built["next"], built)
        keep_page("一期的报告（合成数据）", built["reportFiles"][0])
        html, block, data = page_json(built["file"])
        check("工作台生成成功，占位符已替换", "__GEO_DATA__" not in html and data.get("kind") == "workbench" and data.get("runDate") == DATE)
        check("网页里的数据块不含能提前结束标签的字符", block is not None and "<" not in block.group(1))
        check("待办最多保留三件", len(data["actions"]["todos"]) == 3)
        check("工作台数据里有小结和打勾状态，体检做完后不再显示进行中",
              data["actions"]["brief"].startswith("本期小结") and data["actions"]["todos"][1]["done"] is True and data["progress"] == {}, data["actions"])
        check("工作台上的内容：按类型带各自的东西，不发了的不带稿子",
              [(c["no"], c["typeName"], c["status"], bool(c["body"]), bool(c["previewUrl"])) for c in data["contents"]]
              == [(3, "公众号文章", "confirmed", False, True), (2, "小红书笔记", "dropped", False, False), (1, "长文", "preview", True, False)]
              and data["periods"][-1]["content"]["count"] == 2 and data["contentTypes"]["xhs"] == "小红书笔记", data["contents"])
        period = data["periods"][-1]
        check("工作台只放跨期的东西：每期一行，带报告的链接，不带回答原文和逐题明细",
              len(data["periods"]) == 1 and (period["no"], period["reportFile"], period["reportUrl"]) == (1, "report-%s.html" % DATE, built["reportUrl"])
              and "answers" not in data and "dots" not in period and "issues" not in data and data["latest"]["rivals"][0]["name"] == "甲记面包", period)
        check("监测设置：问题、同类店，和员工另外记下的信息",
              len(data["settings"]["questions"]) == 12 and [r["name"] for r in data["settings"]["rivals"]] == ["甲记面包", "乙家烘焙"]
              and data["settings"]["extras"]["wechatOfficial"] == "示例小店官方号" and data["settings"]["from"] == "public", data["settings"]["extras"])
        kinds = [event["kind"] for event in data["log"]]
        check("工作记录自动记下了建档、开通工作台、体检、核对回答、已改、重新打开、写内容",
              all(k in kinds for k in ("profile", "questions", "rivals", "page", "check", "issue", "fixed", "reopen", "content")), kinds)
        check("汇总数：1 次体检、内容 2 篇、其中 1 篇等确认，不把对不上的说法当成一项成绩",
              (data["totals"]["periods"], data["totals"]["contents"], data["totals"]["contentsWaiting"]) == (1, 2, 1) and "issuesFound" not in data["totals"], data["totals"])
        _, _, report = page_json(built["reportFiles"][0])
        check("报告带这一期的全部证据：逐题圆点、回答原文、同类店、内容来源",
              report["kind"] == "report" and report["period"] == {"date": DATE, "no": 1, "latest": True}
              and report["dots"]["q02"]["doubao"] == "hh" and report["dots"]["q03"]["doubao"] == "mn"
              and len(report["answers"]["q02_doubao"]) == 2 and report["rivals"][0]["name"] == "甲记面包" and report["sources"]["doubao"], report["period"])
        check("缺失的查询在报告的圆点里留空", report["dots"].get("q04", {}).get("deepseek", "") == "")
        check("和店铺资料对不上的说法只出现在报告里，带固定序号",
              [(i["no"], i["id"]) for i in report["issues"]] == [(1, "hours-wrong")] and report["workbenchUrl"] == first["pageUrl"], report["issues"])
        check("报告里有这一期的小结、待办和写的内容", report["actions"]["brief"].startswith("本期小结") and len(report["actions"]["todos"]) == 3
              and [c["no"] for c in report["contents"]] == [1, 3], report["contents"])
        rendered = call(REPORT, "render", "--data", write(tmp, "page.json", data), "--out", str(Path(tmp) / "out" / "page.html"), env=env)
        again = call(REPORT, "render", "--data", write(tmp, "report.json", report), "--out", str(Path(tmp) / "out" / "report.html"), env=env)
        check("给一份数据就能直接渲染出网页，工作台和报告都行", (rendered["kind"], again["kind"]) == ("workbench", "report")
              and Path(rendered["file"]).read_text(encoding="utf-8").count("__GEO_DATA__") == 0)
        error = call(REPORT, "render", "--data", write(tmp, "broken.json", {"store": {}}), "--out", str(Path(tmp) / "x.html"), env=env, expect=2)
        check("数据不全时说明缺哪部分", "缺少" in error.get("error", ""), error)
        check("网页文件名是英文", Path(built["file"]).name == "ai-visibility.html")

        call(STATE, "set-assets", "--file", write(tmp, "assets.json", {"items": [{"platform": "公众号", "found": False, "note": "没有搜到同名的号"}]}), env=env)
        failed = call(REPORT, "publish", env=dict(env, MOCK_UPLOAD_FAIL="1"))
        check("上传失败时如实返回，不给新链接，并说明退路",
              failed["published"] is False and failed["pageUrl"] == first["pageUrl"] and "工作台" in failed["reason"] and "报告" in failed["reason"]
              and "youzan-oss" in failed["next"] and "不要编链接" in failed["next"], failed)
        stale = call(REPORT, "links", env=env)
        check("没同步上去的变化会一直提醒", stale["upToDate"] is False and stale["pending"] == ["已有的内容"] and "publish" in stale["next"], stale)
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
        check("报告的链接也能手动补", fixed["report"] == DATE and call(REPORT, "links", env=env)["reports"][DATE].endswith("/f/abc/report-%s.html" % DATE), fixed)

        changed = [dict(q, text="测试市哪家的贝果好吃？") if q["id"] == "q06" else q for q in SYNTHETIC_QUESTIONS]
        bumped = call(STATE, "set-questions", "--file", write(tmp, "changed.json", changed), env=env)
        check("改了问题原文才算口径变化", bumped["questionsVersion"] == 2, bumped)
        restart = call(RUN, "start", "--phase", "open", "--date", DATE, "--only", "q06", env=env)
        check("改过的问题会重新提问", restart["started"] == 3, restart)
        confirmed = call(STATE, "confirm", env=env)
        check("确认后状态变为已确认", confirmed["confirmed"] is True)


def test_environment_error():
    with tempfile.TemporaryDirectory() as tmp:
        env = base_env(tmp, MOCK_RUN_ERROR="1")
        call(STATE, "init", "--segment", "ecom", "--brand", "示例小店", env=env)
        call(STATE, "set-questions", "--file", write(tmp, "q.json", SYNTHETIC_QUESTIONS), env=env)
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
        call(STATE, "set-assets", "--file", str(fixtures / "assets.json"), env=env)
        call(REPORT, "publish", env=env)  # 和员工的真实顺序一样：建完档先开通工作台
        call(RUN, "start", "--phase", "open", "--date", DATE, env=env)
        wait_all(env, DATE)
        call(RUN, "start", "--phase", "brand", "--date", DATE, env=env)
        wait_all(env, DATE)
        digest = call(SCORE, "score", "--date", DATE, env=env)
        check("回放：元宝 0/24、DeepSeek 0/24，豆包剔除 3 个带记忆的回答后是 1/21",
              digest["mention"]["byProvider"] == {"元宝": "0/24", "豆包": "1/21", "DeepSeek": "0/24"} and digest["memoryFlagged"] == 3, digest["mention"])
        check("回放：唯一没带记忆痕迹的提及出在留下附近那道题", digest["questionsMentioned"] == ["q11"], digest["questionsMentioned"])
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
        check("回放：工作台上的汇总数和存档一致（1 期、84 个回答、14 个问题）",
              (data["totals"]["periods"], data["totals"]["answers"], data["totals"]["questions"]) == (1, 84, 14), data["totals"])
        check("回放：报告里对不上的说法按序号排列，资料来源标的是公开信息",
              [i["no"] for i in report["issues"]] == [1, 2, 3, 4] and report["factsFrom"] == "public" and data["settings"]["pending"] is True, report["factsFrom"])
        keep_page("工作台（麦的日尝真实存档）", built["file"])
        keep_page("第 1 期报告（麦的日尝真实存档）", built["reportFiles"][0])
        SAMPLE.mkdir(parents=True, exist_ok=True)
        for source in (built["file"], built["reportFiles"][0]):
            shutil.copyfile(source, SAMPLE / Path(source).name)
        print("      示例已更新：" + str(SAMPLE))


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
        keep_page("工作台（资料来自店铺后台，还没体检）", published["file"])


def test_copies():
    copies = [(SKILLS / name / "scripts" / "geo_common.py").read_bytes() for name in ("geo-profile", "geo-check", "geo-weekly")]
    check("三个技能里的 geo_common.py 内容一致", copies[0] == copies[1] == copies[2])


def test_template():
    html = TEMPLATE.read_text(encoding="utf-8")
    check("模板里只有数据这一个占位符，龙虾图标已经内嵌", html.count("__GEO_DATA__") == 1 and "__MASCOT_B64__" not in html)
    check("模板不引用外部资源", not re.search(r'(?:src|href)\s*=\s*["\']https?://', html) and "@import" not in html and "url(http" not in html)
    script = REPORT.read_text(encoding="utf-8")
    in_template = re.findall(r"\['([a-z]+)', '[^']+', '[a-z]+'\]", html)
    in_script = re.findall(r'\("[^"]+", "([a-z]+)"\)', script.split("PAGES = (")[1].split("\n")[0])
    check("工作台只有三个页面，脚本给出的链接和模板里的导航一一对应",
          in_script == ["overview", "content", "settings"] and in_template == in_script, (in_template, in_script))
    sections_template = re.findall(r"\['([a-z]+)', '[^']+'\]", html.split("var SECTIONS = [")[1].split("];")[0])
    sections_script = re.findall(r'\("[^"]+", "([a-z]+)"\)', script.split("REPORT_SECTIONS = (")[1].split("REPORT_FILE")[0])
    check("报告里的小节，脚本和模板一致", len(sections_script) == 5 and sections_template == sections_script, (sections_template, sections_script))
    docs = (SKILLS / "geo-weekly" / "references" / "workbench.md").read_text(encoding="utf-8")
    in_docs = re.findall(r"`#/([a-z]+)`", docs)
    check("工作台说明里的页面和脚本里的页面完全一致（不多不少）", sorted(set(in_docs)) == sorted(in_script), (sorted(set(in_docs)), sorted(in_script)))
    check("工作台说明里列全了报告的小节", all("`#%s`" % section in docs for section in sections_script), [x for x in sections_script if "`#%s`" % x not in docs])


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
            rendered = call(REPORT, "render", "--data", str(fixture), "--out", str(Path(tmp) / (fixture.stem + ".html")), env=base_env(tmp))
            keep_page(label, rendered["file"])


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
    for (label, _), item in zip(PAGES, report):
        expected = 1 if item["kind"] == "report" else 4  # 工作台三个页面，加一次“地址不对时回到首页”
        check("页面能渲染、没有把空值显示出来：%s" % label, not item["errors"] and item["pages"] == expected, item["errors"][:3] or item["pages"])


if __name__ == "__main__":
    try:
        for test in (test_copies, test_template, test_synthetic, test_backend_source, test_environment_error, test_replay, test_demo_fixture, test_pages_render):
            try:
                test()
            except AssertionError as exc:
                check(test.__name__ + " 中途出错", False, exc)
    finally:
        shutil.rmtree(KEEP, ignore_errors=True)
    failed = [name for name, ok in results if not ok]
    print("\n共 %d 项，失败 %d 项" % (len(results), len(failed)))
    sys.exit(1 if failed else 0)
