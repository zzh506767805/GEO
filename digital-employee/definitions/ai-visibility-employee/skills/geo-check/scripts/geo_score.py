#!/usr/bin/env python3
"""把一轮体检的原始回答算成指标，并记下员工核对回答的结果。

能用规则算的都在这里算：提没提到本店、引用来源、本店内容被引用。凡是靠“名字出现在文字里”算的，
同名的店、同名的养老院都会混进来，所以要员工读完回答后复核（set-reading）：每个回答推荐了哪几家店、
哪些“提到你”其实说的不是这家店、哪些引用其实和这家店无关（或者没写店名但写的就是它）。
发现（set-findings）、AI 怎么介绍这家店和哪句对不上（set-judgement）也由员工写回，脚本负责校验和计数。

“和店铺资料对不上的说法”只是核对顺带的发现：有才记，记了也只出现在那一期的报告里，
工作台上没有它的页面，也没有它的数。

用法（脚本用绝对路径执行）：
  geo_score.py score [--date D]
  geo_score.py answers --provider <平台> [--only q01,q03] [--date D]   一个平台每个回答的全文和引用，给读全文的子 Agent 用
  geo_score.py set-reading --file <json> [--file <json> ...] [--date D]  读全文后写回：推荐的店、不是你的“提到”和引用
  geo_score.py set-findings --file <json> [--date D]                  写回这一期的发现，最多 5 条，每条带原文证据
  geo_score.py brand-digest [--date D] [--max-chars 900]
  geo_score.py set-judgement --file <json> [--date D]
  geo_score.py issues [--status open|done|dismissed|all]   对不上的说法清单，序号和报告上的一致
  geo_score.py mark-issue --no <序号> --status done|dismissed|open
      done 商家已经改了；dismissed 核实后 AI 没说错（先把店铺资料改对）；open 改回待处理

改了数据的命令都会记一笔“待同步”，做完后执行 geo-workbench 技能里的 geo_report.py publish。
"""
from __future__ import annotations

import argparse
import hashlib
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
    ("企业信息", ("tianyancha.com", "qcc.com", "aiqicha.baidu.com", "qixin.com")),
    ("电话黄页", ("dianhua.cn", "114best.com", "huangye88.com")),
    ("本地生活网站", ("bendibao.com",)),
    ("百度系", ("baidu.com",)),
    ("网易", ("163.com",)),
    ("腾讯新闻", ("news.qq.com", "inews.qq.com", "new.qq.com")),
    ("电商平台", ("taobao.com", "tmall.com", "jd.com", "pinduoduo.com", "yangkeduo.com", "1688.com", "youzan.com")),
    ("什么值得买", ("smzdm.com",)),
    ("B站", ("bilibili.com",)),
    ("微博", ("weibo.com", "weibo.cn")),
]
STORE_PAGE_TYPES = ("地图", "大众点评和美团")

SHOPS_SHOWN = 15


def sources_by_provider(summary: dict) -> dict:
    """各平台最常读哪里，前 4 类。算分输出和 geo_report.py show 用同一个写法。"""
    return {gc.PROVIDER_NAMES.get(p, p): ["%s %d%%" % (x["type"], x["pct"]) for x in v[:4]]
            for p, v in ((summary.get("sources") or {}).get("byProvider") or {}).items()}
OTHER_SITE = "其他网站"
READING_FILE = "reading.json"
RELATED_FILE = "related.json"
SITE_SHOWN_FROM = 2  # 对照表里没有的网站，一期被引用到这么多次，图表里就单独成一行，不再算进“其他网站”
FINDINGS_CAP = 5
FINDING_KINDS = {"misread": "认错了你", "lead": "线索", "against": "对你不利的说法", "rivals": "同行的做法", "other": "其他"}
FACT_KINDS = ("address", "hours", "phone", "product", "price", "status", "other")
SOURCE_KINDS = ("map", "note", "own", "other", "unknown")
MISSING_LIMIT = 0.25


def classify(host: str) -> str:
    host = (host or "").lower()
    for label, keys in SOURCE_TYPES:
        if any(key in host for key in keys):
            return label
    return OTHER_SITE


