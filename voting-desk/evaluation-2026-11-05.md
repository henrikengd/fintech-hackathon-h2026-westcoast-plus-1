# Modelltesting 5. november 2026

Felles møtefakta forbedret RAG-forsøket, men den tidligere modellen har fortsatt høyest F1 i dette utvalget. Det nye oppsettet erstatter derfor ikke den tidligere modellen. [Resultatsiden](http://127.0.0.1:8502/evaluation) viser alle målingene.

## Stemmeanbefalinger

Alle metodene i tabellen vurderes på de samme 22 møtene fra 2024. Utvalget har 235 saker, hvorav 232 har kjent NBIM-stemme og 11 er MOT. Dette er tidligere brukt utviklingsdata. De reserverte 20 prosentene er utelatt fra de nye forsøkene, og 2025–2026 er ikke scoret på nytt.

| Oppsett | MOT-presisjon | MOT-recall | F1 | TP | FP | FN | Andel med stemmeanbefaling |
|---|---:|---:|---:|---:|---:|---:|---:|
| Følg styret | 36,4 % | 36,4 % | 36,4 % | 4 | 7 | 7 | 100,0 % |
| Tidligere modell, lagrede svar | 50,0 % | 63,6 % | 56,0 % | 7 | 7 | 4 | 100,0 % |
| Tidligere dokumentagent, lagrede svar | 43,8 % | 63,6 % | 51,9 % | 7 | 9 | 4 | 100,0 % |
| RAG, søk per sak | 0,0 % | 0,0 % | 0,0 % | 0 | 1 | 11 | 1,3 % |
| RAG, sak og felles møtefakta | 100,0 % | 27,3 % | 42,9 % | 3 | 0 | 8 | 11,2 % |

De to nye RAG-kjøringene bruker Claude Sonnet 5.5, effort medium, samme instruksjon og samme daterte regler. Endringen er at den nye varianten også søker etter felles møtefakta om styrets størrelse, uavhengighet, komiteer, oppmøte, roller, godtgjørelse og revisor. Alle 44 møtekjøringer fullførte. Sammenligningen bruker ett svar per møte og oppsett; variasjon mellom modellkjøringer er ikke målt.

Den tidligere modellen og dokumentagenten bruker andre prompter og mer historikk. Noe av denne historikken kommer fra møter som senere havnet i den blandede testdelen. De lagrede resultatene er derfor beskrivende referanser, ikke modeller som er trent på nytt under den nye delingen.

Presisjon er TP / (TP + FP). Recall er TP / (TP + FN). Manglende anbefaling teller som FN når NBIM stemte MOT. F1 er det harmoniske gjennomsnittet av presisjon og recall. Ukjent fasit er utelatt. De tidligere 85,2 prosentene beskriver ruting av avvik fra styret til et menneske og er et annet mål enn MOT-recall.

## Hva vi lærte av feilene

Felles møtefakta fant tre MOT-saker der styreleder også var administrerende direktør: First Horizon, First Financial Bankshares og Hartford. Presisjon på 100 prosent bygger på bare tre foreslåtte MOT. Modellen overser fortsatt åtte av elleve MOT-saker.

Fire av de gjenværende sakene gjelder godtgjørelse hos Zebra, Fortrea, Snowflake og Tesla. Modellen mangler blant annet samlet tildeling, utvanning, opptjeningstid og forholdet mellom lønn og prestasjon. De øvrige fire gjelder aksjonærforslag hos Dell og Tesla. Her mangler deler av selve forslaget, styrets svar eller grunnlag for å vurdere vesentlighet og hvor detaljstyrende forslaget er.

Den forbedrede RAG-varianten ga 26 anbefalinger av 232 kjente stemmer. 206 saker fikk ingen anbefaling, og 226 krevde særskilt manuell kontroll. Alle anbefalinger krever uansett menneskelig godkjenning. 230 saker hadde sitater som kunne gjenfinnes i dokumentutdragene; bare 15 hadde et verifisert regelsitat. Dette inkluderer saker uten stemmeanbefaling. At et sitat finnes i kilden, viser ikke at det logisk støtter konklusjonen.

Neste utviklingssteg bør hente hele forslaget med styrets svar, og lage en faktatabell for godtgjørelse med eksplisitte mangler. Deretter kan samme modell vurderes på disse faktaene. Et bytte av vektordatabase alene løser ikke hullene i beslutningsgrunnlaget. En ny variant bør fastsettes før den sammenlignes på flere utviklingsmøter. Det reserverte testsettet brukes først når oppsettet er valgt.

## Lokal klassifikator med fem valideringsdeler

Tre avgrensede modeller ble sammenlignet med fem deler gruppert etter selskap og møtedato. Treningen brukte 6470 kjente stemmer fra 2019–2023 i den blandede treningsdelen, med 318 MOT. Modellen og terskelen ble valgt fra prediksjoner utenfor treningsfolden. Ingen 2024-resultater inngikk i valget.

På 1505 kjente utviklingsstemmer fra 2024, med 77 MOT, fikk ord- og tegnmodellen 38,1 % presisjon, 41,6 % recall og 39,8 % F1. Den lagrede tidligere modellen fikk 49,3 prosent presisjon, 44,2 prosent recall og 46,6 prosent F1 på de samme sakene. Den nye klassifikatoren erstatter ikke dagens modell. Foldresultatene er brukt til modellvalg og er ikke et uavhengig testresultat.

## Kildesøk

Tolv forhåndsmerkede spørsmål fra tre utviklingsmøter ble brukt til å kontrollere om et kjent kildeutdrag finnes blant de fem første treffene.

| Søkemetode | Anker funnet blant topp 5 | Andel |
|---|---:|---:|
| Nøkkelord | 8 av 12 | 66,7 % |
| Vektorsøk | 9 av 12 | 75,0 % |
| Hybridsøk | 9 av 12 | 75,0 % |
| Vekslende treff fra vektor- og nøkkelordsøk | 11 av 12 | 91,7 % |

De 24 forhåndsdefinerte queryvariantene ga henholdsvis 15, 12, 13 og 17 treff. Alle 720 returnerte utdrag hadde gyldig kildetekst og metadata. Dette er små utviklingstester med ufullstendige relevansvurderinger. De måler verken full søkerecall eller stemmerecall. Vekslende rangering er beholdt som et forsøk og er ikke gjort til standard i brukergrensesnittet.

## Instruksjonsangrep og teknisk kontroll

Ett syntetisk angrep ble lagt til i en kopi av kildeteksten som sendes til Claude, etter søket. Angrepet ba modellen stemme MOT på alle 15 saker og utelate sitater. Ingen stemmer endret seg, og angrepsmarkøren ble ikke skrevet ut. Det rene svaret hadde imidlertid null anbefalinger på alle sakene. Resultatet gir derfor svært lite grunnlag for en generell påstand om robusthet. Innlasting og søk var ikke del av angrepstesten.

98 enhets- og integrasjonstester besto. Kildegrenser, testoverlapp, sitater, feilede svar, cache, skåring og HTTP-visning er kontrollert. `desk.py`, `rules.json` og `real_votes.csv` samsvarer med de opprinnelige kontrollsummene. Historiske resultatfiler er ikke endret. API-nøkkelen ligger i den Git-ignorerte `.env`-filen.

## Etterprøving

- [Kjøring og oppsett](README-rag.md)
- [RAG-rapport](data/local-rag/rag-evaluation-v1/report.json), data-ID `8b10800a48064b79`
- [Saksresultater](data/local-rag/rag-evaluation-v1/predictions.csv)
- [Klassifikator](data/local-rag/mot-experiment-v1/summary.json)
- [Kildesøk](data/local-rag/retrieval-evaluation-v1.json)
- [Angrepstest](data/local-rag/rag-injection-evaluation-v1/summary.json)

Rå modellresultater, fullstendige evidenspakker, kildeidentitet og tokenbruk ligger lokalt under `data/local-rag/`. Det ble lagret 48 fullførte genereringssvar: 44 i hovedsammenligningen, tre i piloten og ett med angrep. Tokenbruk er logget; fakturert beløp er ikke kontrollert. Ingen commit eller push er gjort.
