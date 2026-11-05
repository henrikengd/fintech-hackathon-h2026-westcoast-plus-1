# Stemmedata og innkallinger

NBIMs API beskriver **stemmeintensjoner**. En intendert stemme og en avgitt stemme kan avvike. Tilgang til API-et krever en nøkkel fra NBIM. For arrangørens eksport bruker vi `vote_semantics=unverified` frem til vi har avstemt den mot et faktisk API-svar eller en annen primærkilde for den aktuelle stemmen. [NBIMs API-vilkår](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/api-access-to-our-voting/).

## Kontrollert innkalling

[CCC-møtet 22. mai 2025](../data/meetings/ccc-2025-05-22.json) er en kandidat for utvikling. Selskapets saksliste oppgir tre avstemninger i rekkefølge. Vi kontrollerte emne og nummer mot alle tre radene for møtet i `real_votes.csv`. Innkallingen viser styrets anbefaling for hvert av de tre forslagene. Form 8-K bekrefter de tre avstemningene. Formuleringen om øvrige saker i innkallingen har ingen egen avstemning i sakslisten eller rapporten. [Saksliste i PDF](https://materials.proxyvote.com/Approved/EPLST1/20250515/OTHER_608638.PDF), [DEF 14A](https://www.sec.gov/Archives/edgar/data/1818201/000114036125012861/ny20040008x1_def14a.htm), [8-K](https://www.sec.gov/Archives/edgar/data/1818201/000095017025077048/cccs-20250522.htm).

JSON-filen har korte utdrag fra den kontrollerte sakslisten. Ved vurdering av direktøren, avlønningen og revisoren trenger Claude også opplysningene i den fullstendige DEF 14A. PDF-lenken for den fullstendige innkallingen finnes under «Filing Formats» på [selskapets side for innkallingen](https://ir.cccis.com/sec-filings/sec-filing/def-14a/0001140361-25-012861). Den korte sakslistens SHA-256 ble beregnet fra de nedlastede PDF-bytene. Datoen 15. mai står i URL-en og samsvarer med PDF-ens endringsdato. Form 8-K er publisert etter møtet og inngår bare i den manuelle avstemmingen.

NBIMs stemmeside oppgir 17. februar 2025 som publiseringsdato for 2025-retningslinjene. De tilgjengelige PDF-bytene har opprettelsesdato 13. mai 2025 og SHA-256 `cde5f906ff68e4c13a0408a9b516ca346c821f642db3603405c1736cf7d6378c`. Bruk denne versjonen tidligst fra 13. mai i det lokale regelutvalget. Datoen avgrenser hvilke historiske møter vi kan undersøke med dette dokumentet. Nøyaktig virkningsperiode må fortsatt dokumenteres før en historisk sluttmåling. [NBIMs stemmeside](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/), [2025-retningslinjer](https://www.nbim.no/contentassets/cbee6983c7d044a6a6d2f286ed5fa3df/global-voting-guildeines_2025.pdf).

## Lokal import av referanser

Legg arrangørfilen i `data/raw/real_votes.csv`. Les forventet SHA-256 fra [filinventaret](features/claude-voting-assistant/data-inventory.json). Bygg en eksplisitt kobling fra CSV-ens `item_no` til innkallingens `proposal_id` etter at antall, rekkefølge og innhold er kontrollert. Skriv den importerte referansen til en separat lokal fil under `data/raw/`. Sammenkoblingen gjøres i evaluatoren, etter modellvurderingen.

`load_organizer_reference` i `voting_assistant.data_access` validerer filens kontrollsum, schema, møtets identifikatorer, dato og dekning. Den returnerer data som kan valideres med `MeetingReference`. Inputen er begrenset til dette eksportformatet. N-PX-eksporten bruker egne felt og trenger en separat adapter etter kildeavklaringen.

Bruk originalstemmen fra CSV som utgangspunkt. `Withhold` normaliseres til MOT, med råverdien bevart. Tom stemme, `None`, `Do Not Vote` og frekvensvalg gir `null`. Ukjente verdier eller avvik mellom rå og normalisert stemme stopper importen. Styrets anbefaling må oppgis separat fra den kontrollerte innkallingen. Andre CSV-felt, inkludert begrunnelse og `against_board`, inngår ikke i returverdien. `source.document_date` er mottaksdatoen for eksporten fordi den faktiske uttaksdatoen er ukjent.

## Før sluttmåling

Avstem referansestemmer mot NBIM-kilden og avklar historisk regelversjon. Dokumenter deretter separate utviklingsmøter og senere testmøter med kildelenker, datoer, kontrollsummer og regelversjoner. Det kontrollerte CCC-møtet er et utviklingseksempel. Det er ennå ikke frosset et sluttsett, og API-tilgang, API-respons, saldo og faktisk Claude-tilkobling venter på lagets tilgang.
