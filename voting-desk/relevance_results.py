"""Read-only display of the fixed retrieval/evidence development comparison."""
from html import escape
import json
from pathlib import Path

from f1_results import metric_row, matching, table
from board_results import count, percentage
from model_setups import CLAUDE, LOCAL


def load(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (ValueError, OSError):
        return None


def render_section(base):
    base = Path(base)
    local = load(base / "relevance-board-v1/summary.json")
    claude = load(base / "relevance-claude-v1/report.json")
    audit = load(base / "relevance-claude-v1/independent-verification.json")
    if local is None and claude is None:
        return ""
    parts = ['<section class="evaluation-section"><h2>Nytt søk og bedre saksgrunnlag</h2>',
             '<p>Historikksøket kombinerer tekstvektorer og ordtreff. Hvert treffutvalg begrenser gjentatt ordlyd. '
             'Claude får i tillegg daterte saksdokumenter der disse finnes. Vi måler fortsatt F1 for NBIM ≠ styret.</p>',
             '<p><strong>Dette er en utviklingssammenligning på tidligere eksponerte data, ikke en ny urørt test.</strong> '
             'Oktober-testen er ikke kjørt på nytt. Historiske møter må ligge før møtedato minus fem dager. '
             'Saksdokumenter må tilhøre riktig møte og være publisert før samme frist.</p>']
    headers = ["Oppsett", "F1", "Precision", "Recall", "Riktige avvik", "Falske avvik", "Oversette avvik"]
    if (local and local.get("target") == "against_board" and local.get("test_evaluated") is False
            and local.get("evaluation_kind") == "EXPOSED_2024_CALIBRATION"):
        selected = local.get("calibration_selected", {})
        rows = []
        for candidate in local.get("comparisons", []):
            metrics = candidate.get("calibration", {}).get("metrics", {})
            if matching(selected, metrics):
                name = candidate["config"]["name"]
                label = " · ".join(LOCAL.get(name, (name,))) + (" · valgt" if candidate.get("selected_on_validation") else "")
                rows.append(metric_row(label, metrics))
        parts.append('<h3>Lokal modell</h3><p>Modellen er valgt på tidsordnet validering fra 2020–2023. '
                     'Deretter er hver forhåndsbestemt variant målt med F1-terskel tilpasset 2024. '
                     '2024-resultatene endrer ikke hvilket oppsett som ble valgt.</p>')
        name = str(local.get("selected_config", {}).get("name", "Ukjent"))
        label = " · ".join(LOCAL.get(name, (name,)))
        parts.append(f'<p>Valgt oppsett: <strong>{escape(label)}</strong>. '
                     f'Validerings-F1: {percentage(local.get("model_selection_validation", {}).get("f1"))}. '
                     f'F1 på 2024 med terskelen fra valideringen: {percentage(local.get("calibration_at_validation_threshold", {}).get("f1"))}.</p>')
        parts.append(table(headers, rows, f'Samme {count(selected.get("n"))} saker · terskler tilpasset 2024'))
        parts.append('<p class="muted">De nye lokale variantene bruker det utvidede historikksøket. Saksdokumentene finnes bare fra 2024 '
                     'og er derfor ikke brukt til å trene denne modellen på 2019–2023.</p>')
    if (claude and claude.get("target") == "against_board" and claude.get("test_evaluated") is False
            and claude.get("evaluation_kind") == "EXPOSED_2024_DEVELOPMENT"):
        parts.append('<h3>Claude · samme modell og faste innstillinger</h3>')
        if claude.get("complete") is not True:
            parts.append(f'<p>Kjøring pågår: {count(claude.get("completed_calls"))} vellykkede og '
                         f'{count(claude.get("failed_calls"))} feilede av {count(claude.get("planned_calls"))} planlagte kall. '
                         'Ingen ferdig F1-sammenligning vises ennå.</p>')
        else:
            if (audit and audit.get("plan_id") == claude.get("plan_id") and audit.get("frozen_hashes_valid") is True):
                history_pair = audit.get("old_vs_history_jointly_answered", {})
                filing_pair = audit.get("filing_jointly_answered", {})
                previous = history_pair.get("previous_claude", {})
                history = history_pair.get("hybrid_history", {})
                filing_history = filing_pair.get("hybrid_history", {})
                filing_evidence = filing_pair.get("hybrid_evidence", {})
                parts.append(f'<p><strong>Kontroll av manglende svar:</strong> På de samme {count(history.get("n"))} sakene '
                             f'der gammel og ny historikkvariant svarte, går F1 fra {percentage(previous.get("f1"))} '
                             f'til {percentage(history.get("f1"))}. På {count(filing_history.get("n"))} dokumentdekkede saker '
                             f'der begge nye varianter svarte, er F1 {percentage(filing_history.get("f1"))} uten dokumenter '
                             f'og {percentage(filing_evidence.get("f1"))} med dokumenter.</p>')
                parts.append('<p><strong>Den høyere dokument-F1 i hovedtabellen viser ingen forbedring blant de besvarte sakene.</strong> '
                             'Avviste dokumentmøter fjerner både riktige avvik og falske alarmer. Vi beholder dem i hovedmålingen, '
                             'men tolker ikke økningen som dokumentert nytte av dokumentene.</p>')
            labels = {variant: " · ".join(setup) for variant, setup in CLAUDE.items()}
            for key, caption in (("overall", "Alle saker fra 2024"), ("filing_subset", "Bare møter med daterte saksdokumenter")):
                metrics = claude.get(key, {})
                baseline = metrics.get("previous_claude", {})
                rows = [metric_row(label, metrics[name]) + [f'{count(metrics[name].get("covered"))} / {count(metrics[name].get("n"))}'] for name, label in labels.items()
                        if matching(baseline, metrics.get(name))]
                parts.append(table(headers + ["Besvarte saker"], rows, f'{caption} · {count(baseline.get("n"))} saker, {count(baseline.get("positive"))} faktiske avvik'))
            coverage = claude.get("evidence_coverage", {})
            parts.append(f'<p>Saksdokumenter dekker {count(coverage.get("proposals_with_filings"))} saker i '
                         f'{count(coverage.get("meetings_with_filings"))} møter. Uten dokumenter gjenbruker siste variant '
                         'svaret fra det nye historikksøket. De to nye variantene bruker identisk prompt. '
                         'Sammenligningen med tidligere Claude endrer både søk og prompt.</p>')
            parts.append(f'<p>Avviste eller feilede svar: {count(claude.get("failed_calls"))}. Manglende svar beholdes i målingen. '
                         'Kildesitater kontrolleres mot hentet tekst; det beviser ikke at tolkningen er riktig.</p>')
            parts.append('<p><strong>Les F1 sammen med svarandel.</strong> Manglende svar på faktiske avvik teller som oversette avvik. '
                         'Manglende svar på enighet med styret lager ingen falsk alarm. Flere manglende svar kan derfor løfte F1 uten at '
                         'flere saker får riktig prediksjon. Dokumentvarianten må også vurderes på saker der begge varianter svarte.</p>')
            diagnostic = claude.get("successful_in_all_variants_diagnostic") or {}
            reference = diagnostic.get("previous_claude", {})
            rows = [metric_row(label, diagnostic[name]) for name, label in labels.items()
                    if matching(reference, diagnostic.get(name))]
            if rows:
                parts.append('<details><summary>Kontroll på saker der alle tre varianter svarte</summary>'
                             '<p>Dette er en diagnostisk delmengde valgt etter svarstatus. Den erstatter ikke hovedmålingen.</p>')
                parts.append(table(headers, rows, f'Samme {count(reference.get("n"))} besvarte saker · diagnostikk'))
                parts.append('</details>')
            intervals = claude.get("paired_f1_difference_intervals") or {}
            interval = intervals.get("new_history_minus_previous") or {}
            if isinstance(interval.get("lower_95"), (int, float)) and isinstance(interval.get("upper_95"), (int, float)):
                low, high = interval["lower_95"] * 100, interval["upper_95"] * 100
                bounds = f'{low:.1f} til {high:.1f}'.replace('.', ',')
                parts.append(f'<p class="muted">Usikkerhetsintervallet for F1-endringen fra tidligere Claude til nytt historikksøk '
                             f'er {bounds} prosentpoeng ved ny trekking av hele møter. '
                             'Dette er beskrivende usikkerhet på utviklingsdata, ikke dokumentasjon på forbedring i drift.</p>')
    parts.append('<p class="muted">Vi bruker ikke dagens NBIM-stemme eller begrunnelse som input. '
                 'Retningslinjer uten verifisert historisk gyldighet er utelatt. Tidsgrensen for gamle stemmer bygger på møtedato; '
                 'den er ikke en verifisert publiseringsdato. Kontrollen kan heller ikke utelukke kunnskap fra modellenes forhåndstrening.</p></section>')
    return "".join(parts)
