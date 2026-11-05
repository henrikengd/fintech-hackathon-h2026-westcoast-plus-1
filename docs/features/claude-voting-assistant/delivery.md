# Leveransejournal

Spesifikasjon revisjon 1. Hovedoppgave [#1](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1). Basen er `main` ved `299e422b3d98d08a967669c2cc5e3175009d5007`. Integrasjonsgren er `codex/claude-voting-assistant`.

Ved oppstart var alle sju deloppgaver åpne. Avhengighetene i GitHub samsvarte med spesifikasjonen. Det fantes ingen feature-PR. Python 3.12.12 og uv 0.10.2 ble installert isolert i prosjektets arbeidsmappe. Arbeidergrenene bruker prefikset `codex/claude-voting-assistant-`. Arbeidstrærne ligger under `work/deliver/` i den lokale Codex-arbeidsmappen. Kjør `git worktree list` for fullstendige stier.

| Oppgave | Arbeider og tre | Base | Arbeidercommit → integrert | Status |
|---|---|---|---|---|
| T-01 / #2 | data, `t01` | `299e422` | `7b18205` → `122f238` | Filimport og to offentlige møteavstemminger. Live API, konto, kreditter og historisk virkningsperiode gjenstår. |
| T-02 / #3 | foundation, `t02` | `299e422` | `afb9aba` → `20e0038` | Ren låst installasjon, kontrakter, CLI og tester kontrollert lokalt. |
| T-03 / #4 | foundation, `t03` | `20e0038` | `65149df` → `31929a5` | 18 daterte regelavsnitt og begge MCP-verktøyene verifisert lokalt. |
| T-04 / #5 | assessment, `t04` | `20e0038` | `b615c9f` → `a83b4c2` | API- og kildevalideringskode testet med simulert transport. Live-kjøring og manuell gjennomgang av faktiske modellresultater gjenstår. |
| T-05 / #6 | koordinator | `31929a5` | | HTTPS-oppsett og demo dokumentert. Faktisk Claude-konto, tunnel og ny samtale etter omstart gjenstår. |
| T-06 / #7 | data, `t06` | `122f238` | `a3dcef9` → `68b814a` | Tidsdelt pilot, rapport og gjenopptak testet med simulert transport. Betalt kjøring og faktisk motstandstest gjenstår. |
| T-07 / #8 | koordinator | `68b814a` | | README og kravrespons klargjort. Live demo og endelig innleveringsverifikasjon gjenstår. |

T-04 og T-06 ble delt i kode som kunne bygges mot avtalte kontrakter og akseptanse som avhenger av live-tilgang. Kodestykkene ble integrert i avhengighetsrekkefølge. Oppgavene med utestående live-krav skal forbli åpne.

## Lokale kontroller

- `uv sync --locked --offline` med Python 3.12.12 installerte fra låsefilen. `python -m voting_assistant --help` viste de tre avtalte kommandoene.
- `python -m unittest discover -s tests -v` passerte 31 tester på integrasjonsgrenen ved `68b814a`. Testene dekker kontrakter, CSV-import, regler, modellgrensesnitt, referanseskille, metrikker og kostnader ved avbrudd.
- `python -m voting_assistant index --manifest data/policies/nbim-2025.json` bygde 18 avsnitt fra den kontrollerte PDF-en. Styrevalg, lederlønn og revisor ga forventet første treff på side 9, 12 og 16.
- Den offisielle MCP-klienten kjørte initialize, list og begge oppslagene over lokal Streamable HTTP. Ugyldig vert og manglende bearer ga henholdsvis 421 og 401. Ukjent regelversjon, tomt treff og manglende datodekning ga egne utfall.
- `scripts/prepare_example.py` kontrollerte PDF-hash og bygde separate filer for innkalling og referanse. CCC har tre forslag til utvikling. Sprinklr har fem senere stemmevalg i test.
- Hele `evaluate`-kommandoen ble kjørt på pilotens fem test-ID-er med en simulert Anthropic HTTP-transport. Ingen referansefelt var med i modellforespørselen. Gjenopptak gjenbrukte det ferdige møtet uten nye modellkall. Stubresultatet er et programtestresultat. Det gir ingen måling av modellkvalitet.

## Gjenstående verifikasjon

Sett inn lagets NBIM- og Anthropic-nøkler i lokal `.env` før live-verifikasjon. For API-evalueringen må også modell-ID og gjeldende tokenpriser være satt. Kontroller historisk anvendelse av regelversjonen, kjør den dokumenterte piloten og en kontrollert original-/angrepsvariant, og avstem kildene manuelt. Kjør deretter en faktisk Claude-samtale med PDF og MCP over HTTPS.

## Gjennomgang

Tre uavhengige gjennomganger dekket korrekthet, spesifikasjon og standarder for `048c75c`. Gjennomgangen fant at indeksen kunne overskrive en kilde, at forslag kunne mangle i delrapporter og at et tomt søk kunne ende med anbefaling. Den påpekte også manglende låsing av pilotens regelkilde, avvik i søkegrenser og at CCC-eksemplet kun egner seg til kontroll av saksliste og manuell sjekk.

`594cb08` retter feilhåndteringen, låser kildehashen, samordner søkegrensene og dokumenterer CCC. De tre gjennomgangene kontrollerte rettingene. Ren installasjon, 34 tester, MCP over lokal HTTP og evalueringsflyten med simulert Anthropic-transport passerte på `594cb08`.

Koden kan vurderes i en PR. Full leveranse avventer lagets live-verifikasjon. Hovedoppgaven forblir åpen.
