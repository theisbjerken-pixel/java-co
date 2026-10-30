"""Rapporter, grafer og den regelbaserede ledelsesprofil."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config


BROWN = "#4A3728"
GREEN = "#1B7F4E"
RED = "#A33B32"
GOLD = "#8C6A3D"
BLUE = "#1F4E79"
SAND = "#A67C52"
GRID = "#E6DDD2"

PROFILE_PRIORITY = [
    "Konsoliderende ledelse",
    "Likviditetsorienteret ledelse",
    "Kundefokuseret ledelse",
    "Medarbejderorienteret ledelse",
    "Vækstorienteret ledelse",
    "Risikovillig ekspansion",
]

PROFILE_SUMMARY = {
    "Konsoliderende ledelse": (
        "Beslutningerne peger på konsolidering: pris, bemanding, gæld og det "
        "strategiske valg holder virksomheden samlet frem for at presse volumen."
    ),
    "Likviditetsorienteret ledelse": (
        "Beslutningerne peger på likviditet: gælden er holdt nede, og kassen er "
        "prioriteret over ekspansion."
    ),
    "Kundefokuseret ledelse": (
        "Beslutningerne peger på kunderne: tilfredshed og evnen til at levere "
        "vejer tungere end aggressiv ekspansion."
    ),
    "Medarbejderorienteret ledelse": (
        "Beslutningerne peger på medarbejderne: personalets tilfredshed er det "
        "stærkeste signal i forløbet."
    ),
    "Vækstorienteret ledelse": (
        "Beslutningerne peger på vækst: pris, marketing, bemanding eller "
        "investering er brugt til at søge volumen."
    ),
    "Risikovillig ekspansion": (
        "Beslutningerne peger på høj risiko: gæld, negativ likviditet eller "
        "stort tabt salg dominerer forløbet."
    ),
}


def format_dkk(value: float, decimals: int = 0) -> str:
    negative = value < 0
    number = abs(float(value))
    if decimals == 0:
        raw = f"{number:,.0f}"
    else:
        raw = f"{number:,.{decimals}f}"
    raw = raw.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if negative else ''}{raw} kr."


def format_units(value: float) -> str:
    negative = value < 0
    raw = f"{abs(float(value)):,.0f}".replace(",", ".")
    return f"{'-' if negative else ''}{raw}"


def format_pct(ratio: float | None, decimals: int = 1) -> str:
    if ratio is None:
        return "–"
    raw = f"{ratio * 100:,.{decimals}f}"
    raw = raw.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{raw} %"


def format_score(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}".replace(".", ",")


def format_factor(value: float) -> str:
    return f"{value:.3f}".replace(".", ",")


def _dec(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def amount_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"Post": label, "Beløb": format_dkk(value)} for label, value in rows])


def income_rows(report: dict) -> list[tuple[str, float]]:
    return [
        ("Omsætning", report["revenue"]),
        ("Variable omkostninger", -report["variable_costs"]),
        ("Dækningsbidrag", report["contribution"]),
        ("Løn", -report["wages"]),
        ("Marketing", -report["marketing"]),
        ("Husleje", -report["rent"]),
        ("Administration", -report["admin"]),
        ("Øvrige driftsomkostninger", -report["other_operating"]),
        ("Resultat før afskrivning", report["result_before_depreciation"]),
        ("Afskrivninger", -report["depreciation"]),
        ("Renter", -report["interest"]),
        ("Periodens resultat", report["period_result"]),
    ]


def cash_rows(report: dict) -> list[tuple[str, float]]:
    return [
        ("Likviditet primo", report["opening_cash"]),
        ("Omsætning", report["revenue"]),
        ("Varekøb", -report["purchase_cost"]),
        ("Løn", -report["wages"]),
        ("Marketing", -report["marketing"]),
        ("Husleje", -report["rent"]),
        ("Administration", -report["admin"]),
        ("Øvrige driftsomkostninger", -report["other_operating"]),
        ("Renter", -report["interest"]),
        ("Låneprovenu", report["loan_draw"]),
        ("Afdrag", -report["repayment"]),
        ("Investering", -report["investment_cost"]),
        ("Likviditet ultimo", report["ending_cash"]),
    ]


def bridge_rows(report: dict) -> list[tuple[str, float]]:
    change = report["ending_cash"] - report["opening_cash"]
    return [
        ("Periodens resultat", report["period_result"]),
        ("Afskrivninger, tillægges", report["depreciation"]),
        ("Vareforbrug, tillægges", report["variable_costs"]),
        ("Varekøb, fratrækkes", -report["purchase_cost"]),
        ("Låneprovenu", report["loan_draw"]),
        ("Afdrag", -report["repayment"]),
        ("Investering", -report["investment_cost"]),
        ("Ændring i likviditet", change),
    ]


def balance_frame(report: dict) -> pd.DataFrame:
    def equity(prefix: str) -> float:
        return (
            report[f"{prefix}_cash"]
            + report[f"{prefix}_inventory_value"]
            + report[f"{prefix}_book_value"]
            - report[f"{prefix}_debt"]
        )

    rows = [
        ("Likvider", report["opening_cash"], report["ending_cash"]),
        ("Varelager", report["opening_inventory_value"], report["ending_inventory_value"]),
        ("Automatisering, bogført", report["opening_book_value"], report["ending_book_value"]),
        (
            "Aktiver i alt",
            report["opening_cash"] + report["opening_inventory_value"] + report["opening_book_value"],
            report["ending_cash"] + report["ending_inventory_value"] + report["ending_book_value"],
        ),
        ("Gæld", report["opening_debt"], report["ending_debt"]),
        ("Egenkapital", equity("opening"), equity("ending")),
    ]
    return pd.DataFrame(
        [
            {"Post": label, "Primo": format_dkk(opening), "Ultimo": format_dkk(closing)}
            for label, opening, closing in rows
        ]
    )


def variance_frame(budget: dict, report: dict) -> pd.DataFrame:
    lines = [
        ("Afsætning", budget["volume"], report["sales"], False),
        ("Omsætning", budget["revenue"], report["revenue"], True),
        ("Dækningsbidrag", budget["contribution"], report["contribution"], True),
        ("Resultat", budget["result"], report["period_result"], True),
        ("Slutlikviditet", budget["ending_cash"], report["ending_cash"], True),
    ]
    rows = []
    for label, expected, actual, is_money in lines:
        delta = actual - expected
        if abs(expected) < 0.5:
            percent = "–"
        else:
            percent = format_pct(delta / abs(expected))
        formatter = format_dkk if is_money else format_units
        rows.append(
            {
                "Post": label,
                "Budget": formatter(expected),
                "Realiseret": formatter(actual),
                "Afvigelse": formatter(delta),
                "Afvigelse i procent": percent,
            }
        )
    return pd.DataFrame(rows)


def liquidity_comment(report: dict) -> str:
    cash_change = report["ending_cash"] - report["opening_cash"]
    sentences = [
        f"Resultatet er {format_dkk(report['period_result'])} "
        f"Likviditeten ændrede sig med {format_dkk(cash_change)}"
    ]
    if report["depreciation"] > 0:
        sentences.append(
            f"Afskrivninger på {format_dkk(report['depreciation'])} reducerede resultatet, men ikke likviditeten."
        )
    if report["purchase_cost"] > report["variable_costs"] + 1:
        sentences.append(
            "I købte mere, end I solgte. Det ekstra lager belaster likviditeten, men ikke periodens resultat."
        )
    elif report["variable_costs"] > report["purchase_cost"] + 1:
        sentences.append(
            "En del af vareforbruget kom fra lager, der allerede var betalt. Det belaster resultatet, men ikke likviditeten i dette kvartal."
        )
    if report["loan_draw"] > 0:
        sentences.append(
            f"Lånet på {format_dkk(report['loan_draw'])} øgede likviditeten, men ikke resultatet."
        )
    if report["repayment"] > 0:
        sentences.append(
            f"Afdrag på {format_dkk(report['repayment'])} reducerede likviditeten, men ikke resultatet."
        )
    if report["investment_cost"] > 0:
        sentences.append(
            f"Investeringen på {format_dkk(report['investment_cost'])} blev trukket fra likviditeten. Kun afskrivningen påvirker resultatet."
        )
    return " ".join(sentences)


def consequence_notes(report: dict) -> list[str]:
    notes: list[str] = []
    if report["hires"]:
        notes.append(
            f"I ansatte {report['hires']}. Nye medarbejdere har lavere kapacitet i det kvartal, de bliver ansat."
        )
    if report["fires"]:
        notes.append(f"I sagde {report['fires']} op. De mindst erfarne fratrådte først.")
    if report["lost_sales"] > 0:
        parts = []
        if report["lost_to_capacity"]:
            parts.append(f"{format_units(report['lost_to_capacity'])} på grund af kapacitet")
        if report["lost_to_inventory"]:
            parts.append(f"{format_units(report['lost_to_inventory'])} på grund af lager")
        detail = " og ".join(parts) if parts else format_units(report["lost_sales"])
        notes.append(f"Tabt salg: {detail}.")
    if report["accept_special"]:
        if report["sales_special"] < report["special_demand"]:
            notes.append(
                "Kundeordren blev ikke leveret fuldt ud, og kundetilfredsheden er trukket ned."
            )
        else:
            notes.append(
                f"Kundeordren på {format_units(report['sales_special'])} enheder er leveret til {format_dkk(config.SPECIAL_PRICE)} pr. enhed."
            )
    if report["invest"]:
        notes.append(
            "Investeringen er trukket fra likviditeten og aktiveret. Kun afskrivningen indgår i resultatet."
        )
    if report["loan_draw"] > 0:
        notes.append(
            "Lånet øger likviditeten og gælden. Det indgår ikke i resultatet. Renter af det nye lån starter næste kvartal."
        )
    if report["repayment"] > 0:
        notes.append("Afdraget reducerer likviditet og gæld, men ikke resultatet.")
    if report["interest_overdraft"] > 0:
        notes.append(
            f"Heraf er {format_dkk(report['interest_overdraft'])} renter af kassekredit og {format_dkk(report['interest_loan'])} renter af lån."
        )
    elif report["interest_loan"] > 0:
        notes.append(f"Renter af lån udgør {format_dkk(report['interest_loan'])}")
    if report["ending_cash"] < 0:
        notes.append(
            "Likviditeten er negativ. Næste kvartal beregnes kassekreditrenter af denne saldo."
        )
    break_even = report["break_even_volume"]
    if break_even is not None and break_even > report["capacity"]:
        notes.append(
            "Driftens break-even ligger over kapaciteten ved den valgte pris og bemanding."
        )
    if (
        report["purchases"] > 0
        and report["opening_inventory_units"] > 0
        and abs(report["purchase_unit_cost"] - report["avg_cost"]) > 0.05
    ):
        notes.append(
            "Gennemsnitlig kostpris afviger fra den nye indkøbspris, fordi gammelt og nyt lager blandes."
        )
    return notes


def demand_explanation(report: dict) -> str:
    factors = report["factors"]
    return (
        f"Ordinær efterspørgsel blev {format_units(report['regular_demand'])} ordrer. "
        f"Priseffekt {format_factor(factors['price_effect'])}, "
        f"marketingeffekt {format_factor(factors['marketing_effect'])}, "
        f"tilfredshedseffekt {format_factor(factors['satisfaction_effect'])}, "
        f"serviceeffekt {format_factor(factors['service_effect'])}, "
        f"marked {format_factor(factors['market_factor'])}, "
        f"hændelse {format_factor(factors['demand_factor'])}, "
        f"konkurrence {format_factor(factors['competition_factor'])}, "
        f"støj {format_factor(1 + factors['noise'])}. "
        f"Kundeordre: {format_units(report['special_demand'])}. "
        f"Samlet efterspørgsel: {format_units(report['demand'])}. "
        f"Salg: {format_units(report['sales'])}."
    )


def kpi_lines(report: dict) -> list[tuple[str, str]]:
    break_even = (
        format_units(report["break_even_volume"]) + " ordrer"
        if report["break_even_volume"] is not None
        else "Ikke defineret"
    )
    full = report["break_even_volume_full"]
    if full is not None and report["depreciation"] + report["interest"] > 0:
        break_even += f" (inkl. renter og afskrivning: {format_units(full)})"
    return [
        ("DB pr. ordre", format_dkk(report["db_per_order"] or 0, 2) if report["db_per_order"] is not None else "–"),
        ("Dækningsgrad", format_pct(report["dg"])),
        ("Break-even", break_even),
        ("Kapacitetsudnyttelse", format_pct(report["capacity_utilization"])),
        ("Markedsandel", format_pct(report["market_share"])),
    ]


def collect_reports(game: dict) -> list[dict]:
    reports = [item["report"] for item in game["history"]]
    if game.get("pending_report"):
        reports.append(game["pending_report"])
    return reports


def history_figure(reports: list[dict]) -> go.Figure:
    quarters = [report["quarter"] for report in reports]
    revenue = [report["revenue"] for report in reports]
    result = [report["period_result"] for report in reports]
    cash = [report["ending_cash"] for report in reports]
    sales = [report["sales"] for report in reports]
    customers = [report["customer_satisfaction"] for report in reports]
    employees = [report["employee_satisfaction"] for report in reports]
    result_colors = [GREEN if value >= 0 else RED for value in result]

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=("Omsætning", "Resultat", "Likviditet", "Salg og kundetilfredshed"),
        vertical_spacing=0.16,
        horizontal_spacing=0.10,
        specs=[[{}, {}], [{}, {"secondary_y": True}]],
    )
    fig.add_trace(
        go.Scatter(
            x=quarters,
            y=revenue,
            name="Omsætning",
            mode="lines+markers",
            line={"color": BROWN, "width": 3},
            customdata=[format_dkk(value) for value in revenue],
            hovertemplate="Kvartal %{x}<br>%{customdata}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=quarters,
            y=result,
            name="Resultat",
            marker_color=result_colors,
            customdata=[format_dkk(value) for value in result],
            hovertemplate="Kvartal %{x}<br>%{customdata}<extra></extra>",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=quarters,
            y=cash,
            name="Likviditet",
            mode="lines+markers",
            line={"color": GOLD, "width": 3},
            customdata=[format_dkk(value) for value in cash],
            hovertemplate="Kvartal %{x}<br>%{customdata}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=quarters,
            y=sales,
            name="Salg",
            marker_color=BROWN,
            opacity=0.85,
            customdata=[format_units(value) for value in sales],
            hovertemplate="Kvartal %{x}<br>%{customdata} ordrer<extra></extra>",
        ),
        row=2,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=quarters,
            y=customers,
            name="Kundetilfredshed",
            mode="lines+markers",
            line={"color": BLUE, "width": 3},
            customdata=[format_score(value) for value in customers],
            hovertemplate="Kvartal %{x}<br>Kunder %{customdata}<extra></extra>",
        ),
        row=2,
        col=2,
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=quarters,
            y=employees,
            name="Medarbejdertilfredshed",
            mode="lines+markers",
            line={"color": SAND, "width": 2, "dash": "dot"},
            customdata=[format_score(value) for value in employees],
            hovertemplate="Kvartal %{x}<br>Medarbejdere %{customdata}<extra></extra>",
        ),
        row=2,
        col=2,
        secondary_y=True,
    )
    fig.update_layout(
        height=640,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Segoe UI, sans-serif", "color": "#2C2416"},
        legend={"orientation": "h", "y": 1.14, "x": 0},
        barmode="relative",
    )
    fig.update_xaxes(dtick=1, gridcolor=GRID, title_text="Kvartal")
    fig.update_yaxes(gridcolor=GRID, separatethousands=True)
    fig.update_yaxes(range=[0, 100], secondary_y=True, row=2, col=2, title_text="Score")
    fig.update_annotations(font_size=14)
    return fig


def waterfall_figure(report: dict) -> go.Figure:
    labels = ["Omsætning", "Variable omk.", "Dækningsbidrag"]
    measures = ["absolute", "relative", "total"]
    deltas = [report["revenue"], -report["variable_costs"], 0]
    display = [report["revenue"], -report["variable_costs"], report["contribution"]]
    for label, amount in (
        ("Løn", -report["wages"]),
        ("Marketing", -report["marketing"]),
        ("Husleje", -report["rent"]),
        ("Administration", -report["admin"]),
    ):
        labels.append(label)
        measures.append("relative")
        deltas.append(amount)
        display.append(amount)
    if report["other_operating"]:
        labels.append("Øvrige")
        measures.append("relative")
        deltas.append(-report["other_operating"])
        display.append(-report["other_operating"])
    labels.extend(["Før afskrivning", "Afskrivninger", "Renter", "Resultat"])
    measures.extend(["total", "relative", "relative", "total"])
    deltas.extend([0, -report["depreciation"], -report["interest"], 0])
    display.extend(
        [
            report["result_before_depreciation"],
            -report["depreciation"],
            -report["interest"],
            report["period_result"],
        ]
    )
    fig = go.Figure(
        go.Waterfall(
            x=labels,
            y=deltas,
            measure=measures,
            customdata=[format_dkk(value) for value in display],
            hovertemplate="%{x}<br>%{customdata}<extra></extra>",
            connector={"line": {"color": GRID}},
            increasing={"marker": {"color": GREEN}},
            decreasing={"marker": {"color": RED}},
            totals={"marker": {"color": BROWN}},
        )
    )
    fig.update_layout(
        height=420,
        margin={"l": 20, "r": 20, "t": 30, "b": 80},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Segoe UI, sans-serif", "color": "#2C2416"},
        showlegend=False,
    )
    fig.update_xaxes(tickangle=-35, gridcolor=GRID)
    fig.update_yaxes(gridcolor=GRID, separatethousands=True)
    return fig


def model_explanation() -> str:
    return f"""
