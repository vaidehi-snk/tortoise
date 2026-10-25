"""The tortoise's method, written once. It only calls `step(name, arg)`, so the same code
runs inside a Temporal workflow (each step is a durable activity) or directly (--local).

This module must stay pure: no IO, no clock, no randomness. Temporal replays it."""
from .scoring import normalize

DRAFTS = 3       # independent answers before voting
MAX_KNOWN = 14   # facts carried into drafting


def known_facts(notes: list) -> list:
    out = []
    for n in notes:
        if n and n.get("relevant"):
            for fact in n.get("facts", [])[:3]:
                if fact and fact.strip():
                    out.append({"title": n["title"], "fact": fact.strip()})
    return out[:MAX_KNOWN]


def vote(drafts: list, cands: list, verdicts: list):
    """Plain code picks the answer: one point per draft that agrees, two for passing the check."""
    if not cands:
        return "", {"scores": {}, "rule": "no answer"}
    scores = {}
    for i, c in enumerate(cands):
        agree = sum(1 for d in drafts if normalize(d.get("answer", "")) == normalize(c))
        supported = bool(verdicts[i].get("supported")) if i < len(verdicts) else False
        scores[c] = agree + (2 if supported else 0)
    best = max(cands, key=lambda c: (scores[c], -cands.index(c)))
    i = cands.index(best)
    final = best
    v = verdicts[i] if i < len(verdicts) else {}
    short = (v.get("short_answer") or "").strip()
    # Take the checker's shorter wording only if it still means the same answer.
    if v.get("supported") and short and set(normalize(short).split()) <= set(normalize(best).split()):
        final = short
    return final, {"scores": scores, "picked": best}


async def solve(run: str, qid: str, step) -> dict:
    base = {"run": run, "qid": qid}
    meta = await step("open_question", base)
    n = meta["n"]

    # Pass 1: read every paragraph on its own.
    notes = []
    for i in range(n):
        notes.append(await step("read_paragraph", {**base, "i": i, "pass": 1, "of": n, "known": []}))

    # Pass 2: re-read the paragraphs that looked useless, now knowing what pass 1 found.
    # This is where two-step questions get their second step.
    known = known_facts(notes)
    skipped = [i for i in range(n) if not notes[i].get("relevant")]
    if known:
        for k, i in enumerate(skipped):
            r = await step("read_paragraph", {**base, "i": i, "pass": 2, "of": len(skipped), "pos": k, "known": known})
            if r.get("relevant"):
                notes[i] = r

    known = known_facts(notes)
    drafts = []
    for k in range(DRAFTS):
        drafts.append(await step("draft_answer", {**base, "k": k, "of": DRAFTS, "known": known}))

    cands, seen = [], set()
    for d in drafts:
        a = (d.get("answer") or "").strip()
        if a and normalize(a) and normalize(a) not in seen:
            seen.add(normalize(a))
            cands.append(a)

    verdicts = []
    for j, c in enumerate(cands):
        verdicts.append(await step("verify_answer", {**base, "j": j, "of": len(cands), "candidate": c, "known": known}))

    final, why = vote(drafts, cands, verdicts)
    return await step("finish_question", {
        **base, "final": final, "why": why, "drafts": drafts,
        "cands": cands, "verdicts": verdicts, "notes": notes,
    })
