# Saksgrunnlag og historiske treff

Dette forsøket undersøker om mer relevante historiske eksempler og dokumenter fra det aktuelle møtet forbedrer **F1 for avvik fra styrets anbefaling**. Positiv klasse er kjent NBIM-stemme ulik kjent styreanbefaling. En FOR-stemme kan være et avvik dersom styret anbefaler MOT.

Den lokale sammenligningen er ferdig. De nye historikkegenskapene ga ikke bedre F1. Den eksisterende lokale modellen beholdes. Claude-sammenligningen er også ferdig. Nytt historikksøk og ny instruksjon ga høyere F1 på utviklingsdata, mens saksdokumentene ikke ga bedre klassifisering på sakene der begge varianter svarte.

Ingen av resultatene er en ny, urørt test. Årene er brukt i tidligere utvikling, og utformingen av forsøket bygger også på svakhetene vi fant i oktober. Selve kjøringen leser ikke oktober-data og erstatter ikke oktober-resultatet.

## Hva som er endret

`relevance_retrieval.py` henter historiske forslag ved å kombinere BGE-tekstvektorer med søk etter ord og ordpar. Vektorlikhet vektes med 65 prosent og ordlikhet med 35 prosent. Ordrepresentasjonen bruker en fast hashfunksjon. Den lærer derfor verken ordforråd eller ordvekter fra senere møter.

For hver sak hentes inntil åtte treff på tvers av selskaper og åtte fra samme selskap. Hver av disse gruppene kan ha høyst to treff med samme normaliserte sakstekst. Samlet kan de to gruppene inneholde fire slike treff. Utvalget skal gi flere forskjellige eksempler uten å konstruere en kunstig balanse mellom FOR og MOT.

Rangeringen bruker bare tillatte saksopplysninger. Historiske NBIM-stemmer legges til etter at treffene er valgt. En tidligere stemme kan deretter brukes som historisk observasjon, men ikke som bevis for at de aktuelle saksforholdene er identiske. Den lokale modellen får 48 nye egenskaper fra treffene, blant annet avviksandeler, alder, tekstvariasjon og motstridende tidligere stemmer.

`relevance_evidence.py` henter i tillegg utdrag fra dokumenter til det aktuelle møtet. Søket avgrenses til riktig selskap, møte og publiseringsdato før tekstene rangeres. Det kombinerer vektorsøk og ordsøk, og bruker både forslagsteksten og faste spørsmål om blant annet styresammensetning, godtgjørelse, revisjon og vedtektsendringer. Hver sak får høyst seks utdrag. Identiske og sterkt overlappende utdrag fjernes.

Hvert dokumentutdrag beholder original URL, registrert innsendingsdato, kontrollsum og nøyaktig tekstposisjon. Koden kontrollerer utdraget mot den lokale originalfilen. Bare originale SEC-kilder støttes i dette forsøket. Manglende dokumenter registreres som mangler.

Indeksbyggingen gjenbruker 11 783 tekstvektorer fra eksisterende indekser og beregner 3 012 nye. Gjenbruk krever samme dokumentinnhold, utdrag, metadata og BGE-modellfiler. Når to tidligere indekser inneholder samme utdrag, velges den første i fast rekkefølge. Små numeriske forskjeller mellom ellers samsvarende vektorer registreres i en egen kontrollfil. Gamle indekser endres ikke.

## Datagrunnlag og låst rekkefølge

| Del | Periode | Saker | Faktiske avvik | Bruk |
|---|---|---:|---:|---|
| Trening av endelig lokal modell | 2019–2023 | 7 993 | 477 | Tilpasse modellvekter |
| Fremovervalidering | 2020–2023 | 6 546 | 380 | Velge variant og foreløpig terskel |
| Eksponert kalibrering | 2024 | 1 883 | 98 | Sammenligne og kalibrere endelig terskel |

Hver valideringsperiode bruker en modell trent på tidligere år. Modellen som vurderer 2022 er for eksempel trent på 2019–2021. Historikken kan få nye stemmer underveis i 2022, men bare fra møter som ligger mer enn fem dager før det aktuelle møtet. Modellvektene oppdateres ikke underveis i året.

Planen fastsetter fire varianter før nye modellresultater beregnes. De tre nye variantene bruker samme historiske grunnlag som den tidligere modellen, med de nye treffegenskapene lagt til. Ingen nye kandidater er valgt etter at 2024-resultatene ble kjent.

