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
  <p class=lead>Slipp inn en innkalling eller saksliste til en generalforsamling. Hvert forslag får en foreslått stemme, en konfidens og retningslinjen den bygger på.</p>
</header>
<main class=wrap>
  <div class=upload>
    <div class=drop id=drop tabindex=0>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 15V4M7.5 8.5L12 4l4.5 4.5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>
      <strong>Slipp en fil her</strong><span>eller klikk for å velge. PDF, HTML eller tekst.</span>
      <input id=file type=file accept=".pdf,.htm,.html,.txt" hidden>
    </div>
    <textarea id=text placeholder="Eller lim inn en saksliste" aria-label="Saksliste"></textarea>
    <p id=keyline><label>Anthropic API-nøkkel <input id=key type=password autocomplete=off></label> Holdes bare i minnet på denne maskinen.</p>
    <p class=go><button class="btn primary" id=go type=button>Analyser innlimt saksliste</button><span id=status role=status></span></p>
  </div>
  <section>
    <h2>Tidligere rapporter</h2>
    <div class=tiles>SAMPLES</div>
  </section>
</main>"""
SCRIPT = """<script>
const $ = id => document.getElementById(id), go = $('go'), status = $('status');
async function send(body, name) {
  go.disabled = true; status.textContent = 'Leser dokumentet. Det tar opptil ett minutt.';
  try {
    const reply = await fetch('/review', {method: 'POST', body, headers: {'X-Name': encodeURIComponent(name), 'X-Key': $('key').value.trim()}});
    const data = await reply.json();
    if (data.url) return location = data.url;
    status.textContent = data.error;
    if (reply.status === 401) $('keyline').hidden = false;
  } catch { status.textContent = 'Filen kunne ikke sendes. Den er kanskje for stor.'; }
  go.disabled = false;
}
const take = f => f && send(f, f.name);
$('drop').onclick = () => $('file').click();
$('drop').onkeydown = e => (e.key === 'Enter' || e.key === ' ') && $('file').click();
$('file').onchange = e => take(e.target.files[0]);
$('drop').ondragover = e => { e.preventDefault(); $('drop').classList.add('over'); };
$('drop').ondragleave = () => $('drop').classList.remove('over');
$('drop').ondrop = e => { e.preventDefault(); $('drop').classList.remove('over'); take(e.dataTransfer.files[0]); };
go.onclick = () => $('text').value.trim() ? send($('text').value, 'pasted.txt') : status.textContent = 'Lim inn en saksliste først.';
</script>"""

# Sign-off on a sheet: pick a vote in each proposal, press Log, and a dialog asks for name and reason.
CONTROLS = """<dialog class=logbox id=logbox>
  <form method=dialog id=logform>
    <h3 id=logtitle>Logg beslutning</h3>
    <p id=logwhat></p>
    <div class=seg id=logvote role=group aria-label="Ny stemme" hidden></div>
    <label>Begrunnelse <textarea id=why rows=4></textarea></label>
    <p class=logerror id=logerror role=alert></p>
    <div class=logbuttons><button class=btn type=button id=logcancel>Avbryt</button><button class="btn primary" type=submit>Logg beslutning</button></div>
  </form>
