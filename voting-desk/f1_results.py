"""Read-only presentation of F1 model selection on exposed development data."""
from html import escape
import json
from pathlib import Path

from board_results import count, numeric, percentage, same_cohort

BASE = Path(__file__).resolve().parent / "data/local-rag/f1-board-v1"


def table(headers, rows, caption):
    head = "".join(f'<th scope="col">{escape(value)}</th>' for value in headers)
    body = "".join("<tr>" + "".join(
        f'<th scope="row">{escape(str(value))}</th>' if i == 0 else f'<td>{escape(str(value))}</td>'
        for i, value in enumerate(row)) + "</tr>" for row in rows)
    return (f'<div class="table-scroll" tabindex="0" role="region" aria-label="{escape(caption)}">'
            f'<table><caption>{escape(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')


def matching(left, right):
    return (isinstance(left, dict) and isinstance(right, dict)
            and same_cohort(left, right) and same_cohort(right, left))


def metric_row(label, value):
    return [label, percentage(value.get("f1")), percentage(value.get("precision")), percentage(value.get("recall")),
            count(value.get("tp")), count(value.get("fp")), count(value.get("fn"))]


def render_section(base=BASE):
    chunks = ['<section class="evaluation-section"><h2>Aktivt modellvalg · høyest F1</h2>',
              '<p>Vi maksimerer <strong>F1 for avvik fra styrets anbefaling</strong>. '
              'Modell og terskel velges etter høyest F1 på utviklingsdata. Precision og recall vises fortsatt hver for seg.</p>',
              '<p>F1 er det harmoniske gjennomsnittet av precision og recall: <strong>2 × precision × recall / (precision + recall)</strong>. '
              'Skåren blir lav når modellen enten overser mange avvik eller varsler mange falske avvik. '
              'Positiv klasse er NBIM ≠ styrets anbefaling.</p>']
    try:
        data = json.loads((Path(base) / "summary.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "".join(chunks) + '<p>F1-sammenligningen er ikke lagret ennå. Ingen ny F1-måling vises.</p></section>'
    except (OSError, ValueError):
        return "".join(chunks) + '<p>F1-rapporten kan ikke leses. Ingen ny F1-måling vises.</p></section>'
    if (not isinstance(data, dict) or data.get("objective") != "maximize_f1" or data.get("target") != "against_board"
            or data.get("evaluation_kind") != "EXPOSED_2024_CALIBRATION" or data.get("test_evaluated") is not False
            or data.get("october_test_unchanged") is not True):
        return "".join(chunks) + '<p>Rapporten har ikke riktig mål og evalueringsprotokoll. Ingen sammenligning vises.</p></section>'
    selected, prior = data.get("calibration_selected"), data.get("calibration_at_validation_threshold")
    cohort = data.get("calibration")
    if (not matching(selected, prior) or not isinstance(cohort, dict)
            or not matching(selected, {"n": cohort.get("rows"), "positive": cohort.get("positive")})):
        return "".join(chunks) + '<p>Måleutvalgene stemmer ikke overens. Ingen sammenligning vises.</p></section>'
    config = data.get("selected_config") if isinstance(data.get("selected_config"), dict) else {}
    chunks.append(f'<p>Valgt modell: <strong>{escape(str(config.get("name", "Ikke oppgitt")))}</strong>. '
                  f'F1 etter terskelvalg på 2024: <strong>{percentage(selected.get("f1"))}</strong>. '
                  f'Terskel: {numeric(data.get("selected_threshold"))}.</p>')
    if data.get("model_reused") is True:
        chunks.append('<p>Den samme ferdigtrente modellen ble valgt igjen. Beslutningsterskelen er endret; modellvektene er uendret.</p>')
    chunks.append('<p><strong>Dette er utviklings- og kalibreringsresultater, ikke en ny uavhengig test.</strong> '
                  'Modellvalget bruker tidsordnet validering på data fra 2020–2023. Deretter velges den endelige terskelen på 2024. '
                  'Raden med terskel fra 2020–2023 viser resultatet på 2024 uten at terskelen er tilpasset 2024-utfallene.</p>')
    rows = [metric_row("Lokal modell · F1-terskel fra 2020–2023", prior),
            metric_row("Lokal modell · F1-terskel valgt på 2024", selected)]
    comparators = data.get("comparators") if isinstance(data.get("comparators"), dict) else {}
    omitted = False
    for key, label in (("previous_balanced", "Lokal modell · tidligere balansevalg"),
                       ("cached_claude", "Claude · lagrede historiske vektortreff"),
                       ("follow_board", "Følg alltid styret")):
        reference = comparators.get(key)
        if reference is None:
            continue
        metrics = reference.get("metrics") if isinstance(reference, dict) else None
        if not matching(selected, metrics) or (key == "cached_claude" and reference.get("complete") is not True):
            omitted = True
            continue
        rows.append(metric_row(label, metrics))
    chunks.append(table(["Oppsett", "F1", "Precision", "Recall", "Riktige avvik", "Falske avvik", "Oversette avvik"],
                        rows, f'Samme {count(selected.get("n"))} saker fra 2024 med {count(selected.get("positive"))} faktiske avvik'))
    if omitted:
        chunks.append('<p class="muted">Referanser med andre eller ukjente nevnere er utelatt. Det samme gjelder ufullførte Claude-kjøringer.</p>')
    claude = comparators.get("cached_claude")
    if isinstance(claude, dict) and claude.get("complete") is True and matching(selected, claude.get("metrics")):
        chunks.append(f'<p class="muted">Claude-svarene er gjenbrukt fra den tidligere kjøringen. '
                      f'{count(claude.get("failed_meetings"))} feilede møter beholdes i målingen. '
                      'Claude gir stemmer, ikke en justerbar avviksskår. Vi har ikke endret Claude-prompten eller kalt API-et på nytt.</p>')
    validation = data.get("model_selection_validation")
    candidates = data.get("candidates")
    if isinstance(validation, dict) and matching(validation, validation) and isinstance(candidates, list):
        candidate_rows = []
        for candidate in candidates:
            if not isinstance(candidate, dict) or not matching(validation, candidate.get("validation")):
                continue
            candidate_config = candidate.get("config") if isinstance(candidate.get("config"), dict) else {}
            measured = candidate["validation"]
            candidate_rows.append([str(candidate_config.get("name", "Ikke oppgitt")), percentage(measured.get("f1")),
                                   percentage(measured.get("precision")), percentage(measured.get("recall")), numeric(candidate.get("threshold"))])
        if candidate_rows:
            chunks.append('<details><summary>Modellvalg på 2020–2023</summary>'
                          '<p>Alle modellene nedenfor måles på samme tidsordnede valideringsutvalg. '
                          'Modell og terskel er valgt med disse utfallene, så tallene er modellvalgsresultater.</p>')
            chunks.append(table(["Modell", "F1", "Precision", "Recall", "F1-terskel"], candidate_rows,
                                f'Modellvalg på {count(validation.get("n"))} saker med {count(validation.get("positive"))} avvik'))
            chunks.append('</details>')
    chunks.append('<p class="muted">Den låste oktober-testen nedenfor gjelder det tidligere oppsettet. '
                  'Den nye F1-terskelen er ikke testet på oktober, og oktoberutfallene er ikke brukt til dette modell- eller terskelvalget. '
                  'Eldre MOT-forsøk har en annen måldefinisjon og inngår ikke i F1-rangeringen for avvik fra styret.</p>')
    chunks.append(f'<p class="muted">Nye API-kall: {count(data.get("api_calls"))}. '
                  'En strek betyr at et mål ikke kan beregnes eller mangler. Modellskåren er ikke kalibrert sikkerhet.</p></section>')
    return "".join(chunks)
