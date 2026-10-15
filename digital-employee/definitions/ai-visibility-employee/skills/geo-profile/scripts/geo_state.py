#!/usr/bin/env python3
"""店铺资料和监测设置的读写和校验：店铺资料、问题、同类店、已有的内容。

店铺资料是员工核对和写内容的底稿，不在工作台上展示；差异点、问题、同类店和
员工另外记下的几样信息，显示在工作台的“监测设置”页。

用法（脚本用绝对路径执行，入参写成 JSON 文件后用 --file 传入）：
  geo_state.py status
  geo_state.py init --segment local|ecom --brand <店名>
  geo_state.py show [--part facts|questions|rivals|all]
  geo_state.py set-facts --file <json> [--confirmed-by-merchant] [--replace]
  geo_state.py set-questions --file <json>
  geo_state.py set-rivals --file <json>
  geo_state.py confirm
  geo_state.py confirm-monitoring
  geo_state.py set-schedule --status on|declined|off|unavailable
"""
from __future__ import annotations

import argparse
import re
import sys

sys.dont_write_bytecode = True  # 技能目录只读，不往里写缓存

import geo_common as gc  # noqa: E402

STORE_STATUS = ("在营", "已搬迁", "已关闭")
OPEN_RANGE = (6, 12)
BRAND_RANGE = (1, 3)
RECOMMENDED = (10, 2)
# 店铺资料里几样列表最多记多少条。超出的不记，并在输出里告诉员工，不悄悄丢掉
FACTS_CAPS = {"stores": 200, "products": 50, "edges": 3}
RIVALS_CAP = 5


def _capped(raw: dict, key: str, dropped: list) -> list:
    items = raw.get(key) or []
    if len(items) > FACTS_CAPS[key]:
        dropped.append("%s 传了 %d 条，只记了前 %d 条" % (key, len(items), FACTS_CAPS[key]))
    return items[:FACTS_CAPS[key]]


def _text(value, limit: int) -> str:
    return gc.clean_text(value)[:limit]


def _text_list(value, limit_items: int, limit_chars: int) -> list:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise gc.GeoError("列表字段的格式不对")
    out = []
    for item in value[:limit_items]:
        text = _text(item, limit_chars)
        if text and text not in out:
            out.append(text)
    return out


def _host(value) -> str:
    host = re.sub(r"^[a-z]+://", "", gc.clean_text(value).lower()).split("/")[0]
    return host if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", host) else ""


def normalize_facts(raw: dict, dropped: list | None = None) -> dict:
    """dropped：传一个列表进来，超出上限没记的部分写在里面。"""
    dropped = [] if dropped is None else dropped
    if not isinstance(raw, dict):
        raise gc.GeoError("店铺资料应为一个对象")
    segment = raw.get("segment")
    if segment not in gc.SEGMENTS:
        raise gc.GeoError("segment 只能是 local（本地门店）或 ecom（电商）")
    brand_raw = raw.get("brand") or {}
    name = _text(brand_raw.get("name"), 40)
    if len(name) < 2:
        raise gc.GeoError("店铺资料缺少店名")
    stores = []
    for item in _capped(raw, "stores", dropped):
        if not isinstance(item, dict):
            continue
        status = item.get("status") if item.get("status") in STORE_STATUS else "在营"
        store = {
            "name": _text(item.get("name"), 40),
            "address": _text(item.get("address"), 120),
            "hours": _text(item.get("hours"), 60),
            "phone": _text(item.get("phone"), 30),
            "status": status,
            "source": _text(item.get("source"), 20),
        }
        if store["name"] or store["address"]:
            stores.append(store)
    products = []
    for item in _capped(raw, "products", dropped):
        if not isinstance(item, dict):
            continue
        product = {
            "name": _text(item.get("name"), 40),
            "spec": _text(item.get("spec"), 40),
            "priceRange": _text(item.get("priceRange"), 30),
            "origin": _text(item.get("origin"), 30),
        }
        if product["name"]:
            products.append(product)
    edges = []
    for item in _capped(raw, "edges", dropped):
        if not isinstance(item, dict):
            continue
        edge = {"text": _text(item.get("text"), 30), "basis": _text(item.get("basis"), 40)}
        if edge["text"] and edge["text"] not in [e["text"] for e in edges]:
            edges.append(edge)
    entry = raw.get("buyEntry") or {}
    channels = raw.get("channels") or {}
    rules = raw.get("writingRules") or {}
    return {
        "segment": segment,
        # 资料从哪来：backend 是从店铺后台读的，以后台为准，不用商家再确认；public 是从公开信息整理的，要商家看过才算数。
        "from": raw.get("from") if raw.get("from") in ("backend", "public") else "public",
        "brand": {
            "name": name,
            "aliases": [a for a in _text_list(brand_raw.get("aliases"), 8, 40) if a != name],
            "category": _text(brand_raw.get("category"), 30),
            "city": _text(brand_raw.get("city"), 20),
        },
        # 和同类店不一样的地方。不带店名的问题要挂在这上面出，才有机会赢。
        "edges": edges,
        "stores": stores,
        "products": products,
        "buyEntry": {
            "miniProgram": _text(entry.get("miniProgram"), 40),
            "shopUrl": _text(entry.get("shopUrl"), 200),
        },
        "channels": {
            "wechatOfficial": _text(channels.get("wechatOfficial"), 40),
            "douyin": _text(channels.get("douyin"), 40),
            "ownHosts": [h for h in (_host(v) for v in (channels.get("ownHosts") or [])[:5]) if h],
            # 本店账号发过的内容的编号（如抖音作品编号），用来认出“AI 引用的是你自己发的内容”。
            "ownContentKeys": [k for k in _text_list(channels.get("ownContentKeys"), 200, 64) if len(k) >= 8],
        },
        "writingRules": {
            "tone": _text(rules.get("tone"), 100),
            "bannedWords": _text_list(rules.get("bannedWords"), 30, 20),
            "mustInclude": _text_list(rules.get("mustInclude"), 10, 60),
        },
    }