**Efterspørgsel**

Priseffekt = ({_dec(config.REFERENCE_PRICE)} / salgspris) ^ {_dec(config.PRICE_ELASTICITY)}

Marketingeffekt = 1 + {_dec(config.MARKETING_MAX_LIFT)} × (1 − e^(−marketing / {_dec(config.MARKETING_SCALE)}))

Hver ekstra marketingkrone virker mindre end den forrige.

Tilfredshedseffekt = {_dec(config.CS_FACTOR_BASE)} + {_dec(config.CS_FACTOR_SLOPE)} × (kundetilfredshed / {_dec(config.SAT_REFERENCE)})

Serviceeffekt = {_dec(config.ES_FACTOR_BASE)} + {_dec(config.ES_FACTOR_SLOPE)} × (medarbejdertilfredshed / {_dec(config.SAT_REFERENCE)})

Ordinær efterspørgsel = grundefterspørgsel × marked × hændelse × konkurrence × priseffekt × marketingeffekt × tilfredshedseffekt × serviceeffekt × (1 + støj).

Støjen er højst ±{_dec(config.NOISE_MAX * 100)} % og trækkes med fast seed {config.RANDOM_SEED}. Samme valg giver derfor samme resultat. Efterspørgslen kan ikke overstige markedet.

**Salg og kapacitet**

