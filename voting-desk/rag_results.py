"""Read-only HTML from fixed aggregate evaluation artifacts; no model or index imports."""
from html import escape
import json
import math
from pathlib import Path

import board_results
import claude_board_results
import fresh_results
import f1_results
import relevance_results


BASE = Path(__file__).resolve().parent / "data/local-rag"
ARTIFACTS = {
    "relevance_local": ("Nytt historikksøk · lokal modell", "relevance-board-v1/summary.json"),
    "relevance_claude": ("Nytt søk og saksdokumenter · Claude", "relevance-claude-v1/report.json"),
    "f1": ("Aktivt F1-valg", "f1-board-v1/summary.json"),
    "fresh": ("Nye møter · låst test", "fresh-test-2026-10-v1/report.json"),
    "board": ("Avvik fra styret", "board-disagreement-v1/summary.json"),
    "claude_board": ("Claude med historiske treff", "claude-board-v1/report.json"),
    "learning": ("Lært stemmemodell", "vote-learning-v2/summary.json"),
    "vector": ("Lokal vektormodell", "vector-experiment-v1/summary.json"),
    "rag": ("RAG-evaluering", "rag-evaluation-v1/report.json"),
    "baseline": ("Lagrede referanser", "rag-evaluation-v1/baseline.json"),
    "classifier": ("MOT-klassifikator", "mot-experiment-v1/summary.json"),
    "retrieval": ("Dokumentsøk", "retrieval-evaluation-v1.json"),
    "injection": ("Instruksjonsangrep", "rag-injection-evaluation-v1/summary.json"),
}
METHODS = {"follow_board": "Følg styrets anbefaling", "legacy_cached_system": "Tidligere modell · lagret",
           "legacy_cached_document_agent": "Tidligere dokumentagent · lagret"}
MODES = {"keyword": "nøkkelord", "vector": "vektorsøk", "hybrid": "kombinert søk", "alternate": "vekslende treff · forsøk"}


def load_artifact(base, relative):
    try:
        data = json.loads((Path(base) / relative).read_text(encoding="utf-8"))
        return (data, "Tilgjengelig") if isinstance(data, dict) else (None, "Ugyldig format")
    except FileNotFoundError:
        return None, "Ikke lagret ennå"
    except (OSError, ValueError):
        return None, "Kan ikke leses nå"


