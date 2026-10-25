# tortoise

**The same small open model, racing itself on one laptop.** The hare answers each question in one call. The tortoise takes all night: it reads every paragraph on its own, re-reads the ones it skipped, writes three drafts, checks each against its notes and lets plain code vote. [Temporal](https://temporal.io) makes every one of those steps durable, so you can kill the worker, close the lid or stop Ollama and it carries on from the exact step it was on.

The questions are 50 seeded two-step questions from [HotpotQA](https://hotpotqa.github.io) (distractor setting): each answer needs facts from two of ten paragraphs. Answers are known, so the score is real exact match, not vibes.

Everything runs on your machine. Nothing leaves it.

## Setup (once)

1. Install [Ollama](https://ollama.com) and pull the model:
   ```
   ollama pull gemma3:4b
   ```
2. Install the Python dependency (Python 3.10+):
   ```
   pip install -r requirements.txt
   ```
3. Download the questions:
   ```
   python -m tortoise fetch
   ```

## Run the race

Open four terminals in this folder.

```
# 1. Temporal (downloads the dev server on first run, keeps history in runs/temporal.db)
python -m tortoise server

# 2. The dashboard  ->  http://127.0.0.1:7878
python -m tortoise serve

# 3. The hare: ~5 minutes
python -m tortoise hare

# 4. The tortoise: start a worker, then start the night (from any terminal)
python -m tortoise worker
python -m tortoise night
```

The Temporal web UI is at http://localhost:8233 if you want to watch the workflows themselves.

### Try to break it

- **Kill the worker** (Ctrl+C in terminal 4) mid-question, wait, then run `python -m tortoise worker` again. It resumes at the same step. The dashboard counts the comeback and how many finished steps ran again (it should be 0).
- **Stop Ollama** for a few minutes. Steps fail, Temporal retries with backoff, and the night continues when the model comes back.
- **Inject failures on purpose:** `set TORTOISE_CHAOS=0.05` (Windows) or `export TORTOISE_CHAOS=0.05`, then start the worker. About 5% of steps fail and get retried. The dashboard shows these separately from real failures.

## Numbers for the write-up

```
python -m tortoise report
```

Prints accuracy for both, where the gain came from (first draft, majority vote, checked vote), results by question type, compute time, tokens and the durability counts. Also saved to `runs/night-1/report.md`.

## Put the dashboard online

```
python -m tortoise export site --domain tortoise.yourname.tech
```

`site/` is a static copy of the finished night (index.html + data.json) with a **Replay the night** button. Host it anywhere: GitHub Pages, Render static site, Netlify.


## Record the demo video

```
pip install playwright edge-tts imageio-ffmpeg
python -m playwright install chromium
python -m tortoise video --run night-1
```

Makes a ~70-second captioned walkthrough from your real data (`tortoise-night-1.webm`, plus `.mp4` if ffmpeg is installed).

## Night two

`TORTOISE_METHOD=v2` (the default) lets drafts and checks see the full paragraphs the tortoise flagged, not only its notes. `v1` is the original method.

## Settings

| Variable | Default | |
|---|---|---|
| `TORTOISE_MODEL` | `gemma3:4b` | any Ollama model |
| `TORTOISE_CTX` | `4096` | context window |
| `TORTOISE_CHAOS` | `0` | share of steps that fail on purpose |
| `TORTOISE_GPU` | | shown on the dashboard, e.g. `RTX 2050 4 GB` |
| `OLLAMA_HOST` | `127.0.0.1:11434` | |
| `TEMPORAL_ADDRESS` | `localhost:7233` | |

No Temporal? `python -m tortoise night --local` runs the same method without durability.

## How it works

```
fetch ─> 50 questions, 10 paragraphs each
hare  ─> 1 call: all paragraphs ─> {reasoning, answer}
tortoise (one Temporal workflow per question, every step an activity):
  read      x10  one paragraph at a time ─> {relevant, facts}
  re-read   xN   the skipped ones, now knowing pass-1 facts   <- catches the second hop
  draft     x3   from the notes only (one careful, two exploring)
  check     xM   each distinct answer against the notes ─> {supported, short_answer}
  vote           plain code: +1 per agreeing draft, +2 if supported
```

Both get the same answer rules and the same "reason, then answer" format, so the only difference is time.

## Files

- `tortoise/pipeline.py`: the tortoise's method, pure code, shared by Temporal and `--local`
- `tortoise/workflows.py`: Temporal workflows (night, question)
- `tortoise/activities.py`: every model call and disk write, with heartbeats
- `tortoise/state.py`: turns the logs into the dashboard and report
- `tortoise/web/index.html`: the dashboard

MIT licensed. HotpotQA is CC BY-SA 4.0.
