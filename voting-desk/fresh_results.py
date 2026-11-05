"""Read-only view of the separately frozen new-meeting evaluation."""
from html import escape
import json
from pathlib import Path

from board_results import count, metric_row, metric_table, percentage, same_cohort

BASE = Path(__file__).resolve().parent / "data/local-rag/fresh-test-2026-10-v1"


def valid_comparison(data):
    """Require matching, well-formed denominators before comparing either model."""
    local, claude, cohort = (data.get(name) for name in ("local", "claude", "cohort"))
    if not all(isinstance(value, dict) for value in (local, claude, cohort)):
        return False
    counts = [cohort.get("rows"), cohort.get("meetings"), data.get("known_disagreement_rows"),
              data.get("unknown_nbim"), data.get("known_nbim_unknown_board")]
    if any(count(value) == "—" for value in counts):
        return False
    rows, meetings, known, unknown_nbim, unknown_board = counts
    return (0 < meetings <= rows and known + unknown_nbim + unknown_board == rows
            and same_cohort(local, claude) and same_cohort(claude, local) and local["n"] == known)


def render_section(base=BASE):
    base = Path(base)
    try:
        policy = json.loads((base / "selection-policy.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ""
    except (ValueError, OSError):
        return '<section class="evaluation-section"><h2>Nye møter · låst testoppsett</h2><p>Testprotokollen kan ikke leses.</p></section>'
    if not isinstance(policy, dict):
        return '<section class="evaluation-section"><h2>Nye møter · låst testoppsett</h2><p>Testprotokollen har ugyldig format.</p></section>'
    start, end = escape(str(policy.get("date_start", ""))), escape(str(policy.get("date_end", "")))
    chunks = ['<section class="evaluation-section"><h2>Nye møter · låst test av tidligere oppsett</h2>',
              f'<p>Testperiode: <strong>{start} til {end}</strong>. Nye møter i den tidligere undersøkte selskapsgruppen. '
              'Utvalget ble avgrenset før de nye stemmeutfallene ble vurdert. '
              'Denne kjøringen bruker den tidligere lokale terskelen. Den nye F1-terskelen er ikke testet på disse møtene.</p>',
              '<p>Positiv klasse er <strong>NBIM ≠ styrets anbefaling</strong>. '
              'Precision måler hvor mange varslede avvik som er riktige. Recall måler hvor mange faktiske avvik modellen finner.</p>']
    try:
        data = json.loads((base / "report.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ("".join(chunks) + '<p><strong>Testarbeidet pågår.</strong> Ingen ny testscore er publisert ennå. '
                'Resultatene fra 2024 nedenfor er fortsatt utviklingsmålinger.</p></section>')
    except (OSError, ValueError):
        return "".join(chunks) + '<p>Testrapporten kan ikke leses. Ingen testscore vises.</p></section>'
    if not isinstance(data, dict) or data.get("evaluation_kind") != "FROZEN_NEW_MEETINGS" or data.get("target") != "against_board":
        return "".join(chunks) + '<p>Rapporten har ikke riktig testtype og måldefinisjon.</p></section>'
    if not valid_comparison(data):
        return "".join(chunks) + '<p>Modellenes måleutvalg stemmer ikke overens. Sammenligningen er utelatt.</p></section>'
    local, claude, cohort = (data[name] for name in ("local", "claude", "cohort"))
    chunks.append(f'<p><strong>{count(cohort.get("rows"))} forslag fra {count(cohort.get("meetings"))} møter.</strong> '
                  f'{count(local.get("n"))} forslag har kjent NBIM-stemme og styreanbefaling. '
                  f'Av disse er {count(local.get("positive"))} faktiske avvik fra styret.</p>')
    chunks.append('<p>Den lokale modellen, terskelen, Claude-modellvalget, prompten og søkeinnstillingene var låst før nye sakstabeller ble åpnet. '
                  'Begge modellene fullførte sine forsøk, og prediksjonene ble låst før fasiten ble brukt til skåring. '
                  'Ingen nye testutfall inngår i historikken.</p>')
    chunks.append(metric_table([metric_row("Lokal modell · låst terskel", local), metric_row("Claude · historiske vektortreff", claude)],
                              "Avvik fra styret · samme nye testforslag"))
    chunks.append('<p class="muted">En strek betyr at et mål ikke kan beregnes eller mangler i rapporten. '
                  'F1 sammenfatter precision og recall. Alle mål gjelder avvik fra styret.</p>')
    positives = local.get("positive")
    if positives < 30:
        chunks.append(f'<p><strong>Lite grunnlag for å vurdere recall.</strong> Det er bare {positives} faktiske avvik i dette utvalget. '
                      'Så få avvik gir stor usikkerhet om F1 og ytelsen på nye møter. '
                      'Resultatet skal ikke tolkes som et presist anslag for ytelsen i drift.</p>')
    failures = data.get("failed_meetings", [])
    chunks.append(f'<p>Prediksjonsdekning blant de {count(local.get("n"))} målbare forslagene: '
                  f'lokal modell {percentage(local.get("recommendation_coverage"))}, Claude {percentage(claude.get("recommendation_coverage"))}. '
                  f'{len(failures) if isinstance(failures, list) else "—"} Claude-møter ga ikke et godkjent svar. '
                  'Saker uten prediksjon beholdes i målingen. Manglende prediksjon for et faktisk avvik teller som oversett avvik.</p>')
    chunks.append(f'<p class="muted">Utelatt fra avviksmålingen etter prediksjon: {count(data.get("unknown_nbim"))} saker uten kjent NBIM-stemme '
                  f'og {count(data.get("known_nbim_unknown_board"))} med kjent NBIM-stemme, men ukjent styreanbefaling.</p>')
    mot = data.get("claude_literal_mot")
    if isinstance(mot, dict) and count(mot.get("n")) != "—" and mot["n"] == cohort["rows"] - data["unknown_nbim"]:
        chunks.append('<details><summary>MOT målt separat · Claude</summary>'
                      f'<p>Precision {percentage(mot.get("precision"))}, recall {percentage(mot.get("recall"))}, '
                      f'F1 {percentage(mot.get("f1"))}, målt på {count(mot.get("n"))} forslag med kjent NBIM-stemme. '
                      'Den lokale binære modellen gir ingen MOT-prediksjon.</p></details>')
    chunks.append('<p class="muted">NBIM-kilden beskriver publiserte stemmeintensjoner. Dette er en avgrenset ettertidstest på tidligere kjente selskaper, '
                  'ikke et representativt utvalg av hele fondet eller en sanntidstest. Historikken er fryst fra gamle data, med femdagersgrense. '
                  'Ingen dokumenter eller retningslinjer er lagt til modellen i dette forsøket.</p>')
    chunks.append(f'<p class="muted">Claude: {escape(str(data.get("claude_model", "")))}. '
                  f'API-forsøk: {count(data.get("api_attempts"))}. Lokal terskel: {escape(str(data.get("local_threshold", "")))}.</p>')
    return "".join(chunks) + '</section>'