</dialog>
<script>
(() => {
  const main = document.querySelector('main'), box = document.getElementById('logbox'), form = document.getElementById('logform');
  const why = document.getElementById('why'), error = document.getElementById('logerror');
  const LANE = {against: 'Against board', unclear: 'Unclear', with: 'With board'};
  const sheetName = decodeURIComponent(location.pathname.split('/').pop());
  if (!document.querySelector('details.prop')) return;  // sheets from before this design have no sign-off here
  let pending = null;
  // The log needs a named reviewer. The page has no sign-in yet, so it uses a name saved earlier in this browser, or the role.
  let who = 'Stewardship manager';
  try { who = localStorage.getItem('reviewer') || who; } catch {}

  function ask(task) {
    pending = task; error.textContent = ''; why.value = '';
    document.getElementById('logtitle').textContent = task.title;
    document.getElementById('logwhat').textContent = task.what;
    why.required = task.needsReason; why.placeholder = task.needsReason ? 'Hvorfor du endrer den foreslåtte stemmen' : 'Valgfritt';
    const vote = document.getElementById('logvote');
    vote.hidden = !task.choices;  // Change vote: the new vote is one of the other two
    if (task.choices) vote.innerHTML = task.choices.map((v, i) => `<button type=button data-v="${v}" aria-pressed=${i === 0}>${v}</button>`).join('');
    box.showModal(); why.focus();
  }
  document.getElementById('logcancel').onclick = () => box.close();
  document.getElementById('logvote').onclick = e => {
    const b = e.target.closest('button');
    if (b) document.querySelectorAll('#logvote button').forEach(x => x.setAttribute('aria-pressed', x === b));
  };
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (pending.needsReason && !why.value.trim()) { error.textContent = 'En endret stemme trenger en begrunnelse.'; return why.focus(); }
    if (pending.choices) pending.decision = document.querySelector('#logvote [aria-pressed=true]').dataset.v;
    const r = await fetch('/log', {method: 'POST', body: JSON.stringify({company: main.dataset.company, meeting_date: main.dataset.date, item: pending.item,
      decision: pending.decision, reviewer: who, sheet: sheetName, reason: why.value.trim(), ...pending.extra})});
    if (!r.ok) { error.textContent = (await r.json()).error; return; }
    pending.done(); box.close();
  });

  document.querySelectorAll('details.prop').forEach(row => {
    const act = document.createElement('div'), state = document.createElement('span');
    act.className = 'act';
    state.className = 'logged'; state.setAttribute('role', 'status');
    const extra = {proposed_vote: row.dataset.vote, lane: LANE[row.dataset.lane], confidence: row.dataset.score + ' %'};
    const title = row.querySelector('.title strong').textContent;
    if (row.dataset.lane !== 'unclear') {  // a clear proposal keeps its vote unless a person changes it
      act.innerHTML = '<button class=btn type=button>Endre stemme</button>';
      act.append(state);
      act.querySelector('.btn').onclick = () => ask({title: 'Endre stemme',
        what: `Forslag ${row.dataset.item}: ${title}. Foreslått ${row.dataset.vote}.`, item: row.dataset.item, decision: '',
        choices: ['FOR', 'MOT', 'AVSTÅ'].filter(v => v !== row.dataset.vote), needsReason: true, extra,
        done: () => { state.textContent = `Endret til ${pending.decision}`; row.classList.add('approved'); }});
      return row.querySelector('.body').append(act);
    }
    act.innerHTML = '<div class=seg role=group aria-label="Beslutning">' + ['FOR', 'MOT', 'AVSTÅ'].map(v =>
      `<button type=button data-v="${v}" aria-pressed=${v === row.dataset.vote}>${v}</button>`).join('') + '</div><button class="btn primary" type=button>Logg</button>';
    act.append(state);
    const seg = act.querySelector('.seg'), log = act.querySelector('.btn');
    seg.onclick = e => { const b = e.target.closest('button'); if (b) seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b)); };
    log.onclick = () => {
      const decision = seg.querySelector('[aria-pressed=true]').dataset.v;
      ask({title: 'Logg beslutning', what: `Forslag ${row.dataset.item}: ${title}. Beslutning ${decision}, foreslått ${row.dataset.vote}.`,
        item: row.dataset.item, decision, needsReason: decision !== row.dataset.vote,
        extra, done: () => { state.textContent = `Logget ${decision}`; row.classList.add('approved'); }});
    };
    row.querySelector('.body').append(act);
  });
})();
</script>"""


def samples():
    """Earlier reports as tiles, newest first: live reviews and the samples picked by a fixed seed."""
    files = sorted((review.OUT / "sheets").glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)
    tiles = [sheet.tile(data, f"/sheet/{f.name}") for f in files if (data := sheet.sheet_data(f.read_text(encoding="utf-8")))]
    return "".join(tiles) or "<p>Ingen rapporter ennå.</p>"


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
            page = sheet.dark_page("Voting Desk", UPLOAD.replace("SAMPLES", samples()), SCRIPT, lang="no")
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
