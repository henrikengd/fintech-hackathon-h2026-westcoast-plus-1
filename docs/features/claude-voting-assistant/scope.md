---
feature: claude-voting-assistant
status: ready-for-prepare
updated: 2026-11-05
---

# Stemmegivningsassistent i Claude

## Formål

Hjelpe en analytiker med å vurdere forslag til en generalforsamling mot en forvalters stemmeretningslinjer. Brukeren skal kunne se anbefaling, anvendt regel, dokumenterte selskapsopplysninger og hvilke opplysninger som mangler.

Laget er «westcoast + 1». Leveransen inngår i FinTech Hackathon H2026. Henrik har bedt om et lean opplegg og startet Scope etter diskusjon av case 1, RAG og en connector til Claude.

## Beslutningsstatus

- Bekreftet av brukeren — et minimalt GitHub-repo og en scope-prosess for løsningen som er diskutert.
- Retningen som scopes — case 1 med dokumentopplasting i Claude og en MCP-connector til søk i stemmeretningslinjer. Dette er arbeidsgrunnlaget fra samtalen.
- Bekreftet av brukeren 5. november — laget har fått tilgang til et NBIM-API i tillegg til startpakken. Tilgangen og feltene er ennå ikke kontrollert av agenten.
- Bekreftet av brukeren 5. november — første demo skal behandle hele sakslisten i én innkalling.
- Bekreftet av brukeren 5. november — ved manglende opplysninger skal assistenten gi beskjed og sende forslaget til manuell sjekk.
- Bekreftet av brukeren 5. november — et lagmedlem har API-kreditter knyttet til sitt Claude-abonnement som laget kan bruke, oppgitt til USD 204. Den faktiske API-nøkkelen og saldoen er ennå ikke kontrollert av agenten.
- Bekreftet av brukeren 5. november — lagmedlemmet legger inn NBIM-API-nøkkelen senere. Dokumentasjonslenke eller filsti er ennå ikke mottatt.
- Gjenstår som tekniske avklaringer i Prepare — API-dokumentasjon og felter, relevante historiske regelversjoner og verifikasjon av kontoene.

Scopet har status `ready-for-prepare`. Brukeren har eksplisitt valgt hele sakslisten, NBIM som datagrunnlag og manuell sjekk ved manglende opplysninger. De øvrige konkretiseringene nedenfor er forslag basert på samtalen og arrangørens krav. Produktvalgene er tilstrekkelige for Prepare. API-nøkler og datakontroll er tekniske forutsetninger for gjennomføring.

## Bruker og første arbeidsflyt

Den tiltenkte brukeren er en analytiker som forbereder stemmegivning. Hackathondemoen bruker offentlige dokumenter i lagets egen Claude-konto.

1. Brukeren laster opp en offentlig innkalling i Claude og ber om vurdering etter en angitt forvalters retningslinjer.
2. Claude identifiserer alle forslagene i innkallingen og leser selskapsopplysningene som er nødvendige for vurderingen.
3. Connectoren søker i relevante retningslinjer og returnerer regeltekst med kilde, seksjon og gyldig versjon.
4. Claude presenterer anbefaling, faktagrunnlag, anvendte regler og manglende opplysninger per forslag.
5. Brukeren kan følge kildene og be om utdyping før menneskelig beslutning.

## Foreslått observerbar atferd

- Hvert resultat identifiserer selskap, møte og forslag, og oppgir vurderingsgrunnlaget. Hele sakslisten skal være synlig, med forslag i samme rekkefølge som kilden.
- En stemmeanbefaling bruker alternativene FOR, MOT eller AVSTÅ der datagrunnlaget støtter disse. Behov for menneskelig vurdering er en separat status.
- Hver begrunnelse peker til både relevant regel og selskapsopplysninger. Regelkilden har dokumentversjon og seksjonsidentifikator. Saksgrunnlaget har dokument- og sidereferanse der dette kan hentes pålitelig.
- Hvert identifisert forslag får enten en begrunnet anbefaling eller status manuell sjekk med konkret årsak. Et forslag som systemet mangler regelgrunnlag for, skal også vises.
- Manglende fakta, motstridende kilder og manglende søketreff skal vises og utløse manuell sjekk. Brukeren har valgt overlevering ved manglende grunnlag.
- Kilde- eller serverfeil gir en synlig feil eller ufullstendig vurdering med forklaring.
- Systemet skal synliggjøre usikkerhet. En eventuell numerisk konfidens må beskrives og vurderes mot faktiske utfall. Likhetsscore fra vektorsøket er et søkemål.
- Dokumenter som vurderes, behandles som kilder. Motstandstesten undersøker om instruksjoner skjult i disse påvirker anbefalingen.

## Foreslått teknisk retning

