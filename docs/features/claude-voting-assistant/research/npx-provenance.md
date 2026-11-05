# N-PX-data: kilde, stemmefelt og flagg

Undersøkt 5. november 2026. Henrik bekrefter at `real_votes.csv` og `npx_votes.csv` er utlevert av arrangøren. Det bekrefter overleveringskilden, men identifiserer ikke de opprinnelige forvalterne eller transformasjonene. Notatet gjelder filen med SHA-256 `fa2cc588e5e2dbd1209102fe6bf5273c5a890457111d63d63a52ca9a403f6aa0`.

## Hovedfunn

Det mest vesentlige funnet er en mulig feil i tolkningen av `mgmt_rec_raw`. SECs Form N-PX, Item 1(k)–(l), skiller mellom stemmeretningen og om stemmen var med eller mot ledelsens anbefaling. Det siste er ikke selve anbefalingen. Hvis CSV-kolonnen kopierer XML-feltet `managementRecommendation`, er bruken som styreanbefaling feil. [SEC Form N-PX, side 15](https://www.sec.gov/files/formnpx.pdf).

Dette ses også i en faktisk SEC-rendering: under «DETAILS OF VOTE» står separate kolonner for «HOW VOTED», antall aksjer og «FOR OR AGAINST MANAGEMENT». Et direktørforslag kan ha AGAINST i begge kolonner uten at ledelsen anbefalte å stemme mot sitt eget forslag. [Offentlig N-PX, accession 0000930413-24-002640, kolonneoverskrifter og stemmerader](https://www.sec.gov/Archives/edgar/data/1139819/000093041324002640/xslNPX-INFO-TABLE_X01/ProxyVotingTable.xml).

CSV-en alene viser ikke hvordan `mgmt_rec_raw` ble produsert. Derfor er dette en sterk, kildebegrunnet mistanke om feilmapping, ikke en påstand om at alle rader er feil. Den samme konklusjonen kan ikke automatisk overføres til `real_votes.csv`, som kan bruke et annet kildeskjema.

## Praktisk konsekvens for evaluering

For en binær FOR/MOT-avstemning kan faktisk styreanbefaling utledes fra stemmeretning og korrekt tolket samsvar med styret. FOR-stemme med FOR-samsvar gir styret FOR. MOT-stemme med MOT-samsvar gir også styret FOR. Denne utledningen er ikke generelt entydig for AVSTÅ, WITHHOLD, frekvensvalg eller manglende opplysninger. Den bør ikke brukes som modellinput dersom den er utledet fra referansestemmen: da ville input indirekte bruke fasiten. Prosjektet trenger en styreanbefaling dokumentert i innkallingen eller en tilsvarende kilde fra før møtet.

Den lokale Ferrari-raden `N3167Y103_2024-04-17`, `item_no=9`, er et konkret kontrolltilfelle: `nbim_vote_raw=AGAINST`, `mgmt_rec_raw=AGAINST`, men CSV-ens `against_board=0.0`. Hvis feltet er N-PX-samsvar, burde det siste indikere stemme mot styret. Raden må avstemmes med originalinnsending og arrangørens skript før eventuell korreksjon.

## Hvilken forvalter er dette?

Ikke fastslått. CSV-en inneholder verken rapporterende forvalters navn, CIK, accessionnummer, fondsserie-ID eller kildelenke. Feltene `n_funds` og `funds_disagree` viser at data er bearbeidet, men forklarer ikke om «fond» betyr juridiske registranter, fondsserier eller noe annet. Feltet `nbim_vote` beviser ikke at stemmene tilhører NBIM.

N-PX dekker flere typer rapporterende aktører. Identifikasjon av aktør og eventuelt fondsserie ligger i rapporten. Formatet identifiserer derfor ikke NBIM. [SEC Form N-PX, General Instructions A og Item 1(m)–(n)](https://www.sec.gov/files/formnpx.pdf).

Startpakkens `hent_npx.py` viser BlackRock CIK 1364742 som eksempel. Det er et eksempel i startkoden, ikke dokumentert kilde for den nye CSV-en. Tekstsøk etter Ferrari-forslaget fant også samme forslagstekst i andre primærkilder, blant annet BCI og New Jersey. Forslagstekst kan deles av mange investorer og egner seg derfor ikke alene til å identifisere opphav. [BCIs egen stemmerapport, Q2 2024](https://www.bci.ca/wp-content/uploads/2023/03/09-03-Q2-24-ProxyVotingReport_secured.pdf), [New Jerseys egen stemmerapport, Q2 2024](https://nj.gov/treasury/doinvest/proxy/2024-int-q2.shtml).

## Hva betyr `split_year`?

Alle de 52 906 radene følger regelen: møtets kalenderår pluss én dersom måneden er juli–desember. Dette samsvarer med N-PX-år som slutter 30. juni. Det er derfor sterkt støttet at feltet angir rapporteringssesong. Det er ikke bevis for et ferdig train/test-splitt. Bruk faktisk `meeting_date` og grupper på hele møter ved evalueringsdeling. SEC beskriver rapportering for tolvmånedersperioden som slutter 30. juni. [SEC Form N-PX, General Instructions A](https://www.sec.gov/files/formnpx.pdf).

## Hva betyr `injection_flag`?

Eksakt betydning er ikke offentlig dokumentert i kildene som ble funnet. Feltet finnes ikke blant opplysningene i SECs Form N-PX. Startpakkens utdelte `hent_npx.py` skriver kun `utsteder`, `cusip`, `moetedato`, `forslag`, `kategori` og `stemme`. Det skriptet forklarer dermed heller ikke flagget eller den nye CSV-strukturen. [SEC Form N-PX, Item 1](https://www.sec.gov/files/formnpx.pdf); lokal startpakke `case1_stemmegivning/hent_npx.py`.

I CSV-en har 141 rader flagg 1. De omfatter 81 møter og inkluderer sju tomme forslagstekster. Tretti flaggede tekster slutter på `SY`, blant annet i beskrivelser av lønns- eller insentivsystemer. Observasjonene er forenlige med et flagg fra et rense- eller deteksjonstrinn, men fastslår ikke algoritmen eller om teksten opprinnelig inneholdt et angrep. Flagg 1 må derfor behandles som «må undersøkes», ikke som bekreftet prompt injection. Flagg 0 beviser heller ikke at teksten er sikker.

Et konkret eksempel er Kimco-møtet 7. mai 2024 (`49446R109_2024-05-07`): samtlige elleve CSV-rader er flagget, og tekstene er avkortet etter starten på styrets anbefaling. Kimcos originale fullmaktskort har fullstendig tekst og konkrete forslag. Dette dokumenterer at CSV-tekstene ikke er komplette gjengivelser av kortet. Det beviser ikke hvilket skript som gjorde endringen. [Kimcos eget fullmaktskort, innlevert til SEC](https://www.sec.gov/Archives/edgar/data/879101/000120677424000290/kim4270851-defa14a.htm).

Arrangørens motstandstest bør fortsatt lages som et kontrollert par: original sakstekst og en kopi med en eksplisitt ondsinnet instruksjon. Da kjenner laget angrepet, kan sammenligne resultatene og slipper å bruke et uavklart flagg som fasit.

## Hva prosjektet bør gjøre nå

1. Hold N-PX adskilt fra NBIM-hovedmålingen til forvalter og kildemapping er dokumentert.
2. Registrer `mgmt_rec_raw`, `mgmt_rec` og `against_board` som semantisk uavklart for denne filen. Ikke presenter beregnet «stem som styret»-baseline fra disse feltene som validert.
3. Be arrangøren om innhentings-/renseskript, datadictionary og originalfilenes CIK/accession/serie-ID. Dette avklarer både fondsidentitet, stemmeaggregering, styrefelt og flagg i én forespørsel.
4. Bevar de originale CSV-ene og hashene. Eventuelle rettelser gjøres i et separat, sporbar transformasjonstrinn.

## Supplerende NBIM-spor fra lagets notat

Lagets `interne_notater/case1_datagrunnlag.md` i commit `32a3da7` beskriver separat innhentede filer, blant annet `votes_nbim.csv` fra CIK 1374170. Disse filnavnene og radtallene er forskjellige fra arrangørens to CSV-er. Notatet identifiserer derfor ikke opphavet til `npx_votes.csv`.

CIK **1374170 er verifisert som Norges Bank** i SECs egen filingoversikt. N-PX-innsending `0001374170-26-000072`, publisert 28. august 2026 for perioden til 30. juni 2026, har en offentlig stemmetabell. Dette er en konkret supplerende kilde for NBIM-evaluering. [SEC filingoversikt](https://www.sec.gov/Archives/edgar/data/1374170/000137417026000072/0001374170-26-000072-index.htm).

Forsiden klassifiserer Norges Bank som institusjonell forvalter og opplyser om forespurt konfidensiell behandling. Den kontrollerte stemmetabellen viser lederlønn og tilhørende frekvensvalg, blant annet Snowflake 2. juli 2025 (AGAINST) og Linde 29. juli 2025 (ONE YEAR). Disse eksemplene har aksjetall null samtidig som stemmeretning er oppgitt. En import må derfor ikke automatisk kaste slike rader. Dette er et kontrollert, begrenset NBIM-spor for say-on-pay, ikke bevis for dekning av hele sakslister. Lagnotatets totale radtall og fullstendighet er ikke kontrollert her. [Norges Banks N-PX-forside](https://www.sec.gov/Archives/edgar/data/1374170/000137417026000072/xslN-PX_X01/primary_doc.xml), [Norges Banks offentlige stemmetabell](https://www.sec.gov/Archives/edgar/data/1374170/000137417026000072/xslNPX-INFO-TABLE_X01/ProxyVotingTable.xml).

Lagnotatet bruker dessuten «MOT» om stemmer **mot ledelsen**. Gjeldende prosjektspesifikasjon og `nbim_vote=MOT` måler **MOT selve forslaget** (med dokumentert normalisering av WITHHOLD). Dette er to forskjellige utfall. Bevar begge som navngitte mål dersom begge rapporteres. Ikke bytt fasitdefinisjon uten å endre og avklare evalueringskontrakten.

## Undersøkelsens begrensning

Søk etter de nøyaktige fil- og feltnavnene ga ingen offentlig forklaring som kunne knyttes sikkert til arrangørens data. Offisiell N-PX-form og en faktisk SEC-tabell ble kontrollert. SECs tekniske ZIP ble funnet, men kunne ikke lastes ned i denne kjøringen (HTTP 403), og notatet hevder derfor ikke full gjennomgang av XSD-arkivet. [SECs offisielle tekniske spesifikasjonsside](https://www.sec.gov/file/form-npx-xml).
