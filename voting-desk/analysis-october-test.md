# Hvorfor oktober-testen ga F1 lik null

Gjennomgått 5. november 2026. Analysen bruker lagrede prediksjoner, modellinput og råuttrekk fra `fresh-test-2026-10-v1`. Ingen modeller er kjørt på nytt. Ingen terskel eller søkeinnstilling er valgt på oktoberdataene.

Begge modellene overså alle tre faktiske avvik og varslet to falske avvik. Precision, recall og F1 ble derfor null. Det skyldes modellprediksjonene, ikke mislykkede API-kall eller feil i koblingen til fasiten. De separate kontrollene `verification.json` og `extraction-verification.json` bekrefter alle 36 saksidentiteter og alle stemmemappinger. Hovedmålingen gjelder 33 saker med kjent NBIM-stemme og styreanbefaling.

## Feilene i de fem sakene

Internt saksnummer er radnummeret i uttrekket. Det er ikke alltid samme nummer som på NBIMs nettside. Colruyts offentlige saker 2.1 og 2.2 er interne saker 8 og 9.

| Møte og offentlig sak | NBIM | Lokal avviksskår | Claude | Resultat |
|---|---|---:|---|---|
| Colruyt 2119706, sak 2.1 | MOT | 0,00837 | FOR | Oversett avvik |
| Colruyt 2119706, sak 2.2 | MOT | 0,01748 | FOR | Oversett avvik |
| PT Solusi 2121576, sak 1 | FOR | 0,37770 | MOT | Falskt avvik |
| PT Solusi 2121576, sak 2 | MOT | 0,13159 | FOR | Oversett avvik |
| PT Solusi 2121576, sak 3 | FOR | 0,51554 | MOT | Falskt avvik |

Styret anbefalte FOR i alle fem saker. Den lokale terskelen var 0,225399. Begge falske avvik fikk høyere skår enn alle tre faktiske avvik. Dette er en feil i rangeringen, ikke bare et spørsmål om hvor grensen ble satt. En annen grense kan endre avveiningen, men kan ikke plassere disse fem sakene riktig med de samme skårene. Skårene er ikke kalibrerte sannsynligheter.

Colruyts to saker gjelder fullmakter til tilbakekjøp og gjenutstedelse av aksjer ved alvorlig og umiddelbar skade. De 16 historiske treffene i hver sak består av 15 FOR og én MOT. Den ene MOT gjelder en sluttvederlagsbestemmelse, ikke oppkjøpsvern. For sak 2.1 har alle de åtte globale treffene nøyaktig samme standardtekst om gjenutstedelse av tilbakekjøpte aksjer, og alle fikk FOR. Treffene kommer fra forskjellige møter, men tilfører lite variasjon i sakstekst. For sak 2.2 har de åtte globale treffene tre forskjellige tekster, også med FOR i alle tilfeller.

Ingen av de 13 325 tekstene i den tilgjengelige historikken inneholder ordene `serious` eller `imminent`. Historikken har derimot to MOT-saker om en uttrykkelig oppkjøpsforsvarsplan fra 2020 og 2023, med identitetene `1440770:20` og `1763807:10`. Ingen av disse ble hentet frem for Colruyt-sakene. Søket fant aksjefullmakter som lignet språklig, men koblet ikke den nye formuleringen til oppkjøpsvern. Dette er en konkret begrensning ved de lagrede treffene, ikke bevis for at en annen søkemetode ville gitt riktig prediksjon.

Hos PT Solusi fungerer historisk gjentakelse dårlig i motsatt retning. Sak 3 har nøyaktig samme forslagstekst som selskapets sak `2087754:5` fra 30. juni 2026. NBIMs gamle stemme var MOT, mens oktoberstemmen er FOR. Dette historiske treffet har cosinuslikhet 1,0 og ble sitert av Claude. Samme ordlyd betyr altså ikke samme beslutningsgrunnlag eller samme stemme. I sak 1 legger Claude også vekt på en tidligere MOT-stemme ved en lignende endring av selskapets virksomhetsformål.

