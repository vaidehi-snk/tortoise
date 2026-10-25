"""Temporal workflows. A night is a list of questions; each question is its own durable
workflow. Kill anything at any moment and it picks up at the step it was on."""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .pipeline import solve

STEP = dict(
    start_to_close_timeout=timedelta(minutes=10),
    heartbeat_timeout=timedelta(seconds=30),   # a killed worker is noticed within 30 s
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=3),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(minutes=1),
        maximum_attempts=0,                    # keep trying: if Ollama is down, wait for it
    ),
)


@workflow.defn(name="TortoiseQuestion")
class TortoiseQuestion:
    @workflow.run
    async def run(self, arg: dict) -> dict:
        async def step(name, payload):
            return await workflow.execute_activity(name, payload, **STEP)

        return await solve(arg["run"], arg["qid"], step)


@workflow.defn(name="TortoiseNight")
class TortoiseNight:
    def __init__(self) -> None:
        self.done = 0
        self.total = 0

    @workflow.run
    async def run(self, arg: dict) -> dict:
        self.total = len(arg["qids"])
        results = []
        for qid in arg["qids"]:
            r = await workflow.execute_child_workflow(
                TortoiseQuestion.run, {"run": arg["run"], "qid": qid},
                id=f"tortoise-{arg['run']}-{qid}",
            )
            results.append(r)
            self.done += 1
        return {"run": arg["run"], "done": self.done,
                "em": sum(r["em"] for r in results) / max(1, len(results))}

    @workflow.query
    def progress(self) -> dict:
        return {"done": self.done, "total": self.total}
