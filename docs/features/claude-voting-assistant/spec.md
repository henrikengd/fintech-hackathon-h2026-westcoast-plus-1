---
feature: claude-voting-assistant
revision: 2
status: approved
tracker: github
parent: https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1
publication: published
approved_on: 2026-11-05
---

# Stemmegivningsassistent i Claude

## Avtale og formål

En analytiker laster opp en offentlig innkalling i Claude og får alle stemmevalg vurdert mot NBIMs daterte retningslinjer. Hver anbefaling viser anvendt regel og selskapsopplysninger. Manglende grunnlag gir manuell sjekk med konkret årsak. En separat API-kjøring måler samsvar med NBIMs publiserte referanser og viser dekning og begrensninger.

Revisjon 2 konkretiserer det gjenstående arbeidet etter den første livepiloten. Brukeren ba tidligere uttrykkelig om å publisere tasks, issues og prosjekt i GitHub. Etter gjennomgangen av pilotens svakheter ba brukeren 5. november «OK $prepare». Denne revisjonen viderefører samme produkt og publiseringsoppdrag. De fem åpne oppgavene oppdateres. Hovedissue #1 og fullførte #3 og #4 gjenbrukes. Prepare starter ingen implementering eller betalte modellkall.

Avklarte valg fra [scope](scope.md) beholdes: case 1, NBIM, én komplett innkalling i Claude, FOR/MOT/AVSTÅ og separat manuell sjekk, lean oppsett og oppgitte API-kreditter på USD 204. Hele saldoen er ikke en verifisert kostnadsramme for neste kjøring. Første verifikasjonsrunde planlegges med samlet tak USD 2, inkludert omkjøringer og angrepspar. Gjeldende modellpriser kontrolleres ved kjøring. Claude-abonnementets chatbruk registreres separat dersom tilgjengelig.

## Brukerens klientvalg under Deliver

5. november 2026 ba brukeren uttrykkelig om å bruke ChatGPT i stedet da Claude-kontoen traff chatkvoten. F-05, chatdelen av F-07 og kontodelen av F-09 verifiseres derfor i brukerens ChatGPT med samme offentlige MCP-tjeneste og faste vurderingsinstruks. Dette endrer ikke API-modellen, datagrunnlaget eller øvrige krav. Claude-tilkoblingen ble prøvd, men den komplette Claude-PDF-vurderingen og angrepsparet ble ikke fullført. Testbevis skal navngi den faktiske klienten og modellen.

## Kilder og bekreftet utgangspunkt

- [Pilotgjennomgangen](pilot-review.md) dokumenterer det faktiske modellresultatet og kildemanglene som denne revisjonen skal løse.
- [Scope](scope.md) bevarer brukerens svar om hele sakslisten, NBIM-tilgang, manuell overlevering og kreditter. [CONTEXT.md](../../../CONTEXT.md) definerer domenebegrepene.
- [Datakontroll](data-review.md), [N-PX-kildekontroll](research/npx-provenance.md), [startpakkens henvisninger](research/starter-links.md) og [lagets datanotat](../../../interne_notater/case1_datagrunnlag.md) har forskjellige kilder og skal ikke slås sammen til én dokumentert NBIM-fasit.
- [Claude-undersøkelsen](research/claude-connector.md) og [Claude-oppsettet](../../claude-setup.md) beskriver muligheten og oppsettet. Dokumentasjon alene beviser ikke en gjennomført chatdemo.
- [Datatilgang](../../data-access.md), [evaluering](../../evaluation.md), [regelindeks](../../policy-index.md) og [leveransejournal](delivery.md) beskriver eksisterende kode og tidligere verifikasjon. Historiske statusavsnitt må leses med dato og revisjon.
- Arrangørens lokale dokumenter er `Regler_og_bedommingskriterier.pdf`, `FinTech_Hackathon_Caser_H2026.pdf`, `FinTech Hackathon H2026.pdf` og `case1_stemmegivning/README.md`. De krever en femminutters demo, kravrespons på maksimalt én side, kjørbart repo eller zip og én kommando for hovedresultatet. Oppgitt frist er 6. november 2026 kl. 12.00. Metode og evaluering teller samlet 60 prosent.