Modellvalget maksimerer F1 på de samlede fremoverprediksjonene fra 2020–2023. Lik F1 avgjøres av precision og deretter fast rekkefølge i planen. Terskelvalget maksimerer F1, med precision og deretter høyere terskel ved likhet. Valgt modell lagres før 2024-kjøringen begynner. Resultatene fra 2024 kan derfor ikke erstatte vinneren fra modellvalget.

Alle de fire forhåndsbestemte variantene får likevel en 2024-rad for å vise hva endringen gjør. Vi viser både en terskel valgt på 2020–2023 og en terskel tilpasset 2024. Den sistnevnte er vurdert på de samme utfallene som bestemte terskelen. Den må ikke presenteres som en uavhengig testscore.

## Resultater for lokalmodellen

| Variant | F1 ved modellvalg på 2020–2023 | F1 på 2024, terskel fra 2020–2023 | F1 på 2024, terskel tilpasset 2024 |
|---|---:|---:|---:|
| Eksisterende `semantic-history-boost` | **51,81 %** | **62,15 %** | **62,30 %** |
| Hybrid historikk + BGE, gradient boosting | 50,06 % | 56,22 % | 60,87 % |
| Hybrid historikk, gradient boosting | 41,64 % | 46,53 % | 52,46 % |
| Hybrid historikk + BGE, logistisk regresjon | 34,71 % | 37,50 % | 41,21 % |

Alle 2024-radene gjelder de samme 1 883 sakene. Med terskel tilpasset 2024 blir fordelingen slik:

| Variant | Precision | Recall | F1 | Riktige avvik | Falske alarmer | Oversette avvik |
|---|---:|---:|---:|---:|---:|---:|
| Eksisterende modell | 67,06 % | 58,16 % | 62,30 % | 57 | 28 | 41 |
| Hybrid historikk + BGE, gradient boosting | 65,12 % | 57,14 % | 60,87 % | 56 | 30 | 42 |
| Hybrid historikk, gradient boosting | 56,47 % | 48,98 % | 52,46 % | 48 | 37 | 50 |
| Hybrid historikk + BGE, logistisk regresjon | 50,75 % | 34,69 % | 41,21 % | 34 | 33 | 64 |

Den eksisterende modellen vant både modellvalget og 2024-sammenligningen. Den beholder terskelen `0.24417457727599695` og uendrede modellvekter. Den beste nye varianten ligger 1,43 prosentpoeng lavere i kalibrert F1. Mer varierte historiske treff ga altså ikke bedre klassifisering i dette forsøket.

Dette viser heller ikke at hybrid søk alltid er dårligere. Den eksisterende modellen bruker allerede omfattende historikkegenskaper, inkludert semantiske treff, selskapsmønstre og identisk sakstekst. De 48 nye egenskapene tilfører overlappende informasjon. Treffvariasjon kan også fjerne eksempler som er nyttige for å anslå hvor ofte NBIM har stemt på en bestemt måte. Dette er mulige forklaringer, ikke dokumenterte årsaker til forskjellen.

## Saksdokumenter og Claude-sammenligningen

Den lokale samlingen har 85 registrerte SEC-dokumenter, hvorav 33 gjelder 2024. Ett 2024-møte mangler brukbar dokument- eller datoinformasjon. Dermed kan 32 dokumenter med til sammen 14 795 tekstutdrag inngå i det nye 2024-søket. Dokumentene gjelder 339 av de 1 883 sakene, fordelt på 32 av 168 møter. Den tidligere dokumentindeksen dekket 22 møter. Den ferdige innhentingen rapporterer antall valgte utdrag og eventuelle mangler.

Det finnes ingen originale møtedokumenter for 2019–2023 i denne samlingen. Dokumentutdragene legges derfor ikke ukritisk til som nye, utrente egenskaper i lokalmodellen. Den lokale sammenligningen over måler historisk søk. Claude-sammenligningen undersøker om modellen kan bruke dokumentutdragene direkte sammen med historikken.

Claude-forsøket sammenligner:

1. Tidligere lagrede Claude-svar med historiske vektortreff.
2. En fast ny instruksjon med hybrid historikk på alle 2024-møtene.
3. Samme nye instruksjon og historikk, med daterte dokumentutdrag på alle møter som har slike dokumenter.

