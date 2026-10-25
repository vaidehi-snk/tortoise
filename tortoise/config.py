"""Settings. Everything can be changed with an environment variable."""
import os
import pathlib

ROOT = pathlib.Path(os.environ.get("TORTOISE_HOME", pathlib.Path.cwd()))
DATA = ROOT / "data"
RUNS = ROOT / "runs"
QUESTIONS = DATA / "questions.json"

MODEL = os.environ.get("TORTOISE_MODEL", "gemma3:4b")
NUM_CTX = int(os.environ.get("TORTOISE_CTX", "4096"))


def _ollama_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
    if not host.startswith("http"):
        host = "http://" + host
    return host.replace("0.0.0.0", "127.0.0.1").rstrip("/")


OLLAMA = _ollama_url()

# Fraction of tortoise steps that fail on purpose (Temporal mode only), to show retries.
CHAOS = float(os.environ.get("TORTOISE_CHAOS", "0"))
# Fake model for testing the plumbing without a GPU.
MOCK = os.environ.get("TORTOISE_MOCK") == "1"

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TASK_QUEUE = "tortoise"
PORT = int(os.environ.get("TORTOISE_PORT", "7878"))


def run_dir(run: str) -> pathlib.Path:
    d = RUNS / run
    d.mkdir(parents=True, exist_ok=True)
    return d

# v2: drafts and checks also see the full paragraphs the tortoise flagged, not only its notes.
METHOD = os.environ.get("TORTOISE_METHOD", "v2")
