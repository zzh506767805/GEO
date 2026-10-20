#!/usr/bin/env python3
"""工作台和体检报告：把建档、体检、核对、写内容的结果同步成商家能打开的网页。

两种网页，都用 assets/page.html 这一个模板，样式都在模板里，这里只负责准备数据：

  工作台    <数据目录>/pages/ai-visibility.html      一个固定的链接，只放跨期的东西：
            最新结论、几个数的走势、每一期报告的入口、替商家写的内容、监测设置。
  体检报告  <数据目录>/pages/report-<日期>.html      每期一份独立的文件，带这一期的全部证据：
            问了什么、AI 提没提到、提到了谁、读了哪里的内容、怎么介绍这家店。

商家看报告不用跳到别的页面：工作台把那一期的报告文件嵌在自己的内容区里（地址是 工作台链接#/report/<日期>）。
发给商家的就是这个地址（输出里的 reportUrl）。报告文件自己的链接是 reportFileUrl，商家要单独转发给别人时才用。

同一路径重复上传时云盘链接不变，所以商家收藏一次工作台，就能一直看到最新的内容和每一期的报告。

员工日常只用 publish 这一条：重新生成这一期的报告和工作台、传到云盘、保存链接。
任何一步改了数据（建档、体检、核对、商家确认、写内容），都要再执行一次 publish。

用法（脚本用绝对路径执行）：
  geo_report.py publish [--date D]        生成并同步工作台和这一期的报告（最常用）
  geo_report.py links                      工作台各页面和每一期报告的链接，以及它们是不是最新的
  geo_report.py show                       最新一期的小结、建议、各平台读哪里，和最近的内容（商家说“第 2 篇”时先看这里）
  geo_report.py compare [--date D]         和上一期对比
  geo_report.py set-actions --file <json> [--date D]   本期小结、建议商家做的事、缺的内容、这一期没写内容的原因
  geo_report.py add-content --file <json>              登记一条内容（公众号文章、小红书笔记、长文、抖音视频文案）；带 no 是改稿
  geo_report.py mark-content [--no N] [--status S] [--channel 放到了哪] [--ref 交付凭据]
  geo_report.py site-brief                             做官网要用的东西：能放上去的店铺资料、顾客常问的问题、现在官网到了哪一步
  geo_report.py set-site [--status test|published|dropped] [--test-url U] [--url U] [--page-name N] [--domain D]
                                                       登记官网：测试版好了、正式上线了、绑了独立域名、不要了
  geo_report.py set-page-url --url <云盘链接> [--report 日期]

内容按类型登记。稿子本身跟着类型走：公众号文章是带排版的长文（公众号技能产出，登记排版预览链接），
小红书笔记是短标题、短正文加话题，长文是纯文字稿。这里不关心稿子是谁写的、用哪个技能写的，
只记这一类型交回来的东西，所以不和任何一个写作技能绑死。类型的规格见 CONTENT_TYPES。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.dont_write_bytecode = True

import geo_common as gc  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "page.html"
PLACEHOLDER = "__GEO_DATA__"
# 内容类型。稿子本身跟着类型走：公众号文章和小红书笔记不是同一份稿子换个排版，标题长度、正文长度、写法都不一样。
# 加一种类型：这里加一行规格，再在 geo-content 技能的 references/writing.md 里写清这种稿子怎么写、谁来写、商家怎么审。
#   preview 为 True 表示这种类型的成品是带排版的页面，登记时必须带排版预览链接（公众号技能产出的就是这个）。
CONTENT_TYPES = {
    "wechat": {"name": "公众号文章", "titleMax": 64, "bodyMin": 0, "bodyMax": 8000, "tagsMax": 0, "preview": True},
    "xhs": {"name": "小红书笔记", "titleMax": 20, "bodyMin": 30, "bodyMax": 1000, "tagsMax": 10, "preview": False},
    "text": {"name": "长文", "titleMax": 60, "bodyMin": 80, "bodyMax": 6000, "tagsMax": 0, "preview": False},
    # 抖音视频文案：标题是作品描述的第一句，正文是口播稿（画面提示写在括号里），话题 3 到 5 个
    "douyin": {"name": "抖音视频文案", "titleMax": 30, "bodyMin": 50, "bodyMax": 1500, "tagsMax": 5, "preview": False},
}
# 状态和类型无关：等商家确认 → 商家确认了 → 已发布；或者不发了。放到了哪（公众号草稿箱、知乎……）另外记在 channels 里。
CONTENT_STATUS = ("preview", "confirmed", "published", "dropped")
CONTENT_ORIGINS = ("weekly", "asked")  # 每周主动写的 / 商家点名要的
WEEKLY_CONTENT_CAP = 2     # 每一期主动写的内容上限。批量铺稿是红线，这里用脚本卡住
ACTION_KEYS = ("brief", "todos", "gaps", "contentNote")
EXPECTED_PAGE_HOST = "claw-cloud.youzan.com"
UPLOAD_TIMEOUT = 50  # 一次同步要传报告和工作台两个文件，加起来要比 Bash 工具默认的 2 分钟短
# 工作台的三个页面，按导航顺序。每一页由模板里 PAGES 的同名函数画。某一期分析出来的东西放进那一期的报告，不要做成工作台的页面。
WORKBENCH_PAGES = (
    {"id": "overview", "title": "工作台", "icon": "home", "subtitle": "最新的结论，和每一期的体检报告"},
    {"id": "content", "title": "内容", "icon": "doc", "subtitle": "员工替你写的内容：公众号文章、小红书笔记、长文、抖音视频文案"},
    {"id": "settings", "title": "监测设置", "icon": "list", "subtitle": "员工每周替你问什么、和谁比"},
)
# 每期报告里的小节，顺序和模板里的一致。
REPORT_SECTIONS = (("结论", "summary"), ("有没有提到你", "mentions"), ("提到了谁", "rivals"),
                   ("读哪里的内容", "sources"), ("怎么介绍你", "says"))
REPORT_FILE = "report-%s.html"


def _scored_dates(until: str = "") -> list:
    return [d for d in gc.list_run_dates() if (not until or d <= until) and (gc.run_dir(d) / "summary.json").is_file()]


def _summary(date: str) -> dict:
    summary = gc.read_json(gc.run_dir(date) / "summary.json")
    if not summary:
        raise gc.GeoError("这一期还没有算分，请先按 geo-check 完成体检")
    return summary


def _empty_summary() -> dict:
    bucket = lambda: {"hits": 0, "valid": 0}  # noqa: E731
    return {
        "questionsVersion": 0, "expected": 0, "returned": 0, "missing": [], "complete": True, "notUs": [],
        "answers": {}, "mention": dict(bucket(), byProvider={p: bucket() for p in gc.PROVIDERS}, byQuestion={}),
        "refs": {"total": 0, "own": 0, "storePages": 0, "aboutStore": 0, "ownItems": [], "storePageItems": [], "aboutItems": []},
        "sources": {"all": [], "byProvider": {p: [] for p in gc.PROVIDERS}}, "rivals": [], "shops": [], "shopsPending": [], "findings": [], "buyEntry": None,
    }


def _ratio(bucket: dict) -> str:
    return "%d/%d" % (bucket.get("hits", 0), bucket.get("valid", 0))


def _share(bucket: dict) -> float:
    return bucket["hits"] / bucket["valid"] if bucket.get("valid") else 0.0


def _issues() -> list:
    ledger = gc.read_json(gc.profile_dir() / "issues.json", {}) or {}
    items = list((ledger.get("items") or {}).values())
    # 待处理的排前面，其次按序号；序号和 geo_score.py issues 给出的一致。
    items.sort(key=lambda i: (i["status"] != "open", int(i.get("no") or 0), i["id"]))
    return items


def _contents_path() -> Path:
    return gc.profile_dir() / "contents.json"


def _load_contents() -> dict:
    """内容账本：每一条替商家写的内容，不管是哪种类型、每周主动写的还是商家点名要的。"""
    ledger = gc.read_json(_contents_path(), {}) or {}
    ledger.setdefault("items", [])
    return ledger


def _save_contents(ledger: dict) -> None:
    ledger["updatedAt"] = gc.now_iso()
    gc.write_json(_contents_path(), ledger)


def _content_view(item: dict, with_body: bool = False) -> dict:
    row = {key: item.get(key, default) for key, default in (
        ("no", 0), ("type", "text"), ("title", ""), ("status", "preview"), ("origin", "weekly"), ("period", ""),
        ("forQuestion", ""), ("reason", ""), ("summary", ""), ("whereToPost", ""), ("tip", ""), ("tags", []),
        ("previewUrl", ""), ("channels", []), ("ref", ""), ("createdAt", ""), ("updatedAt", ""))}
    row["typeName"] = CONTENT_TYPES.get(row["type"], {}).get("name", row["type"])
    row["bodyChars"] = len(item.get("body") or "")
    if with_body:
        row["body"] = item.get("body") or ""
    return row


def _period_contents() -> dict:
    """期次 → 这一期写的内容（不含不发了的），新的在后。"""
    out = {}
    for item in _load_contents()["items"]:
        if item.get("status") != "dropped" and item.get("period"):
            out.setdefault(item["period"], []).append(item)
    return out


def _report_urls() -> dict:
    """期次 → 这一期报告的云盘链接。"""
    return (gc.read_json(gc.profile_dir() / "meta.json", {}) or {}).get("reports") or {}


def _period(day: str, number: int, written: dict, reports: dict):
    """一期体检在工作台上的那一行：几个数、写了什么、报告在哪。明细都在那一期的报告里。"""
    folder = gc.run_dir(day)
    summary = gc.read_json(folder / "summary.json")
    if not summary:
        return None
    actions = gc.read_json(folder / "actions.json", {}) or {}
    contents = written.get(day) or []
    mention = summary["mention"]
    return {
        "date": day,
        "no": number,
        "questionsVersion": summary.get("questionsVersion", 0),
        "mention": {"hits": mention["hits"], "valid": mention["valid"], "byProvider": mention["byProvider"]},
        "refs": {k: summary["refs"][k] for k in ("total", "own", "storePages", "aboutStore")},
        "expected": summary["expected"],
        "returned": summary["returned"],
        "complete": summary["complete"],
        "judged": (folder / "judgement.json").is_file(),
        "content": {"count": len(contents), "status": contents[-1]["status"] if contents else "",
                    "title": contents[-1]["title"] if contents else "", "note": actions.get("contentNote", "")},
        "reportFile": REPORT_FILE % day,
        "reportUrl": reports.get(day, ""),
    }


def _periods(date: str) -> list:
    written, reports = _period_contents(), _report_urls()
    # 每一期都留着：旧报告不清理，工作台上就要一直有它的入口
    rows = [_period(day, number, written, reports) for number, day in enumerate(_scored_dates(date), 1)]
    return [row for row in rows if row]


def _progress() -> dict:
    """最近一次体检是不是还在跑。工作台据此显示“体检进行中”。"""
    dates = gc.list_run_dates()
    if not dates:
        return {}
    day = dates[-1]
    items = list(((gc.read_json(gc.run_dir(day) / "queries.json", {}) or {}).get("items") or {}).values())
    if not items:
        return {}
    running = sum(1 for item in items if item["status"] == "running")
    scored = (gc.run_dir(day) / "summary.json").is_file()
    judged = (gc.run_dir(day) / "judgement.json").is_file()
    if scored and judged and not running:
        return {}
    return {"date": day, "total": len(items), "done": sum(1 for item in items if item["status"] == "done"),
            "running": running, "scored": scored, "judged": judged}


def _direction(values: list) -> str:
    """单周涨跌不下结论：最近两次变化同方向才算数。"""
    if len(values) < 3:
        return "observe"
    a, b = values[-1] - values[-2], values[-2] - values[-3]
    if a > 0 and b > 0:
        return "up"
    if a < 0 and b < 0:
        return "down"
    return "observe"


def compare_payload(date: str) -> dict:
    current = _summary(date)
    periods = _periods(date)
    same = [p for p in periods if p["questionsVersion"] == current.get("questionsVersion", 0)]
    prior = same[-2] if len(same) >= 2 else None
    # 数据不全的期次不拿来比：这一期或上一期不全，就不和上一期比
    previous_date = prior["date"] if prior and prior["complete"] and current["complete"] else ""
    previous = gc.read_json(gc.run_dir(previous_date) / "summary.json") if previous_date else None
    # 判断涨跌要最近连续三期都完整；中间夹着一期不全的，就不判断
    recent = same[-3:]
    trend = _direction([_share(p["mention"]) for p in recent]) if len(recent) == 3 and all(p["complete"] for p in recent) else "observe"
    questions = {q["id"]: q["text"] for q in (gc.read_json(gc.profile_dir() / "questions.json", {}) or {}).get("items") or []}
    changes = []
    if previous:
        for qid, now in sorted(current["mention"]["byQuestion"].items()):
            before = previous["mention"]["byQuestion"].get(qid)
            if before and _ratio(before) != _ratio(now):
                changes.append({"id": qid, "text": questions.get(qid, ""), "now": _ratio(now), "before": _ratio(before)})
    payload = {
        "ok": True,
        "date": date,
        "previous": previous_date,
        "baselineReset": len(same) < len(periods),
        "mention": {"now": _ratio(current["mention"]), "before": _ratio(previous["mention"]) if previous else ""},
        "ownRefs": {"now": current["refs"]["own"], "before": previous["refs"]["own"] if previous else None},
        "storePages": {"now": current["refs"]["storePages"], "before": previous["refs"]["storePages"] if previous else None},
        "questionChanges": changes,
        # 上一期建议过商家做的事。这一期写建议时先看一眼：做过的不再提，没理会的最多再提一次
        "previousTodos": [t.get("text", "") for t in ((gc.read_json(gc.run_dir(prior["date"]) / "actions.json") or {}).get("todos") or [])] if prior else [],
        "trend": trend,
        "complete": current["complete"],
        # notes 是给员工的提示（周报该怎么写）；readerNotes 是页面上给商家看的说明。两套话不能混用：
        # 写给员工的“周报里不要写成……”如果原样出现在商家的报告里，就成了把内部提示漏给商家。
        "notes": [],
        "readerNotes": [],
    }
    if not prior:
        if payload["baselineReset"]:
            payload["notes"].append("问题改过了，之前的数不能和这一期比；这一期重新作为基线，周报里不和之前的比")
            payload["readerNotes"].append("每周问的问题改过了，之前的数不能和这一期比。这一期重新作为之后对比的基线")
        else:
            payload["notes"].append("这是第一期，没有可比的上一期；这一期就是基线")
            payload["readerNotes"].append("这是第一期，没有可比的上一期。这一期的数是之后对比的基线")
    elif not current["complete"]:
        payload["notes"].append("本期缺失的查询超过四分之一，周报要注明“本周数据不全”，不和上一期比，也不判断涨跌")
        payload["readerNotes"].append("这一期有超过四分之一的提问没有拿到回答，数据不全，不和上一期比")
    elif not prior["complete"]:
        payload["notes"].append("上一期数据不全，这一期不和它比，也不判断涨跌；周报里写“上一期数据不全，没法比较”")
        payload["readerNotes"].append("上一期有不少提问没有拿到回答，数据不全，这一期没法和它比")
    elif trend == "observe" and not all(p["complete"] for p in recent):
        payload["notes"].append("最近三期里有一期数据不全，还判断不了涨跌，周报里不要写成“上升”或“下降”，写“继续观察”")
        payload["readerNotes"].append("最近几期里有一期数据不全，还看不出是在变多还是变少，先继续观察")
    elif trend == "observe":
        payload["notes"].append("提及情况还没有连续两期同方向变化，周报里不要写成“上升”或“下降”，写“继续观察”")
        payload["readerNotes"].append("和上一期比有出入，但还没有连续两期朝同一个方向变。单独一期的涨跌说明不了问题，先继续观察")
    if not prior and not current["complete"]:
        payload["notes"].append("本期缺失的查询超过四分之一，周报要注明“本周数据不全”")
        payload["readerNotes"].append("这一期有超过四分之一的提问没有拿到回答，数据不全")
    return payload


def cmd_compare(args) -> None:
    payload = compare_payload(gc.resolve_date(args.date))
    payload.pop("readerNotes", None)  # 那是页面上给商家看的，员工照 notes 做就行
    gc.emit(payload)


def _clean_block(value) -> str:
    """多行文字：保留换行，去掉行尾空白和连续的空行。"""
    lines = [line.rstrip() for line in str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def _check_actions(raw: dict) -> None:
    """员工写给商家的话超出长度就退回去改，不从中间截断：截掉的半句话会原样出现在商家的页面上。"""
    errors = []

    def over(label, text, limit):
        text = gc.clean_text(text)
        if len(text) > limit:
            errors.append("%s最多 %d 字，现在是 %d 字" % (label, limit, len(text)))

    todos = raw.get("todos") or []
    if len(todos) > 3:
        errors.append("建议最多三件，现在是 %d 件" % len(todos))
    for number, item in enumerate(todos, 1):
        entry = item if isinstance(item, dict) else {"text": item}
        over("第 %d 件建议的“做什么”" % number, entry.get("text"), 120)
        over("第 %d 件建议的“为什么”" % number, entry.get("why"), 120)
    gaps = raw.get("gaps") or []
    if len(gaps) > 5:
        errors.append("缺口最多五条，现在是 %d 条" % len(gaps))
    for number, item in enumerate(gaps, 1):
        if isinstance(item, dict):
            over("第 %d 条缺口的平台" % number, item.get("where"), 20)
            over("第 %d 条缺口的说明" % number, item.get("note"), 160)
    over("本期小结", raw.get("brief"), 240)
    over("没写内容的原因", raw.get("contentNote"), 160)
    if errors:
        raise gc.GeoError("没有保存，请改短后重新提交：" + "；".join(errors))


def normalize_actions(raw: dict) -> dict:
    """整理存档里的小结和建议。长度在 set-actions 时已经卡过，这里的截断只是兜底。"""
    if not isinstance(raw, dict):
        raise gc.GeoError("本周动作应为一个对象")
    todos = []
    for item in (raw.get("todos") or [])[:3]:
        text = gc.clean_text(item.get("text") if isinstance(item, dict) else item)[:120]
        if text:
            entry = item if isinstance(item, dict) else {}
            todos.append({"text": text, "why": gc.clean_text(entry.get("why"))[:120]})
    gaps = []
    for item in (raw.get("gaps") or [])[:5]:
        if isinstance(item, dict) and gc.clean_text(item.get("where")):
            gaps.append({"where": gc.clean_text(item.get("where"))[:20], "note": gc.clean_text(item.get("note"))[:160]})
    return {
        # 员工写给商家的本期小结，显示在工作台最上面和报告的开头。两三句话，只说存档里有的事实。
        "brief": gc.clean_text(raw.get("brief"))[:240],
        # 建议商家做的事，最多三件，列在这一期报告的结论里。只是建议，不是要打勾的清单。
        "todos": todos,
        "gaps": gaps,
        # 这一期没有写内容时的原因。写了就用 add-content 登记，这里留空。
        "contentNote": gc.clean_text(raw.get("contentNote"))[:160],
    }


def cmd_set_actions(args) -> None:
    date = gc.resolve_date(args.date)
    _summary(date)
    raw = gc.load_input(args.file)
    if not isinstance(raw, dict):
        raise gc.GeoError("本周动作应为一个对象")
    if "article" in raw or "content" in raw:
        raise gc.GeoError("写好的内容不放在这里，用 add-content 登记（要写明类型并带上稿子）；这一期没写，把原因写在 contentNote")
    _check_actions(raw)
    previous = gc.read_json(gc.run_dir(date) / "actions.json") or {}
    # 只传要改的部分：没传的 brief、todos、gaps、contentNote 保持这一期原来的内容。
    actions = normalize_actions({key: raw[key] if key in raw else previous.get(key) for key in ACTION_KEYS})
    # 小结和建议是按哪一份算分结果写的。之后重新算分数变了，status 和 publish 会提醒重写；只改 gaps、contentNote 不算重写
    rewritten = "brief" in raw or "todos" in raw
    based_on = gc.summary_fingerprint(_summary(date)) if rewritten or not previous else previous.get("basedOn")
    if based_on:
        actions["basedOn"] = based_on
    gc.write_json(gc.run_dir(date) / "actions.json", actions)
    gc.mark_changed("本期小结和建议")
    warnings = []
    if not actions["brief"]:
        warnings.append("没有写本期小结（brief），工作台最上面会用一句自动生成的话代替")
    gc.emit({"ok": True, "date": date, "todos": len(actions["todos"]), "brief": bool(actions["brief"]),
             "warnings": warnings, "next": "请执行 publish，生成这一期的报告并同步工作台"})


def cmd_show(_args) -> None:
    """最新一期写了什么（小结、建议、缺的内容）、最近的内容，以及页面是不是最新的。商家说“第 2 篇”时先看这里。
    更早的内容和稿子全文不在这里，直接读 contentsFile（内容账本）。"""
    dates = _scored_dates()
    actions = normalize_actions((gc.read_json(gc.run_dir(dates[-1]) / "actions.json") if dates else None) or {})
    contents = _load_contents()
    ledger = contents["items"]
    items = sorted(ledger, key=lambda a: -a["no"])
    live = [a for a in ledger if a["status"] != "dropped"]
    state = gc.workbench_state()
    summary = _summary(dates[-1]) if dates else {}
    payload = {"ok": True, "date": dates[-1] if dates else "", "brief": actions["brief"],
               "todos": actions["todos"], "gaps": actions["gaps"], "contentNote": actions["contentNote"],
               # 商家问“写什么、往哪发”“AI 读哪里”时用这两样回答：和报告“读哪里的内容”一节是同一份数，分平台。
               # 写法和 geo_score.py score 的 sourcesByProvider 一样。
               "sourcesByProvider": {gc.PROVIDER_NAMES.get(p, p): ["%s %d%%" % (x["type"], x["pct"]) for x in v[:4]]
                                     for p, v in ((summary.get("sources") or {}).get("byProvider") or {}).items()},
               "refs": {k: (summary.get("refs") or {}).get(k, 0) for k in ("total", "own", "storePages", "aboutStore")},
               "contents": [_content_view(item) for item in items[:5]],
               # 内容账本：每一篇的全文、状态、放到了哪都在这个文件里，要看哪一篇直接读
               "contentsFile": str(_contents_path()),
               # 下一篇会拿到的序号。让别的技能生成文件时用它起文件名，免得把上一篇的文件和预览盖掉
               "nextNo": _next_no(contents),
               # 官网到了哪一步、有没有跟上店铺资料（outdated、changed）
               "site": gc.site_state(),
               # 商家问“你都做了哪些事”时用这几个数回答
               "totals": {"periods": len(dates), "contents": len(live),
                          "contentsWaiting": sum(1 for a in live if a["status"] == "preview"),
                          "contentsPublished": sum(1 for a in live if a["status"] == "published")},
               "workbench": state, "links": links(state["url"], _linkable(dates)),
               "reportUrl": report_link(state["url"], _linkable(dates)),
               "reportSections": report_sections(state["url"], _linkable(dates))}
    hint = gc.sync_hint(state)
    if hint:
        payload["next"] = hint
    gc.emit(payload)


def _read_body(raw: dict) -> str:
    """稿子的文字：直接给 body，或者给一个文字稿文件的路径（bodyFile）。长的用文件，省得在 JSON 里转义。"""
    path = str(raw.get("bodyFile") or "").strip()
    if not path:
        return _clean_block(raw.get("body"))
    try:
        return _clean_block(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise gc.GeoError("读不到稿子文件：" + os.path.basename(path)) from exc


def _clean_tags(value, limit: int) -> list:
    """话题标签：去掉开头的 #，去重，最多 limit 个。这种类型不用标签时返回空。"""
    tags = []
    for item in value if isinstance(value, list) else []:
        tag = gc.clean_text(item).lstrip("#＃").replace(" ", "")[:20]
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:limit]


