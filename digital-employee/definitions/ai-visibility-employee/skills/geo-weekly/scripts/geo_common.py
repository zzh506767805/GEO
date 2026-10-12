#!/usr/bin/env python3
"""AI 曝光专员三个技能共用的小工具：定位数据目录、读写 JSON、统一输出。

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


def shop_template_path() -> Path:
    """这家店自己的页面模板。有它就用它生成工作台和报告，没有就用 geo-weekly 自带的标准模板。"""
    return data_root() / "template" / "page.html"


def shop_template_hash() -> str:
    """这家店自己的模板现在的指纹；没有自己的模板时是空串。员工直接改了文件，也能靠它发现页面要重新同步。"""
    try:
        return hashlib.sha256(shop_template_path().read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


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
    if not _DATE_RE.match(str(value or "")):
        raise GeoError("日期格式应为 YYYY-MM-DD")
    return value


def list_run_dates() -> list:
    root = runs_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and _DATE_RE.match(p.name))


def latest_run_date(before: str = "") -> str:
    """最近一次体检的日期；传 before 时取它之前的最近一次。没有则返回空串。"""
    dates = [d for d in list_run_dates() if not before or d < before]
    return dates[-1] if dates else ""


def resolve_date(value: str = "") -> str:
    """命令没传日期时：有当天的体检就用当天，否则用最近一次。"""
    if value:
        return check_date(value)
    dates = list_run_dates()
    if today() in dates or not dates:
        return today()
    return dates[-1]


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
    """读取由员工写好的 JSON 入参文件。"""
    if not file_path:
        raise GeoError("缺少 --file 参数")
    data = read_json(Path(file_path))
    if data is None:
        raise GeoError("找不到入参文件：" + os.path.basename(file_path))
    return data


# ── 工作台有没有跟上最新的数据 ──
# 每个改了数据的命令调 mark_changed 记一笔；geo_report.py publish 同步成功后清掉。
# 这样“工作台是不是最新的”是一个查得到的状态，不靠员工记得去同步。
PUBLISH_COMMAND = "geo-weekly 技能里的 geo_report.py publish"


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
    template = shop_template_hash()
    if template != state.get("templateHash", ""):
        synced.append("页面模板")
    state.update(publishedRev=built, publishedAt=now_iso(), changes=[c for c in changes if int(c.get("rev", 0)) > built],
                 templateHash=template)
    write_json(_sync_path(), state)
    return synced


def workbench_state() -> dict:
    """工作台的链接，以及它是不是最新的。pending 是还没同步上去的变化。"""
    meta = read_json(profile_dir() / "meta.json", {}) or {}
    state = read_json(_sync_path(), {}) or {}
    published = int(state.get("publishedRev", 0))
    pending = [c["what"] for c in state.get("changes") or [] if int(c.get("rev", 0)) > published]
    if url_published(meta) and shop_template_hash() != state.get("templateHash", ""):
        pending.append("页面模板")  # 员工改了这家店的模板文件，还没同步上去
    url = meta.get("pageUrl", "")
    return {"url": url, "publishedAt": state.get("publishedAt", ""), "upToDate": bool(url) and not pending, "pending": pending}


def url_published(meta: dict) -> bool:
    return bool((meta or {}).get("pageUrl"))


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
def needs_confirm(facts: dict) -> dict:
    facts = facts or {}
    if facts.get("from") != "backend":
        # 资料不是从店铺后台读的（比如从公开信息整理的），整份都要商家看过才算数。
        return {k: facts.get(k) for k in ("brand", "stores", "products", "buyEntry", "channels") if facts.get(k)}
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
