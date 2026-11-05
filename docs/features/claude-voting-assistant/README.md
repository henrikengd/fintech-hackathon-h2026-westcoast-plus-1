# Stemmegivningsassistent: status og videre arbeid

Oppdatert 5. november 2026. Dette notatet samler beslutningene fra planleggingen. Gjeldende implementeringsstatus og verifikasjon står i [leveransejournalen](delivery.md).

## Avtalt retning

- Case 1: brukeren laster opp én hel innkalling i Claude og får vurdert alle forslag i rekkefølge.
- En MCP-connector søker i daterte NBIM-retningslinjer med RAG. Referansestemmer og etterfølgende begrunnelser holdes utenfor modellinput og søkeindeksen.
- Resultatet er FOR, MOT eller AVSTÅ når grunnlaget er tilstrekkelig. Manglende fakta eller kilder gir separat manuell sjekk med konkret årsak.
- En egen kommandolinjekjøring skal reprodusere analyse og evaluering. Claude-demo og API-evaluering må begge verifiseres.
- Omfang og krav er fastlagt i [spesifikasjonen](spec.md). [Scope](scope.md) bevarer den tidligere avklaringen. Ingen ny produktretning er vedtatt i dataundersøkelsen.

## Funn som må tas med videre

| Tema | Dokumentasjon |
|---|---|
| Kontoer, remote MCP og dokumentflyt | [Claude-undersøkelsen](research/claude-connector.md) |
| Nye arrangørdata, datakvalitet og fasitlekkasje | [Datakontroll](data-review.md) og [kontrollsummer](data-inventory.json) |
| N-PX-felter, investoropphav og injection_flag | [N-PX-undersøkelsen](research/npx-provenance.md) |
| Hvor startpakken omtaler N-PX og «Kom i gang» | [Startpakkens henvisninger](research/starter-links.md) |
| Lagets separat innhentede data | [Lagnotatet](../../../interne_notater/case1_datagrunnlag.md) |

`real_votes.csv` er kandidat til NBIM-referansesett. `npx_votes.csv` holdes adskilt til investor og kildemapping er dokumentert. SECs felt for samsvar med styret må ikke tolkes som selve styreanbefalingen. MOT på forslaget og mot styret er forskjellige mål. Injection-flaggene omfatter teksttap og er ikke bekreftet angrepsfasit.

Startpakken beskriver N-PX-nedlasting og anbefaler samme forvalter for stemmer og retningslinjer. Ingen arrangørrepo-lenke ble funnet i de fire undersøkte PDF-ene. Veiledningen forklarer ikke opprinnelsen til arrangørens nye CSV-er. Det kan finnes en separat e-post eller nyere versjon som ikke er undersøkt.

## Åpne punkter når arbeidet tas opp igjen

1. Hent arrangørens eksport-/renseskript, feltbeskrivelse og originale kildeidentifikatorer. Avklar særlig forvalter, aggregering, styrefelt, injection_flag og tekst før rensing.
2. Koble en komplett innkalling til referansestemmene og gyldige regler. Frys deretter et lite utvalg med senere møter til sluttmåling.
3. Kontroller NBIM-tilgang, faktisk Anthropic API-nøkkel, Claude-connector og tilgjengelige kreditter. Laget har oppgitt USD 204; brukbarhet og saldo er ikke verifisert.
4. Fortsett fra oppgavestatusen i leveransejournalen. Datatilgang og avstemming ligger i T-01 / #2. Evalueringskontrollene ligger i T-06 / #7.

[GitHub-prosjekt](https://github.com/users/henrikengd/projects/3) · [Hovedissue #1](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1)

Funnene fra datakontrollen er publisert i dokumentene og innarbeidet i issues #1, #2 og #7. Ingen implementeringsoppgaver er lukket av datakontrollen. Originale CSV-er ligger lokalt i `data/raw/` og er Git-ignorert. Det er ikke valgt et endelig testsett eller brukt modellkreditter i denne gjennomgangen.