def answer_text(answer: dict) -> str:
    return gc.clean_answer(answer)


def ref_host(ref: dict) -> str:
    return str(ref.get("host") or urlparse(str(ref.get("url") or "")).netloc).lower()


def _norm(text: str) -> str:
    """比对原文用：去掉空白和 markdown 加粗、统一大小写，免得换行或加粗让一句原话对不上。"""
    return re.sub(r"\s+|\*\*", "", str(text or "")).lower()


def _digest_hash(text: str) -> str:
    return hashlib.sha1(_norm(text).encode("utf-8")).hexdigest()[:12]


def _answer_index(run: dict, profile: dict) -> dict:
    """这一期每个回答：编号 → 正文、平台、题号、是不是没点名的、脚本算不算提到了本店。"""
    aliases = gc.brand_aliases(profile["facts"])
    texts = {q["id"]: q["text"] for q in profile["questions"]}
    kinds = {q["id"]: q["kind"] for q in profile["questions"]}
    out = {}
    for key, item in sorted(run["state"]["items"].items()):
        for index, answer in enumerate(run["raw"][key], 1):
            text = answer_text(answer)
            out["%s#%d" % (key, index)] = {
                "text": text, "provider": item["provider"], "qid": item["qid"],
                "question": texts.get(item["qid"], item["question"]),
                "open": kinds.get(item["qid"], item["kind"]) == "open", "mentioned": gc.contains_any(text, aliases),
                "refs": ((answer.get("references") or {}).get("list")) or [],
            }
    return out


def load_reading(date: str) -> dict:
    """员工读全文后写回的结果：每个回答推荐的店、同一家店的写法、哪些“提到你”其实说的不是这家店。"""
    data = gc.read_json(gc.run_dir(date) / READING_FILE, {}) or {}
    return {"answers": data.get("answers") or {}, "names": data.get("names") or {}, "notUs": data.get("notUs") or {}}


def load_related() -> dict:
    """员工复核过的引用，跨期有效：notUs 同名但不是这家店，aboutUs 没写店名但写的就是这家店。"""
    data = gc.read_json(gc.profile_dir() / RELATED_FILE, {}) or {}
    return {"notUs": set(data.get("notUs") or []), "aboutUs": set(data.get("aboutUs") or [])}


def count_shops(reading: dict, eligible: dict, rivals: list):
    """按员工写回的店名计数。回答重跑过、正文变了的，算作还没读。"""
    counter, by_provider, pending = Counter(), {}, []
    for tag, (text, provider) in sorted(eligible.items()):
        entry = reading["answers"].get(tag)
        if not entry or entry.get("hash") != _digest_hash(text):
            pending.append(tag)
            continue
        for name in {_as_rival(n, rivals) for n in entry.get("shops") or []}:
            counter[name] += 1
            by_provider.setdefault(name, Counter())[provider] += 1
    rival_names = {r["name"] for r in rivals}
    shops = [{"name": name, "count": count, "byProvider": dict(by_provider[name]), "rival": name in rival_names}
             for name, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]
    return shops, pending


def load_findings(date: str, run: dict):
    """这一期的发现。每条的原文证据都重新对一遍：回答重跑过、原话不在了的证据去掉，证据全没了的发现去掉。"""
    items = (gc.read_json(gc.run_dir(date) / "findings.json", {}) or {}).get("items") or []
    texts = {}
    for key, rows in run["raw"].items():
        for index, answer in enumerate(rows, 1):
            texts["%s#%d" % (key, index)] = _norm(answer_text(answer))
    kept, dropped = [], []
    for item in items:
        evidence = [e for e in item.get("evidence") or [] if _norm(e["quote"]) in texts.get(e["answer"], "")]
        if evidence:
            kept.append(dict(item, evidence=evidence))
        else:
            dropped.append(item.get("title", ""))
    return kept, dropped


def _bare_url(value) -> str:
    """比对链接用：去掉 http(s)://、问号和井号后面的部分、末尾的斜杠，统一小写。"""
    text = re.sub(r"^[a-z]+://", "", str(value or "").strip().lower())
    return re.split(r"[?#]", text)[0].rstrip("/")


