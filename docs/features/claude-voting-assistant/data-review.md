# Nye stemmedata fra arrangøren

Kontrollert 5. november 2026. Brukeren bekreftet at begge CSV-filene er utlevert av arrangøren. Original eksport, innhentingstid, lisens og definisjonene av de tilførte feltene følger ikke med filene. Dette notatet dokumenterer filkontroll og hva som gjenstår før evaluering. Det rapporterer ingen modellresultater.

## Omfang

| Kontroll | real_votes.csv | npx_votes.csv |
|---|---:|---:|
| Rader | 13 757 | 52 906 |
| Unike meeting_id | 1 161 | 4 568 |
| Unike, ikke-tomme company_id | 194 | 2 550 |
| Møtedato fra | 2019-01-23 | 2023-07-02 |
| Møtedato til | 2026-09-30 | 2026-06-30 |
| FOR i nbim_vote | 12 598 | 45 939 |
| MOT i nbim_vote | 757 | 2 970 |
| AVSTÅ i nbim_vote | 68 | 983 |
| Tom normalisert nbim_vote | 334 | 3 014 |
| Tom normalisert mgmt_rec | 421 | 3 665 |
| Rader med rationale_text | 627 | 0 |
| injection_flag = 1 | 0 | 141 |
| Dupliserte (meeting_id, item_no) | 0 | 0 |

Ingen eksakte radduplikater eller motstridende company_id/møtedato innen samme meeting_id ble funnet. Dette bekrefter ikke at alle forslag fra hver innkalling finnes. CSV-ene inneholder ikke fullstendige innkallinger, dokumentlenker, regelversjoner eller eksportproveniens. N-PX-filen mangler også ticker og original proposal_number på alle rader, company_id på fem rader og proposal_text på sju.

Kontrollsummene i [data-inventory.json](data-inventory.json) identifiserer de mottatte filene. Uendrede kopier oppbevares lokalt i `data/raw/`, som er utelatt fra Git. Felles tilgang og eventuell viderepublisering av originaldata avklares med arrangørens kildebeskrivelse.

## Anbefalt bruk

Bruk `real_votes.csv` som kandidat til NBIM-referansesett. Feltnavn og begrunnelser passer med prosjektet, men opprinnelse og stemmeintensjon kontra faktisk avgitt stemme må kontrolleres mot NBIM-kilden. Filbasert import kan forberedes nå. NBIM-API, Anthropic-tilgang, daterte regler og matchende innkallinger er fortsatt uverifiserte deler av T-01.

Hold `npx_votes.csv` adskilt. Den kan brukes til importkontroll og senere utvidelser når forvalter, feltbetydning og originaltekster er dokumentert. Kolonnenavnet `nbim_vote` dokumenterer ikke at stemmene tilhører NBIM. Kombiner ikke filene til én NBIM-fasit.

Sett NBIMs daterte retningslinjer i RAG-indeksen. Bruk stemmefilene til evaluering utenfor modellens input. Innkallingen og regelkildene må gi selve beslutningsgrunnlaget.

## Felt som trenger særskilt behandling

