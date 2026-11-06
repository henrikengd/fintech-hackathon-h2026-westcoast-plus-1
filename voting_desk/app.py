"""Drop a meeting document in the browser and get a proposed vote on every proposal.

  python app.py

Runs on this computer only. The first run installs what it needs. A key comes from .env or the page and is kept in memory.
"""
import boot  # noqa: F401
import json
import os
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import anthropic

import review
import sheet

PORT = 8501
LIMIT = 40_000_000
TYPES = (".pdf", ".htm", ".html", ".txt")
PAGE = sheet.page("Voting Desk", """<header><div class=wrap><h1>Voting Desk</h1>
<p>Drop a general meeting agenda or proxy statement. Every proposal gets a proposed vote, a confidence and the guideline behind it.</p></div></header>
<main class=wrap>
<div id=drop tabindex=0><b>Drop a file here</b><br>or click to choose. PDF, HTML or text.<input id=file type=file accept=".pdf,.htm,.html,.txt" hidden></div>
<p><textarea id=text rows=5 placeholder="Or paste an agenda"></textarea></p>
<p><label><input id=research type=checkbox> Agent, exploratory: Claude searches the filing for facts before it drafts. Left off, the review runs three passes, the tested method.</label></p>
<p id=keyline><label>Anthropic API key <input id=key type=password autocomplete=off></label> Kept in memory on this computer.</p>
<p><button id=go>Review pasted agenda</button> <span id=status role=status></span></p>
<h2>Sample reviews from the test sets, picked by a fixed seed</h2><p>SAMPLES</p>
</main>
<style>
#drop{border:1px dashed var(--line);background:var(--sky);padding:64px 24px;text-align:center;cursor:pointer;margin-top:32px}
#drop.over{background:var(--polar);border-color:var(--blue)}
textarea,#key{width:100%;font:inherit;padding:12px;border:1px solid var(--line);color:inherit}#key{max-width:420px;display:block;margin-top:4px}
button{background:var(--midnight);color:#fff;border:0;border-radius:50px;padding:12px 24px;font:inherit;font-weight:400;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
</style>
<script>
const $ = id => document.getElementById(id), go = $('go'), status = $('status');
async function send(body, name) {
  go.disabled = true; status.textContent = 'Reading the document. This takes up to a minute.';
  try {
    const reply = await fetch('/review', {method: 'POST', body, headers: {'X-Name': encodeURIComponent(name), 'X-Research': $('research').checked ? '1' : '', 'X-Key': $('key').value.trim()}});
    const data = await reply.json();
    if (data.url) return location = data.url;
    status.textContent = data.error;
    if (reply.status === 401) $('keyline').hidden = false;
  } catch { status.textContent = 'That file could not be sent. It may be too large.'; }
  go.disabled = false;
}
const take = f => f && send(f, f.name);
$('drop').onclick = () => $('file').click();
$('file').onchange = e => take(e.target.files[0]);
$('drop').ondragover = e => { e.preventDefault(); $('drop').classList.add('over'); };
$('drop').ondragleave = () => $('drop').classList.remove('over');
$('drop').ondrop = e => { e.preventDefault(); $('drop').classList.remove('over'); take(e.dataTransfer.files[0]); };
go.onclick = () => $('text').value.trim() ? send($('text').value, 'pasted.txt') : status.textContent = 'Paste an agenda first.';
</script>""")

CONTROLS = """<div class=wrap id=sign><h2>Sign-off</h2><p><label>Your name <input id=who></label>
<button id=batch>Approve With board batch</button> <a href="/">New document</a> <span id=done role=status></span></p></div>
<style>#sign input,td select,td input{font:inherit;padding:4px 8px;border:1px solid var(--line)}
button{background:var(--midnight);color:#fff;border:0;border-radius:50px;padding:6px 16px;font:inherit;cursor:pointer}
td .act{margin-top:8px;display:flex;gap:4px;flex-wrap:wrap}td .act input{width:100%}</style>
<script>
const main = document.querySelector('main'), who = document.getElementById('who'), done = document.getElementById('done');
async function log(item, decision, reason, mark, row) {
  if (!who.value.trim()) { done.textContent = 'Enter your name first.'; who.focus(); return; }
  const r = await fetch('/log', {method: 'POST', body: JSON.stringify({company: main.dataset.company, meeting_date: main.dataset.date, item, decision, reviewer: who.value, sheet: decodeURIComponent(location.pathname.split('/').pop()), reason, proposed_vote: row ? row.dataset.vote : '', lane: row ? row.dataset.lane : '', confidence: row ? row.children[4].textContent : ''})});
  mark.textContent = r.ok ? 'Logged' : (await r.json()).error;
}
document.querySelectorAll('tr[data-item]').forEach(row => {
  const cell = row.lastElementChild, box = document.createElement('div'), pick = document.createElement('select'), note = document.createElement('input'), b = document.createElement('button');
  box.className = 'act'; ['FOR', 'MOT', 'AVSTÅ'].forEach(v => pick.add(new Option(v, v, false, v === row.dataset.vote)));
  note.placeholder = 'Reason'; b.textContent = 'Log';
  b.onclick = () => log(row.dataset.item, pick.value, note.value, b, row);
  box.append(pick, b, note); cell.append(box);
});
document.getElementById('batch').onclick = () => log('with board batch', 'approve with board batch', '', done);
</script>"""


def samples():
    files = sorted(f for f in (review.OUT / "sheets").glob("*.html") if f.name.startswith(review.SAMPLE_SHEETS))
    return " · ".join(f'<a href="/sheet/{f.name}">{f.stem.split("_", 1)[1].replace("_", " ").strip()}</a>' for f in files)


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
            page = PAGE.replace("SAMPLES", samples())
            return self.send(200, page.replace("<p id=keyline>", "<p id=keyline hidden>") if os.getenv("ANTHROPIC_API_KEY", "").strip() else page)
        if self.path.startswith("/sheet/"):
            path = review.OUT / "sheets" / Path(unquote(self.path[7:])).name
            if path.suffix == ".html" and path.is_file():
                return self.send(200, path.read_text(encoding="utf-8").replace("</body>", CONTROLS + "</body>"))
        self.send(404, "Not found")

    def do_POST(self):
        host, origin = self.headers.get("Host", ""), self.headers.get("Origin")
        if host.split(":")[0] not in ("127.0.0.1", "localhost") or origin not in (None, f"http://{host}"):  # browsers send Origin on any post from another site
            return self.reply(403, {"error": "Only this page can write here."})
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
            except anthropic.AuthenticationError:  # drop the key, so a reload shows the box too
                os.environ.pop("ANTHROPIC_API_KEY", None)
                return self.reply(401, {"error": "The API key was rejected. Enter a valid key above."})
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
