"""Prints the numbers for the write-up as Markdown, and saves them to runs/<run>/report.md."""
from . import config, state, store


def pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


def dur(ms):
    s = int(ms / 1000)
    return f"{s // 3600} h {(s % 3600) // 60} min" if s >= 3600 else f"{s // 60} min {s % 60} s"


def main(run: str) -> None:
    s = state.build(run)
    h, t, p, d = s["hare"], s["tortoise"], s["paired"], s["durability"]
    lines = [
        f"# Tortoise vs hare: run `{run}`, model `{s['meta']['model']}`, method `{s['meta']['method']}`", "",
        f"Questions: {s['meta']['total']}. Hare answered {h['done']}, tortoise answered {t['done']}.", "",
        "## Accuracy on questions both answered", "",
        "| | Exact match | Model calls | Compute time |", "|---|---|---|---|",
        f"| Hare (one call, all 10 paragraphs) | {pct(p['hare_em'])} | {h['calls']} | {dur(h['ms'])} |",
        f"| Tortoise (read, re-read, 3 drafts, check, vote) | {pct(p['tortoise_em'])} | {t['calls']} | {dur(t['ms'])} |", "",
        f"Tortoise right where the hare was wrong: **{p['tortoise_only']}**. "
        f"Hare right where the tortoise was wrong: **{p['hare_only']}**. Both right: {p['both']}. Neither: {p['neither']}.", "",
        "## Where the gain came from", "", "| Step | Exact match |", "|---|---|",
    ]
    for row in s["ablation"] or []:
        lines.append(f"| {row['label']} | {pct(row['em'])} |")
    lines += ["", "## By question type", "", "| Type | n | Hare | Tortoise |", "|---|---|---|---|"]
    for k, v in s["by_type"].items():
        lines.append(f"| {k} | {v['n']} | {pct(v['hare'])} | {pct(v['tortoise'])} |")
    lines += [
        "", "## The price of slowness", "",
        f"- Tortoise compute: {dur(t['ms'])} total, median {dur(t['median_q_ms'])} per question, {t['tok']:,} tokens.",
        f"- Hare compute: {dur(h['ms'])} total, {h['tok']:,} tokens.",
        f"- Wall clock for the night: {dur(t['wall'] * 1000)}.",
        f"- Facts found only on the second read: {s['second_read']}.", "",
        "## Durability (Temporal)", "",
        f"- Times the worker came back after being stopped: {d['resumes']}",
        f"- Real failures retried (model unreachable): {d['fails']}",
        f"- Injected failures retried (TORTOISE_CHAOS): {d['injected']}",
        f"- Finished steps that ran again after a crash: {d['rerun']}",
        f"- Total quiet time (asleep or stopped): {dur(d['quiet'] * 1000)}",
    ]
    text = "\n".join(lines) + "\n"
    (config.run_dir(run) / "report.md").write_text(text, encoding="utf-8")
    print(text)
