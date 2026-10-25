"""The hare: the same model, one call per question, all ten paragraphs at once."""
from . import llm, prompts, store
from .scoring import exact_match, f1


def run(run_name: str) -> None:
    done = store.latest_by_qid(run_name, "hare.jsonl")
    qs = store.questions()
    for n, q in enumerate(qs, 1):
        if q["id"] in done:
            continue
        out, meta = llm.chat(prompts.hare(q["question"], q["paragraphs"]), prompts.ANSWER_SCHEMA)
        out = out or {}
        ans = str(out.get("answer", "")).strip()
        rec = {"qid": q["id"], "answer": ans, "reasoning": str(out.get("reasoning", "")).strip(),
               "gold": q["answer"], "em": exact_match(ans, q["answer"]), "f1": round(f1(ans, q["answer"]), 4), **meta}
        store.append(run_name, "hare.jsonl", rec)
        mark = "ok " if rec["em"] else "-- "
        print(f"[hare {n:>2}/{len(qs)}] {mark}{meta['ms'] / 1000:5.1f}s  {ans[:40]!r}  (gold {q['answer'][:30]!r})")
    print("Hare finished.")