Samtidig får PT Solusis sak 2 åtte globale FOR-treff om vedtektsendringer. Claude beskriver endringen av styrets plikter og myndighet som rutinemessig og predikerer FOR. Det blir feil. NBIMs publiserte begrunnelse viser til aksjonærenes rett til å godkjenne grunnleggende endringer i selskapets styringsdokumenter.

NBIMs begrunnelser ble lest etter skåring. For Colruyt viser de til oppkjøpsvern og aksjonærgodkjenning. De er en kilde til etteranalysen, men kan ikke brukes som input for å predikere de samme stemmene. De ville da røpet fasiten. Kildene er [Colruyt-møtet](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting?m=2119706) og [PT Solusi-møtet](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting?m=2121576).

## Hva testen sier, og hva den ikke sier

Tre faktiske avvik fra bare to møter gir et svært lite grunnlag for å anslå generell F1. To avvik gjelder nært beslektede fullmakter i samme møte. De er ikke tre uavhengige typer feil. Seks av de sju møtene er registrert som Special eller Extraordinary Shareholders. Bare ett er et ordinært årsmøte. Dette er et annet og smalere saksutvalg enn den brede 2024-kalibreringen.

Andelen avvik er 3 av 33, altså 9,1 prosent. Til sammenligning hadde treningsperioden 477 av 7 993, eller 6,0 prosent, og 2024 hadde 98 av 1 883, eller 5,2 prosent. Det nye utvalget hadde ikke færre avvik målt som andel. Problemet var at begge modellene overså akkurat de avvikene som forekom. En modell som alltid følger styret ville hatt 90,9 prosent accuracy og fortsatt F1 lik null.

PT Solusi finnes ikke i treningsperioden til og med 2023. Før oktober finnes bare 11 kjente historiske saker fra to møter i 2025 og 2026. Hainan Jinpan finnes heller ikke i treningsperioden, men gir ingen av de fem feilene. Tynt selskapsspesifikt grunnlag er derfor en mulig medvirkende faktor, ikke en full forklaring. Det er heller ikke dokumentert at NBIM endret generell stemmepolicy mellom juni og oktober. Vi ser bare at stemmer for tilsvarende ordlyd endret seg.

Det kontrollerte oppsettet bruker forslagstekst, styreanbefaling og historiske stemmer. Det bruker ikke selve vedtektsendringene, styrekandidatenes egenskaper, møteinnkallingene eller gjeldende regeltekster. Vi kan derfor dokumentere manglende saksopplysninger og misvisende historiske analogier. Vi kan ikke dokumentere hva en modell med disse opplysningene ville oppnådd uten et eget forsøk.

## Følger for videre modellarbeid

F1 bør velge modell og terskel på de tidligere utviklingsdataene, med hele møter samlet og riktig tidsrekkefølge. Oktoberresultatet skal bevares. Etter denne feilanalyse kan oktoberdata ikke brukes som en ny urørt bekreftelse av forbedringer inspirert av feilene.

De observerte feilene gir noen konkrete hypoteser som kan undersøkes på utviklingsdata. Søket kan kombinere tekstvektorer med ordsøk og gi færre plasser til gjentatt standardtekst. Historiske eksempler kan suppleres med møteinnkalling, konkrete endringer og regeltekst som var tilgjengelig før beslutningen. Modellen bør håndtere at samme tekst har gitt ulike stemmer, og kunne avstå når de avgjørende opplysningene mangler. Dette er forslag til forsøk, ikke dokumenterte forbedringer.

NBIM-kilden beskriver publiserte stemmeintensjoner. Analysen bekrefter ikke faktisk avgitte stemmer, og publiseringshistorikken er ikke fullstendig dokumentert. En senere måling må bruke nye møter som ikke påvirket modellvalget.
