"""Drop a meeting document in the browser and get a proposed vote on every proposal.

  python app.py

Runs on this computer only. The first run installs what it needs. A key comes from .env or the page and is kept in memory.
"""
import boot  # noqa: F401
import json
import os
import re
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from html import unescape
from urllib.parse import unquote

import review
import sheet

PORT = 8501
LIMIT = 40_000_000
TYPES = (".pdf", ".htm", ".html", ".txt")
UPLOAD = """<header class=wrap>
  <p class=eyebrow>Legg til data</p>
  <h1>Voting Desk</h1>
  <p class=lead>Drop a general meeting agenda or proxy statement. Every proposal gets a proposed vote, a confidence and the guideline behind it.</p>
</header>
<main class=wrap>
  <div class=upload>
    <div class=drop id=drop tabindex=0>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 15V4M7.5 8.5L12 4l4.5 4.5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>
      <strong>Drop a file here</strong><span>or click to choose. PDF, HTML or text.</span>
      <input id=file type=file accept=".pdf,.htm,.html,.txt" hidden>
    </div>
    <textarea id=text placeholder="Or paste an agenda" aria-label="Agenda text"></textarea>
    <p id=keyline class=keyline><label>Anthropic API key <input id=key type=password autocomplete=off></label> Kept in memory on this computer.</p>
    <label class=agent><input id=research type=checkbox checked><span>Agent: Claude searches the filing for facts before it drafts. Untick for the three-pass method evaluated on the holdout.</span></label>
    <p class=go><button class="btn primary" id=go type=button>Review pasted agenda</button><span id=status role=status></span></p>
  </div>
  <section>
    <h2>Previous reports</h2>
    <div class=tiles>SAMPLES</div>
  </section>
</main>"""
SCRIPT = """<script>
const $ = id => document.getElementById(id), go = $('go'), status = $('status');
async function send(body, name) {
  go.disabled = true; status.textContent = 'Reading the document. This takes about a minute.';
  try {
    const reply = await fetch('/review', {method: 'POST', body, headers: {'X-Name': encodeURIComponent(name), 'X-Research': $('research').checked ? '1' : '', 'X-Key': $('key') ? $('key').value.trim() : ''}});
    const data = await reply.json();
    if (data.url) return location = data.url;
    status.textContent = data.error;
  } catch { status.textContent = 'That file could not be sent. It may be too large.'; }
  go.disabled = false;
}
const take = f => f && send(f, f.name);
$('drop').onclick = () => $('file').click();
$('drop').onkeydown = e => (e.key === 'Enter' || e.key === ' ') && $('file').click();
$('file').onchange = e => take(e.target.files[0]);
$('drop').ondragover = e => { e.preventDefault(); $('drop').classList.add('over'); };
$('drop').ondragleave = () => $('drop').classList.remove('over');
$('drop').ondrop = e => { e.preventDefault(); $('drop').classList.remove('over'); take(e.dataTransfer.files[0]); };
go.onclick = () => $('text').value.trim() ? send($('text').value, 'pasted.txt') : status.textContent = 'Paste an agenda first.';
</script>"""

# Sign-off for sheets made before the dark design, which use table rows.
OLD_CONTROLS = """<div class=wrap id=sign><h2>Sign-off</h2><p><label>Your name <input id=who></label>
<button id=batch>Approve With board batch</button> <a href="/">New document</a> <span id=done role=status></span></p></div>
<style>#sign input,td select,td input{font:inherit;padding:4px 8px;border:1px solid var(--line)}
button{background:var(--midnight);color:#fff;border:0;border-radius:50px;padding:6px 16px;font:inherit;cursor:pointer}
td .act{margin-top:8px;display:flex;gap:4px;flex-wrap:wrap}td .act input{width:100%}</style>
<script>
const main = document.querySelector('main'), who = document.getElementById('who'), done = document.getElementById('done');
async function log(item, decision, reason, mark) {
  if (!who.value.trim()) { done.textContent = 'Enter your name first.'; who.focus(); return; }
  const r = await fetch('/log', {method: 'POST', body: JSON.stringify({company: main.dataset.company, meeting_date: main.dataset.date, item, decision, reviewer: who.value, reason})});
  mark.textContent = r.ok ? 'Logged' : 'Not logged';
}
document.querySelectorAll('tr[data-item]').forEach(row => {
  const cell = row.lastElementChild, box = document.createElement('div'), pick = document.createElement('select'), note = document.createElement('input'), b = document.createElement('button');
  box.className = 'act'; ['FOR', 'MOT', 'AVSTÅ'].forEach(v => pick.add(new Option(v, v, false, v === row.dataset.vote)));
  note.placeholder = 'Reason, if you change it'; b.textContent = 'Log';
  b.onclick = () => log(row.dataset.item, pick.value, note.value, b);
  box.append(pick, b, note); cell.append(box);
});
document.getElementById('batch').onclick = () => log('with board batch', 'approve with board batch', '', done);
</script>"""
CONTROLS = """<script>
(() => {
const main = document.querySelector('main'), bar = document.querySelector('.bar-head');
const sign = document.createElement('div');
sign.className = 'sign';
sign.innerHTML = '<label>Your name <input type=text id=who></label><button class=btn id=batch type=button>Approve With board batch</button><span id=done role=status></span>';
bar.after(sign);
const who = document.getElementById('who'), done = document.getElementById('done');
async function log(item, decision, reason, mark) {
  if (!who.value.trim()) { done.textContent = 'Enter your name first.'; who.focus(); return; }
  const r = await fetch('/log', {method: 'POST', body: JSON.stringify({company: main.dataset.company, meeting_date: main.dataset.date, item, decision, reviewer: who.value, reason})});
  mark.textContent = r.ok ? 'Logged' : 'Not logged';
}
document.querySelectorAll('details.prop').forEach(row => {
  const box = document.createElement('div'), pick = document.createElement('select'), note = document.createElement('input'), b = document.createElement('button');
  box.className = 'act'; ['FOR', 'MOT', 'AVSTÅ'].forEach(v => pick.add(new Option(v, v, false, v === row.dataset.vote)));
  pick.setAttribute('aria-label', 'Decision'); note.type = 'text'; note.placeholder = 'Reason, if you change it';
  b.className = 'btn primary'; b.type = 'button'; b.textContent = 'Log';
  b.onclick = () => log(row.dataset.item, pick.value, note.value, b);
  box.append(pick, note, b); row.querySelector('.body').append(box);
});
document.getElementById('batch').onclick = () => log('with board batch', 'approve with board batch', '', done);
})();
</script>"""