def _with_site(facts: dict) -> dict:
    """已上线的官网也是本店自己的内容：把它的链接和独立域名带进 channels，classify_ref 据此认。"""
    site = gc.site_state(facts)
    if not site.get("live"):
        return facts
    channels = dict(facts.get("channels") or {}, siteUrl=site["url"], siteDomain=site.get("domain", ""))
    return dict(facts, channels=channels)


def load_profile() -> dict:
    root = gc.profile_dir()
    facts = gc.read_json(root / "facts.json")
    if not facts:
        raise gc.GeoError("还没有建档，请先按 geo-profile 建档")
    return {
        "facts": _with_site(facts),
        "questions": (gc.read_json(root / "questions.json", {}) or {}).get("items") or [],
        "rivals": (gc.read_json(root / "rivals.json", {}) or {}).get("items") or [],
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


def site_name(ref: dict) -> str:
    """对照表里没有的网站叫什么：优先用引用自带的来源名（“天眼查”），没有就用域名。"""
    source = gc.clean_text(ref.get("source"))
    if 2 <= len(source) <= 12 and "." not in source and "/" not in source:
        return source
    return re.sub(r"^(www|m|wap)\.", "", ref_host(ref)) or OTHER_SITE


def classify_ref(ref: dict, facts: dict, aliases: list, related: dict = None) -> dict:
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
    # 员工替商家做的官网：正式链接本身和它下面的页面都算（official-site-2 这种名字相近的不算）；绑了独立域名的，这个域名下的页面都算
    site_url = _bare_url(channels.get("siteUrl"))
    site_domain = str(channels.get("siteDomain") or "").lower()
    relation = ""
    if ((kind == "微信公众号" and official and source == official)
            or any(h and h in host for h in own_hosts)
            or any(key in url for key in own_keys)
            or (site_url and (_bare_url(url) + "/").startswith(site_url + "/"))
            or (site_domain and (host == site_domain or host.endswith("." + site_domain)))):
        relation = "own"
    elif gc.contains_any(title, aliases):
        relation = "store" if kind in STORE_PAGE_TYPES else "about"
    # 员工读全文时复核过的：同名但不是这家店的去掉；没写店名但写的就是这家店的加上
    related = related or {}
    if relation in ("store", "about") and url in related.get("notUs", ()):
        relation = ""
    elif not relation and url in related.get("aboutUs", ()):
        relation = "store" if kind in STORE_PAGE_TYPES else "about"
    return {"type": kind, "site": site_name(ref) if kind == OTHER_SITE else kind, "relation": relation, "title": title[:80], "source": source[:30],
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


def analyse_answer(answer: dict, profile: dict, aliases: list, related: dict) -> dict:
    facts = profile["facts"]
    text = answer_text(answer)
    low = text.lower()
    refs = [classify_ref(ref, facts, aliases, related) for ref in ((answer.get("references") or {}).get("list")) or []]
    entry = facts.get("buyEntry") or {}
    shop_host = urlparse(str(entry.get("shopUrl") or "")).netloc.lower()
    buy_entry = bool(
        (entry.get("miniProgram") and entry["miniProgram"].lower() in low)
        or (shop_host and (shop_host in low or any(shop_host in r["url"].lower() for r in refs)))
    )
    return {"mentioned": first_pos(low, aliases) >= 0, "refs": refs, "buyEntry": buy_entry, "text": text}


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
    reading, related_ok = load_reading(date), load_related()
    cells, answers = {}, {}
    mention = {"hits": 0, "valid": 0, "byProvider": {}, "byQuestion": {}}
    for provider in gc.PROVIDERS:
        mention["byProvider"][provider] = {"hits": 0, "valid": 0}
    eligible = {}  # 要读的回答：顾客没点名的。编号 → (正文, 平台)
    cited = []  # 每条引用：(平台, 类型, 网站名)
    related = {"own": {}, "store": {}, "about": {}}
    related_count = Counter()
    buy_entry = {"count": 0, "valid": 0}
    brand_answers = 0
    missing, not_us = [], []
    for key, item in sorted(run["state"]["items"].items()):
        qid, provider = item["qid"], item["provider"]
        kind = kinds.get(qid, item["kind"])
        rows = [analyse_answer(a, profile, aliases, related_ok) for a in run["raw"][key]]
        cell = {"status": item["status"], "answers": len(rows), "valid": len(rows), "hits": 0}
        if not rows:
            missing.append(key)
        for index, row in enumerate(rows, 1):
            tag = "%s#%d" % (key, index)
            # 员工复核过：脚本算作提到你，其实说的是同名的别的店或别的东西
            if row["mentioned"] and reading["notUs"].get(tag) == _digest_hash(row["text"]):
                row["mentioned"] = False
                not_us.append(tag)
            cell["hits"] += int(row["mentioned"])
            buy_entry["valid"] += 1
            buy_entry["count"] += int(row["buyEntry"])
            if kind == "brand":
                brand_answers += 1
            else:
                eligible[tag] = (row["text"], provider)
            for ref in row["refs"]:
                cited.append((provider, ref["type"], ref["site"]))
                if ref["relation"]:
                    related_count[ref["relation"]] += 1
                    entry = related[ref["relation"]].setdefault(ref["url"] or ref["title"], dict(ref, usedIn=[]))
                    if tag not in entry["usedIn"]:
                        entry["usedIn"].append(tag)
        cells.setdefault(qid, {})[provider] = cell
        answers[key] = [{"mentioned": r["mentioned"], "buyEntry": r["buyEntry"],
                         "refInfo": [[ref["type"], ref["relation"]] for ref in r["refs"]]} for r in rows]
        if kind == "open":
            for bucket in (mention, mention["byProvider"][provider], mention["byQuestion"].setdefault(qid, {"hits": 0, "valid": 0})):
                bucket["hits"] += cell["hits"]
                bucket["valid"] += cell["valid"]
    # 对照表里没有的网站，被引用够多的单独成一行，其余的算“其他网站”
    sites = Counter(site for _, kind, site in cited if kind == OTHER_SITE)
    src_all, src_by_provider = Counter(), {p: Counter() for p in gc.PROVIDERS}
    for provider, kind, site in cited:
        label = site if kind == OTHER_SITE and sites[site] >= SITE_SHOWN_FROM else kind
        src_all[label] += 1
        src_by_provider[provider][label] += 1
    expected = len(run["state"]["items"])
    shops, pending = count_shops(reading, eligible, profile["rivals"])
    findings, dropped_findings = load_findings(date, run)
    shop_counts = {s["name"]: s for s in shops}
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
        # 员工复核后，不算“提到你”的回答
        "notUs": not_us,
        "brandAnswers": brand_answers,
        "refs": {
            "total": len(cited),
            "own": related_count["own"],
            "storePages": related_count["store"],
            "aboutStore": related_count["about"],
            "ownItems": list(related["own"].values())[:20],
            "storePageItems": list(related["store"].values())[:20],
            "aboutItems": list(related["about"].values())[:30],
        },
        "sources": {
            "all": _ratio(src_all, len(cited)),
            "byProvider": {p: _ratio(c, sum(c.values()), 6) for p, c in src_by_provider.items()},
        },
        # 同类店各几次：和“提到了谁”用同一份员工读出来的店名，口径一致；还没读完时都是 0
        "rivals": sorted(({"name": r["name"], "count": shop_counts.get(r["name"], {}).get("count", 0) if not pending else 0,
                           "byProvider": shop_counts.get(r["name"], {}).get("byProvider", {}) if not pending else {}}
                          for r in profile["rivals"]), key=lambda r: -r["count"]),
        "buyEntry": buy_entry if facts["segment"] == "ecom" else None,
        # 顾客没点名时 AI 推荐的所有店，按出现在几个回答里排序。报告“提到了谁”列的就是它。
        # 店名是员工读全文后写回的；还有回答没读（shopsPending）时不出数
        "shops": shops[:SHOPS_SHOWN] if not pending else [],
        "shopsPending": pending,
        "findings": findings,
        "findingsDropped": dropped_findings,
        # 还不是同类店、出现在两个以上回答里的，供第一次体检后挑同类店
        "candidates": [{"name": s["name"], "answers": s["count"]} for s in shops if not s["rival"] and s["count"] >= 2][:25],
    }
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
    items = list(((gc.read_json(gc.run_dir(date) / "queries.json", {}) or {}).get("items") or {}).values())
    summary["askedUpTo"] = gc.last_asked_at(items)  # 之后又重问了题，status 会提醒重新算分
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
        "notUs": summary["notUs"],
        "refs": {k: summary["refs"][k] for k in ("total", "own", "storePages", "aboutStore")},
        # 每个平台各自最常读哪里，和报告“读哪里的内容”一节是同一份数。不给几个平台合起来的数：
        # 各平台读的地方差别很大，合起来看会把元宝读公众号的次数算到 DeepSeek 头上。
        "sourcesByProvider": sources_by_provider(summary),
        "rivals": [{"name": r["name"], "count": r["count"]} for r in summary["rivals"]],
        "shops": [{"name": s["name"], "count": s["count"]} for s in summary["shops"]],
        "buyEntry": summary["buyEntry"],
        "notes": [],
    }
    if dropped:
        digest["notes"].append("这几道题已经从问题清单里删掉，这一期不再算：" + "、".join(dropped))
    if not summary["complete"]:
        digest["notes"].append("本轮缺失的查询超过四分之一，周报要注明“本周数据不全”")
    if summary["notUs"]:
        digest["notes"].append("有 %d 个回答提到的同名不是本店，已经不算“提到你”" % len(summary["notUs"]))
    if summary["shopsPending"]:
        # 还有回答没读：先读全文，写回店名和发现，再往下走
        pending_q = sorted({t.split("_")[0] for t in summary["shopsPending"]})
        open_q = sorted({q["id"] for q in load_profile()["questions"] if q["kind"] == "open"})
        scope = "读全部题" if pending_q == open_q else "只读这几道题：" + ",".join(pending_q)
        digest["next"] = ("还有 %d 个回答没读过。按 geo-check 的“第三步：读全文”读（%s；默认一个平台派一个子 Agent），"
                          "用 set-reading 写回、set-findings 写回发现，然后重新执行 score" % (len(summary["shopsPending"]), scope))
    elif not summary["rivals"]:
        digest["candidates"] = summary["candidates"]
        if summary["candidates"]:
            # 同类店没定，报告里“提到了谁”就是空的。先定同类店再往下走，next 和 notes 说的是同一件事
            digest["next"] = ("同类店还没定：从 candidates 里挑 3 家和本店同品类、同区域的店，"
                              "带上常见的别名，用 geo-profile 技能里的 geo_state.py set-rivals 保存，然后重新执行 score")
            digest["notes"].append("同类店还没定，先按 next 选好同类店，再重新执行 score")
        else:
            digest["notes"].append("AI 的回答里没有提到别的店，这一期先不选同类店")
    digest["shopsPending"] = len(summary["shopsPending"])
    digest["findings"] = len(summary["findings"])
    if summary["findingsDropped"]:
        digest["notes"].append("这几条发现的原文证据在重跑后的回答里找不到了，已经去掉：" + "、".join(summary["findingsDropped"]))
    digest.setdefault("next", "请执行 brand-digest，读完后用 set-judgement 写回 AI 怎么介绍本店；有和店铺资料对不上的说法才写进 issues，没有就传空数组")
    gc.emit(digest)


