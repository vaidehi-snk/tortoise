"""Files on disk: the question set, append-only event logs and results."""
import json
import threading
import time

from . import config

_lock = threading.Lock()
_questions = None


def questions() -> list:
    global _questions
    if _questions is None:
        if not config.QUESTIONS.exists():
            raise SystemExit("No questions yet. Run:  python -m tortoise fetch")
        _questions = json.loads(config.QUESTIONS.read_text(encoding="utf-8"))
    return _questions


def question(qid: str) -> dict:
    for q in questions():
        if q["id"] == qid:
            return q
    raise KeyError(qid)


def append(run: str, name: str, record: dict) -> None:
    record = {"ts": time.time(), **record}
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with open(config.run_dir(run) / name, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def event(run: str, **record) -> None:
    append(run, "events.jsonl", record)


def read(run: str, name: str) -> list:
    path = config.RUNS / run / name
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass  # a line cut off by a crash mid-write
    return out


def latest_by_qid(run: str, name: str) -> dict:
    return {r["qid"]: r for r in read(run, name)}
