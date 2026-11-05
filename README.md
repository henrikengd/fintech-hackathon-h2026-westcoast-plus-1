# westcoast + 1

FinTech Hackathon H2026

## Arbeidsplan

[Status, funn og åpne spørsmål](docs/features/claude-voting-assistant/README.md) samler notatene fra avklaringen og viser hvor arbeidet tas opp igjen.

[Prosjekt](https://github.com/users/henrikengd/projects/3) · [Hovedissue](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1) · [Spesifikasjon](docs/features/claude-voting-assistant/spec.md)

Første gjennomføringsoppgave er [T-02, kjørbart prosjekt og dataformater](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/3).

## Kjør hovedresultatet

Installer [uv](https://docs.astral.sh/uv/getting-started/installation/) og kjør fra repoets rot:

```sh
uv python install 3.12
uv sync --locked
uv run --no-sync python -m voting_assistant --help
uv run --no-sync python -m unittest discover -s tests -v
```

Prosjektet krever Python 3.12. Installerte pakker følger `uv.lock`. Testene trenger ingen API-nøkler.

Kopier `.env.example` til lokal `.env` når du trenger en tilkobling. Fyll ut modell-ID og gjeldende tokenpriser for API-evaluering. Prosessen bruker eksporterte miljøvariabler foran verdier fra `.env`.

CLI-en har kommandoene `serve`, `index` og `evaluate`. Bruk `--help` etter kommandoen for å se parameterne.

## Datakilder

Arrangøren har levert `real_votes.csv` og `npx_votes.csv`. Se [datakontrollen](docs/features/claude-voting-assistant/data-review.md) og [undersøkelsen av N-PX-feltene](docs/features/claude-voting-assistant/research/npx-provenance.md).

Originalfilene oppbevares lokalt i `data/raw/` og følger ikke Git. Ved ny checkout må de hentes fra arrangøren og legges der. [Kontrollsummer](docs/features/claude-voting-assistant/data-inventory.json) identifiserer riktig versjon. Opprinnelige eksportkilder og vilkår for viderepublisering er ennå ikke dokumentert.

Stemmedata brukes som evalueringsreferanse. RAG skal søke i daterte retningslinjer. N-PX-filen holdes adskilt fra NBIM-målingen til opphav og felter er kontrollert.

## KI og kodekreditering

- OpenAI Codex ble brukt til repooppsett, avklaring av scope, undersøkelse av Claude-integrasjonen og utarbeiding av spesifikasjon og GitHub-oppgaver, samt datakontroll og kildeundersøkelse.

Krediter eventuell kode fra startpakken eller andre prosjekter her.
