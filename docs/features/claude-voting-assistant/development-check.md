# Utviklingskontroll etter kildefiksen

Dato: 5. november 2026. T-04, spesifikasjon revisjon 2. Dette dokumentet beskriver endringene og kontrollene uten modellkall. Livekjøring og kontroll av alle fem nye Sprinklr-svar registreres nedenfor etter integrasjon. Den tidligere pilotrapporten bevares; dens resultat står i [pilot-review.md](pilot-review.md).

## Faktagrunnlag

`scripts/prepare_example.py` merker nå både CCC og Sprinklr som `development`. Standardvalget er utvikling; forsøk på å lage disse utviklingseksemplene som test avvises. Lasting av det faktisk genererte manifestet velger CCC med tre stemmevalg og Sprinklr med fem stemmevalg (`1a`, `1b`, `1c`, `2`, `3`). Sprinklr er ikke et urørt testeksempel.

Sprinklrs PDF er fortsatt låst til SHA-256 `23dc506b308b7a76276d1945a4c61449d261d7e4066ba49f8247c5b2eb35e170`. Sidetallene under er én-baserte PDF-sider, fire høyere enn dokumentets trykte sidenummer fra side 13.

| Forslag | PDF-sider | Hvorfor disse kildene trengs |
|---|---|---|
| 1a–1c, styrevalg | 2, 13–20 | Side 13–15 gir kandidatbakgrunn, andre verv og styresammensetning. Side 13 beskriver også Gillis' avgang og reduksjon fra ti til ni medlemmer ved møteslutt. Side 16 oppgir uavhengighet og skillet mellom styreleder og daglig leder. Side 17 gir møtedeltakelse. Side 18 identifiserer revisjonskomiteen; 19 identifiserer kompensasjonskomiteen; 20 identifiserer nominasjonskomiteen og omtaler bindinger. |
| 2, lederlønn | 2, 23, 26, 27, 28, 32, 40, 42 | Beholder de tidligere utdragene om lønnspolitikk, utforming og utbetalinger. En skjønnsmessig MOT-anbefaling må fortsatt kontrolleres mot det fullstendige regelavsnittet. |
| 3, revisor | 2, 18, 19, 61 | Side 18–19 supplerer honorartabellen med komiteens arbeid og omtale av revisors uavhengighet. Side 61 viser valg av KPMG, tjenestekategorier, alle honorarer og forhåndsgodkjenning. |

Poppler trekker ikke ut bildet med komitétabellen på PDF-side 18 som tekst. Prosaen på side 16 og 18–20 gir medlemskap og uavhengighetsvurderinger. Uttrekket skal derfor ikke omtales som en full avskrift av tabellen. Selskapsstørrelse og markedsklassifikasjon er heller ikke etablert bare ved å finne en børsnotering. Når slik avgrensning er nødvendig for konklusjonen, skal modellen gi konkret manuell sjekk.

Ved gjennomgang av styreandel må tidspunktet oppgis: åtte uavhengige av ti før Gillis' avgang er ikke den samme beregningen som sammensetningen etter møteslutt. Ved revisorberegning viser tabellen beløp i tusen dollar: skattehonorar 277 og totalhonorar 3 170 i 2025; 127 og 3 410 i 2024. Beregning gir omtrent 8,74 og 3,72 prosent dersom disse kategoriene brukes som ikke-revisjonshonorar. Sitatet må vise kategorier, år, enhet og tall. Andre MOT-vilkår i revisoravsnittet må vurderes særskilt.

## Kilder og overlevering

API-modellen gir regel-ID og versjon. Systemet henter hele det kanoniske avsnittet fra et oppslag som allerede er validert for møtedatoen. Modellen kan ikke levere et forkortet regelsitat som godkjennes som kanonisk. Ukjent ID, feil versjon og egne sitatfelt avvises. Hele avsnittet bevarer blant annet marked og selskapsstørrelse; det er fortsatt nødvendig å kontrollere at fakta og slutning passer til regelen.

Faktasitater kontrolleres som sammenhengende tekst mot forslagets egne utdrag. Bare blanktegn og U+200B normaliseres. U+200B forekommer som et usynlig layouttegn før 277 i den låste honorartabellen. Synlige tegn, beløp og vilkår omskrives ikke. Automatisk sitatkontroll beviser teksttreff, ikke at alle påstander eller slutninger er riktige.