# 这几项是对象：只传其中几个字段时，没传的字段保持原样。
MERGED_OBJECTS = ("brand", "buyEntry", "channels", "writingRules")


def _is_backend_store(store) -> bool:
    return isinstance(store, dict) and "有赞后台" in str(store.get("source") or "")


def _filled(value) -> bool:
    return bool(value) if not isinstance(value, dict) else any(_filled(v) for v in value.values())


def merge_facts(current: dict, raw) -> tuple:
    """把这次传来的资料合进现有的资料，返回 (合并后的资料, 原样保留下来的字段)。

    每周从店铺后台重读时，员工通常只传后台里读得到的那几样。整份覆盖会把员工另外记下的
    别名、公众号、抖音作品编号、顾客类型、写作要求悄悄清空，所以默认合并：
      - 没传的字段保持原样；传了的字段（包括传空值）以这次为准；
      - brand、buyEntry、channels、writingRules 按字段合并；
      - stores 里如果全是后台的门店，员工另外记下的门店（来源不是“有赞后台”）保留；
        传了非后台的门店，就以这次传的整份门店为准。
    """
    if not isinstance(raw, dict):
        raise gc.GeoError("店铺资料应为一个对象")
    merged, kept = dict(current), []
    for key, value in current.items():
        if key not in raw and _filled(value):
            kept.append(key)
    for key, value in raw.items():
        old = current.get(key)
        if key in MERGED_OBJECTS and isinstance(value, dict) and isinstance(old, dict):
            kept += ["%s.%s" % (key, sub) for sub, before in old.items() if sub not in value and _filled(before)]
            merged[key] = dict(old, **value)
        elif key == "stores" and isinstance(value, list) and all(_is_backend_store(s) for s in value):
            extra = [s for s in old or [] if not _is_backend_store(s)]
            if extra:
                kept.append("stores（后台以外的 %d 家）" % len(extra))
            merged[key] = list(value) + extra
        else:
            merged[key] = value
    return merged, kept


def facts_warnings(facts: dict) -> list:
    warnings = []
    open_stores = [s for s in facts["stores"] if s["status"] == "在营" and s["address"]]
    if facts["segment"] == "local" and not open_stores:
        warnings.append("本地门店版至少要有一家带地址的在营门店，否则没法比对 AI 说的地址")
    if facts["segment"] == "ecom" and not (facts["buyEntry"]["miniProgram"] or facts["buyEntry"]["shopUrl"]):
        warnings.append("电商版缺少购买入口（小程序名或店铺链接），没法统计 AI 有没有给出下单的地方")
    if facts["segment"] == "ecom" and not facts["products"]:
        warnings.append("电商版缺少核心商品，没法比对 AI 说的价格和规格")
    if not facts.get("edges"):
        warnings.append("还没有写这家店和同类店不一样在哪，问题容易出成同类店都能答的题；请按 geo-profile 第 2 步先写 1 到 3 条")
    return warnings


