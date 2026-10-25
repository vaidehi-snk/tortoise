"""Records a ~75-second captioned walkthrough of a finished night, from your real data.

    pip install playwright edge-tts imageio-ffmpeg
    python -m playwright install chromium
    python -m tortoise video --run night-1

Writes tortoise-<run>.webm (and .mp4 if ffmpeg is installed)."""
import asyncio
import os
import re
import time
import urllib.request
import wave
import functools
import http.server
import json
import pathlib
import shutil
import subprocess
import tempfile
import threading

from . import server

W, H = 1280, 720

CAPTION_CSS = """
#cap{position:fixed;left:50%;bottom:34px;transform:translateX(-50%) translateY(12px);z-index:99;max-width:980px;
  font:500 20px/1.4 'Inter Tight',system-ui,sans-serif;color:#ece7db;text-align:center;padding:14px 26px;border-radius:16px;
  background:rgba(8,12,10,.86);border:1px solid rgba(236,231,219,.16);backdrop-filter:blur(8px);opacity:0;
  transition:opacity .45s ease, transform .45s ease;box-shadow:0 18px 50px rgba(0,0,0,.45)}
#cap.on{opacity:1;transform:translateX(-50%)}
#cap b{color:#a9d98f;font-weight:600} #cap i{font-family:'Instrument Serif',serif;font-size:1.15em;color:#f4b860}
#card{position:fixed;inset:0;z-index:98;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;
  background:#0a0e0c;color:#ece7db;opacity:0;pointer-events:none;transition:opacity .6s ease;text-align:center;padding:40px}
#card.on{opacity:1}
#card h1{font:400 76px/1 'Instrument Serif',serif;letter-spacing:-.02em} #card h1 em{color:#a9d98f}
#card p{font:400 15px/1.6 'JetBrains Mono',monospace;color:#8b968d;letter-spacing:.06em}
"""


def _captions(s: dict) -> dict:
    p, h, t, d = s["paired"], s["hare"], s["tortoise"], s["durability"]
    he, te = round((p["hare_em"] or 0) * 100), round((p["tortoise_em"] or 0) * 100)
    per = (t["ms"] / max(1, t["done"])) / max(1, h["ms"] / max(1, h["done"]))
    won = te > he
    return {
        "open": "Same 4B model. Same 4 GB laptop. Fifty two-step questions. <i>One of them takes its time.</i>",
        "method": "<b>Hare:</b> one call per question. <b>Tortoise:</b> read every paragraph, re-read, three drafts, check, vote.",
        "score": (f"The tortoise won: <b>{te}%</b> vs {he}% exact match." if won else
                  f"The hare won: {he}% vs <b>{te}%</b>. Slower wasn't smarter. <i>That's the interesting part.</i>"),
        "race": f"The tortoise spent <b>{per:.0f}×</b> the compute per question: {t['calls']} model calls overnight, for free, on my own GPU.",
        "shell": f"Every hexagon is a question. <i>Amber</i>: only the tortoise got it ({p['tortoise_only']}). "
                 f"Red: only the hare ({p['hare_only']}).",
        "drawer": "Click any question: what each one read, wrote, and why plain code picked the final answer.",
        "steps": f"The second read found <b>{s['second_read']}</b> facts the first read skipped.",
        "durable": f"I killed the worker mid-question <b>{d['resumes']}×</b>. Temporal handed back the exact step it was on.",
        "end": "Open weights. Open benchmark. Open-source durability. <i>Nothing left the laptop.</i>",
    }


VOICE = os.environ.get("TORTOISE_VOICE", "en-US-AriaNeural")


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("Needs ffmpeg once:  pip install imageio-ffmpeg")


def _spoken(html: str) -> str:
    t = re.sub(r"<[^>]+>", "", html).replace("×", " times").replace("%", " percent")
    return t.replace(" vs ", " versus ").replace("4B", "four-billion-parameter").replace("4 GB", "four gigabyte")


async def _tts(text: str, mp3: str) -> None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:  # ElevenLabs narration (also qualifies for the ElevenLabs category)
        vid = os.environ.get("ELEVENLABS_VOICE", "21m00Tcm4TlvDq8ikWAM")
        req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                                     data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode(),
                                     headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
        pathlib.Path(mp3).write_bytes(await asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=120).read()))
        return
    try:
        import edge_tts
    except ImportError:
        raise SystemExit("Needs a voice once:  pip install edge-tts   (or set ELEVENLABS_API_KEY)")
    await edge_tts.Communicate(text, VOICE, rate="-4%").save(mp3)


def _narrate(lines: dict, folder: str) -> dict:
    """Synthesises every line, returns {key: (wav_path, seconds)}."""
    ff, out = _ffmpeg(), {}
    async def go():
        for k, text in lines.items():
            mp3 = os.path.join(folder, f"{k}.mp3")
            await _tts(text, mp3)
            out[k] = mp3
    print("Writing the voiceover...")
    asyncio.run(go())
    res = {}
    for k, mp3 in out.items():
        wav = mp3[:-4] + ".wav"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", mp3, "-ac", "1", "-ar", "24000", wav], check=True)
        with wave.open(wav) as w:
            res[k] = (wav, w.getnframes() / w.getframerate())
    return res