Ved Prepare ble GitHubs standardgren kontrollert som `main` ved `a9bda4903c3f9ae03fab759e45b704503d462c28`. PR #10 er merget. #3 og #4 er lukket med tidligere installasjons-, kontrakt- og MCP-verifikasjon. Den senere livepiloten har fem stemmevalg, to anbefalinger, tre manuelle saker og status `partial`. Anthropic-nøkkelen virker. Faktisk Claude-tilkobling og historisk regelgyldighet er fortsatt uverifisert.

## Akseptansekrav

Krav-ID-ene fra revisjon 1 beholdes. Presiseringene nedenfor erstatter eldre formuleringer for gjenstående arbeid.

| ID | Observerbart krav |
|---|---|
| F-01 | Alle faktiske stemmevalg i en kontrollert innkalling får nøyaktig ett resultat i kildens rekkefølge. Separate kandidatvalg beholdes. Manglende og dupliserte ID-er oppdages. Chat leser hele PDF-en; API-ens dokumenterte klargjøring av samme saksliste kontrolleres separat. |
| F-02 | En anbefaling har etterprøvbar regeltekst, versjon og seksjon, samt faktasitater med dokument og PDF-side. Vesentlige vilkår og benyttede tall bevares. Manuell gjennomgang skiller mellom at et sitat finnes, at det støtter faktapåstanden, og at regelen støtter konklusjonen. |
| F-03 | FOR, MOT og AVSTÅ er stemmeretninger. Manuell sjekk har `recommendation=null` og konkret årsak. Reell faktamangel, motstrid, kildevalideringsfeil og teknisk feil skilles. Sitatfeil skal ikke slette en nyttig mangelbeskrivelse. En gyldig manuell overlevering kan inngå i en fullført kjøring; tekniske feil gir ufullstendig status. |
| F-04 | CCC og Sprinklr brukes videre til utvikling. Minst tre nye, komplette og senere møter fryses før sluttkjøringen, med dokumentert utvalgsregel, kobling, referansesemantikk, kilder, datoer og hash. Historisk anvendelse av regelversjonen dokumenteres utover PDF-metadata. Testfasit og senere begrunnelser holdes utenfor modellinput og RAG. |
| F-05 | En faktisk Claude-samtale bruker `search_guidelines` og `get_guideline` gjennom remote MCP over HTTPS. Alle stemmevalg og minst én kontrollerbar regel- og faktareferanse vises. Flyten gjentas i ny samtale etter omstart. API-ens validator beskrives ikke som en chatkontroll med mindre den faktisk er tilkoblet og testet. |
| F-06 | Én dokumentert kommando kjører analyse og evaluering på det frosne grunnlaget. Rapporten viser baseline, MOT-presisjon, MOT-recall, tellere, anbefalingsdekning, manuell sjekk, eksklusjoner og ufullstendige kjøringer. Første sluttkjøring og alle omkjøringer bevares med årsak og kostnad. |
| F-07 | Alle fem utviklingsresultater gjennomgås manuelt for kildebruk og regelanvendelse. Et faktisk original-/angrepspar kjøres både i API-flyten og i Claude-demoen. Forskjeller i stemme, status, kilder og instruksjonsfølging rapporteres, også ved svakheter. |
| F-08 | En ren installasjon eller lagkamerats checkout kan gjenskape resultatet etter README. Femminutters demo, kravrespons på maks én side, kilder, KI-/kodekreditering og gjeldende status er kontrollert mot de faktiske rapportene. |
| F-09 | Tilgang til den valgte offentlige NBIM-kilden, Anthropic og Claude-connector er kontrollert. Brukes NBIM-API-et, dokumenteres dokumentasjon og faktisk respons. Offentlig avstemte referanser kan brukes uten API-nøkkel. Modell, priser og samlet kostnadsramme registreres; nøkler forblir utenfor Git og logger. |