def normalize_questions(raw, facts: dict) -> list:
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise gc.GeoError("问题库应为一个列表")
    names = gc.brand_aliases(facts)
    out, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise gc.GeoError("问题库里有格式不对的条目")
        qid = gc.clean_text(item.get("id")).lower()
        kind = item.get("kind")
        text = gc.clean_text(item.get("text"))
        if kind not in ("open", "brand"):
            raise gc.GeoError(qid + "：kind 只能是 open（不带店名）或 brand（带店名）")
        if not re.match(r"^q\d{2}$" if kind == "open" else r"^b\d{2}$", qid):
            raise gc.GeoError("问题编号不对：不带店名的用 q01 这种，带店名的用 b01 这种")
        if qid in seen:
            raise gc.GeoError("问题编号重复：" + qid)
        if not 6 <= len(text) <= 60:
            raise gc.GeoError(qid + "：问题长度应在 6 到 60 个字之间")
        mentioned = gc.contains_any(text, names)
        if kind == "open" and mentioned:
            raise gc.GeoError(qid + "：不带店名的问题里出现了店名，会让结果虚高")
        if kind == "brand" and not mentioned:
            raise gc.GeoError(qid + "：带店名的问题里没有出现店名")
        seen.add(qid)
        person = _text(item.get("audience"), 12)
        out.append({"id": qid, "kind": kind, "tag": _text(item.get("tag"), 8), "text": text,
                    "audience": person, "worry": _text(item.get("worry"), 30)})
    n_open = sum(1 for q in out if q["kind"] == "open")
    n_brand = len(out) - n_open
    if not OPEN_RANGE[0] <= n_open <= OPEN_RANGE[1]:
        raise gc.GeoError("不带店名的问题应有 %d 到 %d 个，建议 %d 个" % (OPEN_RANGE + (RECOMMENDED[0],)))
    if not BRAND_RANGE[0] <= n_brand <= BRAND_RANGE[1]:
        raise gc.GeoError("带店名的问题应有 %d 到 %d 个，建议 %d 个" % (BRAND_RANGE + (RECOMMENDED[1],)))
    return sorted(out, key=lambda q: (q["kind"] != "open", q["id"]))


def question_warnings(items: list) -> list:
    """出题时漏写的地方：哪道题没写替谁问。只提醒，不拦。"""
    unassigned = [q["id"].upper() for q in items if q["kind"] == "open" and not q["audience"]]
    if unassigned:
        return ["这几道题没写替谁问：" + "、".join(unassigned)]
    return []


def normalize_rivals(raw, facts: dict) -> list:
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise gc.GeoError("竞品应为一个列表")
    if len(items) > RIVALS_CAP:
        raise gc.GeoError("同类店最多 %d 家，现在传了 %d 家。挑和这家店最像、商家最在意的 %d 家" % (RIVALS_CAP, len(items), RIVALS_CAP))
    own = gc.brand_aliases(facts)
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 40)
        if len(name) < 2 or gc.contains_any(name, own):
            continue
        aliases = [a for a in _text_list(item.get("aliases"), 6, 40) if a != name]
        out.append({"name": name, "aliases": aliases})
    return out


def _paths() -> dict:
    root = gc.profile_dir()
    return {name: root / (name + ".json") for name in ("facts", "questions", "rivals", "meta")}


def _load() -> dict:
    paths = _paths()
    return {name: gc.read_json(path) for name, path in paths.items()}


def _require_facts() -> dict:
    facts = gc.read_json(_paths()["facts"])
    if not facts:
        raise gc.GeoError("还没有建档，请先执行 init")
    return facts


def _touch_meta(**changes) -> dict:
    path = _paths()["meta"]
    meta = gc.read_json(path, {}) or {}
    meta.setdefault("createdAt", gc.now_iso())
    meta.setdefault("confirmedAt", "")
    meta.setdefault("pageUrl", "")
    meta.update(changes)
    gc.write_json(path, meta)
    return meta


