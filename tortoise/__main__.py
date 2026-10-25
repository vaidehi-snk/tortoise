"""tortoise: the same small model, racing itself. One answers instantly, one takes all night.

    python -m tortoise fetch            download 50 seeded HotpotQA questions (once)
    python -m tortoise hare             the hare: one call per question
    python -m tortoise server           local Temporal server (keep this window open)
    python -m tortoise worker           the tortoise's worker (kill it any time, start it again)
    python -m tortoise night            start the night (safe to run twice)
    python -m tortoise night --local    same method without Temporal (no durability)
    python -m tortoise serve            the dashboard at http://127.0.0.1:7878
    python -m tortoise report           the numbers, as Markdown
    python -m tortoise export site      a static copy of the dashboard for any web host
"""
import argparse
import asyncio
import os
import platform
import sys

from . import config, store


def _hardware() -> str:
    gpu = os.environ.get("TORTOISE_GPU", "")
    return " · ".join(x for x in (gpu, platform.system()) if x)


def _say(msg: str) -> None:
    print(msg, flush=True)


async def _server() -> None:
    from temporalio.testing import WorkflowEnvironment
    config.RUNS.mkdir(parents=True, exist_ok=True)
    db = str(config.RUNS / "temporal.db")
    _say("Starting a local Temporal server (first run downloads it once)...")
    env = await WorkflowEnvironment.start_local(
        port=7233, ui=True, ui_port=8233, dev_server_database_filename=db, dev_server_log_level="error")
    _say(f"Temporal is up on localhost:7233. Web UI: http://localhost:8233   History saved in {db}")
    _say("Leave this window open. Ctrl+C stops the server; the history stays on disk.")
    try:
        await asyncio.Event().wait()
    finally:
        await env.shutdown()


async def _client():
    from temporalio.client import Client
    try:
        return await Client.connect(config.TEMPORAL_ADDRESS)
    except Exception as e:
        raise SystemExit(f"Can't reach Temporal at {config.TEMPORAL_ADDRESS}: {e}\n"
                         "Start it first in another window:  python -m tortoise server")


async def _worker(run: str) -> None:
    from temporalio.worker import Worker
    from . import activities, workflows
    client = await _client()
    store.event(run, type="worker_up", pid=os.getpid(), mode="temporal")
    _say(f"Worker up (pid {os.getpid()}), model {config.MODEL}, method {config.METHOD}. Kill it whenever you like; it resumes where it was.")
    if config.CHAOS:
        _say(f"Chaos mode: about {config.CHAOS:.0%} of steps will fail on purpose and be retried.")
    async with Worker(client, task_queue=config.TASK_QUEUE,
                      workflows=[workflows.TortoiseNight, workflows.TortoiseQuestion],
                      activities=activities.ALL, max_concurrent_activities=1):
        await asyncio.Event().wait()


async def _night(run: str, local: bool) -> None:
    qids = [q["id"] for q in store.questions()]
    if local:
        from . import activities, pipeline
        done = store.latest_by_qid(run, "tortoise.jsonl")
        if not done:
            store.event(run, type="run_start", n=len(qids), model=config.MODEL, method=config.METHOD, mode="local", hardware=_hardware())
        store.event(run, type="worker_up", pid=os.getpid(), mode="local")

        async def step(name, arg):
            return await activities.BY_NAME[name](arg)

        for n, qid in enumerate(qids, 1):
            if qid in done:
                continue
            r = await pipeline.solve(run, qid, step)
            _say(f"[tortoise {n:>2}/{len(qids)}] {'ok' if r['em'] else '--'}  {r['answer'][:50]!r}")
        _say("Night finished.")
        return

    from temporalio.client import WorkflowExecutionStatus
    from temporalio.exceptions import WorkflowAlreadyStartedError
    from .workflows import TortoiseNight
    client = await _client()
    wid = f"tortoise-night-{run}"
    try:
        await client.start_workflow(TortoiseNight.run, {"run": run, "qids": qids}, id=wid, task_queue=config.TASK_QUEUE)
        store.event(run, type="run_start", n=len(qids), model=config.MODEL, method=config.METHOD, mode="temporal", hardware=_hardware())
        _say(f"Night '{run}' started: {len(qids)} questions. Watch it at http://127.0.0.1:{config.PORT} (python -m tortoise serve)")
    except WorkflowAlreadyStartedError:
        desc = await client.get_workflow_handle(wid).describe()
        if desc.status == WorkflowExecutionStatus.RUNNING:
            p = await client.get_workflow_handle(wid).query(TortoiseNight.progress)
            _say(f"Night '{run}' is already running ({p['done']}/{p['total']}). Just keep a worker running.")
        else:
            _say(f"Night '{run}' already finished ({desc.status.name}). Use --run <new name> for another.")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="python -m tortoise", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["fetch", "hare", "server", "worker", "night", "serve", "report", "export", "video"])
    ap.add_argument("out", nargs="?", default="site", help="folder for export")
    ap.add_argument("--run", default="night-1")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--local", action="store_true", help="run the night without Temporal")
    ap.add_argument("--domain", default="", help="custom domain for export (writes CNAME)")
    a = ap.parse_args()

    if a.command == "fetch":
        from .fetch import main as fetch_main
        fetch_main(a.n, a.seed)
    elif a.command == "hare":
        from .hare import run
        run(a.run)
    elif a.command == "server":
        asyncio.run(_server())
    elif a.command == "worker":
        asyncio.run(_worker(a.run))
    elif a.command == "night":
        asyncio.run(_night(a.run, a.local))
    elif a.command == "serve":
        from .server import serve
        serve(a.run)
    elif a.command == "report":
        from .report import main as report_main
        report_main(a.run)
    elif a.command == "video":
        from .video import main as video_main
        video_main(a.run)
    elif a.command == "export":
        from .server import export
        export(a.run, a.out, a.domain)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
