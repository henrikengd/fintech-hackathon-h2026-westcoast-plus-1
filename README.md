# westcoast + 1

FinTech Hackathon H2026

## Arbeidsplan

[Status, funn og åpne spørsmål](docs/features/claude-voting-assistant/README.md) samler notatene fra avklaringen og viser hvor arbeidet tas opp igjen.

[Prosjekt](https://github.com/users/henrikengd/projects/3) · [Hovedissue](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1) · [Spesifikasjon](docs/features/claude-voting-assistant/spec.md)

Gjennomføring og verifikasjon står i [leveransejournalen](docs/features/claude-voting-assistant/delivery.md).

## Kjør løsningen

Bruk macOS, Linux eller WSL. Installer [uv](https://docs.astral.sh/uv/getting-started/installation/) og Poppler (`pdftotext`). Kjør fra repoets rot.

```sh
uv sync --locked
mkdir -p data/raw
curl -fL 'https://www.nbim.no/contentassets/cbee6983c7d044a6a6d2f286ed5fa3df/global-voting-guildeines_2025.pdf' -o data/raw/nbim-2025-linked.pdf
curl -fL 'https://investors.sprinklr.com/financial-information/all-sec-filings/content/0001140361-25-017121/0001140361-25-017121.pdf' -o data/raw/sprinklr-2025-proxy.pdf
uv run --no-sync python -m voting_assistant index --manifest data/policies/nbim-2025.json
uv run --no-sync python scripts/prepare_example.py --sprinklr-proxy data/raw/sprinklr-2025-proxy.pdf --output-dir data/raw/development-r2
uv run --no-sync python scripts/prepare_holdout.py --development-manifest data/raw/development-r2/manifest.json --download
```

Kopier `.env.example` til `.env` hvis du ikke allerede har en lokal fil. Sett `ANTHROPIC_API_KEY`, modell-ID og gjeldende input- og outputpriser per million tokens for den valgte modellen. Miljøvariabler satt i terminalen går foran `.env`. Modell og kostnad registreres i rapporten. [Anthropics priser](https://platform.claude.com/docs/en/about-claude/pricing).

Etter oppsett kjører denne ene kommandoen vurdering og poengberegning for de tre frosne testmøtene med 21 stemmevalg. CCC og Sprinklr er utviklingsdata. Testuttrekkene er låst til Poppler-resultatet som ble kontrollert; avvik i uttrekksbytes stopper klargjøringen.

```sh
uv run --no-sync python -m voting_assistant evaluate --manifest data/raw/holdout-2025/manifest.json --output data/raw/holdout-2025/run.json --max-cost-usd 0.80
```

Bruk en ny rapportsti ved en ny måling. Bruk `--resume` for å fortsette med samme manifest og konfigurasjon. Alle forsøk beholdes; et nytt modellresultat er ikke garantert å bli identisk. Rapporten viser MOT-presisjon, MOT-recall, dekning og sammenligning med styrets anbefalinger. [Kildegrunnlaget](docs/data-access.md) beskriver møtene og begrensningene. [Chatoppsettet](docs/claude-setup.md) beskriver den separate demoen i ChatGPT eller Claude. Chatabonnementet brukes i nettleseren; API-kjøringen trenger en egen Anthropic API-nøkkel.

Modell brukt 5. november 2026 var `claude-haiku-5-5`, med `ANTHROPIC_INPUT_USD_PER_MTOK=0.10` og `ANTHROPIC_OUTPUT_USD_PER_MTOK=0.50`. Kontroller prisene før nye kjøringer. Programmet stopper når input overstiger 100 000 tokens. Modellens verktøysvar kan øke input underveis selv om første forespørsel er mindre.

[Liveverifikasjonen](docs/features/claude-voting-assistant/live-verification.md) viser faktisk resultat, første forsøk, omkjøringer, kilder og kostnad. Første sluttkjøring behandlet to av tre møter ferdig, ga ingen automatiske anbefalinger og stoppet på Snowflake etter at konteksten vokste. Dette er en prototype for etterprøvbar manuell gjennomgang, med foreløpig svak automatisk dekning.

Kjør lokale regresjonstester med `uv run --no-sync python -m unittest discover -s tests -v`.

## Datakilder

Arrangøren har levert `real_votes.csv` og `npx_votes.csv`. Se [datakontrollen](docs/features/claude-voting-assistant/data-review.md) og [undersøkelsen av N-PX-feltene](docs/features/claude-voting-assistant/research/npx-provenance.md).

Originalfilene oppbevares lokalt i `data/raw/` og følger ikke Git. De trengs bare hvis dere vil importere eller undersøke arrangørens rådata; den dokumenterte reproduksjonen av det frosne utvalget bruker offentlige kilder og krever ingen av CSV-filene. [Kontrollsummer](docs/features/claude-voting-assistant/data-inventory.json) identifiserer riktig versjon. Opprinnelige eksportkilder og vilkår for viderepublisering er ennå ikke dokumentert.

Stemmedata brukes som evalueringsreferanse. RAG skal søke i daterte retningslinjer. N-PX-filen holdes adskilt fra NBIM-målingen til opphav og felter er kontrollert.

## KI og kodekreditering

- OpenAI Codex ble brukt til repooppsett, avklaring av scope, undersøkelse av Claude-integrasjonen og utarbeiding av spesifikasjon og GitHub-oppgaver, samt datakontroll, kildeundersøkelse, implementering og verifikasjon.

Startpakken ga oppgavebeskrivelsen og evalueringskravene. Koden bruker den offisielle Python-SDK-en for MCP og Anthropic-klienten. Versjonene er låst i `uv.lock`.
