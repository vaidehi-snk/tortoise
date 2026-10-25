"""Turns the logs into everything the dashboard and the report show."""
import time
from collections import Counter

from . import config, store
from .scoring import exact_match, normalize

QUIET_GAP = 120  # seconds with no events = the laptop slept, or everything was stopped


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def majority(drafts: list) -> str:
    answers = [d.get("answer", "") for d in drafts if normalize(d.get("answer", ""))]
    if not answers:
        return ""
    counts = Counter(normalize(a) for a in answers)
    top = max(counts.values())
    return next(a for a in answers if counts[normalize(a)] == top)


def build(run: str) -> dict:
    qs = store.questions()
    events = store.read(run, "events.jsonl")
    hare = store.latest_by_qid(run, "hare.jsonl")
    tort = store.latest_by_qid(run, "tortoise.jsonl")
    steps = [e for e in events if e.get("type") == "step"]

    # --- the shell: one cell per question -------------------------------------------
    started = {e["qid"] for e in events if e.get("type") == "q_start"}
    active = None
    for e in reversed(events):
        if e.get("type") == "q_start" and e["qid"] not in tort:
            active = e["qid"]
            break
    cells = []
    for i, q in enumerate(qs):
        h, t = hare.get(q["id"]), tort.get(q["id"])
        cells.append({"qid": q["id"], "i": i, "type": q["type"],
                      "h": None if h is None else h["em"], "t": None if t is None else t["em"],
                      "started": q["id"] in started, "active": q["id"] == active,
                      "t_ts": t.get("ts") if t else None})

    # --- head to head on questions both have answered --------------------------------
    paired = [q["id"] for q in qs if q["id"] in hare and q["id"] in tort]
    combo = Counter()
    for qid in paired:
        combo[(hare[qid]["em"] > 0, tort[qid]["em"] > 0)] += 1
    by_type = {}
    for kind in ("bridge", "comparison"):
        ids = [q["id"] for q in qs if q["type"] == kind and q["id"] in paired]
        by_type[kind] = {"n": len(ids), "hare": _mean(hare[i]["em"] for i in ids),
                         "tortoise": _mean(tort[i]["em"] for i in ids)}

    t_done = [tort[q["id"]] for q in qs if q["id"] in tort]
    ablation = None
    if t_done:
        ablation = [
            {"label": "Hare: one call", "em": _mean(hare[r["qid"]]["em"] for r in t_done if r["qid"] in hare)},
            {"label": "Slow reading, first draft", "em": _mean(exact_match(r["drafts"][0]["answer"], r["gold"]) for r in t_done if r["drafts"])},
            {"label": "+ majority of 3 drafts", "em": _mean(exact_match(majority(r["drafts"]), r["gold"]) for r in t_done)},
            {"label": "+ checked against notes", "em": _mean(r["em"] for r in t_done)},
        ]

    second_read = sum(1 for r in t_done for n in r["notes"] if n and n.get("pass") == 2 and n.get("relevant"))

    # --- cost of being slow -------------------------------------------------------------
    q_ms = Counter()
    for e in steps:
        q_ms[e["qid"]] += e.get("ms", 0)
    first = next((e["ts"] for e in events if e.get("type") == "q_start"), None)
    last = events[-1]["ts"] if events else None

    # --- durability ---------------------------------------------------------------------
    seen, rerun = set(), 0
    for e in steps:
        key = (e["qid"], e["kind"], e.get("i"))
        if key in seen:
            rerun += 1
        seen.add(key)
    fails = [e for e in events if e.get("type") == "fail"]
    timeline, resumes, quiet_s = [], 0, 0
    prev = None
    for e in events:
        if prev and e["ts"] - prev["ts"] > QUIET_GAP:
            gap = e["ts"] - prev["ts"]
            quiet_s += gap
            timeline.append({"ts": prev["ts"], "kind": "quiet", "text": f"Nothing for {_dur(gap)}. Asleep, or stopped."})
        t = e.get("type")
        if t == "run_start":
            timeline.append({"ts": e["ts"], "kind": "start", "text": f"Night started: {e.get('n', '?')} questions, {e.get('model', '')}"})
        elif t == "worker_up" and first and e["ts"] > first:
            resumes += 1
            timeline.append({"ts": e["ts"], "kind": "resume", "text": f"Worker came back (pid {e.get('pid')}). Temporal handed it the step it was on."})
        elif t == "fail":
            timeline.append({"ts": e["ts"], "kind": "injected" if e.get("injected") else "fail",
                             "text": ("Injected failure" if e.get("injected") else "Model unreachable")
                                     + f" during {e.get('kind')} (attempt {e.get('attempt')}). Retrying."})
        elif t == "q_done":
            h = hare.get(e["qid"])
            if h is not None and e["em"] and not h["em"]:
                timeline.append({"ts": e["ts"], "kind": "win", "qid": e["qid"],
                                 "text": f"Tortoise got Q{_idx(qs, e['qid'])} right. The hare didn't."})
        prev = e

    now = None
    if active:
        q = store.question(active)
        mine = [e for e in steps if e["qid"] == active]
        last_step = mine[-1] if mine else None
        now = {"qid": active, "i": _idx(qs, active), "question": q["question"], "type": q["type"],
               "phase": last_step["kind"] if last_step else "open",
               "pos": last_step.get("pos", 0) if last_step else 0, "of": last_step.get("of", 0) if last_step else 0,
               "feed": [_feed(e) for e in mine[-8:]], "compute_ms": q_ms[active],
               "since": time.time() - (last_step["ts"] if last_step else events[-1]["ts"])}

    run_start = next((e for e in events if e.get("type") == "run_start"), {})
    return {
        "meta": {"run": run, "model": run_start.get("model") or config.MODEL,
                 "mode": run_start.get("mode", ""), "method": run_start.get("method", "v1"), "total": len(qs), "now": time.time(),
                 "last_event": last, "hardware": run_start.get("hardware", "")},
        "hare": {"done": len(hare), "em": _mean(r["em"] for r in hare.values()), "f1": _mean(r["f1"] for r in hare.values()),
                 "ms": sum(r.get("ms", 0) for r in hare.values()), "tok": sum(r.get("tok_in", 0) + r.get("tok_out", 0) for r in hare.values()),
                 "calls": len(hare)},
        "tortoise": {"done": len(tort), "em": _mean(r["em"] for r in t_done), "f1": _mean(r["f1"] for r in t_done),
                     "ms": sum(q_ms.values()), "wall": (last - first) if first and last else 0,
                     "tok": sum(e.get("tok_in", 0) + e.get("tok_out", 0) for e in steps), "calls": len(steps),
                     "median_q_ms": _median([q_ms[r["qid"]] for r in t_done])},
        "paired": {"n": len(paired), "hare_em": _mean(hare[i]["em"] for i in paired),
                   "tortoise_em": _mean(tort[i]["em"] for i in paired),
                   "both": combo[(True, True)], "tortoise_only": combo[(False, True)],
                   "hare_only": combo[(True, False)], "neither": combo[(False, False)]},
        "by_type": by_type, "ablation": ablation, "second_read": second_read,
        "cells": cells, "now": now,
        "durability": {"resumes": resumes, "fails": sum(1 for f in fails if not f.get("injected")),
                       "injected": sum(1 for f in fails if f.get("injected")), "rerun": rerun,
                       "quiet": quiet_s, "timeline": timeline[-60:]},
    }


def detail(run: str, qid: str) -> dict:
    q = store.question(qid)
    hare = store.latest_by_qid(run, "hare.jsonl").get(qid)
    tort = store.latest_by_qid(run, "tortoise.jsonl").get(qid)
    steps = [_feed(e) for e in store.read(run, "events.jsonl") if e.get("type") == "step" and e["qid"] == qid]
    return {"qid": qid, "i": _idx(store.questions(), qid), "question": q["question"], "gold": q["answer"],
            "type": q["type"], "supporting": q.get("supporting", []),
            "titles": [p["title"] for p in q["paragraphs"]], "hare": hare, "tortoise": tort, "steps": steps}


def _feed(e: dict) -> dict:
    keep = ("kind", "i", "pos", "of", "title", "relevant", "facts", "answer", "reasoning",
            "candidate", "supported", "short_answer", "ms", "attempt", "ts")
    return {k: e[k] for k in keep if k in e}


def _idx(qs, qid):
    return next((i + 1 for i, q in enumerate(qs) if q["id"] == qid), 0)


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0


def _dur(s: float) -> str:
    s = int(s)
    if s < 90:
        return f"{s} s"
    if s < 5400:
        return f"{s // 60} min"
    return f"{s // 3600} h {(s % 3600) // 60} min"