Utenfor dokumentdekningen bruker den tredje varianten det samme svaret som varianten med bare hybrid historikk. Den gjør ikke et nytt kall med tom dokumentliste. Rapporten viser både hele utvalget og en separat sammenligning på møtene med dokumenter.

Sammenligningen mellom tidligere Claude og den nye historikkvarianten endrer både instruksjon og søkemetode. En eventuell forskjell kan derfor ikke tilskrives vektorsøket alene. Sammenligningen mellom de to nye variantene holder instruksjonen lik og endrer bare dokumentgrunnlaget.

Alle 200 planlagte forespørsler er behandlet. 186 svar ble godkjent, mens 14 ble avvist ved kontroll av svarformat og kildehenvisninger. Det er seks historikkmøter og åtte dokumentmøter. Ingen svar er kjørt om igjen eller fjernet fra hovedmålingen. Registrert tokenbruk gir anslått API-kostnad **9,40 USD**, etter prisene lagret med sammenligningsoppsettet.

| Oppsett, samme 1 883 saker | Precision | Recall | F1 | Riktige avvik | Falske alarmer | Oversette avvik | Saker med stemmesvar |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tidligere Claude | 60,23 % | 54,08 % | 56,99 % | 53 | 35 | 45 | 1 830 |
| Nytt historikksøk og ny instruksjon | 65,93 % | 61,22 % | 63,49 % | 60 | 31 | 38 | 1 777 |
| Samme nye oppsett med saksdokumenter | 76,00 % | 58,16 % | 65,90 % | 57 | 18 | 41 | 1 683 |

Historikkvarianten øker målt F1 med **6,50 prosentpoeng**. Den finner sju flere faktiske avvik og gir fire færre falske alarmer. Forskjellen inkluderer både endret historikksøk og endret instruksjon. Vi kan derfor ikke tilskrive hele endringen selve vektorsøket. Et beskrivende 95-prosentintervall fra trekking av hele møter går fra **−3,91 til +18,55 prosentpoeng**. Det inkluderer ingen forbedring. Dette er heller ikke en urørt test.

Svarfordelingen forklarer også deler av historikkvariantens økning. På de **1 724 sakene der både tidligere Claude og den nye historikkvarianten svarte**, går F1 fra **62,20 til 63,69 prosent**, en økning på **1,50 prosentpoeng**. Tidligere Claude har 51 riktige avvik, 32 falske alarmer og 30 oversette avvik. Ny historikk har 50 riktige avvik, 26 falske alarmer og 31 oversette avvik. Denne diagnostiske delmengden erstatter ikke hovedmålingen, men viser at den målte forbedringen er mindre når vi sammenligner bare felles besvarte saker.

Den tilsynelatende ekstra gevinsten fra dokumenter må ikke tolkes som bedre klassifisering. På de **243 dokumentdekkede sakene der begge nye varianter ga en stemme**, er forvekslingsmatrisen identisk: 10 riktige avvik, 4 falske alarmer, 6 oversette avvik og 223 riktige enigheter. Begge får **66,67 prosent F1**. To stemmer endres. Én endring retter en feil, mens den andre introduserer en feil.

Dokumentvarianten mangler svar for 95 saker i åtte avviste møter. På disse sakene hadde historikkvarianten tre riktige avvik og 13 falske alarmer. Når dokumentvarianten ikke svarer, forsvinner de 13 falske alarmene fra telleren, samtidig som de tre riktige avvikene blir oversett. Standard F1 kan dermed stige selv om ingen flere saker får et riktig svar. En historikksak uten stemme blir i tillegg riktig besvart med dokumenter. Vi beholder alle disse sakene i hovedmålingen og viser svarandel separat.

| Oppsett, bare de samme 339 sakene med dokumenter | Precision | Recall | F1 | Saker med stemmesvar |
|---|---:|---:|---:|---:|
| Tidligere Claude | 41,94 % | 65,00 % | 50,98 % | 339 |
| Nytt historikksøk | 43,33 % | 65,00 % | 52,00 % | 338 |
| Nytt søk og saksdokumenter | 71,43 % | 50,00 % | 58,82 % | 244 |

Dokumentvariantens F1-forskjell mot historikk alene på disse 339 sakene har et bredt beskrivende intervall fra **−21,18 til +23,27 prosentpoeng**. F1-forskjellen og lavere svarandel gir ikke grunnlag for å konkludere med en dokumentgevinst. Den dokumenterte forbedringen i dette forsøket er den høyere utviklingsscoren for historikkvarianten, med de nevnte forbeholdene.

