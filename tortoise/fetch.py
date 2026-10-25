"""Downloads a fixed, seeded sample of HotpotQA (distractor setting, dev split).

Each question comes with 10 paragraphs: the 2 that hold the answer and 8 distractors.
Everything after this download runs offline."""
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

HF_ROWS = "https://datasets-server.huggingface.co/rows"
CMU = "http://curtis.ml.cmu.edu/datasets/hotpot/hotpot_dev_distractor_v1.json"
DEV_SIZE = 7405


def _from_hf(row: dict) -> dict:
    ctx = row["context"]
    paras = [{"title": t, "text": " ".join(s).strip()} for t, s in zip(ctx["title"], ctx["sentences"])]
    return {"id": row["id"], "question": row["question"], "answer": row["answer"], "type": row["type"],
            "level": row.get("level", ""), "paragraphs": paras,
            "supporting": sorted(set(row["supporting_facts"]["title"]))}


def _from_cmu(row: dict) -> dict:
    paras = [{"title": t, "text": " ".join(s).strip()} for t, s in row["context"]]
    return {"id": row["_id"], "question": row["question"], "answer": row["answer"], "type": row["type"],
            "level": row.get("level", ""), "paragraphs": paras,
            "supporting": sorted({t for t, _ in row["supporting_facts"]})}


def _get(url: str, timeout=60, tries=7):
    """GET JSON, waiting politely and retrying when the server says 'too many requests'."""
    for k in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": "tortoise/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or k == tries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or min(120, 5 * 2 ** k)
            print(f"  server busy ({e.code}), waiting {wait} s and trying again...")
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as e:
            if k == tries - 1:
                raise
            print(f"  network hiccup ({e}), retrying in 5 s...")
            time.sleep(5)


PAGE = 100


def fetch(n: int = 50, seed: int = 2026) -> list:
    """Picks n questions with a fixed seed: a few random pages of 100, then n spread across them.
    Only a handful of requests, so the API never rate-limits it."""
    rng = random.Random(seed)
    pages = max(1, -(-n // 10))  # 10 questions from each page
    starts = sorted(rng.sample(range(0, DEV_SIZE - PAGE, PAGE), pages))
    picked = []
    try:
        for i, start in enumerate(starts):
            qs = urllib.parse.urlencode({"dataset": "hotpotqa/hotpot_qa", "config": "distractor",
                                         "split": "validation", "offset": start, "length": PAGE})
            rows = [r["row"] for r in _get(f"{HF_ROWS}?{qs}")["rows"]]
            take = min(len(rows), n - len(picked), -(-n // pages))
            picked += [_from_hf(r) for r in rng.sample(rows, take)]
            print(f"  page {i + 1}/{len(starts)}  ({len(picked)}/{n} questions)")
            time.sleep(1)
        return picked[:n]
    except Exception as e:
        print(f"Hugging Face failed ({e}). Trying the original CMU file (46 MB)...")
    try:
        rows = _get(CMU, timeout=600, tries=3)
    except Exception as e:
        raise SystemExit(
            f"Could not download HotpotQA from either source ({e}).\n"
            "Wait a few minutes and run  python -m tortoise fetch  again "
            "(Hugging Face rate limits clear quickly).")
    rng = random.Random(seed)
    return [_from_cmu(rows[i]) for i in sorted(rng.sample(range(len(rows)), n))]


def main(n: int, seed: int) -> None:
    config.DATA.mkdir(parents=True, exist_ok=True)
    qs = fetch(n, seed)
    config.QUESTIONS.write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {}
    for q in qs:
        kinds[q["type"]] = kinds.get(q["type"], 0) + 1
    print(f"\nSaved {len(qs)} questions to {config.QUESTIONS}  {kinds}")
