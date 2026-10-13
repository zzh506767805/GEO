#!/usr/bin/env python3
"""模拟“问 AI”技能的查询脚本（ai-data-query.mjs），只用于本地测试，不联网。

支持 geo_run.py 用到的两个命令，输出格式和真实脚本一致：
  run --id 171 --params '{"provider":..,"question":..,"concurrency":2}'  → {"queryId": .., "status": 0}
  get --query-id <id> --no-download-images                               → {"query": {..status..}, "result": {..}}

环境变量：
  MOCK_STATE    必填，保存模拟查询状态的文件
  MOCK_ARCHIVE  可选，真实存档目录（res_<问题>_<平台>.json）。有就按问题原文回放真实回答
  MOCK_QUESTIONS 可选，存档对应的 questions.tsv，用来把问题原文对回编号
  MOCK_POLLS    一条查询要被 get 几次才算完成，默认 2
  MOCK_HANG     逗号分隔的 "平台:问题里的关键词"，命中的查询永远不返回
  MOCK_FAIL     同上，命中的查询返回失败
  MOCK_RUN_ERROR 设了就让 run 直接报错退出（模拟环境不可用）
  MOCK_DEMO_WEEK 设成 1 到 5 时，按 demo_scenario.py 的剧本返回演示数据
"""
import fcntl
import json
import os
import sys


def arg(name, default=""):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def locked_state(update):
    path = os.environ["MOCK_STATE"]
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        text = handle.read()
        state = json.loads(text) if text.strip() else {"next": 1000, "queries": {}}
        result = update(state)
        handle.seek(0)
        handle.truncate()
        json.dump(state, handle, ensure_ascii=False)
        return result


def matches(env_name, provider, question):
    for rule in filter(None, os.environ.get(env_name, "").split(",")):
        prov, _, word = rule.partition(":")
        if prov == provider and word in question:
            return True
    return False


def synthetic(provider, question):
    """没有存档时的合成回答：够测流程和算分即可。"""
    brand = "带店名" in question or "示例小店" in question
    texts = []
    for n in (1, 2):
        parts = ["先说结论，推荐这几家：", "1. **甲记面包**：口碑稳定。", "2. **乙家烘焙**：性价比高。"]
        if brand or ("附近" in question and provider == "doubao"):
            parts.append("3. **示例小店**：地址在测试路 1 号，营业到 20:00。")
        if "吐司" in question:
            parts.append("4. **丙记吐司坊**：吐司扎实。")
        if "可颂" in question:
            parts.append("4. **手工面包**：现做现卖的更好吃。")
        if "记忆" in question and provider == "doubao" and n == 1:
            parts.append("另外你之前问过的示例小店也可以考虑。")
        texts.append("\n".join(parts))
    refs = [
        {"no": 1, "url": "https://mp.weixin.qq.com/s?id=own1", "host": "mp.weixin.qq.com", "title": "示例小店的新品", "source": "示例小店官方号", "summary": "", "publishDate": ""},
        {"no": 2, "url": "https://www.iesdouyin.com/share/video/1", "host": "www.iesdouyin.com", "title": "探店合集", "source": "www.iesdouyin.com", "summary": "", "publishDate": ""},
        {"no": 3, "url": "https://m.dianping.com/shop/1", "host": "m.dianping.com", "title": "示例小店(测试路店)", "source": "大众点评", "summary": "", "publishDate": ""},
    ]
    answers = [{"platform": provider, "mode": "fast", "answer": {"text": t, "markdown": t},
                "references": {"total": len(refs), "list": refs if brand else refs[1:2]}} for t in texts]
    return {"success": True, "provider": provider, "question": question, "answers": answers, "error": ""}


def from_archive(provider, question):
    folder = os.environ.get("MOCK_ARCHIVE", "")
    table = os.environ.get("MOCK_QUESTIONS", "")
    if not folder or not table:
        return None
    for line in open(table, encoding="utf-8").read().splitlines():
        key, _, text = line.partition("\t")
        if text.strip() == question.strip():
            path = os.path.join(folder, "res_%s_%s.json" % (key, provider))
            if os.path.exists(path):
                return json.load(open(path, encoding="utf-8")).get("result")
    return None


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "run":
        if os.environ.get("MOCK_RUN_ERROR"):
            sys.stderr.write("缺少环境变量 AI_DATA_API_KEY\n")
            sys.exit(1)
        params = json.loads(arg("--params"))

        def create(state):
            state["next"] += 1
            state["queries"][str(state["next"])] = {"provider": params["provider"], "question": params["question"], "polls": 0}
            return state["next"]

        print(json.dumps({"queryId": locked_state(create), "status": 0}))
    elif command == "get":
        query_id = arg("--query-id")

        def poll(state):
            record = state["queries"].get(query_id)
            if record:
                record["polls"] += 1
            return dict(record) if record else None

        record = locked_state(poll)
        if not record:
            sys.stderr.write("查询不存在\n")
            sys.exit(1)
        provider, question = record["provider"], record["question"]
        need = int(os.environ.get("MOCK_POLLS", "2"))
        base = {"id": int(query_id), "capabilityId": 171, "startedAt": "", "finishedAt": "", "errorMessage": ""}
        if matches("MOCK_HANG", provider, question) or record["polls"] < need:
            print(json.dumps({"query": dict(base, status=0), "result": None}))
        elif matches("MOCK_FAIL", provider, question):
            print(json.dumps({"query": dict(base, status=2, errorMessage="平台暂时不可用"), "result": None}, ensure_ascii=False))
        else:
            week = int(os.environ.get("MOCK_DEMO_WEEK", "0") or 0)
            if week:
                import demo_scenario
                result = demo_scenario.result(provider, question, week)
            else:
                result = from_archive(provider, question) or synthetic(provider, question)
            print(json.dumps({"query": dict(base, status=1), "result": result}, ensure_ascii=False))
    else:
        sys.stderr.write("mock 只支持 run 和 get\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