def _type_list() -> str:
    return "、".join("%s（%s）" % (key, spec["name"]) for key, spec in CONTENT_TYPES.items())


def cmd_add_content(args) -> None:
    """登记一条内容。登记了，工作台“内容”页才有它；不登记，它就只存在于对话里。"""
    raw = gc.load_input(args.file)
    if not isinstance(raw, dict):
        raise gc.GeoError("内容应为一个对象")
    if not gc.read_json(gc.profile_dir() / "facts.json"):
        raise gc.GeoError("还没有建档，请先按 geo-profile 建档")
    if not gc.confirm_state()["canWrite"]:
        # 店铺后台读来的资料可以直接用。只有资料不是从后台读的（比如从公开信息整理的），才要商家先看过。
        raise gc.GeoError("这家店的资料不是从店铺后台读的，还没有经过商家确认，现在不能替商家写内容。请先请商家看一眼“监测设置”，他回复“确认”即可")
    ledger = _load_contents()
    items = ledger["items"]
    number = int(raw.get("no") or 0)
    current = next((a for a in items if a["no"] == number), None) if number else None
    if number and not current:
        raise gc.GeoError("没有第 %d 篇。现在有哪些看 show 输出里的 contentsFile（内容账本）" % number)
    kind = current["type"] if current else str(raw.get("type") or "")
    if kind not in CONTENT_TYPES:
        raise gc.GeoError("要写明内容类型 type：" + _type_list())
    if current and raw.get("type") and raw["type"] != kind:
        raise gc.GeoError("第 %d 篇是%s，不能改成别的类型。不同类型的稿子不一样，请另外登记一条" % (number, CONTENT_TYPES[kind]["name"]))
    spec, name = CONTENT_TYPES[kind], CONTENT_TYPES[kind]["name"]
    old = current or {}
    title = gc.clean_text(raw.get("title")) if "title" in raw else old.get("title", "")
    body = _read_body(raw) if ("body" in raw or raw.get("bodyFile")) else old.get("body", "")
    preview = str(raw.get("previewUrl") or "").strip() if "previewUrl" in raw else old.get("previewUrl", "")
    tags = _clean_tags(raw.get("tags"), spec["tagsMax"]) if "tags" in raw else old.get("tags", [])
    # 稿子要符合这种类型的规格。超了就退回去改，不替它悄悄截断。
    if not title:
        raise gc.GeoError("%s要有标题" % name)
    if len(title) > spec["titleMax"]:
        raise gc.GeoError("%s的标题最多 %d 个字，现在是 %d 个" % (name, spec["titleMax"], len(title)))
    if not body and spec["bodyMin"]:
        raise gc.GeoError("登记%s必须带上稿子正文：放在 body 里，或者存成文件后用 bodyFile 给出路径" % name)
    if len(body) < spec["bodyMin"]:
        raise gc.GeoError("%s的正文太短：至少 %d 字，现在是 %d 字。这不像一篇写完的稿子" % (name, spec["bodyMin"], len(body)))
    if len(body) > spec["bodyMax"]:
        raise gc.GeoError("%s的正文最多 %d 字，现在是 %d 字" % (name, spec["bodyMax"], len(body)))
    if preview:
        parsed = urlparse(preview)
        if parsed.scheme != "https" or not parsed.netloc:
            raise gc.GeoError("预览链接必须是 https 开头的完整地址，请原样复制生成它的技能返回的链接")
        clash = next((a for a in items if a is not current and a["status"] != "dropped" and a.get("previewUrl") == preview), None)
        if clash:
            raise gc.GeoError("这个预览链接和第 %d 篇《%s》是同一个，说明新的预览把上一篇的盖掉了。请让生成预览的技能给这一篇换一个文件名，重新生成预览"
                              % (clash["no"], clash["title"]))
    elif spec["preview"]:
        raise gc.GeoError("%s要带排版预览链接 previewUrl（由公众号技能生成）。手里只有文字稿的话，按“长文”类型登记" % name)
    extra = {key: gc.clean_text(raw.get(key))[:limit] for key, limit in
             (("summary", 300), ("reason", 160), ("whereToPost", 80), ("tip", 160)) if key in raw}
    if "forQuestion" in raw:
        extra["forQuestion"] = gc.clean_text(raw.get("forQuestion"))[:6].lower()
    reset = False
    if current:
        changed = (title, body, preview, tags) != (current["title"], current["body"], current.get("previewUrl", ""), current.get("tags", []))
        current.update(extra, title=title, body=body, previewUrl=preview, tags=tags, updatedAt=gc.now_iso())
        if changed and current["status"] == "confirmed":
            # 商家确认的是上一版。改过以后要重新确认，才能发或者存草稿。
            current["status"], reset = "preview", True
    else:
        same = next((a for a in items if a["type"] == kind and a["title"] == title and a["status"] != "dropped"), None)
        if same:
            raise gc.GeoError("已经登记过%s《%s》（第 %d 篇）。这次是改稿就带上 \"no\": %d；确实是另一篇，请换一个标题" % (name, title, same["no"], same["no"]))
        origin = raw.get("origin") if raw.get("origin") in CONTENT_ORIGINS else "weekly"
        dates = _scored_dates()
        period = dates[-1] if dates else ""
        if origin == "weekly":
            written = sum(1 for a in items if a.get("origin") == "weekly" and a.get("period") == period and a["status"] != "dropped")
            if written >= WEEKLY_CONTENT_CAP:
                raise gc.GeoError("这一期已经主动写了 %d 篇，每期最多 %d 篇。商家点名要的内容，把 origin 写成 asked" % (written, WEEKLY_CONTENT_CAP))
        number = _next_no(ledger)
        current = dict({"summary": "", "reason": "", "whereToPost": "", "tip": "", "forQuestion": ""}, **extra)
        current.update(no=number, type=kind, title=title, body=body, previewUrl=preview, tags=tags, status="preview",
                       origin=origin, period=period, channels=[], ref="", createdAt=gc.now_iso(), updatedAt=gc.now_iso())
        items.append(current)
        ledger["nextNo"] = number + 1  # 序号给出后不变、不重复使用：商家说“第 2 篇可以发”时靠它对上
    _save_contents(ledger)
    gc.mark_changed("内容")
    payload = dict(_content_view(current), ok=True,
                   next="请执行 publish 同步工作台。告诉商家时给标题、两三句摘要和 links 里“内容”页的链接；稿子在工作台上，不要在对话里再贴一遍")
    if reset:
        payload["note"] = "这一篇之前商家确认过，改稿以后已经变回“等商家确认”，要请他再看一眼"
    gc.emit(payload)