def status_payload() -> dict:
    data = _load()
    facts, meta = data["facts"], data["meta"] or {}
    if not facts:
        return {"ok": True, "exists": False, "next": "还没有建档，请按 geo-profile 的步骤建档"}
    questions = (data["questions"] or {}).get("items") or []
    last_run = gc.latest_run_date()
    workbench = gc.workbench_state()
    hint = gc.sync_hint(workbench)
    state = gc.confirm_state(facts, meta)
    payload = {
        "ok": True,
        "exists": True,
        "segment": facts["segment"],
        "segmentName": gc.SEGMENT_NAMES[facts["segment"]],
        "brand": facts["brand"]["name"],
        "confirmed": bool(meta.get("confirmedAt")),
        "confirmedAt": meta.get("confirmedAt", ""),
        "firstCheckPending": bool(meta.get("firstCheckPending")),
        # 资料从哪来（backend 店铺后台 / public 公开信息）、有没有等商家确认的、现在能不能替商家写内容
        "factsFrom": state["from"],
        "pendingConfirm": state["pending"],
        # 等商家确认的具体是哪几样（你推断的别名、从别处看到的旧门店）。请他确认时点出来，这些也不能写进内容。
        "toConfirm": gc.needs_confirm(facts) if state["pending"] else {},
        "canWrite": state["canWrite"],
        "openQuestions": sum(1 for q in questions if q["kind"] == "open"),
        "brandQuestions": sum(1 for q in questions if q["kind"] == "brand"),
        "questionsVersion": (data["questions"] or {}).get("version", 0),
        "rivals": [r["name"] for r in (data["rivals"] or {}).get("items") or []],
        "lastRun": last_run,
        # 最近一期做到哪了：stage 为 done 才算这一期做完。会话中途断掉，按这里的 next 回到没做完的那一步
        "period": gc.period_stage(last_run) if last_run else {},
        "pageUrl": meta.get("pageUrl", ""),
        # 工作台是不是最新的。pending 不为空时，先同步再把链接发给商家。
        "workbench": workbench,
        # 每周定时体检：on 已开启，declined 商家说先不开，off 商家让关掉，unavailable 当前环境开不了，空的是还没问过
        "schedule": (meta.get("schedule") or {}).get("status", ""),
        # 官网（商家要了才有）：到了哪一步、有没有跟上店铺资料。outdated 为 true 时按 geo-site 提醒商家更新
        "site": gc.site_state(facts, meta),
        "warnings": facts_warnings(facts),
    }
    period = payload["period"]
    if period and not period["done"]:
        # 体检做到一半：先把这一期做完。工作台待同步也不用急，这一期做完 publish 时一起同步
        payload["next"] = "最近一期（%s）还没做完。%s" % (period["date"], period["next"]) + ("。另外，" + hint if hint else "")
    elif hint:
        payload["next"] = hint
    elif last_run and not payload["schedule"]:
        payload["next"] = "第一份报告出来了，还没问过商家要不要开启每周体检；按 geo-weekly 的“开启每周体检”问他一次"
    return payload


def cmd_status(_args) -> None:
    gc.emit(status_payload())


def cmd_init(args) -> None:
    paths = _paths()
    if gc.read_json(paths["facts"]):
        payload = status_payload()
        payload["note"] = "已经建过档，没有改动"
        gc.emit(payload)
        return
    facts = normalize_facts({"segment": args.segment, "brand": {"name": args.brand}})
    gc.write_json(paths["facts"], facts)
    gc.write_json(paths["questions"], {"version": 0, "updatedAt": "", "items": []})
    gc.write_json(paths["rivals"], {"updatedAt": "", "items": []})
    _touch_meta(firstCheckPending=True)
    gc.mark_changed("店铺资料")
    gc.emit(status_payload())


def cmd_show(args) -> None:
    data = _load()
    if not data["facts"]:
        raise gc.GeoError("还没有建档，请先执行 init")
    parts = ("facts", "questions", "rivals", "meta") if args.part == "all" else (args.part,)
    payload = {"ok": True}
    for part in parts:
        payload[part] = data[part]
    gc.emit(payload)


def cmd_set_facts(args) -> None:
    current = _require_facts()
    raw = gc.load_input(args.file)
    dropped = []
    if args.replace:
        if isinstance(raw, dict):
            raw.setdefault("segment", current.get("segment"))
        facts, kept = normalize_facts(raw, dropped), []
    else:
        merged, kept = merge_facts(current, raw)
        facts = normalize_facts(merged, dropped)
    changed = facts != current
    gc.write_json(_paths()["facts"], facts)
    if changed:
        # 商家亲口要求的修改视为已确认。员工自己改的：只有“要商家确认的那部分”变了才重新确认，
        # 每期从店铺后台重读带来的变化（营业时间改了、多了一家店）不用商家再确认。
        updates = {"factsUpdatedAt": gc.now_iso()}
        if args.confirmed_by_merchant:
            updates["confirmedAt"] = gc.now_iso()
        elif gc.needs_confirm(facts) != gc.needs_confirm(current):
            updates["confirmedAt"] = ""
        _touch_meta(**updates)
        gc.mark_changed("店铺资料")
    payload = status_payload()
    payload["changed"] = changed
    if kept:
        # 这次没传、原样保留下来的字段。要删掉其中某一项，就在入参里把它传成空值
        payload["kept"] = kept
    if "from" not in raw and not args.replace and current.get("from") != "backend" and facts["from"] != "backend":
        payload["warnings"].append("资料里没有写 from：从店铺后台读到的资料要写 \"from\": \"backend\"，"
                                   "否则会当成从公开信息整理的，商家确认之前不能替他写内容")
    for text in dropped:
        payload["warnings"].append("超出上限没有记：%s。挑最重要的传，或者告诉维护的人调 FACTS_CAPS" % text)
    gc.emit(payload)


