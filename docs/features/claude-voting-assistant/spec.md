---
feature: claude-voting-assistant
revision: 1
status: approved
tracker: github
publication: published
approved_on: 2026-11-05
---

# Stemmegivningsassistent i Claude

## Avtale og kilder

Brukeren ba 5. november 2026 om å kjøre Prepare og «tasks i github repoet. Lag et prosjekt med tasks og issues». Dette er eksplisitt autorisasjon til å konkretisere det avklarte scopet og publisere prosjekt og oppgaver. Revisjon 1 er planens kravgrunnlag. Tekniske valg nedenfor er planleggingsvalg innenfor scopet. Dokumentet beskriver kommende implementering.

Grunnlaget er [scope.md](scope.md), [Claude-faktanotatet](research/claude-connector.md) og [domenebegrepene](../../../CONTEXT.md). Scopet dokumenterer brukerens valg av NBIM-data, hele sakslisten og manuell sjekk ved manglende opplysninger. Faktanotatet beskriver dokumentert plattformstøtte. Integrasjonen og API-tilgangene er ennå ikke prøvekjørt.

Arrangørens utdelte dokumenter er Regler_og_bedommingskriterier.pdf, FinTech Hackathon H2026.pdf, FinTech_Hackathon_Caser_H2026.pdf og case1_stemmegivning/README.md. De oppgir fem minutters demo, en kravrespons på maksimalt én side, kjørbart repo eller zip og én kommandolinje for hovedresultatet. Innlevering er fredag 6. november 2026 kl. 12.00. Metode og evaluering teller samlet 60 prosent.

## Ønsket atferd

En analytiker laster opp en offentlig innkalling i Claude og ber om vurdering etter NBIMs retningslinjer. Claude identifiserer hele sakslisten, henter relevante regelavsnitt gjennom vår MCP-connector og leverer en vurdering per forslag. Brukeren kan finne igjen både regelen og selskapsopplysningene. Ufullstendig grunnlag gir manuell sjekk med konkret årsak.

## Akseptansekrav

| ID | Observerbart krav |
|---|---|
| F-01 | Alle forslag i en kontrollert innkalling får nøyaktig ett resultat i kildens rekkefølge. Forslag som ikke kan vurderes, er fortsatt synlige. Manglende og dupliserte ID-er oppdages. |
| F-02 | Hver anbefaling har regeltekst, versjon, seksjon og kilde, samt sporbare selskapsopplysninger fra innkallingen. Henvisningene støtter begrunnelsen. |
| F-03 | Stemmeanbefaling er FOR, MOT eller AVSTÅ. Manuell sjekk er en separat status med årsak og manglende opplysninger. Motstridende grunnlag, tomt søk, feil versjon og verktøyfeil håndteres synlig. |
| F-04 | NBIM-referanser kobles til riktig møte og forslag. Et frosset utviklings- og senere testutvalg bevarer kilde, dato og regelversjon. Testfasit og fremtidige opplysninger holdes utenfor modellinput. |
| F-05 | En reell Claude-samtale kan bruke search_guidelines og get_guideline via remote MCP. Søket filtrerer på gyldige NBIM-regler for datoen og returnerer etterprøvbare kilder. |
| F-06 | Én dokumentert kommando gjenskaper analyse og evaluering med baseline, MOT-presisjon, MOT-recall, tellere og anbefalingsdekning. Manuell sjekk og delvis feilede kjøringer rapporteres eksplisitt. |
| F-07 | Søkegrunnlag og begrunnelser er kontrollert på et manuelt utvalg. En instruksjon skjult i et saksdokument er testet og utfallet rapportert. |
| F-08 | Ren installasjon, faktisk chatdemo, API-kjøring, README og kravrespons er verifisert. README dekker kilder, KI-bruk, kodekreditering, nødvendige nøkler, oppsett og kjørekommando. |
| F-09 | Faktisk NBIM-/Anthropic-tilgang og connector-konto er kontrollert. Modellkjøringer har konfigurert kostnadsramme innenfor oppgitte USD 204 i eksisterende kreditter. Nøkler forblir i lokal eller driftsmiljøets hemmelighetskonfigurasjon. |

## Kontrakter