F-04 konkretiserer den tidligere åpne størrelsen på testsettet. Tre møter er lagets praktiske minstekrav i denne planen, ikke arrangørens krav eller bevis for representativitet. F-09 endrer det tidligere obligatoriske NBIM-API-kallet til verifisering av kilden som faktisk brukes. Det gjør API-tilgang til et mulig hjelpemiddel fremfor en blokkering for offentlige referanser. Uavklart N-PX-opphav skal dokumenteres som utsatt arbeid, ikke blokkere NBIM-leveransen.

## Kontrakter og gjennomføringsvalg

Behold Python 3.12, låste avhengigheter, eksisterende CLI og de to MCP-verktøyene. Regelindeksen har 18 avsnitt og bruker deterministiske ordvektorer. Semantiske embeddings, ekstern database, nytt grensesnitt og modellbytte inngår ikke i denne revisjonen. Haiku-modellen fra piloten er utgangspunktet. Modell-ID og priser kontrolleres før videre kjøring.

`Agenda`, `Proposal`, `Source`, `Assessment` og `MeetingReference` er felles kontrakter i `src/voting_assistant/contracts.py`. Kildenes URL, dato, versjon, SHA-256 og én-basert PDF-side beholdes. API-input begrenses til innkalling og regler; referanser kobles på etter vurdering. Forslagstekst alene er ikke tilstrekkelig faktagrunnlag for alle forslagstyper.

T-04 retter uttrekk og sitathåndtering gjennom eksisterende søke- og vurderingsgrensesnitt. Velg den minste løsningen som bevarer fullstendige regelvilkår, for eksempel stabile tekst-ID-er med kanonisk tekst eller en begrenset sitatkorrigering. Ikke løs feil ved å godta parafraser eller vilkårsløse sitater som verifiserte. Eventuell endring av kildeskjema, instruksjon eller checkpoint-format må versjoneres og samordnes med T-06. Eldre rapporter skal fortsatt kunne leses som historiske resultater. De skal ikke gjenopptas med endret konfigurasjon.

Claude-chatten leser vedlegget og får regeltekst gjennom MCP. API-et bruker en kontrollert, dokumentert saksliste med kildeutdrag. Disse kjøremåtene har forskjellige kontroller og kan ha forskjellige modellversjoner. Bruk felles vurderingsinstruksjon der klienten tillater det, registrer forskjellene, og verifiser begge. Direkte filoverføring fra chat til server og en ny chatvalidator inngår ikke i denne revisjonen.

## Evaluering og menneskelig kontroll

Utviklingssettet omfatter CCC og Sprinklr. T-01 velger nye møter etter dato og tilgjengelige primærkilder før modellen vurderer dem. Alle testmøter er senere enn alle utviklingsmøter. Kandidater, utelatelser og antall MOT oppgis. Et bevisst utvalg av MOT-eksempler merkes som et separat utfordringssett og blandes ikke med hovedmålingen. Ved færre enn tre kvalifiserte møter står F-04 åpent; rapporter begrensningen fremfor å kalle piloten en sluttmåling.

Bare dokumenterte historiske regelversjoner gir grunnlag for påstander om historisk samsvar. Uavklart gyldighet gir eksklusjon med årsak eller en separat, tydelig merket demonstrasjon med foreløpige regler. Stemmer fra `real_votes.csv` må avstemmes mot offentlig NBIM-kilde for de valgte møtene. `npx_votes.csv` og lagets separate N-PX-uttak forblir utenfor hovedmålingen.

MOT måler Against/Withhold på selve forslaget etter dokumentert normalisering. Avvik fra styret er et separat mål. Baselinen «stem som styret» bruker dokumenterte styreanbefalinger; manglende verdier og eventuell alternativ baseline oppgis. Hoved-recall inkluderer manuelle og manglende svar på alle sammenlignbare faktiske MOT. En binær ikke-MOT-telling er ikke bevis for korrekt FOR eller AVSTÅ. Rapporten skal derfor ikke kalle MOT-metrikkene samlet stemmetreff.

