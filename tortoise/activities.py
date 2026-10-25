"""Every step that touches the model or the disk. In Temporal mode each of these is an
activity: retried when it fails, never repeated once it has finished."""
import asyncio
import functools
import os
import random

from temporalio import activity

from . import config, llm, prompts, store
from .scoring import exact_match, f1


def _in_activity() -> bool:
    try:
        return activity.in_activity()
    except Exception:
        return False


def _attempt() -> int:
    return activity.info().attempt if _in_activity() else 1


async def _call(run: str, qid: str, kind: str, fn, *args, **kwargs):
    """Runs a blocking model call, heartbeating so a killed worker is noticed in seconds."""
    if kwargs:
        fn = functools.partial(fn, **kwargs)
    if _in_activity() and config.CHAOS and random.random() < config.CHAOS:
        store.event(run, type="fail", qid=qid, kind=kind, injected=True, attempt=_attempt(),
                    error="chaos: failure injected on purpose")
        raise RuntimeError("chaos: failure injected on purpose")
    task = asyncio.ensure_future(asyncio.to_thread(fn, *args))
    try:
        if not _in_activity():
            return await task
        while True:
            done, _ = await asyncio.wait({task}, timeout=5)
            if done:
                return task.result()
            activity.heartbeat()
    except llm.ModelUnavailable as e:
        store.event(run, type="fail", qid=qid, kind=kind, injected=False, attempt=_attempt(), error=str(e)[:200])
        raise


def _step_event(run, qid, kind, meta, **extra):
    store.event(run, type="step", qid=qid, kind=kind, attempt=_attempt(), pid=os.getpid(),
                ms=meta["ms"], tok_in=meta["tok_in"], tok_out=meta["tok_out"], **extra)


@activity.defn(name="open_question")
async def open_question(a: dict) -> dict:
    q = store.question(a["qid"])
    store.event(a["run"], type="q_start", qid=q["id"], question=q["question"], n=len(q["paragraphs"]))
    return {"n": len(q["paragraphs"])}


@activity.defn(name="read_paragraph")
async def read_paragraph(a: dict) -> dict:
    q = store.question(a["qid"])
    p = q["paragraphs"][a["i"]]
    kind = "read" if a["pass"] == 1 else "reread"
    out, meta = await _call(a["run"], q["id"], kind, llm.chat,
                            prompts.read(q["question"], p, a["known"]), prompts.READ_SCHEMA)
    out = out or {}
    facts = [str(f).strip() for f in (out.get("facts") or []) if str(f).strip()][:3]
    note = {"i": a["i"], "title": p["title"], "pass": a["pass"],
            "relevant": bool(out.get("relevant")) and bool(facts), "facts": facts}
    _step_event(a["run"], q["id"], kind, meta, i=a["i"], pos=a.get("pos", a["i"]), of=a["of"],
                title=p["title"], relevant=note["relevant"], facts=facts)
    return note


def _flagged(q: dict, known: list):
    """v2: the full text of the paragraphs the notes came from (at most 5)."""
    if config.METHOD != "v2":
        return None
    titles = list(dict.fromkeys(k["title"] for k in known))[:5]
    return [p for t in titles for p in q["paragraphs"] if p["title"] == t]


@activity.defn(name="draft_answer")
async def draft_answer(a: dict) -> dict:
    q = store.question(a["qid"])
    k = a["k"]
    # Draft 0 is the careful, deterministic one; the others explore.
    out, meta = await _call(a["run"], q["id"], "draft", llm.chat, prompts.draft(q["question"], a["known"], _flagged(q, a["known"])),
                            prompts.ANSWER_SCHEMA, temperature=0.0 if k == 0 else 0.7, seed=k)
    out = out or {}
    d = {"k": k, "answer": str(out.get("answer", "")).strip(), "reasoning": str(out.get("reasoning", "")).strip()}
    _step_event(a["run"], q["id"], "draft", meta, i=k, pos=k, of=a["of"], answer=d["answer"], reasoning=d["reasoning"])
    return d


@activity.defn(name="verify_answer")
async def verify_answer(a: dict) -> dict:
    q = store.question(a["qid"])
    out, meta = await _call(a["run"], q["id"], "verify", llm.chat,
                            prompts.verify(q["question"], a["known"], a["candidate"], _flagged(q, a["known"])), prompts.VERIFY_SCHEMA)
    out = out or {}
    v = {"candidate": a["candidate"], "supported": bool(out.get("supported")),
         "short_answer": str(out.get("short_answer", "")).strip()}
    _step_event(a["run"], q["id"], "verify", meta, i=a["j"], pos=a["j"], of=a["of"], **v)
    return v


@activity.defn(name="finish_question")
async def finish_question(a: dict) -> dict:
    q = store.question(a["qid"])
    rec = {
        "qid": q["id"], "answer": a["final"], "gold": q["answer"],
        "em": exact_match(a["final"], q["answer"]), "f1": round(f1(a["final"], q["answer"]), 4),
        "drafts": a["drafts"], "cands": a["cands"], "verdicts": a["verdicts"],
        "notes": a["notes"], "why": a["why"],
    }
    store.append(a["run"], "tortoise.jsonl", rec)
    store.event(a["run"], type="q_done", qid=q["id"], answer=a["final"], em=rec["em"], f1=rec["f1"])
    return {"qid": q["id"], "em": rec["em"], "f1": rec["f1"], "answer": a["final"]}


ALL = [open_question, read_paragraph, draft_answer, verify_answer, finish_question]
BY_NAME = {"open_question": open_question, "read_paragraph": read_paragraph, "draft_answer": draft_answer,
           "verify_answer": verify_answer, "finish_question": finish_question}