def _next_no(ledger: dict) -> int:
    return max([int(ledger.get("nextNo") or 0)] + [a["no"] + 1 for a in ledger["items"]] + [1])


def cmd_mark_content(args) -> None:
    """改一条内容的状态，或者记下它放到了哪。不带 --no 时指最新的一条。"""
    ledger = _load_contents()
    items = ledger["items"]
    if args.no:
        item = next((a for a in items if a["no"] == args.no), None)
    else:
        live = [a for a in items if a["status"] != "dropped"]
        item = live[-1] if live else None
    if not item:
        raise gc.GeoError(("没有第 %d 篇" % args.no) if args.no else "还没有登记过内容。写好的内容先用 add-content 登记")
    channel = gc.clean_text(args.channel)[:16]
    ref = gc.clean_text(args.ref)[:120]
    if not args.status and not channel and not ref:
        raise gc.GeoError("要么改状态（--status），要么记下放到了哪（--channel）")
    status = args.status or item["status"]
    if (channel or ref) and status not in ("confirmed", "published"):
        # 存进草稿箱、发出去之前，必须得到商家对这一篇的明确确认。
        raise gc.GeoError("第 %d 篇还没有经过商家确认。商家确认后先 --status confirmed，再记它放到了哪" % item["no"])
    item["status"] = status
    if channel and channel not in item.setdefault("channels", []):
        item["channels"] = (item["channels"] + [channel])[:6]
    if ref:
        item["ref"] = ref  # 放进去以后对方给的编号（比如公众号草稿的编号）。以后改稿时原样交还给那个技能
    item["updatedAt"] = gc.now_iso()
    _save_contents(ledger)
    gc.mark_changed("内容")
    gc.emit(dict(_content_view(item), ok=True, next=gc.sync_hint()))