T-04 gjennomgår alle fem utviklingssvar. T-06 gjennomgår alle MOT-anbefalinger, alle uenigheter med referansen og minst ett FOR-/manuelt resultat dersom de finnes i sluttkjøringen. Kontroll av begrunnelse rapporteres separat fra stemmesamsvar. Ingen oppgave krever et bestemt gunstig modellresultat eller 100 prosent anbefalingsdekning. Fullføring krever korrekt måling, sporbare begrunnelser og synlige begrensninger.

Frys modell, instruksjon, kode og indeks før sluttkjøringen. Bevar første forsøk. Reelle tekniske omkjøringer får egen årsak, rapport og kostnad; velg ikke beste resultat i etterkant. Dersom sluttresultatet brukes til nye tilpasninger, er settet utviklingsgrunnlag for neste måling. `--resume` overskriver i dag et delvis møte; bevar derfor den foregående rapporten før slik bruk eller innfør eksplisitt forsøkshistorikk.

Motstandstesten bruker et dokumentpar der eneste innholdsendring er en instruksjon om å overstyre reglene. Regelgrunnlag og modelloppsett holdes like innen hvert par. T-05 eier chatprøven, T-06 eier API-prøven. CSV-feltet `injection_flag` erstatter ikke denne testen. Ett par dokumenterer bare denne konkrete prøven.

## Oppgaver og avhengigheter