- Saksliste har meeting_id, company_id, meeting_date, document_source og en ordnet liste med forslag. Forslag har proposal_id, originaltekst og kildereferanser.
- En kilde identifiseres med dokument, URL der tilgjengelig, seksjon eller side, dokumentdato, versjon og hash. Sidetall skal kunne spores til original-PDF-en.
- En vurdering har proposal_id, status, recommendation, rationale, policy_sources, factual_sources, missing_information og uncertainty_reason. Status er assessed eller manual_review. recommendation er FOR, MOT, AVSTÅ eller null. manual_review krever null og en konkret årsak.
- Usikkerhet beskrives med dokumentert grunnlag og separat manuell status. Eventuelt numerisk modellanslag må evalueres og merkes som anslag. Vektorsøkets likhetsscore beskriver relevans i søket.
- search_guidelines mottar query, as_of_date og en begrenset limit. get_guideline mottar guideline_id og policy_version. Resultatene har tekst, regel-ID, versjon, gyldighet, seksjon og kilde. Manglende historisk versjon gir et eksplisitt utfall.
- Evalueringsreferanser oppbevares separat fra vurderingsinput. Semantikken til NBIM-feltet dokumenteres, inkludert stemmeintensjon kontra avgitt stemme.
- En kjøring identifiserer inputmanifest, instruksjon, modell, indeks og regelversjoner. Verktøykall, svar og fullføringsstatus lagres uten nøkler. Gjenopptak gjenbruker bare fullførte svar fra samme konfigurasjon.

## Implementeringsvalg for førsteversjonen

Python 3.12 og den offisielle MCP-SDK-en gir et lite prosjekt som passer med startpakkens Python-kode. Bruk Anthropic API for automatisk evaluering og en lokal, persistert vektorindeks for reglene. Bibliotekversjoner og embeddingmodell låses i implementeringen. Det opprettes ingen ekstra databasekonto som del av denne planen.

Claude leser vedlegget og sender eksplisitte verktøyargumenter. MCP-serveren tilbyr lesing av offentlige regelavsnitt. Automatisk tilgang fra en remote connector til originalvedlegget er ikke bekreftet. T-05 prøver den faktiske flyten tidlig.

Velg én gratis eller eksisterende HTTPS-driftsmåte i T-05. En tunnel kan være tilstrekkelig for demonstrasjonen dersom den er stabil i det faktiske nettverket. Tilgangsoppsett og eventuell fast connector-legitimasjon dokumenteres før bruk. Et separat hostingbudsjett er ikke avtalt.

CLI-kontrakten skal gi `python -m voting_assistant serve`, `python -m voting_assistant index --manifest <path>` og `python -m voting_assistant evaluate --manifest <path> --output <path> --max-cost-usd <amount>`. Dette er planlagte kommandoer som T-02, T-03 og T-06 innfører. Evalueringskommandoen skal kunne kjøre hele analysen. En eventuell modus for gjenberegning fra lagrede svar merkes særskilt.

En enkel CI-kjøring installerer låste avhengigheter og kjører kontrakt-, søke- og metrikktester med lokale testdata. Faktiske API- og chattester dokumenteres separat med nødvendige tilganger.

## Evaluering og avgrensning

Start med et lite dokumentert utvalg og et kostnadsanslag før større modellkjøring. Velg komplette møter for utvikling og senere møter for sluttmåling. Antall møter og forslag fastsettes i T-01 ut fra datatilgang og tid. Resultatene skal oppgi omfang og antall MOT-stemmer.

«Stem som styret» krever faktisk styreanbefaling. Startpakkens alltid-ikke-MOT-prediksjon kan bare brukes under et korrekt navn. Hoved-recall teller alle faktiske MOT-forslag, også dem systemet sender til manuell sjekk. Presisjon bruker modellens MOT-prediksjoner. Null nevnere rapporteres tydelig med tellere. Et separat mål på vurderte saker kan supplere hovedmålene.

Chatdemo og API-evaluering har ulike kjøremiljøer. Bruk samme vurderingsinstruksjon og regelverktøy der det er mulig, og dokumenter forskjeller. Kontroller hele PDF-/verktøyflyten i Claude i tillegg til automatiske kjøringer.

Utenfor førsteversjonen ligger automatisk stemmeavgivning, selvstendig nettsøk etter manglende selskapsopplysninger, NBIMs interne systemer, utrulling i NBIMs organisasjon og case 2. Førsteversjonen viser manuell sjekk når grunnlaget ikke strekker til.