De avviste svarene er registrert som `ReviewValidationError`. Førstegangskjøringen lagrer ikke råteksten i avviste svar eller den mer detaljerte underårsaken. Vi kan derfor ikke i etterkant skille nøyaktig mellom feil saksdekning, historikkhenvisning og sitat for hvert avvist møte. Ingen etterfølgende kall brukes til å erstatte disse resultatene.

## Kontroller mot datalekkasje

- Historiske stemmer må komme fra møter med dato **strengt før møtedato minus fem dager**. Eget møte og samme selskaps møter på samme dato utelukkes. Tidsfilteret brukes før rangering og utvalg.
- Aktuell NBIM-stemme, aktuell stemmebegrunnelse og kategorier avledet fra fasiten inngår ikke i saksrepresentasjonen. Historiske stemmer brukes først etter at de historiske treffene er valgt.
- Rangeringen balanserer ikke treffene etter stemmeretning. Det kan fortsatt komme bare FOR-treff dersom det er disse som rangeres høyest.
- Modellvekter og statistisk forbehandling tilpasses bare treningsårene. Endelig modell velges før 2024 måles. Den endelige terskelen tilpasses 2024, som derfor kalles kalibrering.
- Dokumenter må tilhøre riktig selskap og møte. Registrert innsendingsdato må være strengt før beslutningsgrensen. Nåværende NBIM-begrunnelser er ikke dokumentkilder.
- Daterte regeltekster krever egen historisk verifisering. Den konfigurerte `rules.json` ble hentet i 2026 og inneholder ikke tilstrekkelig verifiserte historiske versjoner for denne testen. Den brukes derfor ikke som regelgrunnlag for 2024. Manglende regler oppgis eksplisitt.
- Gamle modeller, prediksjoner og oktober-resultater er bevart. Nye kjøringer har egne mapper, kildekopier, kontrollsummer og låst plan. Saker med API-feil eller manglende prediksjoner beholdes i evalueringsutvalget. Manglende prediksjon for et faktisk avvik teller som et oversett avvik.

For lokalmodellens nye historikk ble **124 964 valgte treff** kontrollert. Det var 99 887 treff i treningsgrunnlaget og 25 077 i kalibreringsgrunnlaget. Ingen brøt tidsgrensen eller kom fra eget møte. Testene kontrollerer også at endringer i aktuelle eller fremtidige stemmer ikke påvirker en tidligere saks søkegrunnlag, og at endrede 2024-utfall ikke endrer modellvalget.

## Begrensninger kontrollene ikke fjerner

Femdagersgrensen for historiske stemmer er en antakelse om når opplysningene var tilgjengelige. Datasettet har møtedato, men ikke verifisert publiseringstidspunkt for hver tidligere NBIM-stemme. Vi kan derfor dokumentere tidsregelen i koden, men ikke garantere at hver historisk stemme faktisk var publisert på det tidspunktet.

For SEC-dokumenter brukes innsendingsdatoen registrert i `data/meetings/us.csv`, ikke nedlastingsdato eller filens endringsdato. Kontrollsummene og tekstposisjonene bekrefter hvilken lokal kilde som ble brukt. De er ikke alene en uavhengig kontroll av alle datoopplysningene i den opprinnelige indeksen.