# ── 官网 ──
# 官网由“应用”能力（youzan-application）做：先出测试版给商家看，他确认了才正式上线。
# 这里只做两件事：把能放上官网的店铺资料一次给全（site-brief），登记官网在哪、到了哪一步（set-site）。
SITE_PAGE_NAME = re.compile(r"^[a-z][a-z0-9-]{5,40}$")


def _https(value: str, label: str) -> str:
    url = gc.clean_text(value)
    if not re.match(r"^https://[^\s]+$", url) or len(url) > 400:
        raise gc.GeoError("%s要是 https 开头的完整链接，照“应用”能力输出里的原样复制" % label)
    return url


def _site_title(facts: dict) -> str:
    """页面标题的建议：本地门店是“店名 · 城市 + 品类店”，电商是“店名 · 品类”。"""
    brand = facts.get("brand") or {}
    name, city, category = brand.get("name", ""), brand.get("city", ""), brand.get("category", "")
    if not category:
        return name
    if facts.get("segment") == "local":
        tail = category if category.endswith(("店", "馆", "铺", "坊", "厅", "房", "社")) else category + "店"
        return "%s · %s%s" % (name, city, tail)
    return "%s · %s" % (name, category)


def _shop_cited(facts: dict) -> dict:
    """最近一期里，AI 引用了几次商城自己的页面。"""
    hosts = gc.own_hosts(facts)
    dates = _scored_dates()
    if not hosts or not dates:
        return {}
    folder = gc.run_dir(dates[-1])
    count = 0
    for key in (gc.read_json(folder / "queries.json", {}) or {}).get("items") or {}:
        raw = gc.read_json(folder / "raw" / (key + ".json")) or {}
        for answer in (raw.get("result") or {}).get("answers") or []:
            for ref in (answer.get("references") or {}).get("list") or []:
                if any(gc.host_is(urlparse(str(ref.get("url") or "")).netloc, h) for h in hosts):
                    count += 1
    return {"date": dates[-1], "count": count}