def cmd_answers(args) -> None:
    date = gc.resolve_date(args.date)
    profile = load_profile()
    run = load_run(date)
    only = {q.strip().lower() for q in args.only.split(",") if q.strip()}
    related = load_related()
    rows = []
    for tag, info in _answer_index(run, profile).items():
        if info["provider"] != args.provider or (only and info["qid"] not in only):
            continue
        rows.append({
            "answer": tag,
            "question": info["question"],
            "withBrandName": not info["open"],
            # 要写回店名的回答：顾客没点名的。带店名的回答只用来找发现
            "listShops": info["open"],
            # 脚本按名字算作“提到了你”的回答：要确认说的真是这家店，不是同名的别的店或别的东西
            "mentionedByName": info["open"] and info["mentioned"],
            "text": info["text"],
            # relation：脚本按标题有没有店名判断的，和这家店的关系（own 本店账号、store 门店页、about 别人写本店；空的是无关）
            "refs": [{"no": r.get("no"), "title": gc.clean_title(r.get("title"))[:80], "source": gc.clean_text(r.get("source"))[:30],
                      "url": str(r.get("url") or "")[:300],
                      "relation": classify_ref(r, profile["facts"], gc.brand_aliases(profile["facts"]), related)["relation"]}
                     for r in info["refs"][:20]],
        })
    gc.emit({
        "ok": True, "date": date, "provider": args.provider, "platform": gc.PROVIDER_NAMES[args.provider],
        "store": {"name": profile["facts"]["brand"]["name"], "aliases": gc.brand_aliases(profile["facts"]),
                  "category": profile["facts"]["brand"].get("category", ""), "city": profile["facts"]["brand"].get("city", ""),
                  "edges": profile["facts"].get("edges") or []},
        "rivals": [{"name": r["name"], "aliases": r.get("aliases") or []} for r in profile["rivals"]],
        "answers": rows,
    })


