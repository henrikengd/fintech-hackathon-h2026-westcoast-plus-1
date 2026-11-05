# Leveransejournal

## Aktiv leveranse, revisjon 2

Startet 5. november 2026 etter brukerens `$deliver`. Godkjent kravgrunnlag er [spesifikasjon revisjon 2](spec.md), hovedissue #1. Fjernstandardgrenen er `main` ved `fb704fb17e907350f41ccc522e2a2dd613c1f108`; ingen åpen feature-PR ved oppstart. PR #10 er merget. De gamle arbeidstrærne og lokal konfigurasjon er bevart.

Integrasjonsgren er `codex/claude-voting-verification`. Arbeidstrærne ligger under `/Users/henrik.noteless/.codex/worktrees/`, hver med repoets navn som undermappe. Bare koordinatoren integrerer og oppdaterer denne journalen.

| Oppgave | Arbeider | Worktree-navn / gren | Tildelt base | Status |
|---|---|---|---|---|
| T-01 / #2 | `/root/verification_data` | `voting-data` / `codex/claude-voting-verification-t01` | `fb704fb` | Pågår: nye møter og historiske kilder |
| T-04 / #5 | `/root/verification_assessment` | `voting-assessment` / `codex/claude-voting-verification-t04` | `fb704fb` | `0caf54e` integrert som `f8a5984`; 45 tester passerte. Første liveforsøk krevde større svarramme. |
| T-05 / #6 | `/root/verification_demo`, koordinator for faktisk chat | `voting-demo` / `codex/claude-voting-verification-t05` | `fb704fb` | `333b04e` og `2a4e42c` integrert som `6cdbd97` og `f8413ed`. Faktisk PDF-chat kjører. |
| T-06 / #7 | `/root/verification_assessment` | `voting-evaluation` / `codex/claude-voting-verification-t06` | `f8a5984` | Historikk, rapportering og API-angrepspar forberedes. Sluttkjøring venter på integrert #2 og verifisert #5. |
| T-07 / #8 | Koordinator | `voting-verification` / integrasjonsgren | `fb704fb` | Venter på #6 og #7 |

Felles skrivetilgang er fordelt etter spesifikasjonen. T-04 eier `assessment.py`, `contracts.py` og `prepare_example.py`. T-01 eier nye data-/policyfiler og ny klargjøring. T-05 eier demooppsett og nødvendig serverarbeid. Alle betalte API-kall utføres av koordinatoren etter integrasjon, innen samlet USD 2. Rundens lokale kostnadsjournal ligger i Codex-arbeidsmappens `work/deliver-r2/budget.json`. Ved oppstart var ingen modellkall gjort; oppdatert status følger nedenfor.

### Verifisert grunnlag

Låst installasjon på Python 3.12.12 fra eksisterende uv-cache passerte. Alle 37 eksisterende tester passerte på `fb704fb`. Første installasjonsforsøk pekte på standardcache og manglet uvicorn offline; riktig isolert cache løste dette uten endring av avhengigheter. Kode for #3 og #4 er integrert fra tidligere PR. Deres tidligere lokale MCP-verifikasjon står i den historiske journalen under.

Claude-fanen viste først innlogging. Brukeren opplyste deretter at kontoen er innlogget og at den er separat fra kontoen med API-kreditter. API-nøkkelen er kopiert direkte til lokal ignorert `.env` i integrasjonsmappen med filmodus 0600. Ingen nøkkel er skrevet til journal eller logger. Faktisk connector-test gjenstår.

Neste steg er å verifisere Claude-tilgangen, integrere arbeidercommits etter gjennomgang og kjøre utviklingspiloten før ny sluttmåling. Uavhengig full gjennomgang samt separate Spec- og Standards-gjennomganger gjenstår. Ingen ny PR er opprettet.

### Integrert verifikasjon under arbeid