Claude er grensesnittet og språkmodellen i demoen. En remote MCP-server eksponerer søk i et avgrenset dokumentgrunnlag. Claude leser vedlegget i samtalen og sender søkeparametere til connectoren. Direkte tilgang til originalvedlegget fra MCP-serveren er uavklart og må undersøkes dersom det blir et behov.

Et lite grensesnitt med `search_guidelines` og `get_guideline` er et forslag. Søket må avgrenses til riktig forvalter og regelversjon. Valg av språk, rammeverk, vektorlagring og hosting er åpne implementeringsvalg for Prepare, etter at tilgang og begrensninger er avklart.

En fast vurderingsinstruksjon beskriver kildebruk, resultatformat og håndtering av manglende grunnlag. Samme søkelogikk og vurderingsopplegg skal kunne brukes i en separat evalueringskjøring. Forskjeller mellom Claude-chatten og API-kjøringen må dokumenteres.

Demoens connector har som foreslått tilgangsgrense lesing av offentlige retningslinjer. API-nøkler holdes i lokal miljøkonfigurasjon eller valgt tjenestes hemmelighetslager. Detaljert autentisering og hosting fastsettes i Prepare.

## Data og evaluering

Brukeren har opplyst at laget har fått tilgang til NBIMs API. Scopet tar derfor utgangspunkt i NBIMs retningslinjer og publiserte stemmedata, i tråd med case-PDF-en. API-dokumentasjonen må kontrolleres for identifikatorer, datoer, styreanbefaling, stemmeverdier og kobling til innkallinger. Dokumentasjonen må også avklare om feltet som evalueres er publisert stemmeintensjon eller registrert avgitt stemme.

Datautvalget må inneholde forslag, dato, NBIMs referansestemme og opplysningene som trengs for vurderingen. Utvalget av innkallinger og antall testtilfeller fastsettes ut fra tilgjengelige data. Demoen behandler en komplett saksliste. Evalueringen må rapportere hvilke saker og forslagstyper som faktisk er dekket.

- Hold et senere tidsrom av til sluttmåling. Skill utviklingsgrunnlaget fra testsettet.
- Bruk regelversjoner og saksopplysninger som var tilgjengelige ved beslutningstidspunktet.
- Hold testfasiten og begrunnelser som avslører den utenfor søkegrunnlaget og modellens input.
- Rapporter baseline, presisjon og recall på MOT-stemmer, antall testtilfeller, andelen som får en stemmeanbefaling og andelen sendt til manuell sjekk. Vis hvordan uavklarte saker påvirker målene.
- Kontroller på et manuelt gjennomgått utvalg om søket finner nødvendig regelgrunnlag, og om kildehenvisningene støtter begrunnelsen.
- Gjennomfør og rapporter testen med en instruksjon skjult i saksdokumentet.
- Baseline må samsvare med det som rapporteres. Startpakkens `baseline.py` predikerer alltid «ikke MOT», selv om teksten omtaler «stem som styret». Styrets anbefaling må inngå hvis dette er baselinen som hevdes evaluert.

## Leveranse og rammer fra arrangøren

- Repo eller zip som en annen person kan kjøre. README skal inneholde ett kommandolinjekall som reproduserer hovedresultatet.
- Fem minutters demo, helst kjørende, etterfulgt av spørsmål.
- Kravrespons på maksimalt én side om løsning, verifikasjon og videre behov.
- Åpne eller syntetiske data, med URL-er i README.
- Kreditering av KI-verktøy og bruken av dem, samt eventuell kopiert prosjektkode.
- Frist fredag 6. november 2026 kl. 12.00, ifølge kickoff-presentasjonen. Regeldokumentet oppgir 24 timer, mens case-PDF-ens MVP-sti er merket 48 timer. Planleggingen tar utgangspunkt i den konkrete innleveringsfristen.
- Vekting av bedømmingen er 30 % metode, 30 % evaluering, 20 % beslutningsstøtte og 20 % robusthet.

Reglene angir ingen bestemt plattform, offentlig repo eller offline-kjøring. En egen kommandolinjekjøring for evaluering er vårt forslag til å oppfylle reproduksjonskravet med Claude som demo.

Laget oppgir USD 204 i tilgjengelige API-kreditter. Prepare skal beregne et begrenset prøveutvalg og anslå kostnaden før en større evaluering. Faktisk saldo og hvordan abonnementskredittene kan brukes via API-et må kontrolleres. Hosting planlegges innenfor gratis eller eksisterende tjenester som et forslag for å holde opplegget lean. Et separat hostingbudsjett er ikke avtalt.

## Foreslåtte akseptansekriterier

