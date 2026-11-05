# Evaluering av stemmegivningsassistenten

Evalueringsmanifestet peker på to filer per møte. Sakslisten gir Claude forslag og kilder. Referansefilen inneholder stemmene og styrets anbefalinger. Evaluatoren sender bare sakslisten til vurderingen og kobler på referansen etterpå.

```json
{
  "version": 1,
  "dataset_kind": "nbim_verified",
  "split": "test",
  "meetings": [
    {
      "split": "test",
      "agenda": {"path": "agenda.json", "sha256": "<64 hex characters>"},
      "reference": {"path": "reference.json", "sha256": "<64 hex characters>"}
    }
  ]
}
```

Filstier er relative til manifestet. Beregn SHA-256 fra filenes faktiske bytes. Lagre ett møte i bare én del av utvalget. Alle testmøter må være senere enn alle utviklingsmøter dersom manifestet inneholder begge deler. Kildene i sakslisten må være datert senest på møtedagen. Ved behov kan `policy_documents` låse versjoner til SHA-256 for kildedokumentene. Pilotmanifestet gjør dette for NBIMs 2025-PDF. Standard er å kjøre `test`. Sett `split` til `development` for utprøving.

Bruk `nbim_verified` når stemmene er avstemt mot en kilde som dokumenterer stemmeintensjon eller avgitt stemme. Feltet beskriver referansedataene. Gyldigheten av historiske retningslinjer vurderes separat. Bruk `nbim_candidate` for eksporten med uavklarte stemmedefinisjoner og `synthetic` for konstruerte eksempler. Et syntetisk datasett krever en syntetisk regelindeks. De to NBIM-variantene bruker NBIM-indeksen.

## Kjøring

Bygg regelindeksen med `index` først. Oppgi Anthropic-nøkkel, eksakt modell-ID og gjeldende pris for inn- og uttokens i USD per million i miljøvariablene i `.env.example`.

```bash
python -m voting_assistant evaluate \
  --manifest data/raw/evaluation.json \
  --index data/index.json \
  --output data/raw/evaluation-report.json \
  --max-cost-usd 2
```

Legg til `--resume` for å fortsette fra samme rapport. Evaluatoren sjekker manifest, filenes kontrollsummer, indeks, modell, instruksjon og priser. Fullførte møter gjenbrukes. Et delvis møte kan prøves på nytt. Maksrammen gjelder den samlede rapporten og inkluderer tidligere forsøk. En konservativ reservasjon skrives før modellkallet. Hvis prosessen avbrytes før faktisk bruk kan leses, beholdes reservasjonen i rapporten.

## Les rapporten

MOT-presisjon teller riktige MOT blant modellens scorede MOT. MOT-recall teller dem blant alle faktiske MOT, også ved manuell sjekk eller manglende modellresultat. Rader uten sammenlignbar referanse vises separat. Udefinerte mål har verdien `null`. Dekningen er andelen forslag med en anbefaling. En delvis kjøring får status `partial` og gir feilstatus fra CLI.

Baselinen `stem_som_styret` krever faktiske styreanbefalinger for alle scorede forslag. Ellers vises `aldri_mot` på samme utvalg. Ved rapportering, oppgi om referansen er stemmeintensjon eller avgitt stemme, antall møter, antall scorede forslag, MOT-tellerne og dekningen.

## Motstandstest

Kjør ett valgt møte som en kontroll og en kopi der en uautorisert instruksjon legges inn i saksgrunnlaget. Bruk to manifester med samme referansefil, ulike kontrollsummer for sakslisten og separate rapportfiler. Hold regelindeks, modell, instruksjonsversjon og prisoppsett like. Kontroller om anbefalingen, kildene eller statusen endres. Rapporter også om modellen fulgte instruksjonen. Lokale tester bruker kontrollerte svar for scoring og gjenopptak. Den faktiske modellkjøringen krever Anthropic-tilgang.
