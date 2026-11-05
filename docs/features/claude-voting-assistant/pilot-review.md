# Pilotgjennomgang 5. november 2026

Dette notatet er grunnlaget for spesifikasjon revisjon 2. Det beskriver en teknisk pilot og manuell feilanalyse, ikke en representativ kvalitetsmåling.

## Kjøring og resultat

Koden fra `ab1a5586bb0d4349b35a696eb9c53eec7cc25b8c` er merget i `main` gjennom PR #10 ved `a9bda4903c3f9ae03fab759e45b704503d462c28`. Modellen i den lagrede rapporten er `claude-haiku-5-5`. To forsøk ble kjørt innenfor én samlet rapportgrense på USD 0,10. Registrert samlet kostnad er USD 0,0344488, beregnet med rapportens konfigurerte priser. Dette er ikke en avstemming mot faktura eller saldo.

| Mål i siste forsøk | Resultat |
|---|---|
| Referanse | NBIMs publiserte stemmeintensjoner |
| Møter / stemmevalg | 1 / 5, Sprinklr 12. juni 2025 |
| Anbefalinger / manuell sjekk | 2 / 3 |
| Anbefalingsdekning | 40 prosent |
| MOT-presisjon / MOT-recall | 1/1 og 1/1 |
| Baseline-recall, stem som styret | 0/1 |
| Kjøringsstatus | `partial`, tre sitatvalideringsfeil |

Rapportens SHA-256 er `ab63a69446cfff0e7c9319f239b36856898a5a0fa93989058a54f97d8f73a070`. Inputmanifestets SHA-256 er `719466b4fe6e5337c2076d57e083f10f57af168a81329ae85334a35f88d3e294`. Instruksjonsversjonen er `5d57f30d3f0b07225da3e41eaa8e869c94d2d1e2f0722ab9a1ab1b66513a7db2`. Rårapporten og første forsøk bevares lokalt i `data/raw/pilot/`. Dette notatet publiserer bare funn og kontrollsummer.

Siste forsøk er rapportert som et senere forsøk, ikke som eneste observasjon. Det første hadde én anbefaling og fire manuelle saker. Rapporten med `--resume` erstatter det delvise møtets svar, men summerer kostnaden. Fremtidige sluttmålinger må bevare hvert forsøk.

## Funn som styrer neste arbeid

1. Modellens råsvar satte allerede alle tre styrevalg til manuell sjekk på grunn av manglende fakta. Sitatvalideringen feilet i tillegg og erstattet de konkrete mangelbeskrivelsene med generisk tekst.
2. `scripts/prepare_example.py` gir styrevalg PDF-side 2, 13, 14 og 15. [Sprinklrs innkalling](https://investors.sprinklr.com/financial-information/all-sec-filings/content/0001140361-25-017121/0001140361-25-017121.pdf) har styrets uavhengighetsvurdering på PDF-side 16 og komitéopplysninger på side 18. Manglende kildeutdrag er derfor en konkret forklaring. Flere fakta kan fortsatt være nødvendige for full regelanvendelse.
3. Modellens sitat om styreuavhengighet utelater innledningen som avgrenser regelen etter marked og selskapsstørrelse. En mindre streng tekstmatcher kan dermed godta et sitat som mangler vesentlige vilkår.
4. Revisorbegrunnelsens tall finnes på PDF-side 61, men faktasitatene gjengir ikke talltabellen. Begrunnelsen omtaler dessuten honorargrensen som eneste MOT-vilkår selv om avsnittet har flere. Et akseptert sitat er ikke bevis for en riktig slutning.
5. Anbefalingen om lederlønn bruker ekte sitater og samsvarer med NBIM. Om opplysningene utgjør vesentlige bekymringer etter regelen krever skjønn og kontroll. Samme stemme som NBIM er ikke alene godkjent begrunnelseskvalitet.
6. API-et validerer kildesitater. MCP-serveren tilbyr bare regeloppslag. Claude-chatten har ikke automatisk API-ens validator, og faktisk chatdemo er ikke dokumentert.
7. Regelindeksens tidsavgrensning bygger foreløpig på PDF-metadata og valgt dekning ut 2025. Historisk virkningsperiode må underbygges før sluttmåling.

Sprinklr er nå et utviklings- og regresjonseksempel. Nye senere møter skal brukes til sluttmålingen. Funnene gir ikke grunnlag for å bytte modell eller database før faktagrunnlag, kildebruk og faktisk arbeidsflyt er rettet og prøvd.
