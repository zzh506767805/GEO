#!/usr/bin/env python3
"""批量向 AI 平台提问并等待结果。

一轮体检分两段：先问全部不带店名的问题（open），全部返回后再问带店名的问题（brand）。
顺序不能反：取数账号有记忆，先问带店名的会让后面的回答凭空提到这家店。

用法（脚本用绝对路径执行）：
  geo_run.py start --phase open|brand [--date D] [--only q01,q03] [--retry]
  geo_run.py start --phase open --fresh [--date D]   同一天重新测一次：上一次的结果挪走留底，全部重新问
  geo_run.py wait [--date D] [--max-seconds 90]
  geo_run.py status [--date D]

wait 每次只等一小段时间就返回进度，没完成就再执行一次。查询还在运行不算出错。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True

import geo_common as gc  # noqa: E402

ASK_AI_CAPABILITY_ID = "171"
RUNNING, COMPLETED, FAILED = 0, 1, 2
TERMINAL = ("done", "failed", "expired")
DEADLINE_SECONDS = int(os.environ.get("GEO_DEADLINE_SECONDS", str(15 * 60)))
POLL_INTERVAL = float(os.environ.get("GEO_POLL_INTERVAL", "15"))
CALL_TIMEOUT = 60
PHASE_KIND = {"open": "open", "brand": "brand"}


def query_command() -> list:
    """问 AI 技能自带的查询脚本。测试时可用 GEO_AI_QUERY_CMD 换成模拟脚本。"""
    override = os.environ.get("GEO_AI_QUERY_CMD", "").strip()
    if override:
        return shlex.split(override)
    root = os.environ.get("YOUZAN_GLOBAL_SKILLS_PATH", "").strip()
    script = Path(root) / "youzan-ai-search" / "scripts" / "ai-data-query.mjs" if root else None
    if not script or not script.is_file():
        raise gc.GeoError("这家店还没有开通“问 AI”能力，暂时不能体检")
    return ["node", str(script)]


def _history_store() -> Path:
    """每次调用用独立的历史文件：并发时互不覆盖，也不污染商家自己的查询历史。"""
    base = os.environ.get("YOUZAN_AGENT_SESSION_TEMP", "").strip()
    folder = Path(base) if base else gc.data_root() / "tmp"
    folder = folder / "geo-query-history"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (uuid.uuid4().hex + ".json")


def call_query(args: list) -> dict:
    """执行一次查询脚本，返回 {"ok", "data", "error"}。不抛异常，方便并发收集。"""
    store = _history_store()
    env = dict(os.environ, AI_DATA_QUERY_STORE=str(store))
    try:
        proc = subprocess.run(
            query_command() + args, capture_output=True, text=True, timeout=CALL_TIMEOUT, env=env
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "请求超时"}
    except OSError as exc:
        return {"ok": False, "error": "查询脚本无法执行：" + exc.__class__.__name__}
    finally:
        try:
            store.unlink()
        except OSError:
            pass
    if proc.returncode != 0:
        return {"ok": False, "error": gc.clean_text(proc.stderr or proc.stdout)[:200] or "查询脚本返回错误"}
    try:
        return {"ok": True, "data": json.loads(proc.stdout)}
    except json.JSONDecodeError:
        return {"ok": False, "error": "查询脚本的输出无法解析"}


def _query_id(data: dict) -> str:
    value = data.get("queryId") or data.get("id") or (data.get("query") or {}).get("id")
    return str(value) if value not in (None, "") else ""


def slim(data: dict) -> dict:
    """存档只保留算分和核对要用的字段，去掉体积大的调试信息。"""
    result = dict(data.get("result") or {})
    answers = []
    for answer in result.get("answers") or []:
        if not isinstance(answer, dict):
            continue
        refs = []
        for ref in ((answer.get("references") or {}).get("list")) or []:
            refs.append({k: ref.get(k) for k in ("no", "url", "host", "title", "source", "summary", "publishDate")})
        answers.append({
            "platform": answer.get("platform"),
            "mode": answer.get("mode"),
            "answer": {k: (answer.get("answer") or {}).get(k) for k in ("text", "markdown")},
            "references": {"total": len(refs), "list": refs},
            "statementReferences": answer.get("statementReferences") or [],
            "searchQueries": answer.get("searchQueries") or [],
            "productCards": answer.get("productCards") or [],
        })
    result["answers"] = answers
    return {"query": data.get("query") or {}, "result": result}


def _usable(data: dict) -> bool:
    for answer in ((data.get("result") or {}).get("answers")) or []:
        body = answer.get("answer") or {}
        if gc.clean_text(body.get("markdown") or body.get("text")):
            return True
    return False


def _state_path(date: str) -> Path:
    return gc.run_dir(date) / "queries.json"


def _load_state(date: str) -> dict:
    state = gc.read_json(_state_path(date))
    if state:
        return state
    return {"date": date, "providers": list(gc.PROVIDERS), "answersPerQuery": gc.ANSWERS_PER_QUERY,
            "phases": {}, "items": {}}


def _load_questions() -> dict:
    questions = gc.read_json(gc.profile_dir() / "questions.json")
    if not questions or not questions.get("items"):
        raise gc.GeoError("问题库是空的，请先按 geo-profile 建档")
    return questions


def _elapsed(iso: str) -> int:
    return max(0, int((gc.now() - gc.parse_iso(iso)).total_seconds())) if iso else 0


def progress(state: dict) -> dict:
    items = state["items"]
    count = lambda name: sum(1 for item in items.values() if item["status"] == name)  # noqa: E731
    phases = {}
    for phase in ("open", "brand"):
        rows = [item for item in items.values() if item["kind"] == phase]
        meta = state["phases"].get(phase) or {}
        phases[phase] = {
            "started": bool(rows),
            "total": len(rows),
            "finished": bool(rows) and all(item["status"] in TERMINAL for item in rows),
            "running": sum(1 for item in rows if item["status"] == "running"),
            "elapsedSeconds": _elapsed(meta.get("startedAt", "")) if rows else 0,
        }
    missing = sorted(key for key, item in items.items() if item["status"] in ("failed", "expired", "error"))
    payload = {
        "ok": True,
        "date": state["date"],
        "total": len(items),
        "done": count("done"),
        "running": count("running"),
        "missing": missing,
        "phases": phases,
        # 两段都发起过、且没有还在运行的查询，才算整轮结束。
        "finished": phases["open"]["started"] and phases["brand"]["started"] and count("running") == 0,
    }
    payload["next"] = _next_hint(payload)
    return payload


def _next_hint(p: dict) -> str:
    if not p["phases"]["open"]["started"]:
        return "还没有发起查询，请执行 start --phase open"
    if p["running"]:
        return "还有 %d 条查询在运行，这是正常情况，请再执行一次 wait；不要把它当成出错" % p["running"]
    if not p["phases"]["brand"]["started"]:
        return "不带店名的问题已全部返回，请执行 start --phase brand"
    if p["missing"]:
        return "本轮已结束，有 %d 条没有拿到结果，按缺失处理；请执行 geo_score.py score" % len(p["missing"])
    return "本轮已全部返回，请执行 geo_score.py score"


def _archive_round(date: str, state: dict) -> str:
    """同一天重新测之前，把上一次的查询、回答、算分和核对挪进 old-<时间>/ 留底。小结和建议（actions.json）留着，员工会重写。"""
    if any(item["status"] == "running" for item in state["items"].values()):
        raise gc.GeoError("上一次还有查询在运行，等它们返回（wait）再重新测")
    folder = gc.run_dir(date)
    target = folder / ("old-" + gc.now().strftime("%H%M%S"))
    target.mkdir(parents=True, exist_ok=True)
    for name in ("queries.json", "summary.json", "judgement.json", "raw"):
        if (folder / name).exists():
            shutil.move(str(folder / name), str(target / name))
    return target.name


def cmd_start(args) -> None:
    meta = gc.read_json(gc.profile_dir() / "meta.json", {}) or {}
    if meta.get("firstCheckPending"):
        raise gc.GeoError("首次体检还没有得到商家确认。先说明店铺信息和监测方向，收到明确确认后执行 geo_state.py confirm-monitoring，再开始体检")
    date = gc.check_date(args.date) if args.date else gc.today()
    phase = args.phase
    questions = _load_questions()
    state = _load_state(date)
    archived = ""
    if args.fresh:
        # “重新测一次”和“接着上一次”是两回事：不带 --fresh 时已经有结果的题不会重新问
        if phase != "open":
            raise gc.GeoError("重新测一次要从不带店名的问题开始：start --phase open --fresh")
        if state["items"]:
            archived = _archive_round(date, state)
        state = _load_state(date)
    # 问题清单里已经删掉的题，不再算进这一期
    dropped = gc.drop_removed_questions(state, {q["id"] for q in questions["items"]})
    state["questionsVersion"] = questions.get("version", 0)
    if phase == "brand" and not args.force:
        open_rows = [item for item in state["items"].values() if item["kind"] == "open"]
        if not open_rows or any(item["status"] == "running" for item in open_rows):
            raise gc.GeoError("不带店名的问题还没有跑完，现在不能问带店名的问题")
    only = {q.strip().lower() for q in args.only.split(",") if q.strip()} if args.only else None
    todo = []
    for question in questions["items"]:
        if question["kind"] != PHASE_KIND[phase] or (only and question["id"] not in only):
            continue
        for provider in gc.PROVIDERS:
            key = question["id"] + "_" + provider
            current = state["items"].get(key)
            stale = bool(current) and current.get("question") != question["text"]
            redo = bool(current) and args.retry and current["status"] in ("failed", "expired", "error")
            if current and not stale and not redo:
                continue
            todo.append((key, question, provider))
    if not todo:
        if dropped:
            gc.write_json(_state_path(date), state)
        payload = progress(state)
        payload["started"] = 0
        if dropped:
            payload["dropped"] = dropped
        if payload["finished"] or (phase == "open" and payload["phases"]["open"]["finished"]):
            # 这一天已经问过了。没有新问的题时什么都不会重新问，免得员工以为“重新体检”了
            payload["next"] = ("这一天的问题都已经问过，这次没有重新提问，用的是已有的回答（接着上一次）。"
                               "商家要“重新测一次”，执行 start --phase open --fresh；否则按原来的进度继续：" + payload["next"])
        gc.emit(payload)
        return
    query_command()  # 环境不可用时在这里直接报清楚，不要每条都失败一遍

    def create(job):
        key, question, provider = job
        params = {"provider": provider, "question": question["text"], "concurrency": gc.ANSWERS_PER_QUERY}
        outcome = call_query(["run", "--id", ASK_AI_CAPABILITY_ID, "--params", json.dumps(params, ensure_ascii=False)])
        return key, question, provider, outcome

    with ThreadPoolExecutor(max_workers=5) as pool:
        outcomes = list(pool.map(create, todo))
    started, errors = 0, []
    for key, question, provider, outcome in outcomes:
        item = {"qid": question["id"], "kind": question["kind"], "provider": provider,
                "question": question["text"], "queryId": "", "status": "error",
                "startedAt": gc.now_iso(), "finishedAt": "", "error": ""}
        query_id = _query_id(outcome["data"]) if outcome["ok"] else ""
        if query_id:
            item.update(queryId=query_id, status="running")
            started += 1
        else:
            item["error"] = outcome.get("error") or "没有拿到查询编号"
            errors.append(item["error"])
        raw_file = gc.run_dir(date) / "raw" / (key + ".json")
        if raw_file.exists():
            raw_file.unlink()  # 问题改过或重跑时，旧结果不能留着
        state["items"][key] = item
    state["phases"][phase] = {"startedAt": gc.now_iso()}
    gc.write_json(_state_path(date), state)
    if not started:
        raise gc.GeoError("查询一条都没有发起成功：" + (errors[0] if errors else "原因不明"))
    gc.mark_changed("体检进度")
    payload = progress(state)
    payload["started"] = started
    if archived:
        payload["archived"] = archived  # 上一次的结果挪到了这个目录
    if dropped:
        payload["dropped"] = dropped
    if errors:
        payload["startErrors"] = len(errors)
    gc.emit(payload)


def _poll_once(date: str, state: dict) -> None:
    running = [(key, item) for key, item in state["items"].items() if item["status"] == "running"]

    def fetch(pair):
        key, item = pair
        return key, call_query(["get", "--query-id", item["queryId"], "--no-download-images"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(fetch, running))
    for key, outcome in outcomes:
        item = state["items"][key]
        if not outcome["ok"]:
            item["error"] = outcome["error"]  # 取结果偶尔失败不算终态，下一轮再取
            continue
        data = outcome["data"]
        status = (data.get("query") or {}).get("status")
        if status not in (COMPLETED, FAILED):
            continue
        gc.write_json(gc.run_dir(date) / "raw" / (key + ".json"), slim(data))
        item["finishedAt"] = gc.now_iso()
        if status == COMPLETED and _usable(data):
            item.update(status="done", error="")
        else:
            reason = gc.clean_text((data.get("query") or {}).get("errorMessage")) or "没有返回可用的回答"
            item.update(status="failed", error=reason[:200])


def _expire_overdue(state: dict) -> None:
    for phase, meta in state["phases"].items():
        if _elapsed(meta.get("startedAt", "")) < DEADLINE_SECONDS:
            continue
        for item in state["items"].values():
            if item["kind"] == phase and item["status"] == "running":
                item.update(status="expired", finishedAt=gc.now_iso(), error="超过等待时限仍未返回")


def cmd_wait(args) -> None:
    date = gc.resolve_date(args.date)
    state = _load_state(date)
    if not state["items"]:
        raise gc.GeoError("这一天还没有发起过查询")
    deadline = time.time() + max(5, args.max_seconds)
    while True:
        _poll_once(date, state)
        _expire_overdue(state)
        gc.write_json(_state_path(date), state)
        still_running = any(item["status"] == "running" for item in state["items"].values())
        if not still_running or time.time() + POLL_INTERVAL > deadline:
            break
        time.sleep(POLL_INTERVAL)
    gc.emit(progress(state))


def cmd_status(args) -> None:
    date = gc.resolve_date(args.date)
    gc.emit(progress(_load_state(date)))


def main() -> None:
    parser = argparse.ArgumentParser(description="批量提问")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start")
    p.add_argument("--phase", required=True, choices=("open", "brand"))
    p.add_argument("--date", default="")
    p.add_argument("--only", default="")
    p.add_argument("--retry", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--fresh", action="store_true")  # 同一天重新测一次
    p.set_defaults(func=cmd_start)
    p = sub.add_parser("wait")
    p.add_argument("--date", default="")
    p.add_argument("--max-seconds", type=int, default=90)
    p.set_defaults(func=cmd_wait)
    p = sub.add_parser("status")
    p.add_argument("--date", default="")
    p.set_defaults(func=cmd_status)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    gc.run_cli(main)
