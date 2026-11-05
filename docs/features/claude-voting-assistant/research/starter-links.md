# Hvor startpakken omtaler N-PX og «Kom i gang»

Kontrollert 5. november 2026. Alle fire PDF-er i den lokale startpakken er undersøkt med tekstuttrekk og PDF-annotasjoner for URI-lenker. Ingen av dem inneholder en identifisert GitHub-repo-URL eller en URI-lenkeannotasjon. Dette utelukker ikke en separat e-post, nettside eller nyere oppgaveversjon.

## De konkrete treffene

- `case1_stemmegivning/README.md`, linje 14–24, har overskriften **«Kom i gang»**. Den viser kjøring av `hent_npx.py --cik 1364742 --inspect`, nedlasting til `votes.csv` og deretter `baseline.py votes.csv`.
- Samme README, linje 28–37, beskriver SEC Form N-PX som fasit. Den ber laget velge én forvalter og bruke samme forvalters egne stemmeretningslinjer.
- `Regler_og_bedommingskriterier.pdf`, side 3, beskriver N-PX som åpen strukturert XML med utsteder, CUSIP, forslagstekst, kategori, stemmeretning og aksjetall. Side 2 viser til `startpakke/` for kode. Side 1 krever et kjørbart repo eller en mappe som leveranse, men lenker ikke til et arrangørrepo.
- `FinTech Hackathon H2026.pdf`, PDF-side 14 (trykt lysbildetall 16), sier at startpakken sendes på e-post og lister casehjelpemidler, referanseguide, casebeskrivelser og regler. Ingen GitHub-lenke ble funnet der.
- `FinTech_Hackathon_Caser_H2026.pdf`, side 1, viser til NBIMs stemmedatabase/API på forespørsel, NBIMs retningslinjer og innkallinger fra SEC EDGAR og selskapenes IR-sider. Den nevner ikke N-PX eller et GitHub-repo direkte.
- `FinTech-ReferanseGuide.pdf` nevner GitHub på side 7 i en advarsel mot lagring av API-hemmeligheter i repositorier. Det er ikke en startpakkelenke.

## Betydning for de nye CSV-ene

README-en forklarer N-PX-sporet, men ikke de nye filene `npx_votes.csv` / `real_votes.csv`, hvilke fond de inneholder, eller `injection_flag`. Den medfølgende `hent_npx.py` skriver andre kolonnenavn og kan derfor ikke alene dokumentere transformasjonen til de nye CSV-ene. Eksempel-CIK-en dokumenterer heller ikke at arrangørens fil faktisk kommer fra denne forvalteren.

## Metodegrense

Ingen kildekode ble kjørt. Undersøkelsen fant ingen konkret arrangørrepo-URL å følge videre. Kildehenvisningene over gjelder filnavn, sidetall og linjer i den utdelte startpakken. Startpakken er ikke kopiert inn i repoet.
