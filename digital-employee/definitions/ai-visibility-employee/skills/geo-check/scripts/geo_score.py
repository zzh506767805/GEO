#!/usr/bin/env python3
"""把一轮体检的原始回答算成指标，并记下员工核对回答的结果。

能用规则算的都在这里算：提没提到本店、同类店被提到的次数、引用来源、本店内容被引用、
带记忆痕迹的回答。需要理解语义的部分（AI 怎么介绍这家店、哪句和店铺资料对不上、出处是哪条引用）
由员工读 brand-digest 的输出后，用 set-judgement 写回，脚本负责校验。

“和店铺资料对不上的说法”只是核对顺带的发现：有才记，记了也只出现在那一期的报告里，
工作台上没有它的页面，也没有它的数。

用法（脚本用绝对路径执行）：
  geo_score.py score [--date D]
  geo_score.py exclude-shops --names "<名字>,<名字>" [--remove]   “提到了哪些店”里不是店的名字（品类词、商圈），以后各期都不算
  geo_score.py brand-digest [--date D] [--max-chars 900]
  geo_score.py set-judgement --file <json> [--date D]
  geo_score.py issues [--status open|done|dismissed|all]   对不上的说法清单，序号和报告上的一致
  geo_score.py mark-issue --no <序号> --status done|dismissed|open
      done 商家已经改了；dismissed 核实后 AI 没说错（先把店铺资料改对）；open 改回待处理

改了数据的命令都会记一笔“待同步”，做完后执行 geo-weekly 技能里的 geo_report.py publish。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from urllib.parse import urlparse

sys.dont_write_bytecode = True

import geo_common as gc  # noqa: E402

# 顺序有意义：地图要排在“百度系”前面，否则 map.baidu.com 会被归错。
SOURCE_TYPES = [
    ("微信公众号", ("mp.weixin.qq.com", "weixin.qq.com")),
    ("抖音", ("douyin.com", "iesdouyin.com")),
    ("地图", ("amap.com", "map.baidu.com", "maps.apple.com", "map.qq.com", "map.360.cn", "mapbar.com")),
    ("大众点评和美团", ("dianping.com", "meituan.com")),
    ("知乎", ("zhihu.com",)),
    ("小红书", ("xiaohongshu.com", "xhslink.com")),
    ("今日头条", ("toutiao.com",)),
    ("携程", ("ctrip.com",)),
    ("搜狐", ("sohu.com",)),
    ("百度系", ("baidu.com",)),
    ("网易", ("163.com",)),
    ("腾讯新闻", ("news.qq.com", "inews.qq.com", "new.qq.com")),
    ("电商平台", ("taobao.com", "tmall.com", "jd.com", "pinduoduo.com", "yangkeduo.com", "1688.com", "youzan.com")),
    ("什么值得买", ("smzdm.com",)),
    ("B站", ("bilibili.com",)),
    ("微博", ("weibo.com", "weibo.cn")),
]
STORE_PAGE_TYPES = ("地图", "大众点评和美团")

# 取数账号带着历史对话时，回答里会出现这类说法。只认“和提问者有过对话”的说法，
# “前面提到的”“买之前先看”这类指回答自身或时间先后的不算。
MEMORY_PATTERNS = [
    re.compile(r"(你|您)(之前|上次|上回|此前|早先|刚才|刚刚)[^。，,；;\n]{0,8}(问|聊|看|提|说|关注|查|搜|了解)"),
    re.compile(r"(之前|上次|上回|此前)(聊|问)(过|的|到|起)"),
    re.compile(r"(记得你|你提到过|你说过|你问过|咱们聊过|我们聊过|咱们之前|我们之前)"),
]
CANDIDATE_LINE = re.compile(r"^\s*(?:#{1,4}\s*)?(?:\d+[.、)）]\s*|[-*•]\s*)?\*\*([^*\n]{2,24})\*\*", re.M)
CANDIDATE_STOP = ("推荐", "特点", "地址", "人均", "招牌", "优点", "缺点", "营业", "亮点", "总结", "建议", "注意",
                  "适合", "价格", "口味", "环境", "交通", "结论", "提示", "选购", "攻略", "对比", "理由", "位置",
                  "必点", "必买", "产品", "特色", "风格", "门店", "电话", "时间", "方式", "小贴士", "避雷")
SHOPS_SHOWN = 15
NOT_SHOPS_FILE = "not-shops.json"
FACT_KINDS = ("address", "hours", "phone", "product", "price", "status", "other")
SOURCE_KINDS = ("map", "note", "own", "other", "unknown")
MISSING_LIMIT = 0.25


def classify(host: str) -> str:
    host = (host or "").lower()
    for label, keys in SOURCE_TYPES:
        if any(key in host for key in keys):
            return label
    return "其他网站"


def answer_text(answer: dict) -> str:
    return gc.clean_answer(answer)


def has_memory_trace(text: str) -> bool:
    return any(pattern.search(text) for pattern in MEMORY_PATTERNS)


def ref_host(ref: dict) -> str:
    return str(ref.get("host") or urlparse(str(ref.get("url") or "")).netloc).lower()


def cmd_exclude_shops(args) -> None:
    names = [n.strip() for n in re.split(r"[,，、]", args.names) if n.strip()]
    if not names:
        raise gc.GeoError("没有给出要去掉的名字")
    path = gc.profile_dir() / NOT_SHOPS_FILE
    items = (gc.read_json(path, {}) or {}).get("items") or []
    items = [n for n in items if n not in names] if args.remove else items + [n for n in names if n not in items]
    gc.write_json(path, {"updatedAt": gc.now_iso(), "items": items})
    gc.emit({"ok": True, "notShops": items, "next": "请重新执行 geo_score.py score，报告里的“提到了谁”才会更新"})


def load_profile() -> dict:
    root = gc.profile_dir()
    facts = gc.read_json(root / "facts.json")
    if not facts:
        raise gc.GeoError("还没有建档，请先按 geo-profile 建档")
    return {
        "facts": facts,
        "questions": (gc.read_json(root / "questions.json", {}) or {}).get("items") or [],
        "rivals": (gc.read_json(root / "rivals.json", {}) or {}).get("items") or [],
        "notShops": (gc.read_json(root / NOT_SHOPS_FILE, {}) or {}).get("items") or [],
    }


def load_run(date: str) -> dict:
    folder = gc.run_dir(date)
    state = gc.read_json(folder / "queries.json")
    if not state or not state.get("items"):
        raise gc.GeoError("这一天还没有体检记录")
    raw = {}
    for key, item in state["items"].items():
        data = gc.read_json(folder / "raw" / (key + ".json")) if item["status"] == "done" else None
        raw[key] = ((data or {}).get("result") or {}).get("answers") or []
    return {"state": state, "raw": raw}


def classify_ref(ref: dict, facts: dict, aliases: list) -> dict:
    """一条引用和本店的关系：own 本店账号或页面；store 以本店命名的门店页；about 别人写本店的内容。"""
    host = ref_host(ref)
    kind = classify(host)
    title = gc.clean_title(ref.get("title"))
    source = gc.clean_text(ref.get("source"))
    channels = facts.get("channels") or {}
    official = gc.clean_text(channels.get("wechatOfficial"))
    own_hosts = [h for h in channels.get("ownHosts") or [] if h]
    shop_host = urlparse(str((facts.get("buyEntry") or {}).get("shopUrl") or "")).netloc.lower()
    if shop_host:
        own_hosts.append(shop_host)
    url = str(ref.get("url") or "")
    # 抖音等平台的引用不带作者，只能靠建档时记下的“本店内容编号”来认。
    own_keys = [k for k in channels.get("ownContentKeys") or [] if k]
    relation = ""
    if ((kind == "微信公众号" and official and source == official)
            or any(h and h in host for h in own_hosts)
            or any(key in url for key in own_keys)):
        relation = "own"
    elif gc.contains_any(title, aliases):
        relation = "store" if kind in STORE_PAGE_TYPES else "about"
    return {"type": kind, "relation": relation, "title": title[:80], "source": source[:30],
            "url": str(ref.get("url") or "")[:400], "no": ref.get("no")}


def first_pos(text_low: str, names) -> int:
    hits = [text_low.find(str(n).lower()) for n in names if n and text_low.find(str(n).lower()) >= 0]
    if not hits:
        # 实测里 DeepSeek 返回的正文偶尔丢掉开头第一个字（“麦的日尝…”变成“的日尝…”），
        # 只在正文最开头做这一个补救，不扩大成普通的模糊匹配。
        head = text_low.lstrip()
        if any(len(str(n)) >= 3 and head.startswith(str(n).lower()[1:]) for n in names if n):
            return 0
    return min(hits) if hits else -1


def analyse_answer(answer: dict, profile: dict, aliases: list) -> dict:
    facts = profile["facts"]
    text = answer_text(answer)
    low = text.lower()
    mine = first_pos(low, aliases)
    rival_hits = []
    ahead = 0
    for rival in profile["rivals"]:
        pos = first_pos(low, [rival["name"]] + list(rival.get("aliases") or []))
        if pos >= 0:
            rival_hits.append(rival["name"])
            if mine >= 0 and pos < mine:
                ahead += 1
    refs = [classify_ref(ref, facts, aliases) for ref in ((answer.get("references") or {}).get("list")) or []]
    entry = facts.get("buyEntry") or {}
    shop_host = urlparse(str(entry.get("shopUrl") or "")).netloc.lower()
    buy_entry = bool(
        (entry.get("miniProgram") and entry["miniProgram"].lower() in low)
        or (shop_host and (shop_host in low or any(shop_host in r["url"].lower() for r in refs)))
    )
    return {
        "mentioned": mine >= 0,
        "memory": has_memory_trace(text),
        "rank": (ahead + 1) if mine >= 0 and profile["rivals"] else None,
        "rivals": rival_hits,
        "refs": refs,
        "buyEntry": buy_entry,
        "chars": len(text),
    }


def shop_names(text: str, own: list) -> set:
    """一个回答里被加粗点名的店名或品牌（列表项、小标题里加粗的那几个字）。不含本店。"""
    names = set()
    for match in CANDIDATE_LINE.finditer(text):
        name = re.split(r"[（(：:｜|/]", match.group(1))[0].strip(" ·-—")
        if not 2 <= len(name) <= 16 or any(stop in name for stop in CANDIDATE_STOP):
            continue
        if gc.contains_any(name, own) or re.fullmatch(r"[\d\s.%元]+", name):
            continue
        names.add(name)
    return names


def _as_rival(name: str, rivals: list) -> str:
    """店名对得上某家同类店（名字或别名互相包含），就记在同类店的名字下，免得一家店算成两家。"""
    for rival in rivals:
        keys = [rival["name"]] + list(rival.get("aliases") or [])
        if gc.contains_any(name, keys) or any(k and k in name or name in k for k in keys):
            return rival["name"]
    return name


def _ratio(counter: Counter, total: int, top: int = 8) -> list:
    return [{"type": k, "count": v, "pct": round(v * 100 / total)} for k, v in counter.most_common(top)] if total else []


def build_summary(date: str) -> dict:
    profile = load_profile()
    run = load_run(date)
    facts = profile["facts"]
    aliases = gc.brand_aliases(facts)
    kinds = {q["id"]: q["kind"] for q in profile["questions"]}
    cells, answers = {}, {}
    mention = {"hits": 0, "valid": 0, "byProvider": {}, "byQuestion": {}}
    for provider in gc.PROVIDERS:
        mention["byProvider"][provider] = {"hits": 0, "valid": 0}
    rival_counter = Counter()
    rival_by_provider = {}
    shop_counter, shop_by_provider = Counter(), {}
    not_shops = set(profile.get("notShops") or [])
    src_all, src_by_provider = Counter(), {p: Counter() for p in gc.PROVIDERS}
    related = {"own": {}, "store": {}, "about": {}}
    related_count = Counter()
    buy_entry = {"count": 0, "valid": 0}
    memory_flagged = brand_answers = 0
    missing = []
    for key, item in sorted(run["state"]["items"].items()):
        qid, provider = item["qid"], item["provider"]
        kind = kinds.get(qid, item["kind"])
        rows = [analyse_answer(a, profile, aliases) for a in run["raw"][key]]
        cell = {"status": item["status"], "answers": len(rows), "valid": 0, "hits": 0, "memory": 0}
        if not rows:
            missing.append(key)
        for index, (row, source) in enumerate(zip(rows, run["raw"][key]), 1):
            if row["memory"]:
                cell["memory"] += 1
                memory_flagged += 1
            else:
                cell["valid"] += 1
                cell["hits"] += int(row["mentioned"])
                buy_entry["valid"] += 1
                buy_entry["count"] += int(row["buyEntry"])
            if kind == "brand":
                brand_answers += 1
            elif not row["memory"]:
                for name in row["rivals"]:
                    rival_counter[name] += 1
                    rival_by_provider.setdefault(name, Counter())[provider] += 1
                named = {_as_rival(n, profile["rivals"]) for n in shop_names(answer_text(source), aliases)} | set(row["rivals"])
                for name in named - not_shops:
                    shop_counter[name] += 1
                    shop_by_provider.setdefault(name, Counter())[provider] += 1
            for ref in row["refs"]:
                src_all[ref["type"]] += 1
                src_by_provider[provider][ref["type"]] += 1
                if ref["relation"]:
                    related_count[ref["relation"]] += 1
                    entry = related[ref["relation"]].setdefault(ref["url"] or ref["title"], dict(ref, usedIn=[]))
                    tag = "%s#%d" % (key, index)
                    if tag not in entry["usedIn"]:
                        entry["usedIn"].append(tag)
        cells.setdefault(qid, {})[provider] = cell
        answers[key] = [{k: r[k] for k in ("mentioned", "memory", "rank", "buyEntry")}
                        | {"refInfo": [[ref["type"], ref["relation"]] for ref in r["refs"]]} for r in rows]
        if kind == "open":
            for bucket in (mention, mention["byProvider"][provider], mention["byQuestion"].setdefault(qid, {"hits": 0, "valid": 0})):
                bucket["hits"] += cell["hits"]
                bucket["valid"] += cell["valid"]
    expected = len(run["state"]["items"])
    rival_names = {r["name"] for r in profile["rivals"]}
    shops = [{"name": name, "count": count, "byProvider": dict(shop_by_provider[name]), "rival": name in rival_names}
             for name, count in sorted(shop_counter.items(), key=lambda kv: (-kv[1], kv[0]))]
    summary = {
        "date": date,
        "generatedAt": gc.now_iso(),
        "segment": facts["segment"],
        "questionsVersion": run["state"].get("questionsVersion", 0),
        "expected": expected,
        "returned": expected - len(missing),
        "missing": missing,
        "complete": expected > 0 and len(missing) / expected <= MISSING_LIMIT,
        "cells": cells,
        "answers": answers,
        "mention": mention,
        "memoryFlagged": memory_flagged,
        "brandAnswers": brand_answers,
        "refs": {
            "total": sum(src_all.values()),
            "own": related_count["own"],
            "storePages": related_count["store"],
            "aboutStore": related_count["about"],
            "ownItems": list(related["own"].values())[:20],
            "storePageItems": list(related["store"].values())[:20],
            "aboutItems": list(related["about"].values())[:30],
        },
        "sources": {
            "all": _ratio(src_all, sum(src_all.values())),
            "byProvider": {p: _ratio(c, sum(c.values()), 6) for p, c in src_by_provider.items()},
        },
        "rivals": [{"name": r["name"], "count": rival_counter[r["name"]],
                    "byProvider": dict(rival_by_provider.get(r["name"], {}))} for r in profile["rivals"]],
        "buyEntry": buy_entry if facts["segment"] == "ecom" else None,
        # 顾客没点名时 AI 提到的所有店，按出现在几个回答里排序。报告“提到了谁”列的就是它
        "shops": shops[:SHOPS_SHOWN],
        # 还不是同类店、出现在两个以上回答里的，供第一次体检后挑同类店
        "candidates": [{"name": s["name"], "answers": s["count"]} for s in shops if not s["rival"] and s["count"] >= 2][:25],
    }
    summary["rivals"].sort(key=lambda r: r["count"], reverse=True)
    return summary


def _drop_removed(date: str) -> list:
    """最新一期按现在的问题清单算：商家删掉的题不再算进去。以前各期按当时问的题算，不动。"""
    if date != gc.latest_run_date():
        return []
    path = gc.run_dir(date) / "queries.json"
    state = gc.read_json(path)
    if not state:
        return []
    bank = {q["id"] for q in (gc.read_json(gc.profile_dir() / "questions.json", {}) or {}).get("items") or []}
    dropped = gc.drop_removed_questions(state, bank) if bank else []
    if dropped:
        gc.write_json(path, state)
    return dropped


def cmd_score(args) -> None:
    date = gc.resolve_date(args.date)
    dropped = _drop_removed(date)
    summary = build_summary(date)
    gc.write_json(gc.run_dir(date) / "summary.json", summary)
    mention = summary["mention"]
    gc.mark_changed("体检结果")
    digest = {
        "ok": True,
        "date": date,
        "complete": summary["complete"],
        "expected": summary["expected"],
        "missing": summary["missing"],
        "mention": {"hits": mention["hits"], "valid": mention["valid"],
                    "byProvider": {gc.PROVIDER_NAMES[p]: "%d/%d" % (v["hits"], v["valid"]) for p, v in mention["byProvider"].items()}},
        "questionsMentioned": sorted(q for q, v in mention["byQuestion"].items() if v["hits"]),
        "memoryFlagged": summary["memoryFlagged"],
        "refs": {k: summary["refs"][k] for k in ("total", "own", "storePages", "aboutStore")},
        "topSources": summary["sources"]["all"][:5],
        "rivals": [{"name": r["name"], "count": r["count"]} for r in summary["rivals"]],
        "shops": [{"name": s["name"], "count": s["count"]} for s in summary["shops"]],
        "buyEntry": summary["buyEntry"],
        "notes": [],
    }
    if dropped:
        digest["notes"].append("这几道题已经从问题清单里删掉，这一期不再算：" + "、".join(dropped))
    if not summary["complete"]:
        digest["notes"].append("本轮缺失的查询超过四分之一，周报要注明“本周数据不全”")
    if summary["memoryFlagged"]:
        digest["notes"].append("有 %d 个回答带着历史对话的痕迹，已从提及统计里剔除" % summary["memoryFlagged"])
    if not summary["rivals"]:
        digest["candidates"] = summary["candidates"]
        if summary["candidates"]:
            # 同类店没定，报告里“提到了谁”就是空的。先定同类店再往下走，next 和 notes 说的是同一件事
            digest["next"] = ("同类店还没定：从 candidates 里挑 3 家和本店同品类、同区域的店（不要挑商圈、平台、品类词），"
                              "带上常见的别名，用 geo-profile 技能里的 geo_state.py set-rivals 保存，然后重新执行 score")
            digest["notes"].append("同类店还没定，先按 next 选好同类店，再重新执行 score")
        else:
            digest["notes"].append("AI 的回答里没有提到别的店，这一期先不选同类店")
    if summary["shops"]:
        digest["notes"].append("shops 是报告“提到了谁”要列的店。里面有不是店的名字（品类词、商圈、平台名），"
                               "用 exclude-shops 去掉再重新 score；连锁品牌、网店也算店，不要去掉")
    digest.setdefault("next", "请执行 brand-digest，读完后用 set-judgement 写回 AI 怎么介绍本店；有和店铺资料对不上的说法才写进 issues，没有就传空数组")
    gc.emit(digest)


def cmd_brand_digest(args) -> None:
    date = gc.resolve_date(args.date)
    profile = load_profile()
    run = load_run(date)
    aliases = gc.brand_aliases(profile["facts"])
    texts = {q["id"]: q["text"] for q in profile["questions"]}
    rows = []
    for key, item in sorted(run["state"]["items"].items()):
        for index, answer in enumerate(run["raw"][key], 1):
            text = answer_text(answer)
            mentioned = gc.contains_any(text, aliases)
            if item["kind"] != "brand" and not mentioned:
                continue
            refs = []
            for ref in ((answer.get("references") or {}).get("list")) or []:
                info = classify_ref(ref, profile["facts"], aliases)
                refs.append({k: info[k] for k in ("no", "type", "title", "source", "url")})
            rows.append({
                "answer": "%s#%d" % (key, index),
                "platform": gc.PROVIDER_NAMES.get(item["provider"], item["provider"]),
                "question": texts.get(item["qid"], item["question"]),
                "withBrandName": item["kind"] == "brand",
                "memoryTrace": has_memory_trace(text),
                "text": text[: args.max_chars],
                "truncated": len(text) > args.max_chars,
                "refs": refs[:15],
            })
    ledger = (gc.read_json(gc.profile_dir() / "issues.json", {}) or {}).get("items") or {}
    gc.emit({
        "ok": True,
        "date": date,
        "facts": profile["facts"],
        # 之前已经记过的对不上的说法：同一件事要沿用原来的编号，这样“商家说改过了但 AI 还在说”才能被认出来。
        "knownIssues": [{"id": k, "fact": v["fact"], "aiSays": v["aiSays"], "status": v["status"]} for k, v in sorted(ledger.items())],
        "answers": rows,
        "next": "按 references/judging.md 写出 descriptions；逐条对照 facts，有对不上的具体事实才写进 issues（没有就传空数组），再执行 set-judgement",
    })


def _evidence_refs(run: dict, evidence: list) -> set:
    urls = set()
    for tag in evidence:
        key, _, index = tag.partition("#")
        rows = run["raw"].get(key)
        if rows is None or not index.isdigit() or not 1 <= int(index) <= len(rows):
            raise gc.GeoError("证据编号不存在：" + tag)
        for ref in ((rows[int(index) - 1].get("references") or {}).get("list")) or []:
            urls.add(str(ref.get("url") or ""))
    return urls


def normalize_issue(raw: dict, run: dict) -> dict:
    issue_id = gc.clean_text(raw.get("id")).lower()
    if not re.match(r"^[a-z0-9][a-z0-9-]{2,39}$", issue_id):
        raise gc.GeoError("每一条对不上的说法需要一个英文短编号，例如 address-old-store")
    fact = raw.get("fact") if raw.get("fact") in FACT_KINDS else "other"
    source_type = raw.get("sourceType") if raw.get("sourceType") in SOURCE_KINDS else "unknown"
    ai_says, truth, fix = (gc.clean_text(raw.get(k))[:200] for k in ("aiSays", "truth", "fix"))
    if not (ai_says and truth and fix):
        raise gc.GeoError(issue_id + "：AI 的说法、店铺资料里怎么写、怎么改，三项都要写")
    evidence = [gc.clean_text(e) for e in (raw.get("evidence") or [])][:12]
    if not evidence:
        raise gc.GeoError(issue_id + "：要写明出自哪几个回答")
    allowed = _evidence_refs(run, evidence)
    source_url = str(raw.get("sourceUrl") or "").strip()
    if source_url and source_url not in allowed:
        # 出处只能从这几个回答自带的引用里选，防止凭印象编一个链接。
        raise gc.GeoError(issue_id + "：出处链接不在这些回答的引用列表里，请从 brand-digest 的 refs 里原样复制")
    if source_type in ("map", "note", "own", "other") and not source_url:
        source_type = "unknown"
    platforms = sorted({tag.split("_")[1].split("#")[0] for tag in evidence if "_" in tag})
    return {"id": issue_id, "fact": fact, "aiSays": ai_says, "truth": truth, "fix": fix,
            "evidence": evidence, "platforms": [p for p in platforms if p in gc.PROVIDERS],
            "sourceType": source_type, "sourceTitle": gc.clean_text(raw.get("sourceTitle"))[:80],
            "sourceUrl": source_url[:400]}


def cmd_set_judgement(args) -> None:
    date = gc.resolve_date(args.date)
    run = load_run(date)
    payload = gc.load_input(args.file)
    if not isinstance(payload, dict):
        raise gc.GeoError("核对结果应为一个对象")
    descriptions = {}
    for provider in gc.PROVIDERS:
        text = gc.clean_text((payload.get("descriptions") or {}).get(provider))[:120]
        if text:
            descriptions[provider] = text
    issues = [normalize_issue(item, run) for item in (payload.get("issues") or [])[:20] if isinstance(item, dict)]
    if len({i["id"] for i in issues}) != len(issues):
        raise gc.GeoError("对不上的说法编号重复")
    ledger_path = gc.profile_dir() / "issues.json"
    ledger = gc.read_json(ledger_path, {}) or {}
    items = ledger.get("items") or {}
    for entry in items.values():
        entry["seenThisRun"] = False
    next_no = max([int(e.get("no") or 0) for e in items.values()] + [0]) + 1
    for issue in issues:
        previous = items.get(issue["id"]) or {}
        number = int(previous.get("no") or 0)
        if not number:
            # 序号一旦给出就不再变，也不重复使用：商家说“3 号改好了”时靠它对上。
            number, next_no = next_no, next_no + 1
        items[issue["id"]] = dict(issue, no=number, status=previous.get("status", "open"),
                                  firstSeen=previous.get("firstSeen", date), lastSeen=date, seenThisRun=True)
        if previous.get("status") == "done":
            items[issue["id"]]["status"] = "open"  # 商家说改过了，但 AI 这周还在这么说
            items[issue["id"]]["reopened"] = True
        elif previous.get("status") == "dismissed":
            items[issue["id"]]["status"] = "open"  # 之前核实过不算错，这次又记成对不上：按新的一条待处理
    gc.write_json(ledger_path, {"updatedAt": gc.now_iso(), "lastRun": date, "items": items})
    open_after = sum(1 for e in items.values() if e["status"] == "open")
    gc.write_json(gc.run_dir(date) / "judgement.json",
                  {"date": date, "descriptions": descriptions, "issueIds": [i["id"] for i in issues],
                   "issuesFound": len(issues), "issuesOpenAfter": open_after})
    gc.mark_changed("对回答的核对")
    gc.emit({"ok": True, "date": date, "issuesThisRun": len(issues),
             "issuesOpen": sum(1 for e in items.values() if e["status"] == "open"),
             "reopened": [k for k, e in items.items() if e.get("reopened") and e["lastSeen"] == date],
             "next": "核对结果已保存。接着按 geo-weekly 写本期小结和建议（set-actions），再执行 %s 生成这一期的报告" % gc.PUBLISH_COMMAND})


def _issue_rows(items: dict) -> list:
    rows = [{"no": e.get("no"), "id": k, "status": e["status"], "fact": e["fact"], "aiSays": e["aiSays"],
             "truth": e["truth"], "fix": e["fix"], "firstSeen": e.get("firstSeen", ""), "lastSeen": e.get("lastSeen", ""),
             "seenThisRun": bool(e.get("seenThisRun"))} for k, e in items.items()]
    return sorted(rows, key=lambda r: (r["status"] != "open", r["no"] or 0))


def cmd_issues(args) -> None:
    """对不上的说法清单，序号和报告上显示的一致。"""
    items = (gc.read_json(gc.profile_dir() / "issues.json", {}) or {}).get("items") or {}
    rows = [r for r in _issue_rows(items) if args.status in ("all", r["status"])]
    gc.emit({"ok": True, "open": sum(1 for e in items.values() if e["status"] == "open"), "items": rows,
             "next": "商家说某一条改好了：mark-issue --no <序号> --status done；"
                     "说 AI 其实没说错：先按 geo-profile 把店铺资料改对，再 mark-issue --no <序号> --status dismissed"})


def cmd_mark_issue(args) -> None:
    ledger_path = gc.profile_dir() / "issues.json"
    ledger = gc.read_json(ledger_path, {}) or {}
    items = ledger.get("items") or {}
    issue_id = args.id
    if args.no:
        issue_id = next((k for k, e in items.items() if int(e.get("no") or 0) == args.no), "")
    if not issue_id or issue_id not in items:
        raise gc.GeoError("没有这一条。请先执行 issues 看现在有哪些序号")
    items[issue_id]["status"] = args.status
    items[issue_id]["reopened"] = False
    if args.status == "done":
        items[issue_id]["doneAt"] = gc.now_iso()
    elif args.status == "dismissed":
        # 商家说 AI 这句其实没说错（是店铺资料不全或写错了）。先改资料，再用这个状态把它从待处理里拿掉。
        items[issue_id]["doneAt"] = gc.now_iso()
    gc.write_json(ledger_path, dict(ledger, items=items, updatedAt=gc.now_iso()))
    gc.mark_changed("对回答的核对")
    gc.emit({"ok": True, "id": issue_id, "no": items[issue_id].get("no"), "status": args.status,
             "issuesOpen": sum(1 for e in items.values() if e["status"] == "open"),
             "next": gc.sync_hint()})


def main() -> None:
    parser = argparse.ArgumentParser(description="体检算分")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("score")
    p.add_argument("--date", default="")
    p.set_defaults(func=cmd_score)
    p = sub.add_parser("exclude-shops")
    p.add_argument("--names", required=True)
    p.add_argument("--remove", action="store_true")
    p.set_defaults(func=cmd_exclude_shops)
    p = sub.add_parser("brand-digest")
    p.add_argument("--date", default="")
    p.add_argument("--max-chars", type=int, default=900)
    p.set_defaults(func=cmd_brand_digest)
    p = sub.add_parser("set-judgement")
    p.add_argument("--file", required=True)
    p.add_argument("--date", default="")
    p.set_defaults(func=cmd_set_judgement)
    p = sub.add_parser("issues")
    p.add_argument("--status", default="all", choices=("open", "done", "dismissed", "all"))
    p.set_defaults(func=cmd_issues)
    p = sub.add_parser("mark-issue")
    p.add_argument("--id", default="")
    p.add_argument("--no", type=int, default=0)
    p.add_argument("--status", required=True, choices=("done", "dismissed", "open"))
    p.set_defaults(func=cmd_mark_issue)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    gc.run_cli(main)