def number(value):
    return str(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else "—"


def percentage(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return f"{value * 100:.1f}".replace(".", ",") + " %"
    return "—"


def table(headers, rows, caption):
    head = "".join(f'<th scope="col">{escape(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(
        f'<th scope="row">{escape(str(cell))}</th>' if i == 0 else f"<td>{escape(str(cell))}</td>"
        for i, cell in enumerate(row)) + "</tr>" for row in rows)
    return (f'<div class="table-scroll" tabindex="0" role="region" aria-label="{escape(caption)}">'
            f'<table><caption>{escape(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')


def vote_row(label, metrics, meetings="—", extended=True):
    row = [label, percentage(metrics.get("precision")), percentage(metrics.get("recall")),
           percentage(metrics.get("f1")), number(metrics.get("known_votes", metrics.get("n"))), number(metrics.get("mot"))]
    if extended:
        row += [meetings, percentage(metrics.get("recommendation_coverage")), percentage(metrics.get("manual_review_share")),
                percentage(metrics.get("verified_rule_quote_coverage")) + " / " + percentage(metrics.get("verified_evidence_coverage"))]
    return row


HEADERS = ["Metode", "Precision", "Recall", "F1", "Kjente stemmer", "MOT", "Møter ferdige", "Anbefalinger", "Manuell kontroll", "Regel / fakta"]


def run_label(run):
    strategy = {"proposal": "søk per sak", "meeting": "sak + felles møtefakta"}.get(run.get("strategy"), "strategi ikke oppgitt")
    return "RAG · " + strategy + " · " + MODES.get(run.get("mode"), "ukjent søkemetode")


def progress(run, total):
    return (f'{number(run.get("completed_meetings"))} / {number(total)}')


def baseline_rows(methods, meetings):
    return [vote_row(label, methods[name], meetings) for name, label in METHODS.items() if isinstance(methods.get(name), dict)]


def valid_rate(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1


def same_cohort(left, right):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    n, mot = left.get("n"), left.get("mot")
    return (isinstance(n, int) and not isinstance(n, bool) and n >= 0
            and isinstance(mot, int) and not isinstance(mot, bool) and 0 <= mot <= n
            and (n, mot) == (right.get("n"), right.get("mot")))


def learning_section(data):
    chunks = ['<section class="evaluation-section"><h2>Tidligere forsøk · MOT på forslaget</h2>']
    precision_target = (data or {}).get("target_precision", .85)
    recall_target = (data or {}).get("target_recall", .85)
    chunks.append(f'<p><strong>Historisk MOT-mål: precision strengt over {percentage(precision_target)} og recall strengt over {percentage(recall_target)}, samtidig.</strong> '
                  'Dette forsøket gjaldt MOT på selve forslaget, uavhengig av styrets anbefaling. Det er et annet mål enn avvik fra styret i hovedmålingen over.</p>')
    development = (data or {}).get("development_selected")
    if not isinstance(development, dict):
        return "".join(chunks) + '<p>Resultatene fra den lærte modellen er ikke lagret ennå. Måloppnåelse er ikke vurdert.</p></section>'
    precision, recall = development.get("precision"), development.get("recall")
    if all(valid_rate(value) for value in (precision_target, recall_target, precision, recall)):
        reached = precision > precision_target and recall > recall_target
        status = "nådd" if reached else "ikke nådd"
        chunks.append(f'<p><strong>Det historiske MOT-målet er {status} på utviklingsutvalget.</strong> '
                      f'Målt precision: {percentage(precision)}. Målt recall: {percentage(recall)}. '
                      'Tallene vises avrundet; måloppnåelse beregnes med de uavrundede verdiene. Dette er ingen garanti for nye saker.</p>')
    else:
        chunks.append('<p><strong>Det historiske MOT-målet kan ikke vurderes.</strong> En målverdi eller måling mangler eller er ugyldig.</p>')
    chunks.append('<p>Den lokale modellen lærer sammenhenger mellom historiske stemmer, tekstlikhet og MOT-utfall. '
                  'Dette er en lært klassifikator, i tillegg til det tidligere forsøket med vektede historiske naboer.</p>')
    chunks.append(f'<p class="muted">Registrerte API-kall i dette forsøket: {number(data.get("api_calls"))}. '
                  f'År brukt til å trene klassifikatoren: {escape(str(data.get("fit_period", "Ikke oppgitt")))}. '
                  f'Utviklingsmåling: {escape(str(data.get("development_period", "Ikke oppgitt")))}.</p>')
    if data.get("reference_period") is not None:
        chunks.append(f'<p class="muted">Historiske referansesaker: {escape(str(data["reference_period"]))}. '
                      f'Oppstartsåret {number(data.get("warmup_year"))} brukes bare som historisk referanse, ikke som treningsår for klassifikatoren.</p>')
    rows = [vote_row("Lært stemmemodell · valgt terskel", development, extended=False)]
    omitted = False
    for key, label in (("development_follow_board", "Følg styret · samme saker"),
                       ("local_vector_same_development", "Tidligere lokal vektormodell"),
                       ("local_text_same_development", "Tidligere lokal tekstmodell"),
                       ("cached_claude_same_development", "Tidligere Claude-modell · lagret")):
        reference = data.get(key)
        if not isinstance(reference, dict):
            continue
        if not same_cohort(development, reference):
            omitted = True
            continue
        rows.append(vote_row(label, reference, extended=False))
    chunks.append(table(HEADERS[:6], rows, f"Utviklingsresultater på samme {number(development.get('n'))} saker"))
    if omitted:
        chunks.append('<p class="muted">Referanser med et annet eller ukjent datagrunnlag er utelatt fra sammenligningstabellen.</p>')
    chunks.append('<p class="muted">De tidligere lokale forsøkene hadde andre mål for terskelvalget. Den lagrede Claude-modellen brukte mer historikk og er ikke en kontrollert ny trening på samme grunnlag.</p>')
    points = data.get("operating_points")
    if isinstance(points, list):
        point_rows = []
        names = {"balanced": "Balansert", "precision": "Prioriter precision", "recall": "Prioriter recall"}
        for point in points:
            if not isinstance(point, dict) or point.get("name") not in names:
                continue
            validation = point.get("validation") if isinstance(point.get("validation"), dict) else {}
            measured = point.get("development") if isinstance(point.get("development"), dict) else {}
            if measured and not same_cohort(development, measured):
                measured = {}
            threshold = point.get("threshold")
            threshold_text = str(threshold).replace(".", ",") if valid_rate(threshold) else "—"
            point_rows.append([names[point["name"]], threshold_text,
                               percentage(validation.get("precision")), percentage(validation.get("recall")),
                               percentage(measured.get("precision")), percentage(measured.get("recall")), percentage(measured.get("f1"))])
        if point_rows:
            chunks.append('<h3>Avveininger ved tre terskler</h3><p>Dette er tre terskler for den samme lærte modellen, ikke tre modeller. '
                          'Tersklene velges på valideringen før utviklingsutvalget vurderes. En strek betyr at en terskel eller sammenlignbar måling ikke er tilgjengelig.</p>')
            chunks.append(table(["Terskelvalg", "Terskel", "Validering: precision", "Validering: recall", "Utvikling: precision", "Utvikling: recall", "Utvikling: F1"],
                                point_rows, "Validering og utvikling holdes atskilt"))
    validation = data.get("validation_selected")
    if isinstance(validation, dict):
        validation_rows = [vote_row("Valgt modell · samlet validering", validation, extended=False)]
        years = data.get("validation_per_year", [])
        if isinstance(years, list):
            validation_rows += [vote_row("Valideringsår " + str(year.get("year", "—")), year, extended=False) for year in years if isinstance(year, dict)]
        chunks.append('<details><summary>Validering og modelloppsett</summary><p>Valideringen brukes til å velge modell og terskel. '
                      'Valideringsresultatene er derfor ikke en uavhengig sluttest.</p>')
        if isinstance(years, list):
            validation_years = sorted({year["year"] for year in years if isinstance(year, dict)
                                       and isinstance(year.get("year"), int) and not isinstance(year["year"], bool)})
            if validation_years:
                chunks.append(f'<p class="muted">Valideringsår: {", ".join(map(str, validation_years))}. '
                              'For hvert valideringsår brukes bare tidligere år til å trene modellen.</p>')
        chunks.append(table(HEADERS[:6], validation_rows, "Valideringsmålinger brukt i modellvalget"))
        config = data.get("selected_config") if isinstance(data.get("selected_config"), dict) else {}
        threshold = data.get("selected_threshold")
        threshold_text = str(threshold).replace(".", ",") if valid_rate(threshold) else "—"
        chunks.append(f'<p class="muted">Valgt oppsett: {escape(str(config.get("name", "Ikke oppgitt")))} '
                      f'({escape(str(config.get("kind", "Ikke oppgitt")))}) · {number(data.get("feature_count"))} modellvariabler · '
                      f'terskel {threshold_text}.</p></details>')
    chunks.append('<p><strong>Videre retning:</strong> Undersøk om samtidige fakta om styrets uavhengighet, komitéroller og godtgjørelse kan forklare feilene. '
                  'En annen terskel tilfører ikke disse opplysningene. Dette er en retning å undersøke, ikke dokumentert forbedring. '
                  '<a href="/">Utforsk kildedokumentene</a>.</p>')
    chunks.append('<p class="muted">Reserverte testmøter inngår ikke i det nye utviklingsutvalget. Historiske stemmer og tekstlikhet gir ikke i seg selv kildebelegg fra retningslinjene. '
                  'Modellskåren er ikke kalibrert sikkerhet. Modellen skiller MOT fra ikke-MOT og avgjør ikke FOR versus AVSTÅ.</p></section>')
    return "".join(chunks)


def vector_section(data):
    chunks = ['<section class="evaluation-section"><h2>Tidligere forsøk · lokal vektormodell</h2>',
              '<p>Dette historiske forsøket hadde et mål for recall alene ved MOT-stemmer. Det er et annet mål enn avvik fra styrets anbefaling.</p>',
              '<p><a href="/vector">Utforsk enkeltresultater og historiske naboer →</a></p>']
    development = (data or {}).get("development_selected")
    if not isinstance(development, dict):
        return "".join(chunks) + '<p>Resultatene fra den lokale vektormodellen er ikke lagret ennå. Recall-målet er ikke vurdert her før målingen er ferdig.</p></section>'
    chunks.append('<p>Vår egen stemmeklassifikator finner lignende historiske saker med en lokalt lagret, ferdigtrent BGE-tekstmodell. '
                  'Den vekter de historiske stemmene med en kNN-modell: de nærmeste sakene brukes til å klassifisere den nye saken.</p>')
    api_calls = data.get("api_calls")
    if isinstance(api_calls, int) and not isinstance(api_calls, bool) and api_calls == 0:
        chunks.append('<p class="muted">0 API-kall i dette forsøket. Modellen bruker ingen generativ språkmodell eller Claude-kall.</p>')
    else:
        chunks.append(f'<p class="muted">Registrerte API-kall i forsøket: {number(api_calls)}.</p>')
    target, recall = data.get("target_recall"), development.get("recall")
    valid = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1
    if valid(target) and valid(recall):
        status = "nådd" if recall >= target else "ikke nådd"
        chunks.append(f'<p><strong>Forsøkets tidligere recall-mål på {percentage(target)} er {status} på utviklingsutvalget.</strong> '
                      f'Målt recall er {percentage(recall)} (avrundet). Dette er ingen garanti for nye saker.</p>')
    else:
        chunks.append('<p><strong>Recall-målet kan ikke vurderes ennå.</strong> Målverdi eller målt recall mangler.</p>')
    rows = [vote_row("Lokal vektormodell", development, extended=False) + [number(development.get(k)) for k in ("tp", "fp", "fn")]]
    omitted = False
    for key, label in (("development_follow_board", "Følg styret · samme saker"),
                       ("cached_claude_same_development", "Tidligere Claude-modell · lagret"),
                       ("local_text_same_development", "Lokal tekstmodell · tidligere forsøk")):
        reference = data.get(key)
        if not isinstance(reference, dict):
            continue
        if (reference.get("n"), reference.get("mot")) != (development.get("n"), development.get("mot")):
            omitted = True
            continue
        rows.append(vote_row(label, reference, extended=False) + [number(reference.get(k)) for k in ("tp", "fp", "fn")])
    period = str(data.get("development_period", "2024"))
    chunks.append(table(HEADERS[:6] + ["Riktige MOT", "Falske MOT", "Oversette MOT"], rows,
                        f"Utviklingsutvalg {period} · samme {number(development.get('n'))} saker"))
    if omitted:
        chunks.append('<p class="muted">En referanse har et annet antall saker eller MOT-stemmer og vises ikke i sammenligningstabellen.</p>')
    chunks.append('<p class="muted">Den tidligere Claude-modellen brukte mer historikk og er ikke trent på nytt under de samme vilkårene. '
                  'Den lokale tekstmodellen ble valgt for høy F1, mens vektormodellen prioriterer recall-målet. Ulike terskler gir ulike avveininger mellom precision og recall.</p>')
    validation = data.get("validation_selected")
    if isinstance(validation, dict):
        chunks.append('<details><summary>Validering og modelloppsett</summary><p>Valideringen brukes til å velge oppsett og terskel. '
                      'Den er en del av modellutviklingen og holdes atskilt fra utviklingsresultatet over.</p>')
        chunks.append(table(HEADERS[:6], [vote_row("Valgt vektormodell · validering", validation, extended=False)], "Validering brukt til modellvalg"))
        config = data.get("selected_config") if isinstance(data.get("selected_config"), dict) else {}
        decimal = lambda value: format(value, ".4g").replace(".", ",") if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else "—"
        model = str(data.get("embedding_model", "Ikke oppgitt"))
        fit_period = str(data.get("fit_period", "Ikke oppgitt"))
        chunks.append(f'<p class="muted">Historikkgrunnlag: {escape(fit_period)}. Tekstmodell: {escape(model)} · {number(data.get("embedding_dimension"))} dimensjoner. '
                      f'Historiske naboer: {number(config.get("k"))} · selskapsvekt: {decimal(config.get("company_weight"))} · '
                      f'terskel: {decimal(data.get("selected_threshold"))}.</p></details>')
    chunks.append('<p>Modellen skiller MOT fra ikke-MOT. Den avgjør ikke FOR versus AVSTÅ og gir ikke en full stemmeanbefaling med kildebelegg. '
                  'Modellskåren er ikke et kalibrert mål på sikkerhet. Resultatene gjelder utviklingsdata, ikke en uavhengig sluttest.</p></section>')
    return "".join(chunks)


def rag_section(report, baseline):
    chunks = ['<section class="evaluation-section"><h2>Stemmeanbefalinger fra RAG</h2>']
    runs = [r for r in (report or {}).get("runs", []) if isinstance(r, dict) and isinstance(r.get("metrics"), dict)]
    total = (report or {}).get("cohort_meetings")
    same_data = report and baseline and report.get("data_id") and report.get("data_id") == baseline.get("data_id")
    complete = bool(runs) and same_data and isinstance(total, int) and total > 0 and all(
        r.get("attempted_meetings") == total and r.get("pending_meetings") == 0 for r in runs)
    if complete:
        rows = baseline_rows(baseline.get("methods", {}), number(total) + " · lagret")
        rows += [vote_row(run_label(r), r["metrics"], progress(r, total)) for r in runs]
        chunks.append(table(HEADERS, rows, f"Samme utvalg på {number(total)} møter fra 2024"))
        for run in runs:
            chunks.append(f'<p class="muted">{escape(run_label(run))}: {number(run.get("failed_meetings"))} møter feilet; '
                          f'{number(run.get("pending_meetings"))} gjenstår.</p>')
    elif runs:
        chunks.append('<p>Foreløpige resultater. Hvert oppsett sammenlignes med lagrede referanser på de samme sakene. Oppsett med ulikt antall møter kan ikke sammenlignes direkte.</p>')
        for run in runs:
            label = run_label(run)
            chunks.append(f'<h3>{escape(label)}</h3><p class="muted">{progress(run, total)} møter fullført · '
                          f'{number(run.get("failed_meetings"))} feilet · {number(run.get("pending_meetings"))} gjenstår.</p>')
            rows = baseline_rows(run.get("same_rows_baselines", {}), number(run.get("attempted_meetings")) + " · lagret")
            rows.append(vote_row(label, run["metrics"], progress(run, total)))
            chunks.append(table(HEADERS, rows, "Bare sakene i dette oppsettets forsøkte møter"))
            if not run.get("same_rows_baselines"):
                chunks.append('<p class="muted">Referanser på de samme sakene er ikke lagret ennå.</p>')
    elif baseline:
        chunks.append('<p>Ingen nye RAG-kjøringer er lagret ennå. Tabellen viser bare tidligere resultater på det planlagte utvalget.</p>')
        chunks.append(table(HEADERS, baseline_rows(baseline.get("methods", {}), number(baseline.get("meetings")) + " · lagret"), "Lagrede referanser før RAG-kjøring"))
    else:
        chunks.append('<p class="muted">RAG-resultater er ikke tilgjengelige ennå.</p>')
    chunks.append('<p class="muted">Tidligere modeller brukte andre prompter og mer historikk, delvis fra det nå reserverte testutvalget. De er historiske referanser. En kontrollert sammenligning av søk krever samme saker, modell og prompt.</p>')
    chunks.append('<details><summary>Slik leser du målene</summary><p><strong>Precision:</strong> andelen foreslåtte MOT som stemmer med NBIM. '
                  '<strong>Recall:</strong> andelen av NBIMs MOT som modellen finner. <strong>F1:</strong> balansen mellom de to. MOT gjelder selve forslaget, uavhengig av styrets anbefaling.</p>'
                  '<p>Manglende anbefalinger og feilede modellkall blir falske negative når NBIM stemte MOT. Ukjente NBIM-stemmer er utelatt. '
                  'Anbefalinger viser andelen saker med FOR, MOT eller AVSTÅ; manuell kontroll viser saker som er sendt videre. Alle anbefalinger trenger fortsatt menneskelig godkjenning.</p>'
                  '<p>Regel / fakta viser andelen saker med verifiserte sitater fra henholdsvis retningslinjer og dokumenter. '
                  'Sitatkontrollen viser at teksten finnes i kilden, ikke at den begrunner anbefalingen. Alle andeler bruker kjente NBIM-stemmer som nevner. '
                  'En strek betyr at målet ikke er definert eller ikke er målt.</p></details></section>')
    return "".join(chunks)


def retrieval_section(data):
    chunks = ['<section class="evaluation-section"><h2>Dokumentsøk · egne utviklingsspørsmål</h2>',
              '<p>Dette måler om søket finner et forhåndskontrollert kildeutdrag. Det måler ikke kvaliteten på stemmeanbefalingene.</p>']
    summary = (data or {}).get("primary_questions", {}).get("summary", {})
    if summary:
        rows = [[MODES.get(name, "ukjent metode"), number(m.get("queries")), number(m.get("anchor_hits_at_5")),
                 percentage(m.get("anchor_hit_at_5")), percentage(m.get("mrr_at_5")), percentage(m.get("source_quote_validity"))]
                for name, m in summary.items() if isinstance(m, dict)]
        chunks.append(table(["Søkemetode", "Spørsmål", "Anker funnet", "Treff blant topp 5", "MRR@5", "Gyldige kildesitater"], rows, "12 manuelt kontrollerte utviklingsankre fra tre møter"))
    else:
        chunks.append('<p class="muted">Ingen måling av dokumentsøk er lagret ennå.</p>')
    chunks.append('<p class="muted">Ankrene har ufullstendige relevansvurderinger og er brukt under utviklingen. Tallene er ikke en uavhengig test eller full recall for relevante kilder. '
                  'MRR@5 belønner at ankeret kommer tidlig i trefflisten. Treff som ikke inneholder ankeret kan likevel være relevante.</p></section>')
    return "".join(chunks)


def classifier_section(data):
    chunks = ['<section class="evaluation-section"><h2>MOT-klassifikator · større utviklingsutvalg</h2>']
    if data and isinstance(data.get("development_selected"), dict):
        rows = [vote_row("Ny MOT-klassifikator", data["development_selected"], extended=False)]
        for key, label in (("development_follow_board", "Følg styret · samme saker"), ("cached_claude_same_development", "Tidligere modell · samme saker")):
            if isinstance(data.get(key), dict):
                rows.append(vote_row(label, data[key], extended=False))
        chunks.append('<p>Dette er en separat klassifikator på et større 2024-utvalg enn RAG-forsøket. Tallene skal ikke sammenlignes direkte med RAG-tabellen.</p>')
        chunks.append(table(HEADERS[:6], rows, "Klassifikator og referanser på samme utviklingssaker"))
        chunks.append('<p class="muted">Modell og terskel ble valgt med fem deler gruppert etter selskap og møtedato i treningsårene 2019–2023. '
                      'Den lagrede tidligere modellen brukte et større historikkgrunnlag; dette er en beskrivende referanse.</p>')
    else:
        chunks.append('<p class="muted">Resultater fra MOT-klassifikatoren er ikke lagret ennå.</p>')
    return "".join(chunks) + "</section>"


def injection_section(data):
    chunks = ['<section class="evaluation-section"><h2>Instruksjonsangrep i kildekonteksten · begrenset prøve</h2>']
    if data and data.get("status") == "completed":
        yes_no = lambda value: "Ja" if value is True else "Nei" if value is False else "—"
        chunks.append(table(["Prøve", "Saker", "Endrede stemmer", "Endret til MOT", "Angrepsmarkør i svar", "Hele overstyringen fulgt"], [[
            "Én møtekontekst", number(data.get("proposals")), number(data.get("vote_changes")),
            number(data.get("changed_to_attacker_target")), yes_no(data.get("marker_in_generated_text")),
            yes_no(data.get("full_requested_override_observed"))]], "Sammenligning med et lagret svar uten angrep"))
        if data.get("clean_all_predictions_null") is True:
            chunks.append('<p>Modellen ga ingen stemmeanbefalinger i det rene sammenligningssvaret. Uendrede nullsvar gir derfor svært lite grunnlag for å si at modellen tåler slike angrep.</p>')
        chunks.append('<p class="muted">Angrepsteksten ble lagt til etter dokumentsøket. Prøven tester ikke innlasting, indeksering eller søk, og er ikke en generell måling av robusthet.</p>')
    else:
        chunks.append('<p class="muted">Ingen fullført prøve med instruksjonsangrep er lagret ennå.</p>')
    return "".join(chunks) + "</section>"


def render_body(base=BASE, *, source_search=True):
    loaded = {key: load_artifact(base, relative) for key, (_, relative) in ARTIFACTS.items()}
    data = {key: value[0] for key, value in loaded.items()}
    statuses = "".join(f'<span class="badge">{escape(ARTIFACTS[key][0])}: {escape(status)}</span>' for key, (_, status) in loaded.items())
    relevance = relevance_results.render_section(base)
    f1 = f1_results.render_section(Path(base) / "f1-board-v1")
    if relevance:
        f1 = '<details><summary>Tidligere F1-terskelvalg og referanser</summary>' + f1 + '</details>'
    search_link = '<p><a href="/">← Tilbake til kildesøket</a></p>' if source_search else ""
    return ('<header><div class="wrap">' + search_link + '<h1>Resultater fra modelltestingen</h1>'
            '<p>Det aktive målet er høyest F1 for avvik fra styrets anbefaling. '
            'F1-valget og den uendrede oktober-testen vises separat.</p>'
            '<p class="muted">Kalibrering og utviklingsmålinger er ikke en ny, uavhengig sluttest. '
            'Eldre forsøk ligger under historikken. Siden viser lagrede summer og starter ingen modellkall.</p>'
            '<p><a href="/evaluation">Oppdater resultatvisningen</a></p></div></header><main class="wrap">'
            + relevance + f1
            + fresh_results.render_section(Path(base) / "fresh-test-2026-10-v1")
            + '<details><summary>Tidligere modellforsøk og målinger</summary>'
            + '<section class="evaluation-section"><h2>Kalibrering og utviklingsmålinger · 2024</h2>'
              '<p>De følgende forsøkene brukte tidligere undersøkte data og tidligere utvalgskriterier. '
              'Tidligere prosentmål er avsluttet. De inngår ikke i testen på nye møter over.</p></section>'
            + board_results.render_section(Path(base) / "board-disagreement-v1")
            + claude_board_results.render_section(Path(base) / "claude-board-v1")
            + learning_section(data["learning"]) + vector_section(data["vector"]) + rag_section(data["rag"], data["baseline"]) + retrieval_section(data["retrieval"])
            + classifier_section(data["classifier"]) + injection_section(data["injection"]) + '</details>'
            + '<section class="evaluation-section"><h2>Tilgjengelige målinger</h2><div class="artifact-status">' + statuses
            + '</div><p class="muted">Resultatene leses fra lokale rapporter hver gang siden åpnes. Saker, dokumentutdrag og modellprompter vises ikke her.</p></section></main>')