| ID / issue | Leveranse | Krav | Gjenstående blokkering |
|---|---|---|---|
| T-01 / [#2](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/2) | Frys nye NBIM-møter, kildekoblinger og historiske regler | F-04, F-09 | Ingen tidligere oppgave. Kildetilgjengelighet avklares i oppgaven. |
| T-02 / [#3](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/3) | Prosjekt og kontrakter | F-01, F-03, F-05, F-06, F-08 | Fullført i PR #10. |
| T-03 / [#4](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/4) | Regelindeks og MCP | F-02, F-05, F-07 | Fullført i PR #10. |
| T-04 / [#5](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/5) | Rett faktagrunnlag, sitater og overlevering; håndgå utviklingspiloten | F-01, F-02, F-03, F-07 | #4 er fullført. Kan starte på Sprinklr uten #2. |
| T-05 / [#6](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/6) | Verifiser full Claude-demo, omstart og chatens motstandstest | F-01, F-02, F-03, F-05, F-07, F-09 | #4 er fullført. Faktisk Claude-konto og nettverk må gjøres tilgjengelig. |
| T-06 / [#7](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/7) | Kjør sluttmåling og faktisk API-motstandstest | F-02, F-04, F-06, F-07, F-09 | #2 og #5. |
| T-07 / [#8](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/8) | Ren reproduksjon og ferdig innleveringspakke | F-01 til F-09 | #6 og #7. |

```text
#2 datagrunnlag ---------+
                        +--> #7 API-evaluering ------+
#5 kilder og vurdering --+                           +--> #8 leveranse
#6 Claude-demo og chatens motstandstest -------------+
```

Den gamle kanten #2 → #5 fjernes. Den nye kanten #2 → #7 sikrer at sluttmålingen fortsatt venter på datagrunnlaget. Historiske kanter fra fullførte #3 og #4 beholdes. #7 trenger ikke vente på Claude-kontoen. #2 og #5 er første arbeid som kan tildeles agenter. #6 krever kontotilgang fra et lagmedlem; teknisk forberedelse kan gjøres parallelt.

T-01 eier nye møte-/referansemanifester, historiske policykilder og `docs/data-access.md`. T-04 eier `scripts/prepare_example.py`, vurderingsinstruksjon, `assessment.py`, eventuelle kontraktpresiseringer og utviklingsgjennomgangen. Samordne nødvendige endringer i regelmanifest eller retrieval. T-05 eier `docs/claude-setup.md`, demoartefakter og nødvendige MCP-driftsrettinger. T-06 eier `evaluation.py`, forsøkshistorikk, rapporter og `docs/evaluation.md`. T-07 eier README, kravrespons og endelig status. Samme fil eller kontrakt endres sekvensielt selv når oppgavene ellers er uavhengige. Kontroller faktiske stier ved oppstart.

## Verifikasjon og forutsetninger

Kjør fra en ren checkout med Python 3.12, uv og Poppler. README beskriver nedlasting av låste kilder og indeksering. Følgende grensesnitt finnes allerede:

```sh
uv sync --locked
uv run --no-sync python -m voting_assistant --help
uv run --no-sync python -m unittest discover -s tests -v
uv run --no-sync python -m voting_assistant index --manifest data/policies/nbim-2025.json
uv run --no-sync python scripts/prepare_example.py --sprinklr-proxy data/raw/sprinklr-2025-proxy.pdf
uv run --no-sync python -m voting_assistant evaluate --manifest <frosset-manifest> --output <ny-rapport> --max-cost-usd <gjenstående-ramme>
uv run --no-sync python -m voting_assistant serve --host 127.0.0.1 --port 8000
```

Ved Prepare merket `prepare_example.py` fortsatt Sprinklr som test. T-04 endrer den genererte utviklingspiloten slik at Sprinklr faktisk inngår når utvikling kjøres. Valget `--split development` alene endrer ikke dagens møteetiketter. T-01 eier det separate nye sluttmanifestet.

På Henriks maskin finnes uv under Codex-arbeidsmappens `work/deliver/runtime/bin/uv`, Python 3.12 og en eksisterende venv i det gamle integrasjonstreet. Disse lokale stiene er ikke et installasjonskrav for andre. `.env` og rådata er lokale. Overfør konfigurasjon sikkert til ny kjøremappe ved Deliver uten å skrive hemmeligheter til logger. Den eksisterende pilotens manglende sider og retningslinjevilkår skal dekkes av relevante regresjoner gjennom dagens vurderingsgrensesnitt. Nettverksfrie tester er separate fra faktisk modell- og chatverifikasjon.

T-01 må dokumentere historisk regelperiode og nye kildemøter. T-05 må verifisere konto og HTTPS-endepunkt. T-06 må kontrollere gjeldende priser, samlet forbruk og input før betalt kjøring. CLI-rammen gjelder én rapport; alle rapporter og forsøk må summeres mot rundens USD 2. Hosting bruker gratis eller eksisterende infrastruktur. N-PX-avklaring og bred API-integrasjon ligger utenfor denne rundens kritiske sti.

## Gjennomføring og ferdigkriterium

GitHub er tracker, med [prosjekt 3](https://github.com/users/henrikengd/projects/3) og eksisterende native underoppgaver. Bruk `task` på barn, `ready-for-agent` på #2/#5 og `blocked` på #6/#7/#8 med konkret årsak. Hovedissue får aldri `ready-for-agent`. Publiseringsresultat og kontrollerte relasjoner registreres i [publication.json](publication.json). #3/#4 forblir lukket.

Neste Deliver starter fra oppdatert `origin/main`, med planlagt integrasjonsgren `codex/claude-voting-verification` og arbeidergrener `codex/claude-voting-verification-tXX`. Grenene opprettes først ved Deliver. Bruk egne worktrees fra samme integrasjonsbase. Det gamle integrasjonstreet har lokal konfigurasjon og skal ikke resettes eller slettes. Integrer i avhengighetsrekkefølge, kjør relevante kontroller etter delte endringer og registrer akseptansebevis per oppgave.

Ferdig leveranse krever F-01 til F-09, fullførte kildekontroller, faktiske API-/chatprøver og angrepspar, ren reproduksjon, uavhengig gjennomgang og grønne lokale/CI-sjekker på den nye feature-PR-ens aktuelle commit. Ingen automatisk merge eller innsending til arrangøren inngår. Ved blokkering skal den konkrete mangelen og det faktisk leverte omfanget stå i rapporten. Å publisere denne planen oppfyller ikke implementeringskravene.

Utenfor denne revisjonen ligger automatisk stemmeavgivning, NBIMs interne systemer, generell PDF-ingest for alle dokumenttyper i API-et, selvstendig nettsøk etter manglende fakta under vurdering, ny vektordatabase, modellbenchmark, uavklarte N-PX-data og case 2. Neste steg er `$deliver` med hovedissue #1 som inngang.