def old_sheet(html):
    """Company, country, date and counts from a sheet made before the dark design."""
    name, country, day = (re.search(p, html) for p in (r"<h1>(.*?)</h1>", r"Country:</b> ([^<]*)", r"Meeting date:</b> ([^<]*)"))
    figures = dict((k, int(v)) for v, k in re.findall(r"<div><strong>(\d+)</strong>([a-z ]+)</div>", html))
    if not (name and day):
        return None
    return {"company": unescape(name.group(1)), "country": unescape(country.group(1)) if country else "", "meeting_date": day.group(1),
            "counts": {"against": figures.get("against the board", 0), "unclear": figures.get("unclear", 0), "with": figures.get("with the board", 0)}}


def samples():
    files = sorted((review.OUT / "sheets").glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)
    tiles = []
    for f in files:
        html = f.read_text(encoding="utf-8")
        data = sheet.sheet_data(html) or old_sheet(html)
        if data:
            tiles.append(sheet.tile(data, f"/sheet/{f.name}"))
    return "".join(tiles) or "<p>No reports yet.</p>"


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, kind="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def reply(self, code, value):
        self.send(code, json.dumps(value), "application/json")

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            page = sheet.dark_page("Voting Desk", UPLOAD.replace("SAMPLES", samples()), SCRIPT)
            return self.send(200, re.sub(r"<p id=keyline.*?</p>\n", "", page, flags=re.S) if os.getenv("ANTHROPIC_API_KEY", "").strip() else page)
        if self.path.startswith("/sheet/"):
            path = review.OUT / "sheets" / Path(unquote(self.path[7:])).name
            if path.suffix == ".html" and path.is_file():
                html = path.read_text(encoding="utf-8")
                controls = CONTROLS if sheet.sheet_data(html) else OLD_CONTROLS
                return self.send(200, html.replace("</body>", controls + "</body>"))
        self.send(404, "Not found")

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        if size > LIMIT:
            return self.reply(413, {"error": "That file is too large."})
        body = self.rfile.read(size)
        if self.path == "/log":
            try:
                return self.reply(200, review.log_decision(**json.loads(body)))
            except (TypeError, ValueError) as error:
                return self.reply(400, {"error": str(error)})
        if self.headers.get("X-Key"):
            os.environ["ANTHROPIC_API_KEY"] = self.headers["X-Key"]
        if not os.getenv("ANTHROPIC_API_KEY", "").strip():
            return self.reply(401, {"error": "Enter an Anthropic API key above."})
        suffix = Path(unquote(self.headers.get("X-Name", ""))).suffix.lower()
        if suffix not in TYPES:
            return self.reply(415, {"error": "Use a PDF, HTML or text file."})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / f"document{suffix}"
            path.write_bytes(body)
            try:
                result = review.write_review(str(path), research=bool(self.headers.get("X-Research")))
            except Exception as error:  # the browser shows why, nothing is written
                return self.reply(422, {"error": f"Could not review this document: {error}"})
        self.reply(200, {"url": "/sheet/" + Path(result["sheet"]).name})


if __name__ == "__main__":
    print("Loading the vote record...", flush=True)
    review.state()
    for port in range(PORT, PORT + 20):
        try:
            site = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    url = f"http://127.0.0.1:{port}"
    print(f"Ready at {url}", flush=True)
    if "--no-browser" not in sys.argv:
        threading.Timer(.5, webbrowser.open, [url]).start()
    site.serve_forever()