- `nbim_vote_raw`, `nbim_vote`, `against_board`, `rationale_text`, `position_paper` og `rationale_section` holdes utenfor modellinput og RAG. De kan røpe utfallet eller hvilke regler som ble valgt i etterkant. Av de 627 utfylte begrunnelsene i real_votes gjelder 574 MOT, 40 FOR og 13 AVSTÅ. En evaluering bare på rader med begrunnelse vil være et selektert utvalg.
- Bevar rå stemmeverdier. real_votes mapper 54 `Withhold` til MOT, mens 334 tomme normaliserte stemmer omfatter 283 `None`, 38 frekvensvalg og 13 `Do Not Vote`. N-PX mapper 204 `WITHHOLD` til MOT og har 235 frekvensvalg blant 3 014 tomme normaliserte stemmer. Tom fasit er ikke FOR, AVSTÅ eller modellens manuelle status. Vis slike rader som uten sammenlignbar referanse i evalueringen.
- Verifiser `mgmt_rec` mot kildens semantikk før baseline. SECs N-PX-felt for managementRecommendation beskriver samsvar med styrets anbefaling. Det er ikke nødvendigvis styrets egen stemmeretning. Kopiering til mgmt_rec kan derfor gi feil baseline og feil against_board. Se [kildeundersøkelsen](research/npx-provenance.md).
- `injection_flag` er udefinert av leverandøren. Det markerer 141 rader i 81 N-PX-møter, inkludert alle sju tomme forslagstekster. 30 flaggede tekster slutter med «SY», blant annet avkuttede system-/godtgjørelsesforslag. Bruk feltet som et signal til kildekontroll, ikke som bekreftet angrepsfasit eller en variabel modellen får se.
- Kimco Realty 7. mai 2024 har elleve flaggede rader med bortfalt saksinnhold. Originaldokumentet skiller blant annet mellom direktørvalg, godtgjørelse, kapitalendring og revisor. CSV-tekstene stopper før dette innholdet. Det dokumenterer teksttap, men ikke hvilken rensekode som forårsaket det. [Utstederens proxy-materiale](https://www.sec.gov/Archives/edgar/data/879101/000120677424000290/kim4270851-defa14a.htm).
- `n_funds` varierer fra 1 til 4; fire rader har `funds_disagree=1`. Fondene og aggregeringsregelen er ikke oppgitt. Bevar uenighet og kildeidentitet før en eventuell sammenslåing.
- `split_year` avviker fra møtets kalenderår på 6 915 rader. Bruk faktisk meeting_date ved tidsdeling, og avklar rapporteringsperioden. Hold et helt møte i samme utvalg. `proposal_type` og andre avledede felt holdes utenfor modellinput til beregningsgrunnlaget er dokumentert.

## Konsekvenser for oppgavene

T-01 / #2 skal kontrollere CSV-import og opprinnelse, dokumentere normalisering, koble minst én full innkalling og fryse et lite tidsdelt utvalg med historiske regler. Hashene er frosset, men intet endelig testutvalg er valgt. 2026-delen av real_votes har 141 møte-ID-er og 1 578 rader, inkludert 66 MOT. Det er en mulig senere periode, avhengig av tilgjengelige dokumenter og regelversjoner.

T-06 / #7 skal bruke eksplisitt feltliste for modellinput og dokumentere utelatelser. Manglende styreanbefaling må ikke skjule MOT-saker i hovedmålingen. Baseline på et sammenlignbart delutvalg merkes med sitt eget antall. Manuell sjekk fra modellen teller fortsatt i hoved-recall som avtalt i spesifikasjonen. Motstandstesten lages som et kontrollert original-/angrepspar med kjent endring; de uavklarte CSV-flaggene erstatter ikke testen.

Det er ikke brukt modellkreditter, kjørt applikasjonsevaluering eller lukket implementeringsoppgaver i denne datakontrollen.

## Samordning med lagets datanotat

[Lagets datanotat](../../../interne_notater/case1_datagrunnlag.md) ble lagt til i main under denne undersøkelsen. Det omtaler egne uttak med andre filnavn og radtall, blant annet `votes_nbim.csv` og Fidelity-data. Det dokumenterer ikke originalkilden til arrangørens to nye CSV-er. Kildekontrollen her bekrefter notatets mistanke om SEC-feltet for samsvar med styret.

Notatet bruker MOT om «mot ledelsen», mens `nbim_vote=MOT` i de nye CSV-ene er en normalisering av Against/Withhold på selve forslaget. Disse målvariablene må ikke blandes. FOR/MOT/AVSTÅ-resultatet gjelder forslaget. Et eventuelt mål på avvik fra styret beregnes og navngis separat, etter kontroll av kildefeltene. En MOT-stemme på et aksjonærforslag kan følge styrets anbefaling.

## Opplysninger som fortsatt må hentes

Arrangøren kan avklare restusikkerheten med eksport-/renseskriptet, kilde-URL eller SEC accession/CIK og fondsnavn, definisjonen av injection_flag og originaltekst før rensing. For real_votes trengs NBIM-kilden og uttakstidspunktet. Kontrollen av API-nøkler og kreditter fortsetter separat.
