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
    <p id=keyline><label>Anthropic API key <input id=key type=password autocomplete=off></label> Kept in memory on this computer.</p>
    <label class=agent><input id=research type=checkbox><span>Agent, exploratory: Claude searches the filing for facts before it drafts. Left off, the review runs three passes, the tested method.</span></label>
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
$('drop').onkeydown = e => (e.key === 'Enter' || e.key === ' ') && $('file').click();
$('file').onchange = e => take(e.target.files[0]);
$('drop').ondragover = e => { e.preventDefault(); $('drop').classList.add('over'); };
$('drop').ondragleave = () => $('drop').classList.remove('over');
$('drop').ondrop = e => { e.preventDefault(); $('drop').classList.remove('over'); take(e.dataTransfer.files[0]); };
go.onclick = () => $('text').value.trim() ? send($('text').value, 'pasted.txt') : status.textContent = 'Paste an agenda first.';
</script>"""

# Sign-off on a sheet: pick a vote in each proposal, press Log, and a dialog asks for name and reason.
CONTROLS = """<dialog class=logbox id=logbox>
  <form method=dialog id=logform>
    <h3 id=logtitle>Log decision</h3>
    <p id=logwhat></p>
    <label>Your name <input type=text id=who autocomplete=name required></label>
    <label>Reason <textarea id=why rows=4></textarea></label>
    <p class=logerror id=logerror role=alert></p>
    <div class=logbuttons><button class=btn type=button id=logcancel>Cancel</button><button class="btn primary" type=submit>Log decision</button></div>
  </form>
</dialog>
<script>
(() => {
  const main = document.querySelector('main'), box = document.getElementById('logbox'), form = document.getElementById('logform');
  const who = document.getElementById('who'), why = document.getElementById('why'), error = document.getElementById('logerror');
  const LANE = {against: 'Against board', unclear: 'Unclear', with: 'With board'};
  const sheetName = decodeURIComponent(location.pathname.split('/').pop());
  if (!document.querySelector('details.prop')) return;  // sheets from before this design have no sign-off here
  let pending = null;
  try { who.value = localStorage.getItem('reviewer') || ''; } catch {}

  function ask(task) {
    pending = task; error.textContent = ''; why.value = '';
    document.getElementById('logtitle').textContent = task.title;
    document.getElementById('logwhat').textContent = task.what;
    why.required = task.needsReason; why.placeholder = task.needsReason ? 'Why you change the proposed vote' : 'Optional';
    box.showModal(); (who.value ? why : who).focus();
  }
  document.getElementById('logcancel').onclick = () => box.close();
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (!who.value.trim()) { error.textContent = 'Enter your name.'; return who.focus(); }
    if (pending.needsReason && !why.value.trim()) { error.textContent = 'A changed vote needs a reason.'; return why.focus(); }
    try { localStorage.setItem('reviewer', who.value.trim()); } catch {}
    const r = await fetch('/log', {method: 'POST', body: JSON.stringify({company: main.dataset.company, meeting_date: main.dataset.date, item: pending.item,
      decision: pending.decision, reviewer: who.value.trim(), sheet: sheetName, reason: why.value.trim(), ...pending.extra})});
    if (!r.ok) { error.textContent = (await r.json()).error; return; }
    pending.done(); box.close();
  });

  document.querySelectorAll('details.prop').forEach(row => {
    const act = document.createElement('div'), state = document.createElement('span');
    act.className = 'act';
    act.innerHTML = '<div class=seg role=group aria-label="Decision">' + ['FOR', 'MOT', 'AVSTÅ'].map(v =>
      `<button type=button data-v="${v}" aria-pressed=${v === row.dataset.vote}>${v}</button>`).join('') + '</div><button class="btn primary" type=button>Log</button>';
    state.className = 'logged'; state.setAttribute('role', 'status'); act.append(state);
    const seg = act.querySelector('.seg'), log = act.querySelector('.btn');
    seg.onclick = e => { const b = e.target.closest('button'); if (b) seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b)); };
    log.onclick = () => {
      const decision = seg.querySelector('[aria-pressed=true]').dataset.v, title = row.querySelector('.title strong').textContent;
      ask({title: 'Log decision', what: `Proposal ${row.dataset.item}: ${title}. Decision ${decision}, proposed ${row.dataset.vote}.`,
        item: row.dataset.item, decision, needsReason: decision !== row.dataset.vote,
        extra: {proposed_vote: row.dataset.vote, lane: LANE[row.dataset.lane], confidence: row.dataset.score + ' %'},
        done: () => { state.textContent = `Logged ${decision}`; row.classList.add('approved'); }});
    };
    row.querySelector('.body').append(act);
  });

  const bar = document.querySelector('.bar-head'), batch = document.createElement('div');
  batch.className = 'batch';
  batch.innerHTML = '<button class=btn type=button>Approve With board batch</button><span class=logged role=status></span>';
  bar.after(batch);
  batch.querySelector('button').onclick = () => ask({title: 'Approve the batch',
    what: `Every proposal With the board on this sheet, ${document.querySelectorAll('details.prop[data-lane=with]').length} in all, is approved as proposed.`,
    item: 'with board batch', decision: 'approve with board batch', needsReason: false, extra: {},
    done: () => { batch.querySelector('.logged').textContent = 'Batch approved'; document.querySelectorAll('details.prop[data-lane=with]').forEach(r => r.classList.add('approved')); }});
})();
</script>"""


def samples():
    """Earlier reports as tiles, newest first: live reviews and the samples picked by a fixed seed."""
    files = sorted((review.OUT / "sheets").glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)
    tiles = [sheet.tile(data, f"/sheet/{f.name}") for f in files if (data := sheet.sheet_data(f.read_text(encoding="utf-8")))]
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