5. november 2026, første utviklingsforsøk på `6cdbd97`: manifest `f16dcdeec535b6ab844369e1f4b40d5e3065871ee86130193948e27363b63a65`, Haiku 5.5, input USD 0,10 og output USD 0,50 per million tokens. Pris og maksimalt 128k output kontrollert i [modelloversikten](https://platform.claude.com/docs/en/models/haiku-5-5/overview). Rapport `data/raw/development-r2/first-run.json` bevares. Registrert kostnad USD 0,0211955. CCC ga tre gyldige manuelle svar; Sprinklr ble `partial` med fem manuelle svar fordi modellen nådde 10 000 output-tokens. Ingen ufullstendige anbefalinger ble godkjent. T-05-arbeideren retter den avgrensede svarrammen i en egen liten commit før nytt utviklingsforsøk og før holdout.

Innlogging er faktisk kontrollert i Claude. Kontoen er Free og støtter egen connector. En midlertidig HTTPS-tunnel eksponerer bare den offentlige regelindeksen via lokal port 8002. Connectoren er lagt til og aktiv; ekte `search_guidelines` og `get_guideline`-kall er observert. Kontroll-PDF med alle 70 originalsider og blank side 71 er lastet opp med den faste instruksen. Svaret og kildekontrollen er ennå ikke ferdige. Ingen API-nøkkel er sendt til chatten.

Kontroll-/angreps-PDFene har identiske originalsidebilder ved Poppler 72 dpi, samme metadata og kun angrepstekst på den ekstra siden. Arbeiderens lokale PDF-verifikasjon er kontrollert; dette er ikke i seg selv en bestått modelltest.

## Historisk leveranse, revisjon 1

> Status 5. november etter livepilot og Prepare revisjon 2: PR #10 er merget. Anthropic-tilgang er prøvd, med fem stemmevalg, to anbefalinger og tre manuelle saker i siste forsøk. Se [pilotgjennomgangen](pilot-review.md) og [gjeldende spesifikasjon](spec.md). Avsnittene under beskriver den tidligere leveransen og erstattes ikke som historisk bevis. Ny implementering er ikke startet av Prepare.

Spesifikasjon revisjon 1. Hovedoppgave [#1](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1). Basen er `main` ved `299e422b3d98d08a967669c2cc5e3175009d5007`. Integrasjonsgren er `codex/claude-voting-assistant`.

Ved oppstart var alle sju deloppgaver åpne. Avhengighetene i GitHub samsvarte med spesifikasjonen. Det fantes ingen feature-PR. Python 3.12.12 og uv 0.10.2 ble installert isolert i prosjektets arbeidsmappe. Arbeidergrenene bruker prefikset `codex/claude-voting-assistant-`. Arbeidstrærne ligger under `work/deliver/` i den lokale Codex-arbeidsmappen. Kjør `git worktree list` for fullstendige stier.

| Oppgave | Arbeider og tre | Base | Arbeidercommit → integrert | Status |
|---|---|---|---|---|
| T-01 / #2 | data, `t01` | `299e422` | `7b18205` → `122f238` | Filimport og to offentlige møteavstemminger. Live API, konto, kreditter og historisk virkningsperiode gjenstår. |
| T-02 / #3 | foundation, `t02` | `299e422` | `afb9aba` → `20e0038` | Lukket i GitHub etter ren låst installasjon, kontrakt- og CLI-test og grønn CI. |
| T-03 / #4 | foundation, `t03` | `20e0038` | `65149df` → `31929a5` | Lukket i GitHub etter verifisering av 18 regelavsnitt og begge MCP-verktøyene. |
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


## Pull request

[PR #10](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/pull/10) er åpen som utkast mot `main`. [GitHub Actions](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/actions/runs/42020548597) passerte på `8fdf25c`, som har samme kode som den gjennomgåtte `594cb08`. Oppgave #3 og #4 er lukket med testbevis. Oppgave #2, #5, #6, #7 og #8 er åpne. PR-siden viser sjekkene for gjeldende revisjon.

Neste steg er å kjøre med lagets API-tilgang, kontrollere pilotens reelle anbefalinger og motstandstesten, og prøve Claude-demoen over HTTPS. PR-en forblir utkast frem til live-verifikasjon.