def cmd_set_reading(args) -> None:
    date = gc.resolve_date(args.date)
    profile = load_profile()
    run = load_run(date)
    index = _answer_index(run, profile)
    own = gc.brand_aliases(profile["facts"])
    saved = load_reading(date)
    names, answers, not_us = dict(saved["names"]), dict(saved["answers"]), dict(saved["notUs"])
    related = load_related()
    urls = {str(r.get("url") or "") for info in index.values() for r in info["refs"]} - {""}
    incoming, errors = {}, []
    for file in args.file:
        raw = gc.load_input(file)
        if not isinstance(raw, dict):
            raise gc.GeoError(file + "：应为一个对象")
        for name, spellings in (raw.get("names") or {}).items():
            name = gc.clean_text(name)[:30]
            names[name] = sorted({gc.clean_text(x)[:40] for x in (names.get(name) or []) + list(spellings or []) if gc.clean_text(x)})
        incoming.update(raw.get("answers") or {})
        for tag in raw.get("notUs") or []:
            info = index.get(tag)
            if not info or not info["open"] or not info["mentioned"]:
                errors.append(tag + "：不是脚本算作“提到你”的没点名回答，不用写进 notUs")
            else:
                not_us[tag] = _digest_hash(info["text"])
        for key in ("refsNotUs", "refsAboutUs"):
            for url in raw.get(key) or []:
                if url not in urls:
                    errors.append("这一期没有这条引用：" + str(url)[:80])
                else:
                    target, other = ("notUs", "aboutUs") if key == "refsNotUs" else ("aboutUs", "notUs")
                    related[target].add(url)
                    related[other].discard(url)
    for tag, shops in incoming.items():
        info = index.get(tag)
        if not info:
            errors.append(tag + "：没有这个回答")
            continue
        if not info["open"]:
            errors.append(tag + "：带店名问的回答不用写店名")
            continue
        clean = []
        for name in shops or []:
            name = gc.clean_text(name)[:30]
            if len(name) < 2:
                continue
            if gc.contains_any(name, own):
                errors.append(tag + "：“" + name + "”是本店，不写进来")
                continue
            if not any(_norm(x) in _norm(info["text"]) for x in [name] + (names.get(name) or [])):
                errors.append(tag + "：原文里找不到“" + name + "”，原文的写法不一样时，在 names 里写上原文的写法")
                continue
            if name not in clean:
                clean.append(name)
        answers[tag] = {"hash": _digest_hash(info["text"]), "shops": clean}
    if errors:
        raise gc.GeoError("有 %d 处对不上，整份没有保存：%s" % (len(errors), "；".join(errors[:12])))
    gc.write_json(gc.run_dir(date) / READING_FILE, {"updatedAt": gc.now_iso(), "names": names, "answers": answers, "notUs": not_us})
    gc.write_json(gc.profile_dir() / RELATED_FILE, {"updatedAt": gc.now_iso(), "notUs": sorted(related["notUs"]), "aboutUs": sorted(related["aboutUs"])})
    eligible = [t for t, i in index.items() if i["open"]]
    missing = [t for t in eligible if t not in answers or answers[t]["hash"] != _digest_hash(index[t]["text"])]
    gc.emit({"ok": True, "date": date, "saved": len(incoming), "toRead": len(eligible), "stillMissing": missing[:30],
             "next": ("还有 %d 个回答没写店名，补齐后再执行 score" % len(missing)) if missing
             else "都写齐了。请重新执行 geo_score.py score"})