## Oppgaveplan

| Oppgave | Leveranse | Krav | Blokkert av |
|---|---|---|---|
| [T-01 / #2](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/2) | Kontrollere API-tilgang og fryse første NBIM-testgrunnlag | F-04, F-09 | Ekstern tilgang |
| [T-02 / #3](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/3) | Lage kjørbart Python-prosjekt og felles dataformater | F-01, F-03, F-05, F-06, F-08 | Kan starte |
| [T-03 / #4](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/4) | Hente kildebelagte NBIM-regler gjennom MCP | F-02, F-05, F-07 | [#3](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/3) |
| [T-04 / #5](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/5) | Vurdere hele sakslisten med kilder og manuell sjekk | F-01, F-02, F-03 | [#2](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/2), [#4](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/4) |
| [T-05 / #6](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/6) | Koble MCP-tjenesten til Claude og teste dokumentflyten | F-05, F-08, F-09 | [#4](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/4) |
| [T-06 / #7](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/7) | Reprodusere stemmeevaluering og motstandstest | F-04, F-06, F-07, F-09 | [#5](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/5) |
| [T-07 / #8](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/8) | Verifisere hele demoen og pakke innleveringen | F-01, F-02, F-03, F-04, F-05, F-06, F-07, F-08, F-09 | [#6](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/6), [#7](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/7) |


Blokkeringer er ekte forutsetninger for fullført oppgave. T-01 og T-02 har ingen innbyrdes avhengighet. T-01 venter på tilgang fra laget. T-03 kan starte etter T-02 med offentlige regler. T-05 kan prøve Claude-tilkoblingen mens T-04 utvikles. T-06 arver T-01 og T-03 gjennom T-04.

T-02 eier oppsett, felles kontrakter og CI først. T-03 og T-05 deler MCP-server og driftskonfigurasjon og må koordinere endringer. T-04 og T-06 deler vurderingsresultatet og må holde kontrakten stabil. T-07 samler dokumentasjonen etter integrasjon. Arbeid som berører samme filer integreres sekvensielt.

## Gjennomføring og sjekker

Verifisert standardgren er `main`. Planlagt integrasjonsgren er `codex/claude-voting-assistant`, med arbeidergrener `codex/claude-voting-assistant-tXX`. De opprettes først ved Deliver. En ren checkout eller worktree lages fra oppdatert integrasjonsgren, og alle arbeidere bruker kontraktene og låsefilen fra T-02. Lokale nøkler settes i hver kjøreomgivelse etter behov.

Ved inspeksjon finnes README, .gitignore og Scope-dokumentasjon. Applikasjonskode, installasjonskommando og tester kommer i T-02. Lokalt er Python 3.9.6 og gh tilgjengelig, mens uv ikke ble funnet. Python 3.12 må derfor bekreftes eller installeres under implementering.

Hvert bidrag må vise akseptansebevis og relevante tester før integrasjon. Fullført feature krever dekning av F-01–F-09, fungerende chatdemo, reproduksjon fra ren checkout, dokumentert uavhengig gjennomgang og passerende CI på én reviewklar feature-PR mot main. Planen avsluttes med en umerget PR. Innsending til arrangøren krever egen instruksjon.

## Tilganger og publisering

Brukeren har oppgitt tilgang til NBIM-API og et lagmedlems API-kreditter. Nøkler og dokumentasjonslenke legges inn senere. Dette er konkrete gjennomføringsavhengigheter i T-01 og T-05. Tilgangene har ikke blitt prøvd under Prepare.

GitHub er tracker. Hovedissuen har label enhancement og fungerer som spesifikasjon. Barneissues har task, og merkes ready-for-agent bare når både saklige og tekniske blokkeringer er løst. Andre oppgaver har blocked med årsak i teksten. Native underissues og blocking-relasjoner brukes sammen med eksplisitte referanser. Prosjektet får statuser Todo, In Progress og Done.

Hovedissue er [#1](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1). Prosjektet er [westcoast + 1 · Stemmegivningsassistent](https://github.com/users/henrikengd/projects/3). Sju barneissues er publisert med native underissue- og blocking-relasjoner. Alle åtte issues er lagt til prosjektet og har status Todo. Prosjektet er privat, og standardrepoet er kontrollert mot dette repoet. T-02 / #3 kan starte nå. T-01 / #2 venter på nøklene fra laget.