def cmd_site_brief(_args) -> None:
    """做官网要用的店铺资料，没确认的信息已经去掉了。商品图、详情、评价这些，员工从商品技能里查。"""
    facts = _facts()
    root = gc.profile_dir()
    meta = gc.read_json(root / "meta.json", {}) or {}
    state = gc.confirm_state(facts, meta)
    usable = gc.site_facts(facts, meta)
    questions = (gc.read_json(root / "questions.json", {}) or {}).get("items") or []
    stores = usable["stores"]
    payload = {
        "ok": True,
        "canWrite": state["canWrite"],
        "segment": facts.get("segment", ""),
        "segmentName": gc.SEGMENT_NAMES.get(facts.get("segment", ""), ""),
        "brand": usable["brand"],
        # 别的叫法：商家确认过才放（顾客可能用这个名字搜）
        "aliases": [] if state["pending"] else ((facts.get("brand") or {}).get("aliases") or []),
        "edges": facts.get("edges") or [],
        "stores": [s for s in stores if s.get("status") == "在营"],
        # 搬走或关掉的门店：只在 AI 还常说旧地址时，写一句“原 XX 店已搬到……”
        "oldStores": [s for s in stores if s.get("status") != "在营"],
        "products": usable["products"],
        "buyEntry": usable["buyEntry"],
        # 顾客常问：带店名的直接答；不带店名的，改成这家店能用事实回答的问法
        "faq": [{k: q.get(k, "") for k in ("id", "kind", "text", "tag", "audience", "worry")} for q in questions],
        # AI 说错过的事：官网上把对的说法写清楚
        "issues": [{k: i.get(k, "") for k in ("no", "fact", "aiSays", "truth")} for i in _issues() if i.get("status") == "open"],
        "writingRules": facts.get("writingRules") or {},
        "pageTitle": _site_title(facts),
        "today": gc.today(),
        # 最近一期 AI 引用了几次商城自己的页面；还没体检过时为空
        "shopCited": _shop_cited(facts),
        "site": gc.site_state(facts, meta),
    }
    if not state["canWrite"]:
        payload["next"] = "店铺资料还没经过商家确认，现在不能做官网。先请他看一眼工作台的“监测设置”，确认了再做"
    elif payload["site"].get("exists") and payload["site"]["status"] != "dropped":
        payload["next"] = "已经有官网了：改的是同一个应用，不要新建。出了新的测试版用 set-site --status test 登记"
    gc.emit(payload)


def cmd_set_site(args) -> None:
    """登记官网到了哪一步。官网本身由“应用”能力做，这里只记它在哪、做的时候用的是哪一版店铺资料。"""
    facts = _facts()
    path = gc.site_path()
    site = gc.read_json(path, {}) or {}
    now = gc.now_iso()
    if not (args.status or args.domain is not None or args.page_name):
        raise gc.GeoError("要登记什么？测试版好了用 --status test --test-url，正式上线用 --status published --url，绑了域名用 --domain")
    if args.status in ("test", "published") and not gc.confirm_state(facts)["canWrite"]:
        raise gc.GeoError("店铺资料还没经过商家确认，不能把它放上官网。先请商家确认店铺信息（按 geo-profile）")
    if args.status == "test":
        if site.get("status") == "dropped":
            # 不要了以后重做，是一个新的官网：旧的正式链接、域名、页面标识都不算数了
            site = {"createdAt": now}
        site.update(status="test", testUrl=_https(args.test_url, "测试版链接"), testAt=now, testBasis=gc.site_facts(facts))
    elif args.status == "published":
        if site.get("status") != "test" or not site.get("testBasis"):
            # 官网要先出这一版的测试版给商家看，他确认以后才能正式上线
            raise gc.GeoError("现在没有等商家确认的测试版。先出测试版、用 --status test 登记、等商家确认，再正式发布")
        site.update(status="published", url=_https(args.url, "官网的正式链接"), publishedAt=now, basis=site["testBasis"])
    elif args.status == "dropped":
        if not site.get("status"):
            raise gc.GeoError("还没有登记过官网")
        site.update(status="dropped", droppedAt=now)
    if args.page_name:
        name = gc.clean_text(args.page_name)
        if not SITE_PAGE_NAME.match(name):
            raise gc.GeoError("页面标识照“应用”能力里的原样填：小写英文开头，只有小写英文、数字和短横线，至少 6 个字符")
        site["pageName"] = name
    if args.domain is not None:
        if not site.get("status"):
            raise gc.GeoError("还没有登记过官网")
        domain = re.sub(r"^[a-z]+://", "", gc.clean_text(args.domain).lower()).split("/")[0]
        if domain and not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", domain):
            raise gc.GeoError("域名的格式不对，例如 www.example.com；不要了就传空的 --domain \"\"")
        site["domain"] = domain
    if not site.get("status"):
        raise gc.GeoError("还没有登记过官网。测试版好了先用 --status test --test-url 登记")
    site.setdefault("createdAt", now)
    site["updatedAt"] = now
    gc.write_json(path, site)
    gc.mark_changed("官网")
    state = gc.site_state(facts)
    steps = {
        "test": "执行 publish 同步工作台，再按“应用”能力的格式把测试版链接原样发给商家，停下来等他确认发布",
        "published": "执行 publish 同步工作台，再把官网链接发给商家，并建议他把链接放到自己能填网址的地方（比如地图上的门店页、抖音主页、公众号菜单）",
        "dropped": "执行 publish 同步工作台",
    }
    next_step = steps.get(args.status) or gc.sync_hint()
    if args.status == "published" and state.get("outdated"):
        next_step = ("这一版测试版做好以后，店铺资料里的%s又改了，刚上线的官网已经跟不上。" % "、".join(state["changed"])
                     + "执行 publish 同步工作台，把链接发给商家时说明这一点，问他要不要更新")
    gc.emit({"ok": True, "site": state, "next": next_step})


def _answers(date: str, summary: dict) -> dict:
    """最新一期每个回答的原文和引用，供工作台里点开查看。"""
    state = gc.read_json(gc.run_dir(date) / "queries.json", {}) or {}
    out = {}
    for key in sorted(state.get("items") or {}):
        raw = gc.read_json(gc.run_dir(date) / "raw" / (key + ".json")) or {}
        rows = []
        for index, answer in enumerate(((raw.get("result") or {}).get("answers")) or []):
            flags = summary["answers"].get(key) or []
            flag = flags[index] if index < len(flags) else {}
            info = flag.get("refInfo") or []
            refs = []
            for position, ref in enumerate(((answer.get("references") or {}).get("list")) or []):
                kind, relation = info[position] if position < len(info) else ("", "")
                refs.append({"t": gc.clean_title(ref.get("title"))[:70], "s": gc.clean_text(ref.get("source"))[:20],
                             "u": str(ref.get("url") or "")[:300], "k": kind, "r": relation})
            rows.append({"text": gc.clean_answer(answer), "mentioned": bool(flag.get("mentioned")), "refs": refs})
        out[key] = rows
    return out


def _store(facts: dict) -> dict:
    return {"name": (facts.get("brand") or {}).get("name", ""), "segment": facts.get("segment", ""),
            "segmentName": gc.SEGMENT_NAMES.get(facts.get("segment", ""), ""),
            "demo": bool(os.environ.get("GEO_DEMO"))}  # 只在跑多期回归时设置，页面顶部会标“演示数据”


def _settings(facts: dict, meta: dict, questions: list, rivals: list) -> dict:
    """监测设置页：每周替商家问什么、和谁比，以及员工另外记下的几样信息。

    店铺后台里有的资料（门店、营业时间、商品）不在这里列：那是商家自己维护的，这里抄一份只会抄不全。
    """
    state = gc.confirm_state(facts, meta)
    brand, channels, rules = facts.get("brand") or {}, facts.get("channels") or {}, facts.get("writingRules") or {}
    return {
        "from": state["from"], "confirmed": state["confirmed"], "pending": state["pending"], "canWrite": state["canWrite"],
        "questions": questions,
        "edges": facts.get("edges") or [],
        "rivals": [{"name": r["name"]} for r in rivals],
        "extras": {
            "aliases": brand.get("aliases") or [],
            "wechatOfficial": channels.get("wechatOfficial", ""),
            "douyin": channels.get("douyin", ""),
            # 后台里没有的门店：员工从别处看到的，或者商家说已经关掉的旧店
            "stores": [{k: s.get(k, "") for k in ("name", "address", "status", "source")}
                       for s in facts.get("stores") or [] if "有赞后台" not in str(s.get("source") or "")],
            "tone": rules.get("tone", ""),
            "bannedWords": rules.get("bannedWords") or [],
            "mustInclude": rules.get("mustInclude") or [],
        },
    }


def _contents_for_page() -> list:
    """内容：新的在前，每一篇都带全文（一篇约 2KB，几百篇也只有几百 KB）。不发了的不带稿子。"""
    return [dict(_content_view(item), body=item.get("body", "") if item["status"] != "dropped" else "")
            for item in sorted(_load_contents()["items"], key=lambda a: -a["no"])]


def _facts() -> dict:
    facts = gc.read_json(gc.profile_dir() / "facts.json")
    if not facts:
        raise gc.GeoError("还没有建档，请先按 geo-profile 建档")
    return facts


