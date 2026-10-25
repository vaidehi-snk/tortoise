<!-- TITLE (pick after night 2):
  If night 2 beats the hare: "I gave a 4B model all night to think. Night one it lost. Night two it won."
  If it still loses:          "I gave a 4B model 5× the compute and all night to think. It got worse. Here's why."
Tags: devchallenge, hf26challenge, gemma, temporal
Fill every [N2 …] from `python -m tortoise report --run night-2`. Delete this comment. -->

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

The fable says slow and steady wins the race. I wanted to know if that's true for a language model, so I made one race itself. Same open model, same 4 GB laptop, same fifty questions. One answers immediately. The other gets the whole night.

On the first night, the hare won.

## What I Built

**Tortoise** is that race, built so I can do nothing while it runs. I queue the questions before bed, close the laptop if I want to, and read the result at breakfast.

- **The hare** reads all ten paragraphs at once and answers in one call. Fifty questions took 14 minutes.
- **The tortoise** reads each paragraph on its own, then re-reads the ones it skipped now that it knows what to look for. It writes three drafts from its notes, checks each one against those notes, and plain code votes. Fifty questions took 829 model calls and three hours of wall clock.

Both are **Gemma 3 4B** through Ollama on an RTX 2050 with 4 GB of VRAM. The questions are 50 seeded two-hop questions from HotpotQA ("who directed the film that starred…"), where the answer hides across two of ten paragraphs. The answers are known, so every score below is real exact match.

A night is long and laptops get closed, so every one of the tortoise's 829 steps is a **Temporal** activity. I killed the worker mid-question twice. Both times it came back at the step it was on.

![dashboard](screenshot-1)

## Demo

**Watch the real night replay: [https://tortoise.vaidehi-k.tech](https://tortoise.vaidehi-k.tech)** Press *Replay the night*, then click any hexagon to see what each of them read, wrote and answered.

{% embed YOUR_VIDEO_URL %}

## Code

{% embed https://github.com/vaidehi-snk/tortoise %}

## How I Built It

```
hare      1 call: all 10 paragraphs -> {reasoning, answer}
tortoise  one Temporal workflow per question, every step an activity:
  read     x10  one paragraph at a time       -> {relevant, facts}
  re-read  xN   the skipped ones, with pass-1 facts in hand
  draft    x3   one careful (temp 0), two exploring (temp 0.7)
  check    xM   each distinct answer against the notes
  vote          plain code: +1 per agreeing draft, +2 if the check passed
```

Both get the same answer rules and the same "reason, then answer" format. The only difference is time.

### Night one: the hare won

| | Exact match | F1 | Model calls | Compute |
|---|---|---|---|---|
| Hare | **42%** | 0.57 | 50 | 14 min |
| Tortoise | 34% | 0.43 | 829 | 1 h 8 min |

Five times as much compute, eight points worse. The tortoise got 5 questions the hare missed, and missed 9 that the hare got.

So I measured each slow step on its own:

| Step | Exact match |
|---|---|
| Hare, one call | 42% |
| Tortoise, first draft only | 36% |
| + majority of 3 drafts | 34% |
| + checked against its notes | 34% |

That table told me where it went wrong. **The damage was already done before any voting.** Reading slowly wasn't the problem: the second read found **43 facts** the first read had skipped. The problem was what came next. The tortoise wrote its answers from *its notes*, short sentences it had extracted, and never looked at the paragraphs again. Every note is a small lossy summary. Chain two lossy summaries for a two-hop question and the link between them breaks. The hare, sloppy as it is, still has the actual text in front of it.

The voting didn't help either. The two "exploring" drafts at temperature 0.7 were mostly worse than the careful one, so majority vote pulled answers *down* (36% → 34%).

### Night two: one change

[N2: Pick the paragraph that matches.]

I changed exactly one thing: when the tortoise drafts and checks, it now sees the full text of the paragraphs it flagged, not only its notes. Same questions, same model, same hare.

| | Night 1 | Night 2 |
|---|---|---|
| Hare | 42% | 42% |
| Tortoise | 34% | [N2 %] |

[IF IT WON: write 2–3 sentences. The careful reading picks *which* paragraphs matter; the answer still has to come from the source. Open one amber hexagon on the dashboard and quote what it found on the second read.]

[IF IT LOST: "It closed [x] points of the gap, and still lost. My honest read: a 4B model gains less from more steps than from a better single look at the evidence. Chaining many small model calls compounds small mistakes. Slow and steady only wins if every step is reliable, and at 4B, they aren't yet."]

### Making it durable

A tortoise that has to run all night can't start over every time something goes wrong. Each step is a Temporal activity with a heartbeat every 5 seconds, a 30-second heartbeat timeout, and unlimited retries with backoff. If Ollama goes down, the night waits for it instead of failing.

I killed the worker in the middle of a question twice. The dashboard logged the 1 h 46 min it was quiet, and both comebacks. One step that had finished in the instant before a kill ran a second time. That's Temporal's at-least-once guarantee working exactly as documented: the result hadn't been recorded yet, so it ran again, and because each step's output only depends on its input, a repeat changes nothing.

The method is written once, as pure code with no clock and no randomness, and both Temporal and a plain `--local` loop run that same code.

### What I'd do differently

- Exact match is harsh. The tortoise often wrote "Ed Wood film" for "Ed Wood". F1 (0.43 vs 0.57) says the hare really was better on night one, though, not just tidier.
- One run of fifty questions is a small sample. A few questions either way moves the score by several points.

## Why Does Open Innovation Matter?

1. **Being slow is only free when you own the model.** The tortoise used 335,033 tokens in a night. On my GPU that cost nothing. On a paid API, "think all night" is a bill, so nobody would run this experiment, or learn that it doesn't work, which is the useful part.
2. **I could open up every step.** JSON schemas, temperature per draft, the prompt each step saw, the notes it took. That's how I found the lossy-notes problem. With a closed endpoint, I'd only have seen the 34%.
3. **It runs offline.** After downloading the questions once, the whole night ran with the Wi-Fi off.
4. **Open all the way down:** open weights, an open benchmark, and an open-source durability engine.

Where a closed model would win: a frontier model would probably beat both of mine in one call. It just wouldn't run on my laptop, offline, overnight, for free.

## Prize Categories

- **Best Use of Temporal:** every tortoise step is a durable activity with heartbeats and unlimited retries. I killed the worker twice mid-question and it resumed at the same step, from a deterministic method shared with a local runner.
- **Best Use of Gemma:** Gemma 3 4B is both contestants, running locally through Ollama with structured JSON output.
- **Best Use of a .tech Domain:** the replay lives at tortoise.vaidehi-k.tech.