Faktisk salg = minimum af efterspørgsel, kapacitet og lager efter indkøb.

En erfaren medarbejder leverer {format_units(config.EXPERIENCED_CAPACITY)} ordrer. En ny medarbejder leverer {format_units(config.NEW_EMPLOYEE_CAPACITY)} i ansættelseskvartalet. Ved opsigelse fratræder de mindst erfarne først.

**Resultat og likviditet**

Dækningsbidrag = omsætning − vareforbrug. Vareforbruget bruger gennemsnitlig kostpris.

Likviditeten ændres af omsætning, varekøb, løn, marketing, husleje, administration, renter, lån, afdrag og investeringer. Afskrivninger ændrer resultatet, men ikke likviditeten. Et lån ændrer likviditeten, men ikke resultatet. Renter beregnes af gæld og eventuel kassekredit ved kvartalets start.
"""


def rules_markdown() -> str:
    return f"""
- Spillet har {config.QUARTERS} kvartaler. Hvert kvartal kan kun gennemføres én gang.
- Pris {config.PRICE_MIN}–{config.PRICE_MAX} kr. Marketing 0–{format_dkk(config.MARKETING_MAX)} Medarbejdere {config.EMPLOYEES_MIN}–{config.EMPLOYEES_MAX}.
- Salg kan ikke overstige efterspørgsel, kapacitet eller lager. Lageret kan ikke blive negativt.
- Lån kan højst være {format_dkk(config.MAX_LOAN_DRAW)} pr. kvartal, og gælden kan højst være {format_dkk(config.MAX_DEBT)}
- Rente af lån: {_dec(config.LOAN_RATE_QUARTER * 100)} % pr. kvartal af primo-gælden. Rente af kassekredit: {_dec(config.OVERDRAFT_RATE_QUARTER * 100)} % pr. kvartal af negativ primo-likviditet.
- Nye lån forrentes fra kvartalet efter optagelsen. Afdrag reducerer likviditet og gæld, ikke resultatet.
- Budgettet afgives før kvartalet køres. Bagefter vises budget, realiseret tal og afvigelse.
"""


def final_metrics(history: list[dict], state: dict) -> dict:
    reports = [item["report"] for item in history]
    decisions = [item["decisions"] for item in history]
    total_revenue = sum(report["revenue"] for report in reports)
    total_contribution = sum(report["contribution"] for report in reports)
    total_sales = sum(report["sales"] for report in reports)
    total_demand = sum(report["demand"] for report in reports)
    total_lost = sum(report["lost_sales"] for report in reports)
    last = reports[-1]
    percent_errors = []
    for item in history:
        budget = item["budget"]
        report = item["report"]
        for expected, actual in (
            (budget["volume"], report["sales"]),
            (budget["revenue"], report["revenue"]),
            (budget["contribution"], report["contribution"]),
            (budget["result"], report["period_result"]),
            (budget["ending_cash"], report["ending_cash"]),
        ):
            if abs(expected) >= 1:
                percent_errors.append(abs(actual - expected) / abs(expected))
    return {
        "total_result": sum(report["period_result"] for report in reports),
        "total_revenue": total_revenue,
        "total_contribution": total_contribution,
        "total_sales": total_sales,
        "ending_cash": state["cash"],
        "ending_debt": state["debt"],
        "ending_inventory": state["inventory_units"],
        "customer_satisfaction": state["customer_satisfaction"],
        "employee_satisfaction": state["employee_satisfaction"],
        "market_share": last["market_share"],
        "average_dg": (total_contribution / total_revenue) if total_revenue else None,
        "average_price": (total_revenue / total_sales) if total_sales else None,
        "marketing_sum": sum(decision["marketing"] for decision in decisions),
        "employees_end": last["employees"],
        "employees_start": config.START_EMPLOYEES,
        "invested": any(decision["invest"] for decision in decisions),
        "accepted_special": any(decision["accept_special"] for decision in decisions),
        "strategy": decisions[-1].get("strategy"),
        "min_cash": min(report["ending_cash"] for report in reports),
        "lost_ratio": (total_lost / total_demand) if total_demand else 0.0,
        "budget_mape": (sum(percent_errors) / len(percent_errors)) if percent_errors else None,
        "book_value": state["automation_gross"] - state["accumulated_depreciation"],
    }


def budget_comment(mape: float | None) -> str:
    if mape is None:
        return "Budgetterne var ikke udfyldt med tal, der kan sammenlignes procentvis."
    if mape <= 0.15:
        return f"Budgetterne ramte i gennemsnit inden for {format_pct(mape)}. Afvigelserne er små."
    if mape <= 0.40:
        return f"Budgetterne havde moderate afvigelser. Den gennemsnitlige absolutte afvigelse er {format_pct(mape)}."
    return f"Budgetterne afveg væsentligt fra de realiserede tal. Den gennemsnitlige absolutte afvigelse er {format_pct(mape)}."


def _add(scores: dict, rules: list[str], profile: str, points: int, text: str) -> None:
    scores[profile] += points
    rules.append(f"{text} (+{points} til {profile.lower()})")


def management_profile(history: list[dict], state: dict) -> dict:
    """Fast regelbaseret profil. Bruger ikke en sprogmodel."""
    metrics = final_metrics(history, state)
    scores = {name: 0 for name in PROFILE_PRIORITY}
    rules: list[str] = []
    if metrics["ending_cash"] >= 250_000:
        _add(scores, rules, "Likviditetsorienteret ledelse", 3, "Slutlikviditeten er mindst 250.000 kr.")
    elif metrics["ending_cash"] >= 0:
        _add(scores, rules, "Likviditetsorienteret ledelse", 1, "Slutlikviditeten er positiv og under 250.000 kr.")
    else:
        _add(scores, rules, "Risikovillig ekspansion", 3, "Slutlikviditeten er negativ.")
    if metrics["ending_debt"] <= 0.5:
        _add(scores, rules, "Likviditetsorienteret ledelse", 2, "Virksomheden er gældfri.")
    elif metrics["ending_debt"] > 1_000_000:
        _add(scores, rules, "Risikovillig ekspansion", 4, "Gælden er over 1.000.000 kr.")
    elif metrics["ending_debt"] > 500_000:
        _add(scores, rules, "Risikovillig ekspansion", 2, "Gælden er over 500.000 kr.")
    if metrics["invested"]:
        _add(scores, rules, "Vækstorienteret ledelse", 2, "Automatiseringen er gennemført.")
    elif metrics["ending_debt"] <= 200_000:
        _add(scores, rules, "Konsoliderende ledelse", 1, "Ingen automatisering og gæld på højst 200.000 kr.")
    if metrics["strategy"] == "vaekst":
        _add(scores, rules, "Vækstorienteret ledelse", 3, "Kvartal 8: vækst er valgt.")
    elif metrics["strategy"] == "konsolidering":
        _add(scores, rules, "Konsoliderende ledelse", 3, "Kvartal 8: konsolidering er valgt.")
    customers = metrics["customer_satisfaction"]
    staff = metrics["employee_satisfaction"]
    if customers >= 80:
        _add(scores, rules, "Kundefokuseret ledelse", 3, "Kundetilfredsheden er mindst 80.")
    elif customers >= 70:
        _add(scores, rules, "Kundefokuseret ledelse", 1, "Kundetilfredsheden er mindst 70.")
    elif customers < 55:
        _add(scores, rules, "Risikovillig ekspansion", 1, "Kundetilfredsheden er under 55.")
    if staff >= 80:
        _add(scores, rules, "Medarbejderorienteret ledelse", 3, "Medarbejdertilfredsheden er mindst 80.")
    elif staff >= 70:
        _add(scores, rules, "Medarbejderorienteret ledelse", 1, "Medarbejdertilfredsheden er mindst 70.")
    elif staff < 55:
        _add(scores, rules, "Risikovillig ekspansion", 1, "Medarbejdertilfredsheden er under 55.")
    average_price = metrics["average_price"] or 0
    if average_price >= 60:
        _add(scores, rules, "Konsoliderende ledelse", 2, "Den gennemsnitlige salgspris er mindst 60 kr.")
    elif average_price <= 42:
        _add(scores, rules, "Vækstorienteret ledelse", 2, "Den gennemsnitlige salgspris er højst 42 kr.")
    share = metrics["market_share"] or 0
    if share >= 0.30:
        _add(scores, rules, "Vækstorienteret ledelse", 2, "Markedsandelen i sidste kvartal er mindst 30 %.")
    elif share <= 0.12:
        _add(scores, rules, "Konsoliderende ledelse", 1, "Markedsandelen i sidste kvartal er højst 12 %.")
    if metrics["employees_end"] >= metrics["employees_start"] + 3:
        _add(scores, rules, "Vækstorienteret ledelse", 2, "Bemanding er øget med mindst 3 personer.")
    elif metrics["employees_end"] < metrics["employees_start"]:
        _add(scores, rules, "Konsoliderende ledelse", 1, "Bemanding er lavere end ved start.")
    if metrics["marketing_sum"] >= 800_000:
        _add(scores, rules, "Vækstorienteret ledelse", 2, "Marketing over otte kvartaler er mindst 800.000 kr.")
    elif metrics["marketing_sum"] <= 80_000:
        _add(scores, rules, "Konsoliderende ledelse", 1, "Marketing over otte kvartaler er højst 80.000 kr.")
    if metrics["accepted_special"]:
        _add(scores, rules, "Vækstorienteret ledelse", 1, "Den store kundeordre blev accepteret.")
    if metrics["min_cash"] < -300_000:
        _add(scores, rules, "Risikovillig ekspansion", 2, "Likviditeten har været under −300.000 kr.")
    if metrics["lost_ratio"] > 0.12:
        _add(scores, rules, "Risikovillig ekspansion", 1, "Over 12 % af efterspørgslen blev tabt som salg.")
    elif metrics["lost_ratio"] <= 0.03 and customers >= 70:
        _add(scores, rules, "Kundefokuseret ledelse", 1, "Tabt salg er højst 3 %, og kundetilfredsheden holder mindst 70.")

    profile = max(PROFILE_PRIORITY, key=lambda name: (scores[name], -PROFILE_PRIORITY.index(name)))
    if metrics["total_result"] >= 0:
        outcome = "Driften endte samlet i overskud."
    else:
        outcome = "Driften endte samlet i underskud."
    if metrics["ending_cash"] >= 0:
        outcome += " Likviditeten var positiv ved afslutningen."
    else:
        outcome += " Likviditeten var negativ ved afslutningen."
    return {
        "profile": profile,
        "summary": PROFILE_SUMMARY[profile],
        "outcome": outcome,
        "scores": sorted(scores.items(), key=lambda item: (-item[1], PROFILE_PRIORITY.index(item[0]))),
        "rules": rules,
        "metrics": metrics,
        "budget_comment": budget_comment(metrics["budget_mape"]),
    }


def decisions_frame(history: list[dict]) -> pd.DataFrame:
    rows = []
    for item in history:
        decision = item["decisions"]
        quarter = item["quarter"]
        strategy = {"vaekst": "Vækst", "konsolidering": "Konsolidering"}.get(decision.get("strategy"), "–")
        rows.append(
            {
                "Kvartal": quarter,
                "Pris": format_dkk(decision["price"]),
                "Marketing": format_dkk(decision["marketing"]),
                "Medarbejdere": decision["employees"],
                "Indkøb": format_units(decision["purchases"]),
                "Lån": format_dkk(decision["loan_draw"]),
                "Afdrag": format_dkk(decision["repayment"]),
                "Kundeordre": ("Ja" if decision["accept_special"] else "Nej") if quarter == 3 else "–",
                "Investering": ("Ja" if decision["invest"] else "Nej") if quarter == 4 else "–",
                "Strategi": strategy if quarter == 8 else "–",
            }
        )
    return pd.DataFrame(rows)


def quarter_result_frame(history: list[dict]) -> pd.DataFrame:
    rows = []
    for item in history:
        report = item["report"]
        rows.append(
            {
                "Kvartal": report["quarter"],
                "Omsætning": format_dkk(report["revenue"]),
                "Dækningsbidrag": format_dkk(report["contribution"]),
                "Resultat": format_dkk(report["period_result"]),
                "Slutlikviditet": format_dkk(report["ending_cash"]),
                "Salg": format_units(report["sales"]),
                "Markedsandel": format_pct(report["market_share"]),
            }
        )
    return pd.DataFrame(rows)


def budget_deviation_frame(history: list[dict]) -> pd.DataFrame:
    rows = []
    for item in history:
        budget = item["budget"]
        report = item["report"]
        rows.append(
            {
                "Kvartal": item["quarter"],
                "Afsætning": format_units(report["sales"] - budget["volume"]),
                "Omsætning": format_dkk(report["revenue"] - budget["revenue"]),
                "Dækningsbidrag": format_dkk(report["contribution"] - budget["contribution"]),
                "Resultat": format_dkk(report["period_result"] - budget["result"]),
                "Slutlikviditet": format_dkk(report["ending_cash"] - budget["ending_cash"]),
            }
        )
    return pd.DataFrame(rows)


def score_frame(scores: list[tuple[str, int]]) -> pd.DataFrame:
    return pd.DataFrame([{"Profil": name, "Point": points} for name, points in scores])
