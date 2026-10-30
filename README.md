# Java & Co. – Økonomistyringsspillet

Browserbaseret undervisningsspil, hvor de studerende driver kaffekæden Java & Co. gennem 8 kvartaler. Spillet er en virksomhedssimulation: pris, marketing, bemanding, indkøb, finansiering og investering får konsekvenser for omsætning, dækningsbidrag, resultat, likviditet, kapacitet, lager, markedsandel og tilfredshed.

Teknologien er Python, Streamlit, pandas og Plotly. Der er ingen database og ingen ekstern AI.

## Økonomisk model

Pris, løn, husleje, administration, startlikviditet, prisinterval og elasticitet følger opgaven.

Kapacitet, grundefterspørgsel, markedsstørrelse og startlager er ganget med `VOLUME_SCALE` i `config.py` (standard **4**):

| Opgavens tal | I spillet ved skala 4 |
| --- | --- |
| 1.000 ordrer pr. erfaren medarbejder | 4.000 |
| 700 ordrer for en ny medarbejder | 2.800 |
| Grundefterspørgsel 5.500 | 22.000 |
| Marked 22.000 | 88.000 |
| Startlager 1.000 | 4.000 |

Uden skalering er lønnen pr. medarbejder højere end det største dækningsbidrag, en medarbejder kan skabe inden for prisloftet. Break-even kan da ikke nås, uanset beslutning. Skala 4 lægger break-even lige over startkapaciteten, så kvartalerne kan ende i både overskud og underskud.

Sæt `VOLUME_SCALE = 1` i `config.py` for at køre de uskallerede mængder.

Efterspørgslen er

`priseffekt = (50 / pris) ^ 1,4`

med aftagende marketingeffekt og højst ±5 % støj. Støjen trækkes med fast seed, så samme valg giver samme resultat.

## Installation

Kræver Python 3.11 eller nyere.

```bash
cd java-co
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS og Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Start spillet lokalt

Fra mappen `java-co`:

```bash
streamlit run app.py
```

Spillet åbner på http://localhost:8502. Porten er sat i `.streamlit/config.toml`, så TraderDash kan blive på http://localhost:8501.

Kør testene med:

```bash
python -m pytest
```

## Push til GitHub

Kør kommandoerne i mappen `java-co`, så kun spillet kommer med. Opret først et tomt repository på GitHub uden README.

```bash
git init
git add .
git commit -m "Tilføj Java & Co. økonomistyringsspil"
git branch -M main
git remote add origin https://github.com/BRUGER/java-co.git
git push -u origin main
```

`BRUGER` er jeres GitHub-brugernavn, og `java-co` er repository-navnet.

Med GitHub CLI kan det samme gøres sådan:

```bash
git init
git add .
git commit -m "Tilføj Java & Co. økonomistyringsspil"
gh repo create java-co --private --source=. --remote=origin --push
```

## Deploy på Streamlit Community Cloud

1. Push projektet til GitHub som vist ovenfor.
2. Gå til [share.streamlit.io](https://share.streamlit.io) og log ind med GitHub.
3. Vælg **Create app**.
4. Vælg repository, branch `main` og main file path `app.py`.
5. Klik **Deploy**.

`requirements.txt` installeres automatisk. Appen bruger ikke secrets, database eller API-nøgle. `runtime.txt` beder om Python 3.12.

Når I har pushet en ny version, kan I genstarte appen under menuen **Manage app**.
