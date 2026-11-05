"""Aggregate-only view of the chronological board-disagreement experiment."""
from html import escape
import json
import math
from pathlib import Path


BASE = Path(__file__).resolve().parent / "data/local-rag/board-disagreement-v1"


def valid_rate(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1


def percentage(value):
    return f"{value * 100:.1f}".replace(".", ",") + " %" if valid_rate(value) else "—"


def count(value):
    return str(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else "—"


def numeric(value):
    return str(value).replace(".", ",") if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else "—"


def same_cohort(left, right):
    n, positive = left.get("n"), left.get("positive")
    return (count(n) != "—" and count(positive) != "—" and positive <= n
            and isinstance(right, dict) and (n, positive) == (right.get("n"), right.get("positive")))


def metric_row(label, metrics):
    return [label, percentage(metrics.get("precision")), percentage(metrics.get("recall")), percentage(metrics.get("f1")),
            count(metrics.get("n")), count(metrics.get("positive")), count(metrics.get("tp")), count(metrics.get("fp")), count(metrics.get("fn"))]


def metric_table(rows, caption):
    headers = ["Oppsett", "Precision", "Recall", "F1", "Saker", "Faktiske avvik", "Riktige avvik", "Falske avvik", "Oversette avvik"]
    head = "".join(f'<th scope="col">{escape(header)}</th>' for header in headers)
    body = "".join("<tr>" + "".join(f'<th scope="row">{escape(str(cell))}</th>' if i == 0 else f'<td>{escape(str(cell))}</td>'
                                    for i, cell in enumerate(row)) + "</tr>" for row in rows)
    return (f'<div class="table-scroll" tabindex="0" role="region" aria-label="{escape(caption)}"><table>'
            f'<caption>{escape(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')


def render_section(base=BASE):
    chunks = ['<section class="evaluation-section"><h2>Avvik fra styrets anbefaling · tidligere balansevalg</h2>',
              '<p>Positiv klasse er <strong>NBIM ≠ styrets anbefaling</strong>. Vi måler om modellen finner saker der NBIM stemmer annerledes enn styret anbefaler.</p>',
              '<p class="muted">Eksempel: styret anbefaler MOT og NBIM stemmer FOR → avvik. Styret anbefaler MOT og NBIM stemmer MOT → ikke avvik. '
              'Dette er et annet mål enn å finne alle MOT-stemmer.</p>']
    try:
        data = json.loads((Path(base) / "summary.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "".join(chunks) + '<p>Resultatene for avvik fra styret er ikke lagret ennå.</p></section>'
    except (OSError, ValueError):
        return "".join(chunks) + '<p>Rapporten kan ikke leses nå. Ingen nye målinger vises.</p></section>'
    if not isinstance(data, dict) or data.get("target") != "against_board" or data.get("positive_class") != "NBIM != mgmt_rec":
        return "".join(chunks) + '<p>Rapporten mangler riktig måldefinisjon og kan ikke vises som en måling av avvik fra styret.</p></section>'
    fit_period = escape(str(data.get("fit_period", "Ikke oppgitt")))
    calibration_period = escape(str(data.get("calibration_period", "Ikke oppgitt")))
    test_period = escape(str(data.get("test_period", "Ikke oppgitt")))
    chunks.append(f'<p>Trening: <strong>{fit_period}</strong>. Terskelkalibrering: <strong>{calibration_period}</strong>. '
                  f'Testperiode: <strong>{test_period}</strong>.</p>')
    fit = data.get("fit") if isinstance(data.get("fit"), dict) else {}
    if fit:
        chunks.append(f'<p class="muted">Treningsgrunnlaget har {count(fit.get("rows"))} saker, hvorav {count(fit.get("positive"))} faktiske avvik fra styret.</p>')
    if data.get("test_evaluated") is False:
        chunks.append('<p><strong>Testsettet er ikke kjørt på nytt.</strong> Tallene under er ikke resultater fra testperioden.</p>')
    elif data.get("test_evaluated") is True:
        chunks.append('<p>Rapporten markerer testsettet som evaluert, men denne visningen inneholder ingen testmåling.</p>')
    else:
        chunks.append('<p>Teststatus er ikke oppgitt. Denne visningen inneholder ingen testmåling.</p>')
    selected = data.get("calibration_selected")
    if isinstance(selected, dict):
        chunks.append(f'<h3>Terskel valgt på {calibration_period}</h3>'
                      '<p><strong>Dette er en tilpasset måling på kalibreringsdata.</strong> De samme utfallene brukes til å velge terskel og beregne resultatet. '
                      'Det er ikke en uavhengig evaluering.</p>')
        chunks.append('<p>Dette tidligere oppsettet valgte modell og terskel ved å maksimere det laveste av precision og recall. '
                      'Resultatene er bevart som historisk sammenligning. Det aktive modellvalget prioriterer nå F1.</p>')
        rows = [metric_row("Modell · terskel valgt på kalibreringsåret", selected)]
        references = [
            ("Samme modell · terskel fra tidligere validering", data.get("calibration_at_validation_threshold")),
            ("Ingen avvik · følg alltid styret", data.get("calibration_no_disagreement")),
        ]
        historical = data.get("historical_vote_reference")
        if isinstance(historical, dict):
            references.append(("Tidligere agent · lagrede stemmer", historical.get("against_board")))
        omitted = False
        for label, metrics in references:
            if metrics is None:
                continue
            if not isinstance(metrics, dict) or not same_cohort(selected, metrics):
                omitted = True
                continue
            rows.append(metric_row(label, metrics))
        chunks.append(metric_table(rows, f"Avvik fra styret · samme {count(selected.get('n'))} kalibreringssaker"))
        if omitted:
            chunks.append('<p class="muted">Referanser med et annet eller ukjent antall saker og faktiske avvik er utelatt.</p>')
        if isinstance(historical, dict):
            chunks.append('<p class="muted">Den tidligere agenten er en historisk referanse med et annet oppsett. Dens eventuelle MOT-måling inngår ikke i denne avvikstabellen.</p>')
    else:
        chunks.append('<p>Ingen fullført måling på kalibreringsdata er lagret ennå.</p>')
    validation = data.get("model_selection_validation")
    if isinstance(validation, dict):
        chunks.append('<details><summary>Validering brukt til modellvalg</summary><p>Dette er valideringen fra før kalibreringsåret. '
                      'Den brukes til å velge modell og skal holdes atskilt fra terskelkalibreringen over.</p>')
        chunks.append(metric_table([metric_row("Valgt modell · tidligere validering", validation)], "Modellvalg · eget valideringsutvalg"))
        chunks.append('</details>')
    chunks.append('<p><strong>MOT-precision og MOT-recall er ikke definert for denne binære modellen.</strong> '
                  'Et binært avviksflagg sier ikke hvilken stemme som skal velges. Vi regner derfor ikke «stem motsatt av styret» som en stemmeanbefaling fra modellen.</p>')
    historical = data.get("historical_vote_reference")
    mot = historical.get("mot") if isinstance(historical, dict) else None
    if isinstance(mot, dict) and isinstance(selected, dict) and count(selected.get("n")) != "—" and mot.get("n") == selected.get("n"):
        chunks.append('<details><summary>MOT målt separat · tidligere agents lagrede stemmer</summary>'
                      f'<p>Historisk referanse på {count(mot.get("n"))} saker med {count(mot.get("mot"))} MOT-stemmer: '
                      f'precision {percentage(mot.get("precision"))}, recall {percentage(mot.get("recall"))}, F1 {percentage(mot.get("f1"))}. '
                      'Dette måler MOT på forslaget, ikke avvik fra styret, og gjelder ikke den nye klassifikatoren.</p></details>')
    if data.get("history_policy") == "walk_forward_5d":
        chunks.append(f'<p class="muted">Historikken oppdateres fremover i tid: tidligere stemmer fra {calibration_period} kan brukes når de er mer enn fem dager eldre enn saken som vurderes. '
                      'Dette er historiske modellinput; klassifikatoren er trent på årene oppgitt over.</p>')
    if data.get("rules_used") is False:
        chunks.append('<p class="muted">Denne lokale modellen bruker ikke retningslinjer. Den tidligere agenten brukte regler, men denne klassifikatoren gir ikke kildebelegg for om en stemme følger en regel.</p>')
    config = data.get("selected_config") if isinstance(data.get("selected_config"), dict) else {}
    chunks.append(f'<p class="muted">Valgt oppsett: {escape(str(config.get("name", "Ikke oppgitt")))}. '
                  f'Kalibrert terskel: {numeric(data.get("selected_threshold"))}. API-kall: {count(data.get("api_calls"))}.</p>')
    chunks.append('<p class="muted">Bare saker med kjent NBIM-stemme og styreanbefaling inngår. En avviksskår er ikke kalibrert sikkerhet og avgjør ikke alene hvilken av FOR, MOT eller AVSTÅ som bør velges. '
                  'MOT-resultater og eldre forsøk vises separat på siden.</p></section>')
    return "".join(chunks)
