"""Read-only aggregates for Claude with locally retrieved historical votes."""
from html import escape
import json
import math
from pathlib import Path

from board_results import count, metric_row, metric_table, percentage, same_cohort


BASE = Path(__file__).resolve().parent / "data/local-rag/claude-board-v1"


def mapping(value):
    return value if isinstance(value, dict) else {}


def valid_count(value):
    return count(value) != "—"


def render_section(base=BASE):
    chunks = ['<section class="evaluation-section"><h2>Claude + lokalt søk i historiske stemmer</h2>']
    try:
        data = json.loads((Path(base) / "report.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "".join(chunks) + '<p>Claude-sammenligningen er ikke lagret ennå.</p></section>'
    except (OSError, ValueError):
        return "".join(chunks) + '<p>Claude-rapporten kan ikke leses nå. Ingen nye målinger vises.</p></section>'
    if (not isinstance(data, dict) or data.get("target") != "against_board"
            or data.get("evaluation_kind") != "EXPOSED_2024_DEVELOPMENT"
            or data.get("scope") != "historical_votes_only"):
        return "".join(chunks) + '<p>Rapporten mangler riktig mål, periode eller informasjonsgrunnlag. Ingen sammenligning vises.</p></section>'
    chunks.append('<p><strong>Utviklingsmåling på tidligere brukte 2024-data, ikke en uavhengig sluttest.</strong> '
                  'Positiv klasse er NBIM ≠ styrets anbefaling. Claude får saksteksten og tidligere stemmer som det lokale vektorsøket finner. '
                  'Den får tekst og historiske utfall, ikke selve vektorkoordinatene eller den lokale modellens svar.</p>')
    cohort = mapping(data.get("cohort"))
    attempted, completed = data.get("attempted_meetings"), data.get("completed_meetings")
    failed, pending = data.get("failed_meetings"), data.get("unattempted_meetings")
    total, total_rows = cohort.get("meetings"), cohort.get("rows")
    consistent_status = (all(valid_count(value) for value in (attempted, completed, failed, pending, total))
                         and completed + failed == attempted and attempted + pending == total)
    if consistent_status:
        finished = data.get("complete") is True and pending == 0
        label = "Alle møter er forsøkt" if finished else "Foreløpige resultater"
        chunks.append(f'<p><strong>{label}.</strong> {completed} / {total} møter har fullførte svar; '
                      f'{failed} møter feilet og {pending} er ikke forsøkt.</p>')
    else:
        chunks.append('<p>Kjøringsstatus er ufullstendig eller motstridende. Resultatene kan ikke omtales som en fullført evaluering.</p>')
    chunks.append(f'<p>Planlagt utvalg: {count(total_rows)} saker fra {count(total)} møter, '
                  f'med {count(cohort.get("positive"))} faktiske avvik. '
                  f'Sammenligningen nedenfor gjelder {count(data.get("attempted_rows"))} saker fra forsøkte møter.</p>')
    chunks.append('<p class="muted">Manglende svar og feilede kall beholdes i målingen. Et oversett faktisk avvik teller som falskt negativt. '
                  'Saker fra møter som ennå ikke er forsøkt, inngår ikke i de foreløpige resultatene.</p>')
    primary = mapping(mapping(data.get("claude")).get("disagreement"))
    n, positive = primary.get("n"), primary.get("positive")
    valid_primary = (valid_count(n) and valid_count(positive) and 0 <= positive <= n
                     and valid_count(data.get("attempted_rows")) and n == data["attempted_rows"]
                     and valid_count(total_rows) and n <= total_rows)
    if valid_primary and n:
        rows = [metric_row("Claude · historiske vektortreff", primary)]
        references = mapping(data.get("same_rows_local"))
        omitted = False
        for key, label in (("at_validation_threshold", "Lokal modell · terskel fra tidligere validering"),
                           ("at_calibration_threshold", "Lokal modell · terskel valgt på 2024")):
            other = references.get(key)
            if same_cohort(primary, other):
                rows.append(metric_row(label, other))
            else:
                omitted = True
        chunks.append(metric_table(rows, f"Avvik fra styret · samme {n} forsøkte saker"))
        if omitted:
            chunks.append('<p class="muted">Lokale referanser med et annet eller ukjent antall saker og faktiske avvik er utelatt.</p>')
        chunks.append(f'<p>Claude ga en gyldig stemmeprediksjon for {count(primary.get("covered"))} av {n} saker '
                      f'({percentage(primary.get("recommendation_coverage"))}). '
                      'Et nullsvar betyr ukjent, ikke at modellen støtter styret.</p>')
    else:
        chunks.append('<p>Ingen sammenlignbar måling er tilgjengelig: antallet forsøkte saker mangler, er null eller stemmer ikke med målingen.</p>')
    chunks.append('<p class="muted">Samme saksutvalg og tidsgrense gjør resultatene sammenlignbare, men læringsoppsettene er forskjellige. '
                  'Claude bruker en fast instruksjon og de historiske treffene. Den lokale modellens kalibrerte terskel er allerede valgt med 2024-utfallene.</p>')
    mot = mapping(mapping(data.get("claude")).get("literal_mot"))
    if valid_primary and n and mot.get("n") == n:
        chunks.append('<details><summary>MOT målt separat · Claude</summary>'
                      f'<p>På de samme {n} sakene: precision {percentage(mot.get("precision"))}, '
                      f'recall {percentage(mot.get("recall"))}, F1 {percentage(mot.get("f1"))}. '
                      'Dette gjelder MOT på forslaget, uavhengig av styrets anbefaling. '
                      'Den lokale binære avviksmodellen velger ikke stemmeretning og har derfor ingen tilsvarende MOT-måling.</p></details>')
    if data.get("history_policy") == "strict_before_meeting_minus_5_days":
        chunks.append('<p class="muted">Historikken må være mer enn fem dager eldre enn saken som vurderes. '
                      'Tidligere møter i 2024 kan inngå, mens eget møte og senere møter er utelukket. '
                      'Møtedato brukes som tilnærming til når en historisk stemme var tilgjengelig.</p>')
    chunks.append('<p class="muted">Dette forsøket bruker ikke innkallinger eller retningslinjer. Historiske treff gir eksempler på tidligere stemmer, '
                  'men dokumenterer ikke at en ny stemme følger en regel. Prediksjonene er ikke kildebelagte stemmeanbefalinger.</p>')
    if data.get("test_evaluated") is False:
        chunks.append('<p><strong>2025–2026 er ikke kjørt på nytt i dette forsøket.</strong></p>')
    else:
        chunks.append('<p>Rapporten bekrefter ikke at 2025–2026 er urørt i dette forsøket. Ingen testscore vises her.</p>')
    usage = mapping(data.get("usage"))
    chunks.append(f'<p class="muted">Modell: {escape(str(data.get("model", "Ikke oppgitt")))}. '
                  f'API-kall: {count(data.get("api_calls"))}. '
                  f'Input-token: {count(usage.get("input_tokens"))}. Output-token: {count(usage.get("output_tokens"))}.')
    cost = data.get("estimated_usd")
    if isinstance(cost, (float, int)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
        formatted_cost = f"{cost:.2f}".replace(".", ",")
        chunks.append(f' Beregnet API-kostnad: {formatted_cost} USD. Dette er et estimat, ikke en faktura.')
    chunks.append('</p></section>')
    return "".join(chunks)
