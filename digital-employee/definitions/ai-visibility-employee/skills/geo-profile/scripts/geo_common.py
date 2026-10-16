#!/usr/bin/env python3
"""AI 曝光专员几个技能共用的小工具：定位数据目录、读写 JSON、统一输出。

三个技能目录各放一份内容完全相同的副本。技能目录是互相独立安装的只读目录，
不能跨目录 import，所以用复制而不是共享；tests/run_tests.py 会校验三份一致。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path

EMPLOYEE_DIR = "ai-visibility-employee"
PAGE_FILE = "ai-visibility.html"

# 第一版固定测这三家。文心返回的正文缺字，千问和 Kimi 不返回引用来源，暂不测。
PROVIDERS = ("hunyuan", "doubao", "deepseek")
PROVIDER_NAMES = {"hunyuan": "元宝", "doubao": "豆包", "deepseek": "DeepSeek"}
ANSWERS_PER_QUERY = 2
SEGMENTS = ("local", "ecom")
SEGMENT_NAMES = {"local": "本地门店", "ecom": "电商"}

_BEIJING = dt.timezone(dt.timedelta(hours=8))
# 各平台正文里夹带的引用、图片、卡片占位符，展示和匹配前先去掉。
_ANSWER_MARKS = re.compile(r"\[\]\(@replace=\d+\)|\[citation:\d+\]|\[img:\d+\]|\[applet_-?\d+\]|\[rich_media:\d+\]|\u200b")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 一期体检的编号：当天的第一期就是日期，同一天再体检一次是 日期-2、日期-3……按字符串排序就是先后顺序（到 -9 为止）
_PERIOD_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-([2-9]))?$")


class GeoError(Exception):
    """可以直接转述给商家的业务错误。"""


def data_root() -> Path:
    """体检数据的根目录：<会话工作区>/ai-visibility-employee。"""
    override = os.environ.get("GEO_DATA_ROOT", "").strip()
    if override:
        return Path(override)
    workspace = os.environ.get("YOUZAN_AGENT_SESSION_WORKSPACE", "").strip()
    if not workspace:
        raise GeoError("当前环境没有可用的工作空间，暂时不能保存体检数据")
    return Path(workspace) / EMPLOYEE_DIR


def profile_dir() -> Path:
    return data_root() / "profile"


def runs_dir() -> Path:
    return data_root() / "runs"


def run_dir(date: str) -> Path:
    return runs_dir() / check_date(date)


def pages_dir() -> Path:
    return data_root() / "pages"


def now() -> dt.datetime:
    """容器时区不确定，日期一律按北京时间算。GEO_FAKE_NOW 只给测试和演示数据用。"""
    fake = os.environ.get("GEO_FAKE_NOW", "").strip()
    if fake:
        return dt.datetime.fromisoformat(fake)
    return dt.datetime.now(_BEIJING)


def today() -> str:
    return now().strftime("%Y-%m-%d")


def now_iso() -> str:
    return now().strftime("%Y-%m-%dT%H:%M:%S+08:00")


def parse_iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def check_date(value: str) -> str:
    """一期体检的编号：日期，同一天的第二期起是 日期-2 这样。"""
    if not _PERIOD_RE.match(str(value or "")):
        raise GeoError("期次应为 YYYY-MM-DD，同一天的第二期起是 YYYY-MM-DD-2 这样")
    return value


def period_day(period: str) -> str:
    """期次是哪一天做的。"""
    return period[:10]


def new_period(day: str = "") -> str:
    """开一期新的体检：这一天还没有体检就用日期，有了就排到下一个编号。"""
    day = day or today()
    taken = [p for p in list_run_dates() if period_day(p) == day]
    if not taken:
        return day
    number = max(int(_PERIOD_RE.match(p).group(2) or 1) for p in taken) + 1
    if number > 9:
        raise GeoError("同一天最多做 9 期体检")
    return "%s-%d" % (day, number)


def list_run_dates() -> list:
    """所有期次，按先后排。"""
    root = runs_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and _PERIOD_RE.match(p.name))


def latest_run_date(before: str = "") -> str:
    """最近一次体检的日期；传 before 时取它之前的最近一次。没有则返回空串。"""
    dates = [d for d in list_run_dates() if not before or d < before]
    return dates[-1] if dates else ""


def resolve_date(value: str = "") -> str:
    """命令没传期次时：用最近一期；一期都没有就用今天。"""
    if value:
        return check_date(value)
    dates = list_run_dates()
    return dates[-1] if dates else today()


PERIOD_STAGES = ("asking", "scoring", "reading", "judging", "wrapup", "done")


def period_stage(date: str) -> dict:
    """这一期做到哪了。会话中途断掉、隔天再来时，status 和 publish 靠它把员工带回没做完的那一步。

    asking 还在提问；scoring 还没算分；reading 还有回答没读全文；judging 还没核对；
    wrapup 还没写本期小结和建议（或者写在重新核对之前，已经过时）；done 这一期做完了。
    """
    folder = run_dir(date)
    items = list(((read_json(folder / "queries.json", {}) or {}).get("items") or {}).values())
    # 不带 --date 时，start 只接着做今天的最新一期（否则开新的一期），其余命令用最新一期。不是这种情况就把期次写明
    flag = "" if date == latest_run_date() and period_day(date) == today() else " --date " + date
    stage, hint = "done", ""
    phase_rows = {kind: [i for i in items if i.get("kind") == kind] for kind in ("open", "brand")}
    asked = {kind: [i for i in rows if i.get("status") != "error"] for kind, rows in phase_rows.items()}
    summary = read_json(folder / "summary.json") if (folder / "summary.json").is_file() else None
    judgement = folder / "judgement.json"
    actions = folder / "actions.json"
    if any(i.get("status") == "running" for i in items):
        stage, hint = "asking", "还有查询在运行：按 geo-check 执行 geo_run.py wait%s，等它们返回" % flag
    elif not asked["open"] and summary is None:
        stage, hint = "asking", "这一期还没有问成功：按 geo-check 执行 geo_run.py start --retry%s" % flag
    elif not phase_rows["brand"] and summary is None:
        stage, hint = "asking", "还有带店名的问题没问：按 geo-check 执行 geo_run.py start%s（已经问过的不会重复问）" % flag
    elif summary is None or _asked_after(items, summary):
        stage, hint = "scoring", "提问都返回了，还没算分（或者算分之后又重问过几道题）：按 geo-check 执行 geo_score.py score%s" % flag
    elif summary.get("shopsPending"):
        stage, hint = "reading", ("还有 %d 个回答没读全文：按 geo-check 的“第三步：读全文”读完、写回，再执行 geo_score.py score%s"
                                  % (len(summary["shopsPending"]), flag))
    elif not judgement.is_file():
        stage, hint = "judging", "还没核对 AI 怎么介绍这家店：按 geo-check 的“第四步”执行 geo_score.py brand-digest%s，再 set-judgement" % flag
    elif not actions.is_file() or actions.stat().st_mtime < judgement.stat().st_mtime:
        stage, hint = "wrapup", "体检做完了，还没写本期小结和建议（或者写在重新核对之前）：按 geo-weekly 收尾，再 publish"
    elif (read_json(actions, {}) or {}).get("basedOn", summary_fingerprint(summary)) != summary_fingerprint(summary):
        stage, hint = "wrapup", ("写完小结以后又重新算过分，数变了（比如改了题、换了同类店）：按 geo-weekly 重写本期小结和建议"
                                 "（set-actions 传 brief 和 todos），再 publish")
    return {"date": date, "stage": stage, "done": stage == "done", "next": hint}


def summary_fingerprint(summary: dict) -> str:
    """小结和建议会引用的那几个数。写小结时记下来，之后重新算分数变了，就知道小结过时了；只是重跑一次、数没变，不算。"""
    picked = {key: summary.get(key) for key in ("mention", "complete", "notUs")}
    picked["refs"] = {k: (summary.get("refs") or {}).get(k) for k in ("total", "own", "storePages", "aboutStore")}
    picked["rivals"] = [[r.get("name"), r.get("count")] for r in summary.get("rivals") or []]
    picked["shops"] = [[s.get("name"), s.get("count")] for s in summary.get("shops") or []]
    picked["findings"] = [f.get("title") for f in summary.get("findings") or []]
    raw = json.dumps(picked, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _stamp(value: str) -> float:
    moment = parse_iso(value)
    return (moment if moment.tzinfo else moment.replace(tzinfo=_BEIJING)).timestamp()


def last_asked_at(items: list) -> str:
    """这一期最近一次发起提问的时间。算分时记进 summary.json，之后又重问了题，就知道要重新算分。"""
    started = [i["startedAt"] for i in items if i.get("startedAt")]
    return max(started, key=_stamp) if started else ""


def _asked_after(items: list, summary: dict) -> bool:
    scored_upto, latest = summary.get("askedUpTo", ""), last_asked_at(items)
    return bool(scored_upto and latest) and _stamp(latest) > _stamp(scored_upto)


def drop_removed_questions(state: dict, bank_ids) -> list:
    """体检记录里那些已经从问题清单删掉的题：挪进 removed 留底，不再统计，也不出现在报告里。

    只用于当前这一期（正在体检、或者最新一期重新算分时）。以前各期按当时的问题算，保留原样。
    返回被挪走的问题编号。
    """
    keys = [key for key, item in (state.get("items") or {}).items() if item.get("qid") not in bank_ids]
    for key in keys:
        state.setdefault("removed", {})[key] = state["items"].pop(key)
    return sorted({key.rpartition("_")[0] for key in keys})


def read_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise GeoError("存档文件损坏，无法读取：" + path.name) from exc


def write_json(path: Path, data) -> None:
    """先写临时文件再改名，避免写到一半被打断留下坏文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_input(file_path: str):
    """读取由员工写好的 JSON 入参文件。

    子 Agent 交回的是一段文字，员工原样存成文件：外面可能包着 ```json 代码块，前后可能带一两句话。
    这里只取第一个 { 或 [ 到最后一个 } 或 ] 之间的部分，其余的一概不猜。
    """
    if not file_path:
        raise GeoError("缺少 --file 参数")
    try:
        text = Path(file_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise GeoError("找不到入参文件：" + os.path.basename(file_path)) from None
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    end = max(text.rfind("}"), text.rfind("]"))
    if not starts or end < min(starts):
        raise GeoError("入参文件里没有 JSON：" + os.path.basename(file_path))
    try:
        return json.loads(text[min(starts):end + 1])
    except json.JSONDecodeError as exc:
        raise GeoError("入参文件不是合法的 JSON（%s 第 %d 行）：%s" % (os.path.basename(file_path), exc.lineno, exc.msg)) from exc


# ── 工作台有没有跟上最新的数据 ──
# 每个改了数据的命令调 mark_changed 记一笔；geo_report.py publish 同步成功后清掉。
# 这样“工作台是不是最新的”是一个查得到的状态，不靠员工记得去同步。
PUBLISH_COMMAND = "geo-workbench 技能里的 geo_report.py publish"


def _sync_path() -> Path:
    return data_root() / "sync.json"


def mark_changed(what: str) -> None:
    """记下“数据变了，工作台要重新同步”。what 是变了什么，例如“店铺资料”。失败不影响主流程。"""
    try:
        state = read_json(_sync_path(), {}) or {}
        rev = int(state.get("rev", 0)) + 1
        changes = [c for c in state.get("changes") or [] if c.get("what") != what] + [{"what": what, "rev": rev}]
        state.update(rev=rev, changes=changes[-20:], changedAt=now_iso())
        write_json(_sync_path(), state)
    except Exception:  # noqa: BLE001
        pass


def mark_built() -> None:
    """工作台文件刚按当前数据生成了一遍（还没上传）。"""
    state = read_json(_sync_path(), {}) or {}
    state["builtRev"] = int(state.get("rev", 0))
    write_json(_sync_path(), state)


def mark_published() -> list:
    """最近一次生成的工作台已经传到云盘。返回这次同步上去的变化。"""
    state = read_json(_sync_path(), {}) or {}
    before = int(state.get("publishedRev", 0))
    built = int(state.get("builtRev", state.get("rev", 0)))
    changes = state.get("changes") or []
    synced = [c["what"] for c in changes if before < int(c.get("rev", 0)) <= built]
    state.update(publishedRev=built, publishedAt=now_iso(), changes=[c for c in changes if int(c.get("rev", 0)) > built])
    write_json(_sync_path(), state)
    return synced


def workbench_state() -> dict:
    """工作台的链接，以及它是不是最新的。pending 是还没同步上去的变化。"""
    meta = read_json(profile_dir() / "meta.json", {}) or {}
    state = read_json(_sync_path(), {}) or {}
    published = int(state.get("publishedRev", 0))
    pending = [c["what"] for c in state.get("changes") or [] if int(c.get("rev", 0)) > published]
    url = meta.get("pageUrl", "")
    return {"url": url, "publishedAt": state.get("publishedAt", ""), "upToDate": bool(url) and not pending, "pending": pending}


def sync_hint(state: dict = None) -> str:
    """提醒员工同步工作台的一句话；工作台已经是最新的就返回空串。"""
    state = state or workbench_state()
    if state["upToDate"]:
        return ""
    if not state["url"]:
        return "工作台还没有开通。请执行 %s，再把返回的链接发给商家" % PUBLISH_COMMAND
    return "工作台还没同步这些变化：%s。请执行 %s" % ("、".join(state["pending"]), PUBLISH_COMMAND)


# ── 哪些信息要商家确认 ──
# 店铺后台里有的资料（店名、门店、营业时间、商品、小程序）是商家自己维护的，以后台为准，不用他再确认一遍。
# 要确认的只是后台里没有、员工自己找来或推断的那几样：别名、他的公众号和抖音号、后台里没有的门店。
def _filled(value) -> bool:
    """真的填了东西：空字符串、空列表、各项都空着的对象都算没填。"""
    if isinstance(value, dict):
        return any(_filled(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_filled(v) for v in value)
    return bool(value)


def needs_confirm(facts: dict) -> dict:
    facts = facts or {}
    if facts.get("from") != "backend":
        # 资料不是从店铺后台读的（比如从公开信息整理的），整份都要商家看过才算数。
        # 只列真的填了的：空着的公众号、抖音号列进来，员工会以为要去问商家。
        return {k: facts.get(k) for k in ("brand", "stores", "products", "buyEntry", "channels") if _filled(facts.get(k))}
    brand, channels = facts.get("brand") or {}, facts.get("channels") or {}
    extras = {
        "aliases": brand.get("aliases") or [],
        "channels": {k: channels.get(k) for k in ("wechatOfficial", "douyin", "ownHosts", "ownContentKeys") if channels.get(k)},
        "stores": [s for s in facts.get("stores") or [] if "有赞后台" not in str(s.get("source") or "")],
    }
    return {k: v for k, v in extras.items() if v}


def confirm_state(facts: dict = None, meta: dict = None) -> dict:
    """资料从哪来、有没有要商家确认的、现在能不能替商家写内容。"""
    facts = read_json(profile_dir() / "facts.json", {}) or {} if facts is None else facts
    meta = read_json(profile_dir() / "meta.json", {}) or {} if meta is None else meta
    confirmed = bool(meta.get("confirmedAt"))
    from_backend = facts.get("from") == "backend"
    return {"from": "backend" if from_backend else "public", "confirmed": confirmed,
            "pending": bool(needs_confirm(facts)) and not confirmed,
            # 后台来的资料可以直接用来写内容；每一篇内容发之前本来就要商家确认，不用再卡一道“先确认资料”。
            "canWrite": confirmed or from_backend}


# ── 官网 ──
# 员工用有赞的“应用”能力替商家做的官网。这里只记它在哪、到了哪一步，和做的时候用的是哪一版店铺资料：
# 官网上放的那几样（店名和品类、这家店的特点、门店、招牌商品、怎么买）后来在店铺资料里改了，官网就过时了，要提醒商家更新。
SITE_STATUS = ("test", "published", "dropped")  # 有测试版等商家看 / 已上线 / 不要了
SITE_PARTS = (("brand", "店名和品类"), ("edges", "这家店的特点"), ("stores", "门店"), ("products", "招牌商品"), ("buyEntry", "怎么买"))


def site_path() -> Path:
    return profile_dir() / "site.json"


def site_facts(facts: dict, meta: dict = None) -> dict:
    """能放上官网的店铺资料。和写内容一样：员工另外记下、商家还没确认的（别名、后台里没有的门店）不放。"""
    facts = facts or {}
    unconfirmed = confirm_state(facts, meta)["pending"]
    brand = facts.get("brand") or {}
    stores = [s for s in facts.get("stores") or []
              if not unconfirmed or "有赞后台" in str(s.get("source") or "")]
    return {
        "brand": {k: brand.get(k, "") for k in ("name", "category", "city")},
        "edges": list(facts.get("edges") or []),
        "stores": [{k: s.get(k, "") for k in ("name", "address", "hours", "phone", "status")} for s in stores],
        "products": [{k: p.get(k, "") for k in ("name", "spec", "priceRange", "origin")} for p in facts.get("products") or []],
        "buyEntry": {k: (facts.get("buyEntry") or {}).get(k, "") for k in ("miniProgram", "shopUrl")},
    }


def site_state(facts: dict = None, meta: dict = None) -> dict:
    """官网在哪、到了哪一步、有没有跟上店铺资料。没做过官网时 exists 为 false。

    status 为 test 时，可能是第一次出的测试版，也可能是已上线的官网又改了一版、在等商家确认：
    url（正式链接）有值就说明官网已经在线。changed 是和最新那一版比，店铺资料里改了哪几样。
    """
    site = read_json(site_path(), {}) or {}
    status = site.get("status")
    if status not in SITE_STATUS:
        return {"exists": False}
    if facts is None:
        facts = read_json(profile_dir() / "facts.json", {}) or {}
    basis = site.get("testBasis") if status == "test" else site.get("basis")
    changed = []
    if status != "dropped" and isinstance(basis, dict):
        now_basis = site_facts(facts, meta)
        # 只比做的时候记下的那几样：以前登记的官网没记“这家店的特点”、商品没记价格带，不能因此算过时
        if not any("priceRange" in p for p in basis.get("products") or []):
            now_basis["products"] = [{k: v for k, v in p.items() if k != "priceRange"} for p in now_basis["products"]]
        changed = [name for key, name in SITE_PARTS if key in basis and basis[key] != now_basis.get(key)]
    return {"exists": True, "status": status, "live": bool(site.get("url")) and status != "dropped",
            "url": site.get("url", ""), "testUrl": site.get("testUrl", ""), "domain": site.get("domain", ""),
            "pageName": site.get("pageName", ""), "testAt": site.get("testAt", ""), "publishedAt": site.get("publishedAt", ""),
            "outdated": bool(changed), "changed": changed}


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")


def run_cli(main) -> None:
    """统一的出错方式：业务错误输出 {"ok": false, "error": ...}，退出码 2。"""
    try:
        main()
    except GeoError as exc:
        emit({"ok": False, "error": str(exc)})
        sys.exit(2)


def clean_answer(answer: dict) -> str:
    """一个回答的正文：优先取 markdown，去掉占位符，还原被转义的符号。"""
    body = (answer or {}).get("answer") or {}
    text = str(body.get("markdown") or body.get("text") or "")
    return html.unescape(_ANSWER_MARKS.sub("", text)).strip()


def clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_title(value) -> str:
    """引用内容的标题：去掉来源页面自己带的占位符，例如大众点评标题里的“ - [undefined]”。"""
    text = re.sub(r"\s*[-–—|_]?\s*\[undefined\]", "", clean_text(value), flags=re.I)
    return text.strip(" -–—|_")


def brand_aliases(facts: dict) -> list:
    """店名和别名，长的排前面，匹配时不区分大小写。"""
    brand = (facts or {}).get("brand") or {}
    names = [clean_text(brand.get("name"))] + [clean_text(a) for a in brand.get("aliases") or []]
    unique = []
    for name in names:
        if len(name) >= 2 and name.lower() not in [u.lower() for u in unique]:
            unique.append(name)
    return sorted(unique, key=len, reverse=True)


def contains_any(text: str, names) -> bool:
    low = str(text or "").lower()
    return any(str(name).lower() in low for name in names if name)


# 很多店共用的平台域名。链接的域名对上了说明不了是哪家店（有赞的商品页都在 detail.youzan.com 下），
# 所以这些平台上的商品页不算“你自己的”。
SHARED_HOSTS = ("youzan.com", "youzanyun.com", "taobao.com", "tmall.com", "jd.com", "pinduoduo.com", "yangkeduo.com",
                "1688.com", "weidian.com", "douyin.com", "iesdouyin.com", "xiaohongshu.com", "xhslink.com",
                "dianping.com", "meituan.com", "weixin.qq.com", "qq.com", "baidu.com", "amap.com")


def host_is(host: str, domain: str) -> bool:
    """host 是 domain 本身或它的子域名。不用“包含”，免得 ab.com 认成 b.com。"""
    host, domain = str(host or "").lower(), str(domain or "").lower().lstrip(".")
    return bool(domain) and (host == domain or host.endswith("." + domain))


def is_shared_host(host: str) -> bool:
    return any(host_is(host, d) for d in SHARED_HOSTS)


def own_hosts(facts: dict) -> list:
    """本店自己的域名：登记的独立域名和店铺链接的域名，去掉共用平台的。"""
    from urllib.parse import urlparse
    channels = (facts or {}).get("channels") or {}
    shop_url = str(((facts or {}).get("buyEntry") or {}).get("shopUrl") or "")
    hosts = list(channels.get("ownHosts") or []) + [urlparse(shop_url if "://" in shop_url else "https://" + shop_url).netloc.lower()]
    return [h for h in hosts if h and not is_shared_host(h)]


def own_keys(facts: dict) -> list:
    """登记过的本店内容编号（如抖音作品编号）。抖音的引用不带作者，只能靠它认。"""
    return [k for k in ((facts or {}).get("channels") or {}).get("ownContentKeys") or [] if k]


def has_key(text: str, keys) -> bool:
    """编号要完整出现，前后不能紧挨着字母或数字，免得 12345678 认成 912345678。"""
    low = str(text or "").lower()
    return any(re.search(r"(?<![0-9a-z])" + re.escape(str(k).lower()) + r"(?![0-9a-z])", low) for k in keys if k)

