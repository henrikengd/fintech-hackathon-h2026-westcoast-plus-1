"""Local evidence search explorer. Run: python rag_app.py --no-browser."""
import boot  # noqa: F401
import argparse
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

import rag_results


CSS = """
:root{color-scheme:light;--ink:#001538;--blue:#0026ff;--muted:#536077;--line:#d9dce2;--paper:#f5f2eb}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#fff;font:16px/1.55 system-ui,sans-serif}
.wrap{max-width:1060px;margin:auto;padding:0 24px}.band{background:#f4cea4;font-size:13px;padding:9px 24px}
header{background:var(--paper);padding:40px 0 32px}h1{font-size:40px;line-height:1.15;font-weight:550;margin:0 0 12px}
h2{font-size:22px;font-weight:550;margin:0 0 12px}p{margin:10px 0}.muted{color:var(--muted);font-size:14px}
main{padding-top:28px!important;padding-bottom:48px!important}.stats{display:flex;gap:20px;flex-wrap:wrap;margin:20px 0}
.stats span{border-left:2px solid var(--line);padding-left:12px}.stats b{display:block;font-size:24px;font-weight:550}
form{background:#faf9f5;border:1px solid var(--line);border-radius:12px;padding:24px}.row{display:grid;grid-template-columns:1fr 190px 100px;gap:16px}
label{display:block;font-size:14px;font-weight:550;margin-bottom:6px}input,select,button{font:inherit}
input,select{width:100%;padding:11px 12px;background:#fff;border:1px solid #a9b0bd;border-radius:5px;color:var(--ink)}
.query{margin-top:18px}.actions{display:flex;gap:12px;align-items:center;margin-top:18px;flex-wrap:wrap}
button{border:0;border-radius:28px;background:var(--ink);color:#fff;padding:11px 22px;cursor:pointer}button:disabled{opacity:.5;cursor:wait}
button.example{background:transparent;color:var(--blue);border:1px solid var(--line);font-size:13px;padding:7px 12px}
a{color:var(--blue)}:focus-visible{outline:3px solid #6680ff;outline-offset:3px}#status{margin:22px 0}
.result{padding:24px 0;border-top:1px solid var(--line)}.result h2{font-size:19px}.quote{white-space:pre-wrap;border-left:3px solid #b5c4f5;padding-left:16px;margin:16px 0}
.links{display:flex;gap:20px;flex-wrap:wrap;font-size:14px}.badge{display:inline-block;font-size:12px;padding:3px 9px;border-radius:12px;background:#e7f6f8;margin-bottom:10px}
.source{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.7 system-ui,sans-serif}mark{background:#fff0ac;color:inherit;scroll-margin-top:30px}
.error{color:#a12020}footer{border-top:1px solid var(--line);padding:22px 0;color:var(--muted);font-size:13px}
.evaluation-section{padding:0 0 28px;margin:0 0 28px;border-bottom:1px solid var(--line)}.evaluation-section:last-child{border:0;margin:0;padding:0}
.evaluation-section h3{font-size:17px;font-weight:550;margin:24px 0 6px}.table-scroll{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}caption{text-align:left;padding:12px;background:var(--paper);font-weight:550}
th,td{text-align:right;padding:11px 10px;vertical-align:top;border-bottom:1px solid var(--line)}th:first-child{text-align:left;min-width:165px}
thead th{font-size:12px;background:#faf9f5}tbody th{font-weight:500}tbody tr:last-child>*{border-bottom:0}td{white-space:nowrap}
details{margin-top:18px}summary{cursor:pointer;color:var(--blue)}.artifact-status{display:flex;gap:8px;flex-wrap:wrap}
@media(max-width:700px){h1{font-size:30px}.row{grid-template-columns:1fr 1fr}.row>div:first-child{grid-column:1/-1}form{padding:18px}.wrap{padding-left:18px;padding-right:18px}}
"""


def page(title, body):
    return ('<!doctype html><html lang="nb"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><style>{CSS}</style></head><body>'
            '<div class="band">Westcoast + 1 · Lokalt RAG-forsøk · Studentprosjekt</div>'
            f'{body}<footer><div class="wrap">Lokalt studentprosjekt · Utforskende analyser og dokumentsøk · En person må godkjenne alle stemmeanbefalinger.</div></footer></body></html>')


