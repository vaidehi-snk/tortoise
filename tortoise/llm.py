"""Talks to Ollama on this machine. Standard library only."""
import json
import random
import re
import time
import urllib.error
import urllib.request

from . import config


class ModelUnavailable(RuntimeError):
    """Ollama could not be reached. Callers let Temporal retry this."""


def chat(prompt: str, schema: dict, *, temperature: float = 0.0, seed: int = 0, system: str = ""):
    """Returns (parsed_json_or_None, meta) where meta has ms, tok_in, tok_out."""
    if config.MOCK:
        return _mock(prompt, schema)
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    body = {
        "model": config.MODEL,
        "messages": messages,
        "stream": False,
        "format": schema,
        "keep_alive": "60m",
        "options": {"temperature": temperature, "seed": seed, "num_ctx": config.NUM_CTX},
    }
    req = urllib.request.Request(
        config.OLLAMA + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise ModelUnavailable(f"ollama unreachable at {config.OLLAMA}: {e}") from e
    if "error" in data:
        raise ModelUnavailable(f"ollama error: {data['error']}")
    meta = {
        "ms": round((time.perf_counter() - t0) * 1000),
        "tok_in": data.get("prompt_eval_count", 0),
        "tok_out": data.get("eval_count", 0),
    }
    return parse(data.get("message", {}).get("content", "")), meta


def parse(text: str):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


def _mock(prompt: str, schema: dict):
    """A fake model that returns schema-shaped answers. Only for testing plumbing."""
    time.sleep(0.01)
    props = schema.get("properties", {})
    words = re.findall(r"[A-Z][a-z]+(?: [A-Z][a-z]+)*", prompt.split("QUESTION:")[-1])
    pick = random.Random(len(prompt)).choice(words) if words else "unknown"
    out = {}
    if "relevant" in props:
        para = prompt.split("PARAGRAPH")[-1]
        q = prompt.split("QUESTION:")[1].split("\n")[0] if "QUESTION:" in prompt else ""
        hit = any(w.lower() in para.lower() for w in re.findall(r"\w{5,}", q))
        out = {"relevant": hit, "facts": [para.strip().split(".")[0][:120]] if hit else []}
    elif "supported" in props:
        out = {"supported": True, "short_answer": pick}
    else:
        out = {"reasoning": "mock reasoning", "answer": pick}
    return out, {"ms": 10, "tok_in": len(prompt) // 4, "tok_out": 12}