def workbench_data(date: str = "") -> dict:
    """工作台用到的数据。还没体检过也能生成：这时只有监测设置和“体检进行中”。"""
    root = gc.profile_dir()
    facts = _facts()
    meta = gc.read_json(root / "meta.json", {}) or {}
    scored = _scored_dates(date)
    current = scored[-1] if scored else ""
    questions = (gc.read_json(root / "questions.json", {}) or {}).get("items") or []
    rivals = (gc.read_json(root / "rivals.json", {}) or {}).get("items") or []
    actions = normalize_actions((gc.read_json(gc.run_dir(current) / "actions.json") if current else None) or {})
    periods = _periods(current) if current else []
    latest = None
    compare = {"previous": "", "mention": {}, "ownRefs": {}, "trend": "observe", "baselineReset": False}
    if current:
        summary = _summary(current)
        latest = dict(periods[-1], buyEntry=summary["buyEntry"],
                      rivals=[{"name": r["name"], "count": r["count"]} for r in summary.get("rivals") or []],
                      shops=[{"name": s["name"], "count": s["count"], "rival": s["rival"]} for s in (summary.get("shops") or [])[:3]])
        full = compare_payload(current)
        compare = {k: full[k] for k in compare}
    contents = _contents_for_page()
    live = [c for c in contents if c["status"] != "dropped"]
    return {
        "kind": "workbench",
        "generatedAt": gc.now_iso(),
        "runDate": current,
        "store": _store(facts),
        "nav": list(WORKBENCH_PAGES),
        "providers": [{"id": p, "name": gc.PROVIDER_NAMES[p]} for p in gc.PROVIDERS],
        "progress": _progress(),
        "latest": latest,
        "actions": actions,
        "periods": periods,
        "contents": contents,
        "contentTypes": {key: spec["name"] for key, spec in CONTENT_TYPES.items()},
        # 官网：没做过时只有 exists: false。“内容”页按它显示官网那一块
        "site": gc.site_state(facts, meta),
        "questions": questions,
        "settings": _settings(facts, meta, questions, rivals),
        "totals": {
            "periods": len(scored),
            "contents": len(live),
            "contentsWaiting": sum(1 for c in live if c["status"] == "preview"),
            "contentsPublished": sum(1 for c in live if c["status"] == "published"),
        },
        "compare": compare,
    }


def report_data(day: str) -> dict:
    """一期体检的报告：这一期的全部证据。生成以后就是这一期的记录，之后的变化在工作台上看。"""
    root = gc.profile_dir()
    facts = _facts()
    meta = gc.read_json(root / "meta.json", {}) or {}
    summary = _summary(day)
    folder = gc.run_dir(day)
    state = gc.read_json(folder / "queries.json", {}) or {}
    judgement = gc.read_json(folder / "judgement.json", {}) or {}
    actions = normalize_actions(gc.read_json(folder / "actions.json") or {})
    scored = _scored_dates()
    # 问题：以这一期实际问的为准；“替谁问、他在意什么”这类标注从现在的问题库里按原文对上
    profile = {(q["id"], q["text"]): q for q in (gc.read_json(root / "questions.json", {}) or {}).get("items") or []}
    questions = {}
    for item in (state.get("items") or {}).values():
        meta_q = profile.get((item["qid"], item["question"]), {})
        questions[item["qid"]] = {"id": item["qid"], "kind": item["kind"], "text": item["question"],
                                  "tag": meta_q.get("tag", ""), "audience": meta_q.get("audience", ""), "worry": meta_q.get("worry", "")}
    dots = {}
    for key, flags in (summary.get("answers") or {}).items():
        qid, _, provider = key.rpartition("_")
        # 每个回答一个字符：h 提到了本店，n 没提到
        dots.setdefault(qid, {})[provider] = "".join("h" if flag.get("mentioned") else "n" for flag in flags)
    seen = set(judgement.get("issueIds") or [])
    compare = compare_payload(day)
    notes = list(compare["readerNotes"])
    if summary.get("notUs"):
        notes.append("有 %d 个回答里出现的同名说的不是你（比如同名的别的店），没有算作提到你" % len(summary["notUs"]))
    confirm = gc.confirm_state(facts, meta)
    if confirm["from"] != "backend" and not confirm["confirmed"]:
        notes.append("这家店的资料是员工从公开信息里整理的，还没有经过你确认；AI 的说法和它对不上，不一定是 AI 说错")
    return {
        "kind": "report",
        "generatedAt": gc.now_iso(),
        "store": _store(facts),
        "providers": [{"id": p, "name": gc.PROVIDER_NAMES[p]} for p in gc.PROVIDERS],
        "aliases": gc.brand_aliases(facts),
        "period": {"date": day, "no": scored.index(day) + 1 if day in scored else 0, "latest": bool(scored) and day == scored[-1]},
        "workbenchUrl": meta.get("pageUrl", ""),
        "workbenchFile": gc.PAGE_FILE,
        "summary": {"mention": summary["mention"], "refs": {k: summary["refs"][k] for k in ("total", "own", "storePages", "aboutStore")},
                    "buyEntry": summary["buyEntry"], "expected": summary["expected"], "returned": summary["returned"],
                    "complete": summary["complete"], "judged": bool(judgement)},
        "compare": {k: compare[k] for k in ("previous", "mention", "ownRefs", "trend", "baselineReset")},
        "actions": actions,
        "questions": sorted(questions.values(), key=lambda q: (q["kind"] != "open", q["id"])),
        "dots": dots,
        "answers": _answers(day, summary),
        "rivals": summary.get("rivals") or [],
        "shops": summary.get("shops") or [],
        # 还没读过的回答数：不为 0 时“提到了谁”不出数
        "shopsPending": len(summary.get("shopsPending") or []),
        # 员工读全文后写的发现，最多 5 条，每条带 AI 的原话
        "findings": summary.get("findings") or [],
        "sources": (summary.get("sources") or {}).get("byProvider") or {},
        "related": {"own": summary["refs"]["ownItems"], "store": summary["refs"]["storePageItems"], "about": summary["refs"]["aboutItems"]},
        "descriptions": judgement.get("descriptions") or {},
        # 这一期 AI 的说法里，和店铺资料对不上的。没有就是空的，报告里不单独占一块。
        "issues": [i for i in _issues() if i["id"] in seen],
        "contents": [_content_view(c) for c in _load_contents()["items"] if c.get("period") == day and c["status"] != "dropped"],
        "factsFrom": confirm["from"],
        "factsConfirmed": confirm["confirmed"],
        "notes": notes,
    }


def embed_json(data: dict) -> str:
    """放进 <script type="application/json"> 里的数据：不能出现能提前结束标签的字符。"""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for raw, safe in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        text = text.replace(raw, safe)
    return text


def _template_text() -> str:
    try:
        template = TEMPLATE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise gc.GeoError("工作台模板读取失败") from exc
    if template.count(PLACEHOLDER) != 1:
        raise gc.GeoError("工作台模板不完整")
    return template


def render_html(data: dict) -> str:
    return _template_text().replace(PLACEHOLDER, embed_json(data))


def report_link(url: str, day: str) -> str:
    """在工作台里打开某一期报告的地址：商家点开看到的是工作台的框架，右边是这一期的报告。"""
    return "%s#/report/%s" % (url, day) if url and day else ""


def report_sections(url: str, day: str) -> dict:
    """在工作台里直接打开这一期报告某一节的地址，按小节的 id：summary、mentions、rivals、sources、says。照抄，不用自己拼。"""
    base = report_link(url, day)
    return {section: base + "/" + section for _, section in REPORT_SECTIONS} if base else {}


def links(url: str, report_day: str = "") -> dict:
    """员工跟商家说到某件事时给的链接：工作台上能打开的每一个页面，加“在工作台里打开这一期的报告”。"""
    out = {page["title"]: url + "#/" + page["id"] for page in WORKBENCH_PAGES} if url else {}
    if url and report_day:
        out["这一期的报告"] = report_link(url, report_day)
    return out


def _latest_report_url() -> str:
    """最新一期报告文件自己的云盘链接。没传上去时是空的。"""
    scored = _scored_dates()
    return _report_urls().get(scored[-1], "") if scored else ""


def _linkable(dates: list = None) -> str:
    """最新一期的日期。它的报告文件已经传上云盘才算数：没传上去的话，工作台里也打不开它。"""
    dates = _scored_dates() if dates is None else dates
    return dates[-1] if dates and _report_urls().get(dates[-1]) else ""