PAGE = page("Lokalt kildesøk · Voting Desk", """
<header><div class="wrap"><h1>Finn grunnlaget for vurderingen</h1>
<p>Søk i møtedokumentene og åpne hvert treff i sin opprinnelige sammenheng.</p>
<p><a href="/evaluation">Se resultatene fra modelltestingen →</a></p>
<div id="stats" class="stats" aria-live="polite"></div>
<p id="model" class="muted"></p></div></header>
<main class="wrap"><form id="search-form">
<div class="row"><div><label for="meeting">Generalforsamling</label><select id="meeting" required></select></div>
<div><label for="mode">Søkemetode</label><select id="mode"><option value="hybrid">Kombinert</option><option value="keyword">Nøkkelord</option><option value="vector">Vektorsøk</option></select></div>
<div><label for="k">Antall treff</label><select id="k"><option>5</option><option>10</option><option>20</option></select></div></div>
<div class="query"><label for="query">Hva vil du finne dokumentasjon på?</label>
<input id="query" maxlength="500" required placeholder="director independence committee membership" autocomplete="off"></div>
<p class="muted">Dokumentene og søkemodellen er engelske. Bruk gjerne engelske søkeord. Kombinert søk bruker både nøkkelord og meningslikhet.</p>
<div class="actions"><button id="go" type="submit" disabled>Søk i dokumentene</button>
<button type="button" class="example" data-query="director independence committee membership">Styrets uavhengighet</button>
<button type="button" class="example" data-query="executive compensation performance targets">Godtgjørelse</button></div>
</form><p id="status" role="status" aria-live="polite">Laster den lokale indeksen …</p><div id="results"></div></main>
<script>
const $ = id => document.getElementById(id);
function node(tag, text, cls) { const n = document.createElement(tag); n.textContent = text; if (cls) n.className = cls; return n; }
async function get(path) { const response = await fetch(path); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Forespørselen mislyktes.'); return data; }
function safeSource(url) { try { const u = new URL(url); return u.protocol === 'https:' && ['sec.gov','www.sec.gov'].includes(u.hostname) && !u.username && !u.password && (!u.port || u.port === '443'); } catch { return false; } }
function showResults(hits) {
  $('results').replaceChildren();
  hits.forEach((hit, i) => {
    const card = node('article', '', 'result');
    card.append(node('span', 'Treff ' + (i + 1), 'badge'), node('h2', hit.heading || 'Utdrag fra møtedokumentet'));
    card.append(node('p', hit.company + ' · Møte ' + hit.meeting_date + ' · Dokument publisert ' + hit.filed, 'muted'));
    card.append(node('blockquote', hit.text, 'quote'));
    const links = node('div', '', 'links');
    const local = node('a', 'Les utdraget i sammenheng');
    local.href = '/source?' + new URLSearchParams({id: hit.document_id, start: hit.start, end: hit.end}) + '#excerpt';
    local.target = '_blank'; local.rel = 'noopener'; links.append(local);
    if (safeSource(hit.url)) { const original = node('a', 'Åpne original hos SEC'); original.href = hit.url; original.target = '_blank'; original.rel = 'noopener noreferrer'; links.append(original); }
    card.append(links); $('results').append(card);
  });
}
document.querySelectorAll('[data-query]').forEach(b => b.onclick = () => { $('query').value = b.dataset.query; $('query').focus(); });
$('search-form').onsubmit = async event => {
  event.preventDefault(); $('go').disabled = true; $('status').className = '';
  $('status').textContent = 'Søker lokalt. Første vektorsøk kan ta litt tid mens modellen lastes.'; $('results').replaceChildren();
  try { const result = await get('/search?' + new URLSearchParams({q: $('query').value, meeting_id: $('meeting').value, k: $('k').value, mode: $('mode').value})); showResults(result.hits); $('status').textContent = result.hits.length ? result.hits.length + ' treff. Kontroller at utdragene støtter vurderingen du skal gjøre.' : 'Ingen treff. Prøv andre engelske søkeord eller en annen søkemetode.'; }
  catch (error) { $('status').textContent = error.message; $('status').className = 'error'; }
  finally { $('go').disabled = !$('meeting').value; }
};
Promise.all([get('/status'), get('/meetings')]).then(([status, meetings]) => {
  [['Dokumenter', status.documents], ['Kildeutdrag', status.chunks]].forEach(([label, value]) => { const item = node('span', label); item.prepend(node('b', String(value))); $('stats').append(item); });
  $('model').textContent = 'Lokal modell: ' + status.model + '. Dokumentene er filtrert på tilgjengelighet før møtets beslutningstidspunkt.';
  meetings.forEach(m => $('meeting').add(new Option(m.company + ' · ' + m.meeting_date, m.meeting_id)));
  $('go').disabled = !meetings.length; $('status').textContent = meetings.length ? 'Velg et møte og søk etter opplysningene du trenger.' : 'Indeksen inneholder ingen møter.';
}).catch(error => { $('status').textContent = error.message; $('status').className = 'error'; });
</script>
""")