def _serve(folder: str, port: int):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=folder)
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def _record(url: str, caps: dict, outdir: str, voice: dict, marks: list) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": W, "height": H}, record_video_dir=outdir,
                                        record_video_size={"width": W, "height": H})
        page = await ctx.new_page()
        t0 = time.monotonic()
        await page.goto(url)
        await page.wait_for_selector("#shell .hex")
        await page.add_style_tag(content=CAPTION_CSS + "#banner{display:none!important}")
        await page.evaluate("""() => {
            const c = document.createElement('div'); c.id = 'cap'; document.body.appendChild(c);
            const k = document.createElement('div'); k.id = 'card';
            k.innerHTML = '<h1>The tortoise <em>and the hare</em></h1><p>SAME OPEN MODEL · ONE LAPTOP · ONE NIGHT</p>';
            document.body.appendChild(k);
            window.cap = (h) => { c.classList.remove('on'); setTimeout(() => { c.innerHTML = h; if (h) c.classList.add('on'); }, h ? 380 : 0); };
            window.card = (on, html) => { if (html) k.innerHTML = html; k.classList.toggle('on', on); };
            window.go = (sel, block) => document.querySelector(sel).scrollIntoView({behavior: 'smooth', block: block || 'center'});
        }""")
        wait = page.wait_for_timeout
        ev = page.evaluate

        async def say(key, minimum_ms, caption=True):
            if caption:
                await ev(f"cap({json.dumps(caps[key])})")
            marks.append((key, time.monotonic() - t0 + (0.45 if caption else 0.1)))
            spoken = voice.get(key, (None, 0))[1] * 1000 + 700
            await wait(max(minimum_ms, spoken))

        await ev("card(true)"); await say("card", 2600, caption=False)
        await ev("card(false)"); await wait(700)
        await say("open", 4200)
        await say("method", 5200)
        await ev("go('.scores')"); await say("score", 5200)
        await ev("go('.race')"); await say("race", 5000)
        await ev("cap('')")
        await ev("document.querySelector('#replay').click()"); await wait(900)
        await say("shell", 14500)

        hexes = page.locator("#shell .hex.tonly")
        target = hexes.first if await hexes.count() else page.locator("#shell .hex").first
        await target.hover(); await wait(700)
        await target.click(); await wait(600)
        await ev(f"cap({json.dumps(caps['drawer'])})")
        marks.append(("drawer", time.monotonic() - t0 + 0.45))
        for y in (0, 260, 520, 820):
            await ev(f"document.querySelector('#drawer').scrollTo({{top:{y},behavior:'smooth'}})")
            await wait(max(2000, (voice.get("drawer", (0, 0))[1] * 1000 + 900) / 4))
        await page.keyboard.press("Escape"); await wait(700)

        await ev("go('#ablation')"); await say("steps", 5200)
        await ev("go('#timeline')"); await say("durable", 5500)
        await ev("cap('')")
        await ev("card(true, '<h1>Slow <em>and steady</em></h1><p>" + caps["end"].replace("'", "\\'") + "</p>')")
        await say("end", 3800, caption=False)
        await wait(600)

        video = page.video
        await ctx.close(); await browser.close()
        return await video.path()


def main(run: str) -> None:
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise SystemExit("Needs Playwright once:\n  pip install playwright edge-tts imageio-ffmpeg\n  python -m playwright install chromium")
    tmp = tempfile.mkdtemp(prefix="tortoise-video-")
    site = pathlib.Path(tmp) / "site"
    server.export(run, str(site))
    s = json.loads((site / "data.json").read_text(encoding="utf-8"))["state"]
    if not s["tortoise"]["done"]:
        raise SystemExit(f"Run '{run}' has no finished questions yet.")
    caps = _captions(s)
    lines = {"card": "The tortoise and the hare. Same open model, one laptop, one night."}
    lines.update({k: _spoken(v) for k, v in caps.items()})
    voice = {} if os.environ.get("TORTOISE_NO_VOICE") else _narrate(lines, tmp)
    httpd = _serve(str(site), 7880)
    print("Recording (about 80 seconds, nothing to do)...")
    marks = []
    try:
        raw = asyncio.run(_record("http://127.0.0.1:7880/", caps, tmp, voice, marks))
    finally:
        httpd.shutdown()
    out = pathlib.Path(f"tortoise-{run}.mp4").resolve()
    cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-i", raw]
    clips = [(voice[k][0], t) for k, t in marks if k in voice]
    for wav, _ in clips:
        cmd += ["-i", wav]
    if clips:
        f = ";".join(f"[{i + 1}:a]adelay={int(t * 1000)}:all=1[a{i}]" for i, (_, t) in enumerate(clips))
        f += ";" + "".join(f"[a{i}]" for i in range(len(clips))) + f"amix=inputs={len(clips)}:normalize=0,volume=1.6[aud]"
        cmd += ["-filter_complex", f, "-map", "0:v", "-map", "[aud]", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print(f"Saved {out}")
