"""Read-only explorer for saved local vector predictions; no model or API imports."""
import csv
from html import escape
import json
import math
from pathlib import Path
import re
from urllib.parse import urlencode

from rag_results import number, table


BASE = Path(__file__).resolve().parent / "data/local-rag/vector-experiment-v1"
PREDICTIONS = {"MOT": "MOT", "NOT_MOT": "Ikke-MOT", "UNKNOWN": "Ukjent · ingen klassifikasjon"}
VOTES = {"FOR", "MOT", "AVSTÅ"}


def text(value):
    return escape(str(value)) if value is not None else "—"


def numeric(value, digits=None):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        rendered = format(value, f".{digits}f") if digits is not None else format(value, ".6f").rstrip("0").rstrip(".")
        return rendered.replace(".", ",")
    return "—"


def frame(body):
    return ('<style>.vector-neighbors td:nth-child(3){white-space:normal;min-width:260px;max-width:420px}</style>'
            '<header><div class="wrap"><p><a href="/evaluation">← Tilbake til resultatene</a></p>'
            '<h1>Utforsk den lokale vektormodellen</h1><p>Se hvilke historiske saker som ligger bak en lagret klassifikasjon.</p>'
            '<p class="muted">Denne siden leser lokale resultater. Den kjører ikke modellen og gjør ingen API-kall.</p>'
            '</div></header><main class="wrap">' + body + '</main>')


def read_snapshots(base):
    try:
        summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
        neighbors = json.loads((base / "neighbors.json").read_text(encoding="utf-8"))
        if not isinstance(summary, dict) or numeric(summary.get("selected_threshold")) == "—" or not isinstance(neighbors, dict) or not isinstance(neighbors.get("items"), list):
            return None
        if not all(isinstance(item, dict) for item in neighbors["items"]):
            return None
        return summary, neighbors["items"]
    except (OSError, ValueError):
        return None


def outcome(base, meeting, item):
    """Outcome labels are read only for a separately marked after-prediction check."""
    try:
        with (base / "development.csv").open(encoding="utf-8-sig", newline="") as handle:
            matches = [row.get("nbim_vote") for row in csv.DictReader(handle)
                       if row.get("meeting_id") == meeting and row.get("item_no") == item]
        return matches[0] if len(matches) == 1 and matches[0] in VOTES else None
    except (OSError, ValueError, csv.Error):
        return None


def search_body(items, query):
    terms = query.casefold().split()
    matches = [item for item in items if all(term in (str(item.get("company", "")) + " " + str(item.get("proposal_text", ""))).casefold() for term in terms)]
    chunks = ['<form action="/vector" method="get"><label for="vector-query">Selskap eller sak</label>'
              f'<input id="vector-query" name="q" maxlength="200" value="{escape(query, quote=True)}" placeholder="Tesla compensation">'
              '<div class="actions"><button type="submit">Finn lagrede saker</button></div></form>',
              f'<p class="muted">Viser {min(20, len(matches))} av {len(matches)} treff. Søk mer presist for å finne en bestemt sak.</p>']
    for item in matches[:20]:
        url = "/vector?" + urlencode({"meeting": str(item.get("meeting_id", "")), "item": str(item.get("item_no", ""))})
        chunks.append('<article class="result">'
                      f'<h2><a href="{escape(url, quote=True)}">{text(item.get("company"))} · sak {text(item.get("item_no"))}</a></h2>'
                      f'<p>{text(item.get("proposal_text"))}</p><p class="muted">Møtedato: {text(item.get("meeting_date"))}</p></article>')
    if not matches:
        chunks.append('<p>Ingen lagrede saker passer til søket.</p>')
    return "".join(chunks)