Resultatet får standardtom `validation_errors` og valgfri `unverified_explanation`. Sistnevnte inneholder kun modellens opprinnelige begrunnelse, oppgitte mangler og usikkerhetsårsak fra et entydig identifisert svar. Feltet er uttrykkelig uverifisert. Ved avvist svar er den aksepterte anbefalingen fortsatt null, status `manual_review` og kildearrayene tomme. Duplikate svar får ingen vilkårlig valgt opprinnelig forklaring. En gyldig manuell overlevering har ingen valideringsfeil og kan inngå i en `complete`-kjøring; avviste svar og tekniske feil gir `partial`.

De nye feltene har standardverdier slik at eldre rapporter kan leses. Den faktiske gamle rapporten med SHA-256 `ab63a69446cfff0e7c9319f239b36856898a5a0fa93989058a54f97d8f73a070` er lest med `AssessmentRun` etter endringen: fem svar, fortsatt `partial`. Ny instruksjon og input krever en ny rapport; den gamle skal ikke gjenopptas med endret konfigurasjon.

## Utførte kontroller uten modellkall

- 45 tester passerer, inkludert begge møter i utviklingsutvalget, side 16/18–20, full kanonisk regeltekst, avvist modellskrevet regelsitat, ukjent regel/versjon, bevart uverifisert mangelbeskrivelse, gyldig manuell overlevering og numerisk faktasitat. Endring av beløpet 277 til 999 avvises selv om usynlige layouttegn normaliseres.
- Faktisk PDF-uttrekk med Poppler og kontrakt-/hashkontroll gjennom `load_manifest` er gjennomført. Manifestets SHA-256 er `f16dcdeec535b6ab844369e1f4b40d5e3065871ee86130193948e27363b63a65`.
- Instruksjonsversjonen er `6eaaef71361c11c47c0c8bfc0cb5b55cff57fe49bb24b74c3e587197c2ad0862`. Den avhenger av instruksjonsteksten og skal registreres fra faktisk kjøring sammen med kode- og indeksversjon.

## Kontrollark for integrert livekjøring

Fylles fra ny rapport, uten å erstatte første forsøk. Registrer rapportsti/hash, manifest/hash, modell, kode, indeks, instruksjon, tidspunkt, priser og registrert kostnad. Summer mot rundens felles USD 2-ramme. Et gyldig manuelt resultat teller som et gjennomgått svar; 100 prosent anbefalingsdekning er ikke et krav.

| Forslag | Status og stemme | Kildesitat finnes | Faktapåstander og benyttede tall støttes | Regelvilkår og slutning holder / konkret manuell grunn |
|---|---|---|---|---|
| 1a, Hauser | Avventer livekjøring | Avventer | Avventer | Avventer |
| 1b, Haverty | Avventer livekjøring | Avventer | Avventer | Avventer |
| 1c, Thomas | Avventer livekjøring | Avventer | Avventer | Avventer |
| 2, lederlønn | Avventer livekjøring | Avventer | Avventer | Avventer |
| 3, revisor | Avventer livekjøring | Avventer | Avventer | Avventer |

For hver rad kontrolleres alle vedlagte regel- og faktakilder og at anbefaling, mangler og usikkerhet ikke motsier hverandre. Skill mellom reell informasjonsmangel og teknisk/valideringsfeil. Oppgi feil eller uavklarte vilkår; samsvar med NBIM er ikke alene godkjent begrunnelseskvalitet. Ikke bruk denne utviklingskontrollen som sluttmåling eller som bevis for faktisk Claude-chat.

### Kildekontekst etter faktisk utviklingskontroll

Det andre utviklingsforsøket (`data/raw/api-attack-r2/original-run.json`, kode `46660aa`) fullførte alle fem svar som manuell sjekk, USD 0,0139135. Kontroll av alle fem viste at modellens eksakte faktasitater kunne være for korte: navn uten påfølgende uavhengighetsvurdering, og revisortall uten samtlige operander. Det var teksttreff, men utilstrekkelige utdrag for flere påstander. Første svar er bevart.

Faktakilden i nye rapporter får derfor hele det opprinnelige kontrollerte sideutdraget etter at modellens valgte sitat er validert. Ingen tekst fra usiterte sider legges til. `raw_answer` beholder modellens eget korte sitat, og valideringen avviser fortsatt endrede beløp eller ukjent tekst. Dette gjør kildene etterprøvbare, men beviser ikke at modellens slutning er riktig. Thomas-begrunnelsen i dette forsøket forenklet størrelses-/kontrollvilkår og brukte styresammensetningen før Gillis' avgang. Null anbefaling beholdes; begrunnelsen er ikke et godkjent stemmeråd.
