# Stemmedata og innkallinger

NBIMs API beskriver **stemmeintensjoner**. En intendert stemme og en avgitt stemme kan avvike. Tilgang til API-et krever en nøkkel fra NBIM. For arrangørens eksport bruker vi `vote_semantics=unverified` frem til vi har avstemt den mot et faktisk API-svar eller en annen primærkilde for den aktuelle stemmen. [NBIMs API-vilkår](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/api-access-to-our-voting/).

## Kontrollert innkalling

[CCC-møtet 22. mai 2025](../data/meetings/ccc-2025-05-22.json) er en kandidat for utvikling. Selskapets saksliste oppgir tre avstemninger i rekkefølge. Vi kontrollerte emne og nummer mot alle tre radene for møtet i `real_votes.csv`. Innkallingen viser styrets anbefaling for hvert av de tre forslagene. Form 8-K bekrefter de tre avstemningene. Formuleringen om øvrige saker i innkallingen har ingen egen avstemning i sakslisten eller rapporten. [Saksliste i PDF](https://materials.proxyvote.com/Approved/EPLST1/20250515/OTHER_608638.PDF), [DEF 14A](https://www.sec.gov/Archives/edgar/data/1818201/000114036125012861/ny20040008x1_def14a.htm), [8-K](https://www.sec.gov/Archives/edgar/data/1818201/000095017025077048/cccs-20250522.htm).

JSON-filen har korte utdrag fra den kontrollerte sakslisten. Ved vurdering av direktøren, avlønningen og revisoren trenger Claude også opplysningene i den fullstendige DEF 14A. PDF-lenken for den fullstendige innkallingen finnes under «Filing Formats» på [selskapets side for innkallingen](https://ir.cccis.com/sec-filings/sec-filing/def-14a/0001140361-25-012861). Den korte sakslistens SHA-256 ble beregnet fra de nedlastede PDF-bytene. Datoen 15. mai står i URL-en og samsvarer med PDF-ens endringsdato. Form 8-K er publisert etter møtet og inngår bare i den manuelle avstemmingen.

NBIMs stemmeside oppgir 17. februar 2025 som publiseringsdato for 2025-retningslinjene. PDF-en i indeksen har SHA-256 `cde5f906ff68e4c13a0408a9b516ca346c821f642db3603405c1736cf7d6378c`. Historisk kildekontroll for de tre nye testmøtene er nå dokumentert nedenfor. Indeksens dato 13. mai er fortsatt et teknisk nedre filter, ikke en bekreftet virkningsdato for CCC-møtet.

## Lokal import av referanser

Legg arrangørfilen i `data/raw/real_votes.csv`. Les forventet SHA-256 fra [filinventaret](features/claude-voting-assistant/data-inventory.json). Bygg en eksplisitt kobling fra CSV-ens `item_no` til innkallingens `proposal_id` etter at antall, rekkefølge og innhold er kontrollert. Skriv den importerte referansen til en separat lokal fil under `data/raw/`. Sammenkoblingen gjøres i evaluatoren, etter modellvurderingen.

`load_organizer_reference` i `voting_assistant.data_access` validerer filens kontrollsum, schema, møtets identifikatorer, dato og dekning. Den returnerer data som kan valideres med `MeetingReference`. Inputen er begrenset til dette eksportformatet. N-PX-eksporten bruker egne felt og trenger en separat adapter etter kildeavklaringen.

Bruk originalstemmen fra CSV som utgangspunkt. `Withhold` normaliseres til MOT, med råverdien bevart. Tom stemme, `None`, `Do Not Vote` og frekvensvalg gir `null`. Ukjente verdier eller avvik mellom rå og normalisert stemme stopper importen. Styrets anbefaling må oppgis separat fra den kontrollerte innkallingen. Andre CSV-felt, inkludert begrunnelse og `against_board`, inngår ikke i returverdien. `source.document_date` er mottaksdatoen for eksporten fordi den faktiske uttaksdatoen er ukjent.

## Utvikling og nytt fryst testsett — 5. november 2026

CCC 22. mai og Sprinklr 12. juni 2025 er **utvikling**. Den tidligere Sprinklr-piloten var valgt med kjennskap til en MOT-referanse; den teller ikke som ny sluttmåling. Den offentlige NBIM-siden har tre valg for CCC og fem for Sprinklr fordi de tre direktørvalgene er separate. [CCC hos NBIM](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting?m=1952285), [Sprinklr hos NBIM](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting?m=1968008).

Det nye utvalget er de tre første amerikanske møtene i `real_votes.csv`, sortert på dato og møte-ID, etter 12. juni 2025 og før 2026, med komplett offentlig innkalling og offentlig NBIM-side. Valget ble skrevet ned før referansestemmene ble undersøkt. Ingen modellutfall er brukt til utvalg eller sideseleksjon. Ingen av de tre første kandidatene måtte utelates. Senere amerikanske kandidater og avgrensningene står i [kilde- og koblingsplanen](../data/meetings/holdout-2025-plan.json).

| Testmøte | Nummererte forslag | Separate stemmevalg | NBIM-referanse | Styrets anbefaling |
|---|---:|---:|---|---|
| CrowdStrike, 18. juni 2025 | 2 | 4 | [1968745](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting/?m=1968745) | FOR på alle, innkalling PDF-side 1 |
| Dell, 26. juni 2025 | 3 | 10 | [1974465](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting/?m=1974465) | FOR på alle, innkalling PDF-side 3 |
| Snowflake, 2. juli 2025 | 5 | 7 | [1976170](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting/?m=1976170) | FOR på alle, innkalling PDF-side 4 |

Alle 21 valg er avstemt mot selskapets originale innkalling, den offentlige NBIM-tabellen og arrangørfilen, med eksplisitt ID/rekkefølge i planen. NBIM beskriver dataene som **stemmeintensjoner**. De 21 referansene er sammenlignbare: 20 FOR og én MOT. Ingen av de valgte møtene har `Withhold`, frekvensvalg eller manglende referanse. Reglene for slike verdier gjelder fortsatt: `Withhold` er MOT med råverdi bevart; frekvensvalg og manglende stemme er `null`; ukjent verdi skal stoppe importen. MOT betyr imot selve forslaget, mens avvik fra styret må sammenlignes separat med styrets faktiske anbefaling.

Utvalget er lite, amerikansk og avgrenset til tre selskaper. Én MOT er for lite for en stabil vurdering av MOT-presisjon og -gjenfinning. Dette er ikke et representativt mål for hele fondet. Det er heller ikke et eget MOT-utfordringssett.

### Historiske regler med arkivbevis

[Historisk regelkontroll](../data/policies/nbim-2025-historical-evidence.json) inneholder kilder, datoer og kontrollsummer. En kopi av NBIMs offisielle 2025-PDF fra **23. mai 2025** har nøyaktig samme SHA-256 som dagens regelindeks. Arkivkopier fra **20. juni og 30. august** har også identiske PDF-byter. Dette underbygger at teksten var tilgjengelig før, under og etter de tre møtene; beviset bygger dermed på mer enn PDF-metadata. [Arkiv 23. mai](https://web.archive.org/web/20250523042825id_/https://www.nbim.no/contentassets/01a7ee19b5d84a73a67a365e76a0fb01/global-voting-guildeines_2025.pdf), [arkiv 20. juni](https://web.archive.org/web/20250620163045id_/https://www.nbim.no/contentassets/01a7ee19b5d84a73a67a365e76a0fb01/global-voting-guildeines_2025.pdf), [arkiv 30. august](https://web.archive.org/web/20250830025340id_/https://www.nbim.no/contentassets/5396c77d31934c5baad3fe80882cb1ba/global-voting-guildeines_2025.pdf).

Den [arkiverte offisielle regelsiden 18. juli](https://web.archive.org/web/20250718014430id_/https://www.nbim.no/en/responsible-investment/voting/global-voting-guidelines/) peker til den samme 2025-utgaven. NBIMs [stemmerapport publisert 11. august 2025](https://www.nbim.no/en/responsible-investment/voting/voting-reviews/2025/our-voting-first-half-2025/) beskriver bruken av retningslinjene i første halvår; [årsrapporten for 2025](https://www.nbim.no/en/news-and-insights/reports/2025/responsible-investment-2025/) beskriver årlig anvendelse. Samlet gir dette grunnlag for historisk anvendelse på de tre valgte møtedatoene. Dette er en dokumentert slutning fra arkiv- og primærkilder, ikke en attest for eksakt ikrafttredelse eller uavbrutt uforandret publisering mellom arkivtidspunktene. Indeksens grenser 13. mai 2025 og 1. januar 2026 er tekniske filtre, og dette beviset validerer ikke CCC 22. mai.

NBIMs retningslinjer er ikke-bindende og åpner for selskapsspesifikke hensyn. Offentlig samsvar viser derfor ikke at modellen har funnet en objektivt riktig stemme. Senere rapporter, arkivert HTML og stemmebegrunnelser brukes bare til kildekontroll; de legges ikke i modellinput eller regelindeksen.

### Gjenskaping og frysing

`data/meetings/holdout-2025-plan.json` låser dokumentversjoner, original-URL-er, PDF-hasher, dokumentdatoer, alle stemmevalg og relevante PDF-sider. `data/meetings/holdout-2025-freeze.json` låser plan, tre genererte sakslister og tre referansefiler før modellkjøring. Hele relevante sider trekkes ut; layoutmellomrom normaliseres, mens ordene bevares. Grafiske markeringer kan mangle i tekstuttrekket. Eksplisitt prosa beholdes, og manglende fakta må gi manuell kontroll.

Kjør først den eksisterende klargjøringen av utviklingsmøtene. Oppgi deretter dette manifestet til den nye klargjøringen:

```bash
uv run python scripts/prepare_example.py \
  --sprinklr-proxy data/raw/sprinklr-2025-proxy.pdf \
  --output-dir data/raw/development
uv run python scripts/prepare_holdout.py --download \
  --development-manifest data/raw/development/manifest.json \
  --source-dir data/raw/holdout-sources \
  --output-dir data/raw/holdout-2025
```

Bruk faktisk lokal filsti til Sprinklr-PDF-en. `prepare_holdout.py` krever en tom målmappe, verifiserer kilde- og uttrekkshasher, setter både CCC og Sprinklr til utvikling og skriver ett validert manifest. Ulik PDF-utgave eller endret uttrekk stopper klargjøringen. Referansene kopieres som separate filer. Bare `Agenda`-felter fra innkallingen sendes videre til vurdering; ingen NBIM-stemmer, begrunnelser, `against_board` eller andre avledede arrangørfelt inngår. Styrets anbefalinger finnes naturlig i originalinnkallingen og som separat evalueringsegenskap i referansefilen.

Programmet skriver manifestets SHA-256. Behold dette manifestet og kildeplanen uendret gjennom kjøringen. Utviklingsuttrekk kan forbedres før ny kjøring uten å endre de låste testinputene. Offentlige NBIM-sider er dynamiske: referansens kildehash identifiserer HTML-øyeblikksbildet hentet 5. november 2026; et nytt nedlastet HTML-dokument kan få annen hash selv om stemmene er like. PDF-kilder og arkivkopier er lastet ned og hashkontrollert; råfiler og HTML-snapshots er fortsatt Git-ignorert.

Offentlig NBIM-tilgang er faktisk prøvd for alle tre møter. NBIM-API-nøkkel er ikke nødvendig for dette utvalget. `npx_votes.csv`, ukjent fondstilhørighet og `injection_flag` er fortsatt utsatt kildearbeid og inngår ikke i hovedmålingen. Ingen betalte modellkall inngår i denne dataklargjøringen.