1. En offentlig innkalling kan lastes opp i Claude, og resultatet dekker alle forslagene i den kontrollerte sakslisten. Antall og identifikatorer sammenlignes med dokumentet.
2. Hvert forslag har en kildebelagt stemmeanbefaling eller en konkret begrunnelse for manuell sjekk. AVSTÅ og manuell sjekk har forskjellige betydninger og presenteres separat.
3. Regler og selskapsopplysninger som brukes i begrunnelsen, kan åpnes eller finnes igjen i kilden.
4. Et fast testsett gir dokumentert sammenligning med baseline, MOT-presisjon, MOT-recall og andelen som får anbefaling. Omfang, dataversjoner og behandlingen av manuell sjekk fremgår av resultatet.
5. Motstandstesten er gjennomført og utfallet rapportert. En eventuell svakhet beskrives i leveransen.
6. README beskriver oppsett og én kommando som kjører analysen og evalueringen på det avtalte grunnlaget. Modell-ID, vurderingsinstruksjon, data, regelversjoner, verktøykall og svar lagres eller identifiseres slik at kjøringen kan etterprøves.
7. Den faktiske flyten med opplasting og connector i Claude er prøvekjørt. API-evalueringen og chatdemoen dokumenteres som separate kjøremåter.

## Foreslåtte grenser og tilgang

Førsteversjonen gir beslutningsstøtte for hele sakslisten gjennom dokumenterte anbefalinger eller manuell sjekk. Automatisk stemmeavgivning, selvstendig nettsøk etter manglende fakta, tilkobling til NBIMs interne systemer og utrulling i NBIMs organisasjon ligger utenfor hackathonleveransen. Regnskapsanalyse fra case 2 ligger utenfor denne funksjonen.

Tilgang til connectoren i lagmedlemmets konto og bruken av de oppgitte kredittene via modell-API må verifiseres. Intern NBIM-tilgang krever en egen avklaring. Repoet ble opprettet privat. Under Prepare 5. november ble det kontrollert som offentlig. Leveransen må fortsatt gi mottakeren nødvendige instruksjoner og datatilgang.

## Tekniske avklaringer for Prepare

Disse avklaringene blokkerer deler av gjennomføringen, men produktets første arbeidsflyt er definert.

| Beslutning | Konsekvens | Status |
|---|---|---|
| Claude-konto og fungerende Anthropic API-nøkkel? | Nødvendig for chatdemo og automatisert evaluering. | Brukeren oppgir et lagmedlems abonnement med USD 204 i API-kreditter. Nøkkel og brukbarhet må verifiseres. |
| Hvor ligger dokumentasjonen til NBIM-API-et? | Gjør det mulig å avklare datamodell og egnet testgrunnlag. | Brukeren oppgir at nøkkelen legges inn senere. Dokumentasjonen må lokaliseres eller hentes fra lagmedlemmet. |
| Hvilke innkallinger og historiske regelversjoner brukes i evalueringen? | Bestemmer testutvalg og sporbarhet. | Datainspeksjon i Prepare etter at API-dokumentasjonen er kjent. |
| Hvor skal remote MCP-serveren kjøre? | Claude må kunne nå tjenesten fra Anthropics infrastruktur. | Prepare foreslår gratis eller eksisterende hosting og konkret tilgangsoppsett. |
| Hvilken modell og hvordan uttrykkes usikkerhet? | Påvirker kostnad, reproduserbarhet og manuell sjekk. | Fastsettes i Prepare ut fra tilgang og testgrunnlag. |

## Repo og kilder

Repoet er `henrikengd/fintech-hackathon-h2026-westcoast-plus-1`. Ved inspeksjon 5. november inneholdt `main` bare `README.md` og `.gitignore`. Arbeidstreet var rent, og det fantes ingen egne repo-instruksjoner, domeneglossar eller arkitekturbeslutninger.

Kildene nedenfor følger arrangørens utdelte startpakke.

- `Regler_og_bedommingskriterier.pdf`, særlig punkt 2–5.
- `FinTech Hackathon H2026.pdf`, leveranse og innleveringsfrist.
- `FinTech_Hackathon_Caser_H2026.pdf`, beskrivelse av case 1.
- `case1_stemmegivning/README.md` og `baseline.py`, datavei, krav og baseline.

Faktaundersøkelsen om Claude-connectoren ligger i [research/claude-connector.md](research/claude-connector.md). Den dokumenterer PDF-støtte, eksplisitte MCP-verktøyargumenter, nettverksbehov og en mulig API-kjøring med samme connector. Automatisk tilgang fra MCP-serveren til et opplastet vedlegg er uavklart. Konto- og budsjettbehov må kontrolleres konkret. Integrasjonen er ennå ikke prøvekjørt.

Avklarte domenebegreper står i repoets `CONTEXT.md`. Tekniske valg om lagring og hosting står åpne for Prepare. Det er ennå ikke grunnlag for en egen ADR.

Den kanoniske scope-filen er `docs/features/claude-voting-assistant/scope.md`.

Brukeren ba deretter om Prepare og publisering av GitHub-prosjekt og issues 5. november. [spec.md](spec.md) inneholder krav, oppgaveplan og publiseringsreferanser for neste steg.