Vi fant også [en offisiell 2024-PDF med globale stemmeretningslinjer](https://www.nbim.no/contentassets/5396c77d31934c5baad3fe80882cb1ba/global-voting-guidelines2024.pdf). NBIMs [rapport om stemmegivning første halvår 2024](https://www.nbim.no/en/responsible-investment/voting/voting-reviews/2024/our-voting-first-half-2024/) er datert 13. august 2024 og omtaler regler brukt i perioden. Dette etablerer ikke første publiseringsdato eller hele gyldighetsperioden for den konkrete PDF-versjonen. Den inngår derfor ikke i denne kjøringen. Et årstall i filnavnet er ikke grunnlag for å anta at dokumentet var tilgjengelig 1. januar.

Claude og BGE er forhåndstrente modeller. Vi kan kontrollere innholdet vi gir dem, men kan ikke utelukke at forhåndstreningen allerede inneholdt opplysninger om historiske selskaper eller møter. Instruksjonen ber Claude om å bruke det oppgitte grunnlaget og ikke huskede møteutfall. Det er ingen garanti for fullstendig historisk blindhet.

Et eksakt sitat beviser at teksten finnes i et oppgitt utdrag. Det beviser ikke at sitatet støtter modellens konklusjon eller at anbefalingen følger NBIMs regler. Utdrag kan også mangle den avgjørende opplysningen selv om dokumentet er korrekt.

Oktober-feilene har påvirket hva vi valgte å forbedre. En ny kjøring på oktober ville derfor vært utviklingsanalyse, ikke en ny uavhengig test. Bedre F1 på 2024 vil heller ikke alene dokumentere bedre resultater i drift. Det krever nye møter som ikke er brukt til modellvalg, terskelvalg eller vurdering av endringer.

## Kjøring og etterprøving

Kjør fra `voting-desk/` i prosjektets eksisterende miljø:

```bash
# Bygg en ny dokumentindeks og hent kildekontrollerte utdrag. Eksisterende filer overskrives ikke.
.venv/bin/python relevance_evidence.py --build
.venv/bin/python relevance_evidence.py

# Lokal sammenligning. Standardmappen finnes allerede og blir ikke overskrevet.
.venv/bin/python relevance_experiment.py run --output data/local-rag/relevance-board-v2

# Gjenspill én lagret 2024-sak med modellen og terskelen som faktisk ble valgt.
.venv/bin/python relevance_experiment.py predict --meeting 1841869 --item 1

# Kontroller lokalt søk og forsøksprotokoll uten API-kall.
.venv/bin/python -m unittest test_relevance_retrieval test_relevance_experiment -v

# Les eller regenerer Claude-rapporten fra lagrede svar, uten nye API-kall.
.venv/bin/python relevance_claude.py report
```

`relevance_claude.py prepare` fryser et nytt forsøksgrunnlag. `relevance_claude.py run` gjør betalte API-kall for planlagte møter som mangler svar. Tidligere svar gjenbrukes. Et avbrutt kall som kan ha blitt belastet stoppes for kontroll i stedet for automatisk omkjøring.

Hovedmålingen beholder alle saker, også ved API-feil. Rapporten har i tillegg en diagnostisk sammenligning på sakene hvor alle tre Claude-varianter ga en kjent stemme. Denne målingen erstatter ikke hovedmålingen. F1-forskjellene får et beskrivende usikkerhetsintervall fra 2 000 trekninger av hele møter med tilbakelegging. Det tar hensyn til avhengigheten mellom saker i samme møte, men fjerner ikke tidligere eksponering av utviklingsdataene.

Den lokale kjøringen tok omtrent 110 sekunder og gjorde ingen API-kall. De 17 testene for lokal innhenting og forsøksoppsett bestod. Alle fire forvekslingsmatriser er telt opp uavhengig fra de lagrede prediksjonene. Alle tre nye modeller er gjenspilt på samtlige 1 883 kalibreringssaker og gir de samme skårene som de lagrede resultatene. Modell- og kildekontrollsummene stemmer.

Hele testpakken består etter endringene: 314 tester. Dette omfatter også avvisning av feil kilde, feil dato, endrede sitater, uventede fasitfelt og svar som tilhører en annen forespørsel. En eldre test for uendrede prediksjoner bruker nå én tråd under trebasert prediksjon, slik at avrundingsforskjeller rundt `1e-16` ikke gir tilfeldige feil i den strenge sammenligningen. Modellkoden og modellvektene er uendret av denne testrettingen.

Artefaktene ligger under `data/local-rag/relevance-board-v1/`, `relevance-evidence-v1/` og `relevance-claude-v1/`. Modelltabellen, forsøksplanen, de valgte historiske treffene og kildekopiene gjør det mulig å kontrollere hva hvert resultat bygger på. [Resultatsiden](http://127.0.0.1:8502/evaluation) viser rapportene uten å starte nye modellkall.

Den uavhengige kontrollen er lagret i `data/local-rag/relevance-claude-v1/independent-verification.json`. Den bekrefter alle kilde- og artefaktkontrollsummer, de ni hoved- og delutvalgsmålingene, usikkerhetsintervallene og kontrollen av manglende svar. Den ferdige resultatsiden er også kontrollert i nettleseren.