DATA_BLOCK = re.compile(r'(<script type="application/json" id="geo-data">)(.*?)(</script>)', re.S)
GENERATED_FILE = ".generated.json"  # 脚本写出每个网页时，标准模板的指纹


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# 61d9a0e 之前，脚本写出页面时没有记下用的是哪一版模板（记的是整页的指纹，员工改过的页面也这样记）。
# 这些是那以前各版标准模板去掉数据后的指纹，用来认出没改过的老页面，让它们跟着升级。
LEGACY_TEMPLATE_SHELLS = frozenset((
    "0b88a4f9cbb1875f", "1a48b92e455e5c1e", "320d617b990b235b", "37c8e6ff027b434b", "3cf30fd2a457a834", "427518f295f93fb2",
    "4f1fe5bc2f79ccde", "51f73989622b0521", "6af1e88e28daa7d0", "749592bce72e61c5", "7bd75ff2700a5387", "83c117198b6e42f3",
    "92f0ef3f07c1cdbf", "954edffe41de12d4", "97e27a7407a16089", "9bc6143e4d0479cc", "a129bd588db197d5", "a475b3deff415652",
    "b55ad0883fad3e7e", "d1ade229e5992805", "d34a1ad631f7dd9e", "dc5f1c8c1c7abb4d", "f47a12e0d87d2141",
))


def _shell(text: str) -> str:
    """网页去掉数据之后剩下的样子。"""
    return DATA_BLOCK.sub(lambda m: m.group(1) + m.group(3), text)


def _edited(name: str, current: str, record: dict) -> bool:
    """员工改过这个页面没有：去掉数据以后的样子，不是任何一版标准模板（包括写出它的那一版），就是改过。
    只看样子不看数据，所以改过的页面同步多少次都认得出来；没改过的页面跟着标准模板升级。
    认不出来的一律当成改过：只换数据，员工的改动不会被冲掉，最多是这一页暂时用不上新样式。"""
    known = LEGACY_TEMPLATE_SHELLS | {_fingerprint(_shell(_template_text().replace(PLACEHOLDER, "")))}
    if record.get(name):
        known = known | {record[name]}
    return _fingerprint(_shell(current)) not in known


def _merge_data(old_block: str, data: dict) -> dict:
    """换进员工改过的页面的数据：脚本算的以新的为准；员工自己往数据里加的（脚本不写的字段、导航里多出来的页面）保留。"""
    try:
        old = json.loads(old_block)
    except json.JSONDecodeError:
        return data
    if not isinstance(old, dict):
        return data
    merged = dict({k: v for k, v in old.items() if k not in data}, **data)
    ids = {p.get("id") for p in data.get("nav") or []}
    extra = [p for p in old.get("nav") or [] if isinstance(p, dict) and p.get("id") not in ids]
    if "nav" in data and extra:
        merged["nav"] = list(data["nav"]) + extra
    return merged


def _write_page(name: str, data: dict) -> Path:
    """写一个网页。员工改过的页面（和脚本上次写出的不一样）只换数据块，员工加的、改的都保留；
    没改过的按标准模板整页重写，标准模板升级了也能跟上。"""
    target = gc.pages_dir() / name
    target.parent.mkdir(parents=True, exist_ok=True)
    record_path = gc.pages_dir() / GENERATED_FILE
    record = gc.read_json(record_path, {}) or {}
    try:
        current = target.read_text(encoding="utf-8") if target.is_file() else ""
    except (OSError, UnicodeDecodeError) as exc:
        raise gc.GeoError("读不出页面文件 %s，没有同步" % name) from exc
    if current and _edited(name, current, record):
        blocks = DATA_BLOCK.findall(current)
        if len(blocks) != 1:
            raise gc.GeoError("页面 %s 被改过，但找不到放数据的地方（要有且只有一处 <script type=\"application/json\" id=\"geo-data\">…</script>），"
                              "没有同步，也没有覆盖。把这一处加回去再同步；要恢复标准样子，删掉这个文件再同步" % name)
        merged = _merge_data(blocks[0][1], data)
        text = DATA_BLOCK.sub(lambda m: m.group(1) + embed_json(merged) + m.group(3), current)
    else:
        text = render_html(data)
        record[name] = _fingerprint(_shell(text))  # 只在按标准模板写出时记，员工改过的页面不记
        gc.write_json(record_path, record)
    target.write_text(text, encoding="utf-8")
    return target


def _build_reports(current: str) -> list:
    """生成报告文件，返回 [(日期, 文件)]。

    这一期的报告每次都重新生成，小结、待办、核对结果改了要跟上；
    以前各期的是当时的记录，文件还在就不动，丢了才补。
    """
    built = []
    for day in _scored_dates(current) if current else []:
        target = gc.pages_dir() / (REPORT_FILE % day)
        if day == current or not target.is_file():
            built.append((day, _write_page(REPORT_FILE % day, report_data(day))))
    return built


def _build_workbench(date: str) -> dict:
    data = workbench_data(date)
    target = _write_page(gc.PAGE_FILE, data)
    built = {"file": str(target), "sizeKB": round(target.stat().st_size / 1024), "date": data["runDate"],
             "periods": len(data["periods"]), "progress": data["progress"]}
    wrapped_up = bool(data["runDate"]) and (gc.run_dir(data["runDate"]) / "actions.json").is_file()
    written = any(a["period"] == data["runDate"] and a["status"] != "dropped" for a in data["contents"])
    warnings = []
    if wrapped_up and data["settings"]["canWrite"] and not written and not data["actions"]["contentNote"]:
        # 最常见的漏法：内容在对话里写了，但没登记，工作台上就没有它。
        warnings.append("这一期既没有登记内容，也没有写没写的原因。内容如果已经写了，请先 add-content 登记（带上稿子）；"
                        "确实没写，用 set-actions 把原因写进 contentNote")
    if written and data["actions"]["contentNote"]:
        # 先写了“这一期不写”，后来又写了内容：报告上两句话会打架
        warnings.append("这一期已经登记了内容，但 contentNote 里还写着没写的原因。请用 set-actions 传 {\"contentNote\": \"\"} 清掉，"
                        "并看一眼本期小结（brief）是不是也要跟着改")
    if warnings:
        built["warnings"] = warnings
    return built


def _current(date: str) -> str:
    scored = _scored_dates(date)
    return scored[-1] if scored else ""


def _save_url(url: str) -> bool:
    path = gc.profile_dir() / "meta.json"
    meta = gc.read_json(path, {}) or {}
    first_time = not meta.get("pageUrl")
    meta.update(pageUrl=url, pageUrlUpdatedAt=gc.now_iso())
    gc.write_json(path, meta)
    return first_time


def _upload(file_path: str) -> dict:
    """用云盘上传技能自带的脚本生成链接。测试时可用 GEO_UPLOAD_CMD 换成模拟命令。"""
    override = os.environ.get("GEO_UPLOAD_CMD", "").strip()
    if override:
        command = shlex.split(override)
    else:
        root = os.environ.get("YOUZAN_GLOBAL_SKILLS_PATH", "").strip()
        script = Path(root) / "youzan-oss" / "scripts" / "upload.js" if root else None
        if not script or not script.is_file():
            return {"ok": False, "error": "当前环境没有找到云盘上传能力"}
        command = ["node", str(script)]
    try:
        proc = subprocess.run(command + ["--file-path", file_path], capture_output=True, text=True, timeout=UPLOAD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "上传超时"}
    except OSError as exc:
        return {"ok": False, "error": "上传脚本无法执行：" + exc.__class__.__name__}
    if proc.returncode != 0:
        return {"ok": False, "error": gc.clean_text(proc.stderr or proc.stdout)[:240] or "上传失败"}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "上传结果无法解析"}
    url = str(payload.get("url") or "").strip()
    if not url.startswith("https://"):
        return {"ok": False, "error": "上传结果里没有可用的链接"}
    return {"ok": True, "url": url, "warning": gc.clean_text(payload.get("warning"))}


def _save_report_urls(urls: dict) -> None:
    path = gc.profile_dir() / "meta.json"
    meta = gc.read_json(path, {}) or {}
    meta["reports"] = urls
    gc.write_json(path, meta)