def detail_body(summary, item, base):
    prediction = PREDICTIONS.get(item.get("prediction"), PREDICTIONS["UNKNOWN"])
    chunks = ['<p><a href="/vector">← Finn en annen sak</a></p>'
              f'<section class="evaluation-section"><h2>{text(item.get("company"))} · sak {text(item.get("item_no"))}</h2>'
              f'<p>{text(item.get("proposal_text"))}</p><p class="muted">Møtedato: {text(item.get("meeting_date"))} · '
              f'Styrets anbefaling: {text(item.get("mgmt_rec"))} · Forslagsstiller: {text(item.get("proponent"))}</p>'
              f'<p><strong>Modellens klassifikasjon: {text(prediction)}</strong></p>'
              f'<p>Rå modellskår: <strong>{numeric(item.get("score"))}</strong> · terskel for MOT: '
              f'<strong>{numeric(summary.get("selected_threshold"))}</strong>.</p>'
              '<p class="muted">Skår lik eller over terskelen gir MOT. Tallene vises avrundet; klassifikasjonen bruker full presisjon. '
              'Skåren er en vektet andel historiske MOT-stemmer, ikke en kalibrert sannsynlighet eller sikkerhet. '
              'Ikke-MOT skiller ikke mellom FOR og AVSTÅ.</p></section>']
    counts = item.get("neighbor_vote_counts") if isinstance(item.get("neighbor_vote_counts"), dict) else {}
    chunks.append('<section class="evaluation-section"><h2>Historiske saker bak klassifikasjonen</h2>'
                  f'<p>{number(item.get("neighbor_count"))} naboer ble brukt av {number(item.get("history_count"))} tilgjengelige historiske saker. '
                  f'Stemmer blant alle brukte naboer: FOR {number(counts.get("FOR"))} · MOT {number(counts.get("MOT"))} · AVSTÅ {number(counts.get("AVSTÅ"))}.</p>')
    if item.get("conflicting_votes") is True:
        chunks.append('<p>Naboene har ulike historiske stemmer. Vektingen avgjør den samlede modellskåren.</p>')
    neighbors = item.get("neighbors") if isinstance(item.get("neighbors"), list) else []
    neighbors = [neighbor for neighbor in neighbors if isinstance(neighbor, dict)][:5]
    rows = [[str(neighbor.get("company", "—")), str(neighbor.get("meeting_date", "—")),
             str(neighbor.get("proposal_text", "—")), neighbor.get("nbim_vote") if neighbor.get("nbim_vote") in VOTES else "—",
             numeric(neighbor.get("similarity"), 4), numeric(neighbor.get("weight"), 4)] for neighbor in neighbors]
    if rows:
        chunks.append('<div class="vector-neighbors">' + table(["Selskap", "Møtedato", "Historisk sak", "NBIM-stemme", "Likhet", "Vekt"], rows, "Inntil fem historiske naboer · alle valgte naboer inngår i skåren") + '</div>')
    else:
        chunks.append('<p class="muted">Ingen historiske naboer er lagret for denne saken.</p>')
    chunks.append('<p class="muted">Likhet måler hvor nær sakstekstene er i vektorrommet. Historisk likhet dokumenterer ikke samsvar med retningslinjene og gir ikke et regel- eller kildesitat. '
                  'Dette er en klassifikasjon av MOT versus ikke-MOT, ikke en full stemmeanbefaling.</p></section>')
    gold = outcome(base, str(item.get("meeting_id", "")), str(item.get("item_no", "")))
    chunks.append('<details><summary>NBIMs stemme · fasit til etterkontroll</summary>'
                  '<p>Dette er det registrerte utfallet for utviklingssaken. Det vises separat for å kontrollere den lagrede prediksjonen og er ikke modellens svar.</p>'
                  f'<p>Registrert NBIM-stemme: <strong>{text(gold) if gold else "Ikke tilgjengelig"}</strong>.</p></details>')
    return "".join(chunks)


def render_body(query="", meeting="", item="", base=BASE):
    if len(query) > 200 or any(len(value) > 100 for value in (meeting, item)):
        return 400, frame('<p>Søket eller saksidentifikatoren er for lang.</p>')
    if bool(meeting) != bool(item) or any(value and not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in (meeting, item)):
        return 400, frame('<p>Oppgi både møte og saksnummer fra en lenke i søkeresultatet.</p>')
    snapshots = read_snapshots(Path(base))
    if snapshots is None:
        return 200, frame('<p>Modellresultatene er ikke klare til visning ennå. Prøv igjen når den lokale kjøringen er ferdig.</p>')
    summary, items = snapshots
    if meeting:
        selected = [row for row in items if str(row.get("meeting_id")) == meeting and str(row.get("item_no")) == item]
        if not selected:
            return 404, frame('<p>Saken finnes ikke i de lagrede resultatene.</p><p><a href="/vector">Tilbake til sakssøket</a></p>')
        if len(selected) != 1:
            return 503, frame('<p>Resultatene har flere oppføringer for samme sak og kan ikke vises entydig.</p>')
        return 200, frame(detail_body(summary, selected[0], Path(base)))
    return 200, frame(search_body(items, query.strip()))