def safe_sec_url(value):
    try:
        url = urlsplit(value)
        return url.scheme == "https" and url.hostname in ("sec.gov", "www.sec.gov") and not url.username and not url.password and url.port in (None, 443)
    except (ValueError, TypeError):
        return False


def source_page(document, start=0, end=0):
    text = document["text"]
    if not 0 <= start <= end <= len(text):
        raise ValueError("Ugyldig plassering av kildeutdraget.")
    marked = escape(text[:start]) + '<mark id="excerpt">' + escape(text[start:end]) + '</mark>' + escape(text[end:])
    url = document.get("url", "")
    link = f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">Originaldokument hos SEC</a>' if safe_sec_url(url) else ""
    title = f"{document['company']} · {document['meeting_date']}"
    return page(title, f'<header><div class="wrap"><p><a href="/">← Tilbake til søket</a></p><h1>{escape(title)}</h1>'
                f'<p>Dokument publisert {escape(document["filed"])} · {link}</p>'
                '<p class="muted">Tekstuttrekk fra originaldokumentet. Markeringen viser det hentede utdraget.</p></div></header>'
                f'<main class="wrap"><div class="source">{marked}</div></main>')


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, kind="text/html; charset=utf-8"):
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(encoded)

    def reply(self, code, data):
        self.send(code, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")

    def log_message(self, *args):
        pass

    def do_GET(self):
        port = self.server.server_port
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return self.reply(403, {"error": "Kun lokale forespørsler er tillatt."})
        if len(self.path) > 4096:
            return self.reply(414, {"error": "Forespørselen er for lang."})
        parsed = urlsplit(self.path)
        args = parse_qs(parsed.query)
        arg = lambda key, default="": args.get(key, [default])[0]
        index = self.server.index
        try:
            if index is None:
                if parsed.path in ("/", "/evaluation"):
                    return self.send(200, page("Modelltesting · Voting Desk", rag_results.render_body(source_search=False)))
                return self.reply(404, {"error": "Dokumentsøk krever oppstart med en lokal indeks."})
            if parsed.path == "/":
                return self.send(200, PAGE)
            if parsed.path == "/evaluation":
                return self.send(200, page("Modelltesting · Voting Desk", rag_results.render_body()))
            if parsed.path == "/vector":
                import vector_app
                code, body = vector_app.render_body(query=arg("q"), meeting=arg("meeting"), item=arg("item"))
                return self.send(code, page("Lokal vektormodell · Voting Desk", body))
            if parsed.path == "/status":
                return self.reply(200, index.status())
            if parsed.path == "/meetings":
                return self.reply(200, index.meetings())
            if parsed.path == "/search":
                query, meeting, mode = arg("q").strip(), arg("meeting_id"), arg("mode", "hybrid")
                k = int(arg("k", "5"))
                if not query or len(query) > 500 or not 1 <= k <= 20 or mode not in ("keyword", "vector", "hybrid"):
                    raise ValueError("Bruk et søk på 1–500 tegn, en gyldig søkemetode og 1–20 treff.")
                if meeting not in {str(m["meeting_id"]) for m in index.meetings()}:
                    raise ValueError("Velg en generalforsamling fra listen.")
                return self.reply(200, {"hits": index.search(query, meeting, k=k, mode=mode)})
            if parsed.path == "/source":
                document = index.document(arg("id"))
                if not document:
                    return self.reply(404, {"error": "Dokumentet finnes ikke i indeksen."})
                return self.send(200, source_page(document, int(arg("start", "0")), int(arg("end", "0"))))
            return self.reply(404, {"error": "Siden finnes ikke."})
        except (ValueError, KeyError) as error:
            return self.reply(400, {"error": str(error)})
        except Exception as error:
            print(f"RAG request failed: {error}", file=sys.stderr, flush=True)
            return self.reply(503, {"error": "Søket kunne ikke fullføres. Kontroller lokal indeks og modell i terminalen."})


def main(argv=None):
    from local_rag import DEFAULT_DB, RagIndex

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--results-only", action="store_true", help="Serve saved reports without a document index")
    args = parser.parse_args(argv)
    try:
        index = None if args.results_only else RagIndex(args.db)
        server = HTTPServer(("127.0.0.1", args.port), Handler)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Cannot start local RAG search: {error}\n")
    server.index = index
    path = "/evaluation" if args.results_only else "/"
    url = f"http://127.0.0.1:{server.server_port}{path}"
    print(f"{'Resultatside' if args.results_only else 'Lokalt kildesøk'}: {url}", flush=True)
    if not args.no_browser:
        threading.Timer(.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if index is not None:
            index.close()


if __name__ == "__main__":
    main()