def cmd_publish(args) -> None:
    date = gc.check_date(args.date) if args.date else ""
    current = _current(date)
    failures, warnings = [], []
    # 先传报告。拿到报告的链接，工作台里才有“看报告”的入口。
    reports = _build_reports(current)
    urls = dict(_report_urls())
    pending = dict(reports)
    for day in _scored_dates(current) if current else []:
        # 以前某一期没传上去的，这次一起补
        if day not in urls and day not in pending and (gc.pages_dir() / (REPORT_FILE % day)).is_file():
            pending[day] = gc.pages_dir() / (REPORT_FILE % day)
    for day in sorted(pending):
        uploaded = _upload(str(pending[day]))
        if uploaded["ok"]:
            urls[day] = uploaded["url"].split("#")[0]
            if uploaded.get("warning"):
                warnings.append(uploaded["warning"])
        else:
            failures.append("%s 这一期的报告：%s" % (day, uploaded["error"]))
    _save_report_urls(urls)
    built = _build_workbench(date)
    gc.mark_built()
    uploaded = _upload(built["file"])
    saved = (gc.read_json(gc.profile_dir() / "meta.json", {}) or {}).get("pageUrl", "")
    first_time = False
    if uploaded["ok"]:
        saved = uploaded["url"].split("#")[0]
        first_time = _save_url(saved)
        if uploaded.get("warning"):
            warnings.append(uploaded["warning"])
    else:
        failures.insert(0, "工作台：" + uploaded["error"])
    shown = current if urls.get(current) else ""  # 这一期的报告文件传上去了，工作台里才打得开
    # reportUrl：在工作台里打开这一期的报告，发给商家用它；reportFileUrl：报告文件自己的链接，商家要单独转发时才用
    payload = dict(built, ok=True, pageUrl=saved, reportUrl=report_link(saved, shown), reportFileUrl=urls.get(current, ""),
                   reportSections=report_sections(saved, shown),
                   links=links(saved, shown), reportFiles=[str(path) for _, path in reports])
    payload.setdefault("warnings", [])
    payload["warnings"] += warnings
    if not payload["warnings"]:
        del payload["warnings"]
    if failures:
        gc.emit(dict(payload, published=False, reason="；".join(failures),
                     next="页面已在本地生成，但没有全部同步成功。先再执行一次 publish；还是不行，改为调用 youzan-oss 技能给 file（工作台）"
                          "或 reportFiles（报告）生成云盘链接，再用 set-page-url 存回来（报告加 --report <日期>）。"
                          "都不行就如实告诉商家页面暂时没更新，不要编链接"))
        return
    synced = gc.mark_published()
    hint = "这是第一次开通工作台，请先按 geo-workbench 的 references/tabs.md 调用 claw-admin-request 固定工作台，再把 pageUrl 发给商家。" if first_time else "工作台和报告已同步。"
    if first_time and (gc.read_json(gc.profile_dir() / "meta.json", {}) or {}).get("firstCheckPending"):
        # 初始化时员工一路调工具，到问“要不要开始”那一步常常只弹卡片、一个字不写（10-20 实测两次）。
        # 写在 geo-profile 里离动作太远，在这里当场提醒一次。
        hint += ("固定页签、建好提醒之后，按 geo-profile 第 3 步请商家确认：在同一次回复里先写文字"
                 "（识别到的店铺、这家店的特点、三个顾客会怎么问 AI 的例子、工作台链接），紧接着再调用交互卡片问要不要开始。"
                 "不要只弹卡片。")
    latest = gc.latest_run_date()
    period = gc.period_stage(latest) if latest else {}
    if period and period["stage"] in ("scoring", "reading", "judging", "wrapup"):
        # 体检做到一半也会同步（让商家看到进度），但这时的报告还不完整，不能当成这一期的结果发出去
        payload["unfinished"] = period
        payload["warnings"] = payload.get("warnings", []) + [
            "最近一期（%s）还没做完，报告上的内容不完整，先别把它当成这一期的结果发给商家。%s" % (period["date"], period["next"])]
        hint += "这一期还没做完：%s。" % period["next"]
    elif period and period["stage"] == "asking" and payload["reportUrl"]:
        # 新一期还在提问：reportUrl 指的还是之前算过分的那一期，不能当成这一期的结果发出去
        payload["unfinished"] = period
        older = "上一期（%s）" % current if current != period["date"] else "重问之前"
        hint += "体检进行中，现在的报告还是%s的，不是这一期的结果，先别发给商家。%s。" % (older, period["next"])
    elif payload["reportUrl"]:
        hint += "这一期的结果给 reportUrl（在工作台里打开这一期的报告），说到某一节时给 reportSections 里那一节的链接；"
    # synced：这次同步上去的变化，可以据此告诉商家哪里更新了
    payload.update(published=True, firstTime=first_time, synced=synced,
                   next=hint + "说到内容、监测设置时给 links 里对应页面的链接。商家要把报告单独转发给别人时，才给 reportFileUrl。链接逐字照抄")
    payload["tabConfiguration"] = {"tabs": [
        {"tabKey": "conversation", "tabName": "对话", "render_source": "internal",
         "tabUrl": "/digital-employees/{employeeId}/conversation"},
        {"tabKey": None, "tabName": "AI 曝光工作台", "render_source": "external",
         "tabUrl": saved + "#/overview"},
    ]}
    tabs_file = gc.profile_dir() / "employee-tabs.json"
    gc.write_json(tabs_file, payload["tabConfiguration"])
    payload["tabConfigFile"] = str(tabs_file)
    payload["tabSetup"] = "用 Bash 里的 claw-admin-request 按 geo-workbench/references/tabs.md 固定工作台：先读，不对再写，写完读回核对。"
    if urlparse(saved).netloc != EXPECTED_PAGE_HOST:
        payload["hostWarning"] = "链接的域名不是 %s" % EXPECTED_PAGE_HOST
    gc.emit(payload)


def cmd_links(_args) -> None:
    state = gc.workbench_state()
    if not state["url"]:
        raise gc.GeoError("工作台还没有链接，请先执行 publish")
    files = _report_urls()
    payload = {"ok": True, "pageUrl": state["url"],
               # 在工作台里打开最新一期报告；reports 是每一期各自的这个地址。发给商家用这两样
               "reportUrl": report_link(state["url"], _linkable()),
               # 这一期报告的各节，商家问“提到了谁”“读哪里”时给对应那一节
               "reportSections": report_sections(state["url"], _linkable()),
               "links": links(state["url"], _linkable()),
               "reports": {day: report_link(state["url"], day) for day in sorted(files)},
               # 报告文件自己的链接，商家要单独转发给别人时才用
               "reportFileUrl": _latest_report_url(), "reportFiles": files,
               "upToDate": state["upToDate"], "pending": state["pending"], "publishedAt": state["publishedAt"]}
    if not state["upToDate"]:
        payload["next"] = "页面还没同步这些变化：%s。先执行 publish，再把链接发给商家" % "、".join(state["pending"])
    gc.emit(payload)


def cmd_set_page_url(args) -> None:
    """publish 传不上去时的退路：用 youzan-oss 技能生成链接后存回来。带 --report 是存某一期报告的链接。"""
    url = args.url.strip().split("#")[0]
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise gc.GeoError("链接必须是 https 开头的完整地址，请原样复制云盘返回的 url")
    if args.report:
        day = gc.check_date(args.report)
        if day not in _scored_dates():
            raise gc.GeoError("没有 %s 这一期" % day)
        _save_report_urls(dict(_report_urls(), **{day: url}))
        payload = {"ok": True, "report": day, "reportFileUrl": url,
                   "next": "报告文件的链接存好了。请重新生成工作台并传上去（publish），工作台里才打得开这份报告"}
    else:
        _save_url(url)
        gc.mark_published()
        payload = {"ok": True, "pageUrl": url, "links": links(url, _linkable())}
    if parsed.netloc != EXPECTED_PAGE_HOST:
        payload["warning"] = "链接的域名不是 %s，请确认是不是云盘返回的原始链接" % EXPECTED_PAGE_HOST
    gc.emit(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="工作台")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("publish", cmd_publish), ("compare", cmd_compare)):
        p = sub.add_parser(name)
        p.add_argument("--date", default="")
        p.set_defaults(func=func)
    sub.add_parser("links").set_defaults(func=cmd_links)
    sub.add_parser("show").set_defaults(func=cmd_show)
    p = sub.add_parser("set-actions")
    p.add_argument("--file", required=True)
    p.add_argument("--date", default="")
    p.set_defaults(func=cmd_set_actions)
    p = sub.add_parser("add-content")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_add_content)
    p = sub.add_parser("mark-content")
    p.add_argument("--no", type=int, default=0)
    p.add_argument("--status", default="", choices=("",) + CONTENT_STATUS)
    p.add_argument("--channel", default="")
    p.add_argument("--ref", default="")
    p.set_defaults(func=cmd_mark_content)
    sub.add_parser("site-brief").set_defaults(func=cmd_site_brief)
    p = sub.add_parser("set-site")
    p.add_argument("--status", default="", choices=("",) + gc.SITE_STATUS)
    p.add_argument("--test-url", default="")
    p.add_argument("--url", default="")
    p.add_argument("--page-name", default="")
    p.add_argument("--domain", default=None)
    p.set_defaults(func=cmd_set_site)
    p = sub.add_parser("set-page-url")
    p.add_argument("--url", required=True)
    p.add_argument("--report", default="")
    p.set_defaults(func=cmd_set_page_url)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    gc.run_cli(main)