def cmd_set_findings(args) -> None:
    date = gc.resolve_date(args.date)
    profile = load_profile()
    run = load_run(date)
    index = _answer_index(run, profile)
    raw = gc.load_input(args.file)
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise gc.GeoError("发现应为一个列表")
    if len(items) > FINDINGS_CAP:
        raise gc.GeoError("发现最多 %d 条，宁缺毋滥。只留最值得商家知道的" % FINDINGS_CAP)
    out, errors = [], []
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append("第 %d 条格式不对" % number)
            continue
        kind = item.get("kind") if item.get("kind") in FINDING_KINDS else "other"
        title, detail, action = (gc.clean_text(item.get(k)) for k in ("title", "detail", "action"))
        if not 4 <= len(title) <= 40:
            errors.append("第 %d 条：标题要 4 到 40 个字" % number)
        if not 10 <= len(detail) <= 240:
            errors.append("第 %d 条：说明要 10 到 240 个字" % number)
        if len(action) > 120:
            errors.append("第 %d 条：可以怎么做最多 120 个字" % number)
        evidence = []
        for e in (item.get("evidence") or [])[:4]:
            tag, quote = gc.clean_text((e or {}).get("answer")), gc.clean_text((e or {}).get("quote"))
            info = index.get(tag)
            if not info:
                errors.append("第 %d 条：没有回答 %s" % (number, tag))
            elif not 4 <= len(quote) <= 120 or _norm(quote) not in _norm(info["text"]):
                errors.append("第 %d 条：%s 里找不到这句原话：%s" % (number, tag, quote[:40]))
            else:
                evidence.append({"answer": tag, "quote": quote, "provider": info["provider"], "qid": info["qid"]})
        if not evidence:
            errors.append("第 %d 条：至少要有一句能在回答原文里找到的原话" % number)
        out.append({"kind": kind, "kindName": FINDING_KINDS[kind], "title": title, "detail": detail, "action": action,
                    "evidence": evidence})
    if errors:
        raise gc.GeoError("有 %d 处不对，整份没有保存：%s" % (len(errors), "；".join(errors[:12])))
    gc.write_json(gc.run_dir(date) / "findings.json", {"updatedAt": gc.now_iso(), "items": out})
    summary_path = gc.run_dir(date) / "summary.json"
    summary = gc.read_json(summary_path)
    if summary:
        summary["findings"], summary["findingsDropped"] = load_findings(date, run)
        gc.write_json(summary_path, summary)
    gc.mark_changed("这一期的发现")
    gc.emit({"ok": True, "date": date, "findings": len(out), "next": gc.sync_hint() or "已保存，同步时会放进这一期的报告"})


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
    p = sub.add_parser("answers")
    p.add_argument("--provider", required=True, choices=gc.PROVIDERS)
    p.add_argument("--only", default="")
    p.add_argument("--date", default="")
    p.set_defaults(func=cmd_answers)
    p = sub.add_parser("set-reading")
    p.add_argument("--file", required=True, action="append")
    p.add_argument("--date", default="")
    p.set_defaults(func=cmd_set_reading)
    p = sub.add_parser("set-findings")
    p.add_argument("--file", required=True)
    p.add_argument("--date", default="")
    p.set_defaults(func=cmd_set_findings)
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