def cmd_set_questions(args) -> None:
    facts = _require_facts()
    items = normalize_questions(gc.load_input(args.file), facts)
    path = _paths()["questions"]
    current = gc.read_json(path, {}) or {}
    previous = current.get("items") or []
    changed = items != previous
    # 只有问题本身变了才算口径变化；只改“替谁问”这类标注不重置基线。
    core = lambda rows: [(q["id"], q["kind"], q["text"]) for q in rows]  # noqa: E731
    core_changed = core(items) != core(previous)
    if changed:
        version = int(current.get("version") or 0) + (1 if core_changed else 0)
        gc.write_json(path, {"version": max(version, 1), "updatedAt": gc.now_iso(), "items": items})
        if core_changed and gc.latest_run_date():
            # 问题库变了，之前的数字不能和之后的连成一条线。
            _touch_meta(baselineResetAt=gc.today())
        gc.mark_changed("问题库")
    payload = status_payload()
    payload["changed"] = changed
    n_open, n_brand = payload["openQuestions"], payload["brandQuestions"]
    if (n_open, n_brand) != RECOMMENDED:
        payload["warnings"].append("建议用 %d 个不带店名加 %d 个带店名的问题，现在是 %d 加 %d" % (RECOMMENDED + (n_open, n_brand)))
    payload["warnings"].extend(question_warnings(items))
    gc.emit(payload)


def cmd_set_rivals(args) -> None:
    facts = _require_facts()
    items = normalize_rivals(gc.load_input(args.file), facts)
    gc.write_json(_paths()["rivals"], {"updatedAt": gc.now_iso(), "items": items})
    gc.mark_changed("同类店")
    payload = status_payload()
    if gc.latest_run_date():
        payload["next"] = "同类店已保存。已经体检过的话，请重新执行 geo_score.py score，再执行 " + gc.PUBLISH_COMMAND
    gc.emit(payload)


def cmd_confirm(_args) -> None:
    facts = _require_facts()
    questions = (gc.read_json(_paths()["questions"], {}) or {}).get("items") or []
    if not questions:
        raise gc.GeoError("问题库还是空的，不能确认")
    _touch_meta(confirmedAt=gc.now_iso(), firstCheckPending=False)
    gc.mark_changed("商家的确认")
    payload = status_payload()
    payload["warnings"] = facts_warnings(facts)
    gc.emit(payload)


def cmd_confirm_monitoring(_args) -> None:
    _require_facts()
    if not (gc.read_json(_paths()["questions"], {}) or {}).get("items"):
        raise gc.GeoError("问题库还是空的，不能确认监测方向")
    _touch_meta(firstCheckPending=False)
    gc.emit(status_payload())


def cmd_set_schedule(args) -> None:
    _require_facts()
    if args.status == "on" and (_load()["meta"] or {}).get("firstCheckPending"):
        raise gc.GeoError("商家还没确认监测方向，不能开启每周体检")
    _touch_meta(schedule={"status": args.status, "at": gc.now_iso()})
    gc.emit(status_payload())


def main() -> None:
    parser = argparse.ArgumentParser(description="店铺资料和监测设置")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p = sub.add_parser("init")
    p.add_argument("--segment", required=True, choices=gc.SEGMENTS)
    p.add_argument("--brand", required=True)
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("show")
    p.add_argument("--part", default="all", choices=("facts", "questions", "rivals", "meta", "all"))
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("set-facts")
    p.add_argument("--file", required=True)
    p.add_argument("--confirmed-by-merchant", action="store_true")
    p.add_argument("--replace", action="store_true")  # 整份覆盖：没传的字段全部清空。只在要从头重写资料时用
    p.set_defaults(func=cmd_set_facts)
    for name, func in (("set-questions", cmd_set_questions), ("set-rivals", cmd_set_rivals)):
        p = sub.add_parser(name)
        p.add_argument("--file", required=True)
        p.set_defaults(func=func)
    sub.add_parser("confirm").set_defaults(func=cmd_confirm)
    sub.add_parser("confirm-monitoring").set_defaults(func=cmd_confirm_monitoring)
    p = sub.add_parser("set-schedule")
    p.add_argument("--status", required=True, choices=("on", "declined", "off", "unavailable"))
    p.set_defaults(func=cmd_set_schedule)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    gc.run_cli(main)
