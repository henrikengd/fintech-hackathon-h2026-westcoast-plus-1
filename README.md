# westcoast + 1

FinTech Hackathon H2026

## Arbeidsplan

[Status, funn og åpne spørsmål](docs/features/claude-voting-assistant/README.md) samler notatene fra avklaringen og viser hvor arbeidet tas opp igjen.

[Prosjekt](https://github.com/users/henrikengd/projects/3) · [Hovedissue](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1) · [Spesifikasjon](docs/features/claude-voting-assistant/spec.md)

Gjennomføring og verifikasjon står i [leveransejournalen](docs/features/claude-voting-assistant/delivery.md).

## Kjør piloten

Installer [uv](https://docs.astral.sh/uv/getting-started/installation/) og Poppler (`pdftotext`). Kjør fra repoets rot.

```sh
uv sync --locked
mkdir -p data/raw
curl -fL 'https://www.nbim.no/contentassets/cbee6983c7d044a6a6d2f286ed5fa3df/global-voting-guildeines_2025.pdf' -o data/raw/nbim-2025-linked.pdf
curl -fL 'https://investors.sprinklr.com/financial-information/all-sec-filings/content/0001140361-25-017121/0001140361-25-017121.pdf' -o data/raw/sprinklr-2025-proxy.pdf
uv run --no-sync python -m voting_assistant index --manifest data/policies/nbim-2025.json
uv run --no-sync python scripts/prepare_example.py --sprinklr-proxy data/raw/sprinklr-2025-proxy.pdf
```

Kopier `.env.example` til `.env`. Sett `ANTHROPIC_API_KEY`, modell-ID og gjeldende input- og outputpriser per million tokens for den valgte modellen. Miljøvariabler satt i terminalen går foran `.env`. Modell og kostnad registreres i rapporten. [Anthropics priser](https://platform.claude.com/docs/en/about-claude/pricing).

Etter oppsett kjører denne kommandoen vurdering og poengberegning for hele testmøtet.

```sh
uv run --no-sync python -m voting_assistant evaluate --manifest data/raw/pilot/manifest.json --output data/raw/pilot/run.json --max-cost-usd 2
```

Bruk `--resume` for å fortsette med samme manifest og konfigurasjon. Rapporten viser MOT-presisjon, MOT-recall, dekning og sammenligning med styrets anbefalinger. [Pilotens kildegrunnlag](docs/data-access.md) beskriver møtene og begrensningene. [Claude-oppsett](docs/claude-setup.md) beskriver den separate chatdemoen.

Kjør lokale regresjonstester med `uv run --no-sync python -m unittest discover -s tests -v`.

## Datakilder

Arrangøren har levert `real_votes.csv` og `npx_votes.csv`. Se [datakontrollen](docs/features/claude-voting-assistant/data-review.md) og [undersøkelsen av N-PX-feltene](docs/features/claude-voting-assistant/research/npx-provenance.md).

Originalfilene oppbevares lokalt i `data/raw/` og følger ikke Git. Ved ny checkout må de hentes fra arrangøren og legges der. [Kontrollsummer](docs/features/claude-voting-assistant/data-inventory.json) identifiserer riktig versjon. Opprinnelige eksportkilder og vilkår for viderepublisering er ennå ikke dokumentert.

Stemmedata brukes som evalueringsreferanse. RAG skal søke i daterte retningslinjer. N-PX-filen holdes adskilt fra NBIM-målingen til opphav og felter er kontrollert.

## KI og kodekreditering

- OpenAI Codex ble brukt til repooppsett, avklaring av scope, undersøkelse av Claude-integrasjonen og utarbeiding av spesifikasjon og GitHub-oppgaver, samt datakontroll, kildeundersøkelse, implementering og verifikasjon.

Startpakken ga oppgavebeskrivelsen og evalueringskravene. Koden bruker den offisielle Python-SDK-en for MCP og Anthropic-klienten. Versjonene er låst i `uv.lock`.
