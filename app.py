"""Streamlit-brugerflade for Java & Co.

Økonomiske beregninger ligger i game_engine.py. Denne fil viser
briefing, beslutninger, rapporter og slutrapport.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config
import events
import game_engine
import reporting


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.3rem; padding-bottom: 3rem; max-width: 1180px;}
        h1 {font-weight: 650; letter-spacing: -0.03em; margin-bottom: 0.15rem;}
        .kpi {
            background: #ffffff;
            border: 1px solid #E6DDD2;
            border-radius: 12px;
            padding: 0.8rem 0.95rem 0.7rem;
            min-height: 104px;
        }
        .kpi .label {color: #6E645B; font-size: 0.82rem;}
        .kpi .value {color: #2C2416; font-size: 1.28rem; font-weight: 650; margin: 0.2rem 0;}
        .kpi .sub {color: #6E645B; font-size: 0.78rem; line-height: 1.3;}
        .kpi.bad .value {color: #A33B32;}
        .kpi.good .value {color: #1B7F4E;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def ensure_state() -> None:
    if "generation" not in st.session_state:
        st.session_state.generation = 0
    if "game" not in st.session_state:
        st.session_state.game = game_engine.initial_state()


def reset_game() -> None:
    st.session_state.generation += 1
    st.session_state.game = game_engine.initial_state()
    st.rerun()


def kpi_card(label: str, value: str, subtitle: str, tone: str = "") -> None:
    st.markdown(
        f'<div class="kpi {tone}"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="sub">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


def render_sidebar(game: dict) -> None:
    with st.sidebar:
        st.markdown("**Java & Co.**")
        st.caption("Otte kvartaler. Samme valg giver samme resultat.")
        st.divider()
        if not game["history"] and not game.get("pending_report"):
            st.caption("Ingen kvartaler gennemført endnu.")
        for item in game["history"]:
            st.caption(
                f"Kvartal {item['quarter']}: {reporting.format_dkk(item['report']['period_result'])}"
            )
        pending = game.get("pending_report")
        if pending:
            st.caption(
                f"Kvartal {pending['quarter']} afventer refleksion: "
                f"{reporting.format_dkk(pending['period_result'])}"
            )


def render_header(game: dict) -> None:
    if game["finished"]:
        subtitle = "Slutrapport efter 8 kvartaler"
        done = config.QUARTERS
    else:
        title, _ = events.briefing(game["quarter"])
        status = "resultat og refleksion" if game["locked"] else "beslutning"
        subtitle = f"Kvartal {game['quarter']} af {config.QUARTERS} · {title} · {status}"
        done = len(game["history"]) + (1 if game.get("pending_report") else 0)
    left, right = st.columns([5, 1])
    with left:
        st.markdown("# Java & Co.")
        st.caption("Økonomistyringsspillet")
        st.markdown(f"**{subtitle}**")
    with right:
        st.write("")
        if st.button("Nulstil spil", width="stretch"):
            reset_game()
    st.progress(done / config.QUARTERS, text=f"{done} af {config.QUARTERS} kvartaler gennemført")


def render_kpis(game: dict) -> None:
    reports = reporting.collect_reports(game)
    last = reports[-1] if reports else None
    cash_tone = "bad" if game["cash"] < 0 else ""
    result_tone = "good" if game["cumulative_result"] > 0 else "bad" if game["cumulative_result"] < 0 else ""
    columns = st.columns(5)
    cards = [
        (
            "Likviditet",
            reporting.format_dkk(game["cash"]),
            "Kassebeholdning lige nu",
            cash_tone,
        ),
        (
            "Akkumuleret resultat",
            reporting.format_dkk(game["cumulative_result"]),
            "Sum af periodens resultater",
            result_tone,
        ),
        (
            "Markedsandel",
            reporting.format_pct(last["market_share"]) if last else "–",
            "Seneste kvartals salg i forhold til markedet",
            "",
        ),
        (
            "Kundetilfredshed",
            f"{reporting.format_score(game['customer_satisfaction'])} / 100",
            f"Medarbejdere: {reporting.format_score(game['employee_satisfaction'])} / 100",
            "",
        ),
        (
            "Kapacitetsudnyttelse",
            reporting.format_pct(last["capacity_utilization"]) if last else "–",
            "Seneste kvartals salg i forhold til kapacitet",
            "",
        ),
    ]
    for column, card in zip(columns, cards):
        with column:
            kpi_card(*card)


def render_charts(game: dict) -> None:
    reports = reporting.collect_reports(game)
    if not reports:
        st.info("Graferne vises, når det første kvartal er gennemført.")
        return
    st.plotly_chart(reporting.history_figure(reports), width="stretch")


def _situation_frame(game: dict, facts: dict) -> None:
    experienced = sum(1 for tenure in game["employee_tenures"] if tenure >= 1)
    capacity = game_engine.total_capacity(
        game["employee_tenures"],
        automated=game["automation"],
        new_employee_capacity=facts["new_employee_capacity"],
    )
    rows = [
        ("Likviditet", reporting.format_dkk(game["cash"])),
        ("Gæld", reporting.format_dkk(game["debt"])),
        ("Lager", f"{reporting.format_units(game['inventory_units'])} enheder"),
        ("Lagerets værdi", reporting.format_dkk(game["inventory_value"])),
        ("Medarbejdere", f"{len(game['employee_tenures'])}, heraf {experienced} erfarne"),
        ("Kapacitet nu", f"{reporting.format_units(capacity)} ordrer"),
        ("Løn pr. medarbejder", reporting.format_dkk(facts["wage"])),
        ("Husleje", reporting.format_dkk(facts["rent"])),
        ("Administration", reporting.format_dkk(facts["admin"])),
        ("Råvarepris på nye indkøb", reporting.format_dkk(facts["unit_cost"])),
        ("Grundefterspørgsel", f"{reporting.format_units(facts['base_demand'])} ordrer"),
        ("Markedsstørrelse", f"{reporting.format_units(facts['market_size'])} ordrer"),
        ("Kundetilfredshed", f"{reporting.format_score(game['customer_satisfaction'])} / 100"),
        ("Medarbejdertilfredshed", f"{reporting.format_score(game['employee_satisfaction'])} / 100"),
        ("Automatisering", "Ja" if game["automation"] else "Nej"),
    ]
    left, right = st.columns(2)
    half = (len(rows) + 1) // 2
    for column, chunk in ((left, rows[:half]), (right, rows[half:])):
        with column:
            st.dataframe(
                pd.DataFrame(chunk, columns=["Forhold", "Værdi"]),
                hide_index=True,
                width="stretch",
            )


def render_plan(game: dict) -> None:
    quarter = game["quarter"]
    generation = st.session_state.generation
    title, body = events.briefing(quarter)
    facts = events.structural_conditions(game)
    st.subheader("1. Markedsbriefing")
    st.info(f"**{title}**\n\n{body}")

    st.subheader("2. Virksomhedens situation")
    _situation_frame(game, facts)
    if game["cash"] < 0:
        st.warning(
            "Likviditeten er negativ. Kassekreditten forrentes med "
            f"{str(config.OVERDRAFT_RATE_QUARTER * 100).replace('.', ',')} % pr. kvartal af primo-saldoen."
        )

    previous = game["history"][-1]["decisions"] if game["history"] else None
    key = f"{generation}_{quarter}"

    st.subheader("3. Budget")
    st.caption(
        "Estimér før I ser resultatet. I må gerne budgettere et underskud. "
        "Positiv afvigelse betyder bagefter, at det realiserede tal ligger over budgettet."
    )
    b1, b2, b3 = st.columns(3)
    with b1:
        budget_volume = st.number_input(
            "Forventet afsætning, ordrer",
            min_value=0,
            max_value=500_000,
            value=0,
            step=100,
            key=f"b_vol_{key}",
        )
    with b2:
        budget_revenue = st.number_input(
            "Forventet omsætning, kr.",
            min_value=0,
            max_value=config.BUDGET_ABS_MAX,
            value=0,
            step=1_000,
            key=f"b_rev_{key}",
        )
    with b3:
        budget_contribution = st.number_input(
            "Forventet dækningsbidrag, kr.",
            min_value=-config.BUDGET_ABS_MAX,
            max_value=config.BUDGET_ABS_MAX,
            value=0,
            step=1_000,
            key=f"b_db_{key}",
        )
    b4, b5 = st.columns(2)
    with b4:
        budget_result = st.number_input(
            "Forventet resultat, kr.",
            min_value=-config.BUDGET_ABS_MAX,
            max_value=config.BUDGET_ABS_MAX,
            value=0,
            step=1_000,
            key=f"b_res_{key}",
        )
    with b5:
        budget_cash = st.number_input(
            "Forventet slutlikviditet, kr.",
            min_value=-config.BUDGET_ABS_MAX,
            max_value=config.BUDGET_ABS_MAX,
            value=0,
            step=1_000,
            key=f"b_cash_{key}",
        )

    st.subheader("4. Beslutninger")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        price = st.number_input(
            "Salgspris, kr.",
            min_value=config.PRICE_MIN,
            max_value=config.PRICE_MAX,
            value=int(previous["price"]) if previous else config.START_PRICE,
            step=1,
            key=f"price_{key}",
            help="Højere pris sænker efterspørgslen. Elasticiteten er 1,4.",
        )
    with d2:
        marketing = st.number_input(
            "Marketingbudget, kr.",
            min_value=config.MARKETING_MIN,
            max_value=config.MARKETING_MAX,
            value=int(previous["marketing"]) if previous else 0,
            step=5_000,
            key=f"mkt_{key}",
            help="Effekten stiger, men aftager for hver ekstra krone.",
        )
    with d3:
        current_staff = len(game["employee_tenures"])
        staff_max = config.EMPLOYEES_MAX
        if facts["max_new_hires"] is not None:
            staff_max = min(staff_max, current_staff + facts["max_new_hires"])
        employees = st.number_input(
            "Antal medarbejdere",
            min_value=config.EMPLOYEES_MIN,
            max_value=staff_max,
            value=min(staff_max, max(config.EMPLOYEES_MIN, current_staff)),
            step=1,
            key=f"emp_{key}",
            help="Ny bemanding gælder hele kvartalet. De mindst erfarne fratræder først.",
        )
    with d4:
        purchases = st.number_input(
            "Indkøb, enheder",
            min_value=0,
            max_value=config.PURCHASES_MAX,
            value=int(previous["purchases"]) if previous else config.DEFAULT_PURCHASES,
            step=500,
            key=f"buy_{key}",
            help="Salg kan ikke overstige startlager plus indkøb.",
        )

    loan_room = max(0, int(config.MAX_DEBT - game["debt"]))
    loan_max = min(config.MAX_LOAN_DRAW, loan_room)
    loan_step = 10_000 if loan_max >= 10_000 else 1
    f1, f2 = st.columns(2)
    with f1:
        loan_draw = st.number_input(
            "Nyt lån, kr.",
            min_value=0,
            max_value=loan_max,
            value=0,
            step=loan_step,
            key=f"loan_{key}",
            help="Renter beregnes af gælden ved kvartalets start. Et nyt lån koster først renter fra næste kvartal.",
        )
    with f2:
        if game["debt"] > 0:
            repay_max = int(game["debt"])
            repay_step = 10_000 if repay_max >= 10_000 else 1
            repayment = st.number_input(
                "Afdrag, kr.",
                min_value=0,
                max_value=repay_max,
                value=0,
                step=repay_step,
                key=f"repay_{key}",
                help="Afdrag reducerer likviditet og gæld, ikke resultatet.",
            )
        else:
            repayment = 0
            st.caption("Ingen gæld at afdrage på.")

    invest_choice = False
    accept_choice = False
    strategy_choice = None
    if facts["special_offer"]:
        special = st.radio(
            "Stor kundeordre",
            ["Afvis ordren", "Accepter ordren"],
            index=None,
            horizontal=True,
            key=f"special_{key}",
        )
        accept_choice = None if special is None else special == "Accepter ordren"
    if facts["investment_offer"]:
        invest_label = f"Invester {reporting.format_dkk(config.INVESTMENT_COST)}"
        investment = st.radio(
            "Automatisering",
            ["Invester ikke", invest_label],
            index=None,
            horizontal=True,
            key=f"invest_{key}",
        )
        invest_choice = None if investment is None else investment == invest_label
    if facts["strategy_choice"]:
        strategy = st.radio(
            "Strategisk valg",
            ["Konsolidering", "Vækst"],
            index=None,
            horizontal=True,
            key=f"strategy_{key}",
        )
        strategy_choice = {"Konsolidering": "konsolidering", "Vækst": "vaekst"}.get(strategy)

    decisions = {
        "price": int(price),
        "marketing": int(marketing),
        "employees": int(employees),
        "purchases": int(purchases),
        "loan_draw": int(loan_draw),
        "repayment": int(repayment),
        "invest": invest_choice,
        "accept_special": accept_choice,
        "strategy": strategy_choice,
    }
    preview = game_engine.decision_preview(game, decisions)

    st.subheader("Regnehjælp")
    st.caption(
        "Hjælpen viser omkostninger, kapacitet og break-even. "
        "Den viser ikke efterspørgslen og ikke den tilfældige variation på ±5 %."
    )
    if preview["capacity"] is None:
        capacity_text = "–"
    else:
        capacity_text = (
            f"{reporting.format_units(preview['capacity'])} ordrer "
            f"({preview['experienced']} erfarne × {reporting.format_units(preview['experienced_capacity'])}"
        )
        if preview["new_employees"]:
            capacity_text += (
                f", {preview['new_employees']} nye × {reporting.format_units(preview['new_capacity'])}"
            )
        capacity_text += ")"
    break_even = (
        f"{reporting.format_units(preview['break_even'])} ordrer"
        if preview["break_even"] is not None
        else "Ikke defineret ved negativt dækningsbidrag"
    )
    help_rows = [
        ("Indkøbspris ved dette valg", reporting.format_dkk(preview["purchase_price"])),
        ("DB pr. ordre ved ordinær pris", reporting.format_dkk(preview["cm_per_order"], 2)),
        ("Kapacitet", capacity_text),
        ("Løn i alt", reporting.format_dkk(preview["wages"])),
        ("Faste omkostninger", reporting.format_dkk(preview["fixed_costs"])),
        ("Break-even, drift", break_even),
        ("Indkøbets træk på likviditeten", reporting.format_dkk(preview["purchase_cash"])),
        ("Renter af primo-gæld og kassekredit", reporting.format_dkk(preview["interest"])),
        ("Afskrivning i kvartalet", reporting.format_dkk(preview["depreciation"])),
        ("Markedsfaktor", reporting.format_factor(preview["market_factor"])),
        ("Hændelsesfaktor", reporting.format_factor(preview["demand_factor"])),
        ("Konkurrencefaktor", reporting.format_factor(preview["competition_factor"])),
    ]
    st.dataframe(
        pd.DataFrame(help_rows, columns=["Nøgletal", "Værdi"]),
        hide_index=True,
        width="stretch",
    )

    with st.expander("Sådan beregnes efterspørgslen"):
        st.markdown(reporting.model_explanation())
    with st.expander("Stående spilleregler"):
        st.markdown(reporting.rules_markdown())

    budget = {
        "volume": float(budget_volume),
        "revenue": float(budget_revenue),
        "contribution": float(budget_contribution),
        "result": float(budget_result),
        "ending_cash": float(budget_cash),
    }
    budget_empty = all(abs(value) < 0.5 for value in budget.values())
    if budget_empty:
        st.caption("Udfyld budgettet for at kunne gennemføre kvartalet.")
    for message in preview["errors"]:
        st.warning(message)

    if st.button(
        "Gennemfør kvartalet",
        type="primary",
        disabled=bool(preview["errors"]) or budget_empty,
    ):
        try:
            updated, _report = game_engine.play_quarter(game, decisions, budget)
            st.session_state.game = updated
            st.rerun()
        except game_engine.DecisionError as error:
            for message in error.messages:
                st.error(message)
        except game_engine.QuarterAlreadyCompleted as error:
            st.error(str(error))


def render_results(game: dict) -> None:
    report = game["pending_report"]
    budget = game["pending_budget"]
    st.subheader("Resultatrapport")
    headline = (
        f"Resultat {reporting.format_dkk(report['period_result'])} "
        f"Slutlikviditet {reporting.format_dkk(report['ending_cash'])}"
    )
    if report["ending_cash"] < 0:
        st.error(headline)
    elif report["period_result"] < 0:
        st.warning(headline)
    else:
        st.success(headline)

    notes = reporting.consequence_notes(report)
    if notes:
        st.markdown("\n".join(f"- {note}" for note in notes))
    st.info(reporting.liquidity_comment(report))

    left, right = st.columns(2)
    with left:
        st.markdown("**Resultatopgørelse**")
        st.dataframe(reporting.amount_frame(reporting.income_rows(report)), hide_index=True, width="stretch")
    with right:
        st.markdown("**Likviditet**")
        st.dataframe(reporting.amount_frame(reporting.cash_rows(report)), hide_index=True, width="stretch")

    with st.expander("Fra resultat til likviditet", expanded=True):
        st.caption(
            "Afskrivninger lægges tilbage, fordi de ikke er en udbetaling. "
            "Vareforbrug lægges tilbage, og varekøb trækkes fra, fordi lageret betales ved indkøb."
        )
        st.dataframe(reporting.amount_frame(reporting.bridge_rows(report)), hide_index=True, width="stretch")

    cards = st.columns(5)
    for column, (label, value) in zip(cards, reporting.kpi_lines(report)):
        with column:
            kpi_card(label, value, "")

    st.plotly_chart(reporting.waterfall_figure(report), width="stretch")

    with st.expander("Hvorfor blev efterspørgslen, som den blev?"):
        st.write(reporting.demand_explanation(report))
    with st.expander("Balance"):
        st.dataframe(reporting.balance_frame(report), hide_index=True, width="stretch")
        st.caption("Egenkapitalen ændrer sig med periodens resultat.")

    st.subheader("Budget og realiseret")
    st.caption("Afvigelse = realiseret − budget. En positiv afvigelse betyder, at tallet ligger over budgettet.")
    st.dataframe(reporting.variance_frame(budget, report), hide_index=True, width="stretch")

    st.subheader("Refleksion")
    quarter = game["quarter"]
    key = f"{st.session_state.generation}_{quarter}"
    with st.form(f"reflection_{key}"):
        expected = st.text_area("Hvad gik som forventet?", key=f"ref_a_{key}")
        deviation = st.text_area("Hvad var den vigtigste afvigelse?", key=f"ref_b_{key}")
        cause = st.text_area("Hvad vurderer du var årsagen?", key=f"ref_c_{key}")
        nxt = st.text_area("Hvad vil du ændre næste kvartal?", key=f"ref_d_{key}")
        label = "Gem refleksion og se slutrapport" if quarter == config.QUARTERS else "Gem refleksion og gå til næste kvartal"
        submitted = st.form_submit_button(label, type="primary")
    if submitted:
        reflection = {
            "expected": expected,
            "deviation": deviation,
            "cause": cause,
            "next_change": nxt,
        }
        try:
            st.session_state.game = game_engine.advance_quarter(game, reflection)
            st.rerun()
        except game_engine.DecisionError as error:
            for message in error.messages:
                st.error(message)


def render_final(game: dict) -> None:
    history = game["history"]
    profile = reporting.management_profile(history, game)
    metrics = profile["metrics"]
    st.subheader("Ledelsesrapport")
    st.write(profile["outcome"])
    row1 = st.columns(4)
    row1_cards = [
        ("Samlet resultat", reporting.format_dkk(metrics["total_result"]), ""),
        ("Slutlikviditet", reporting.format_dkk(metrics["ending_cash"]), ""),
        ("Samlet omsætning", reporting.format_dkk(metrics["total_revenue"]), ""),
        ("Gennemsnitlig DG", reporting.format_pct(metrics["average_dg"]), "Vægtet med omsætningen"),
    ]
    for column, card in zip(row1, row1_cards):
        with column:
            tone = ""
            if card[0] == "Samlet resultat":
                tone = "good" if metrics["total_result"] > 0 else "bad" if metrics["total_result"] < 0 else ""
            if card[0] == "Slutlikviditet" and metrics["ending_cash"] < 0:
                tone = "bad"
            kpi_card(card[0], card[1], card[2], tone)
    row2 = st.columns(3)
    row2_cards = [
        ("Markedsandel", reporting.format_pct(metrics["market_share"]), "Sidste kvartal"),
        ("Kundetilfredshed", f"{reporting.format_score(metrics['customer_satisfaction'])} / 100", "Ved afslutningen"),
        ("Medarbejdertilfredshed", f"{reporting.format_score(metrics['employee_satisfaction'])} / 100", "Ved afslutningen"),
    ]
    for column, card in zip(row2, row2_cards):
        with column:
            kpi_card(*card)

    st.markdown(f"### {profile['profile']}")
    st.write(profile["summary"])
    st.caption("Vurderingen er regelbaseret og bruger ikke en sprogmodel.")
    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Point**")
        st.dataframe(reporting.score_frame(profile["scores"]), hide_index=True, width="stretch")
    with right:
        st.markdown("**Regler der blev udløst**")
        st.markdown("\n".join(f"- {rule}" for rule in profile["rules"]))

    st.write(profile["budget_comment"])
    if metrics["average_price"] is not None:
        st.caption(
            "Gennemsnitlig salgspris vægtet med solgte ordrer: "
            f"{reporting.format_dkk(metrics['average_price'], 2)} "
            f"Bogført værdi af automatisering: {reporting.format_dkk(metrics['book_value'])}"
        )

    st.markdown("**Kvartalsresultater**")
    st.dataframe(reporting.quarter_result_frame(history), hide_index=True, width="stretch")
    st.markdown("**Beslutninger**")
    st.dataframe(reporting.decisions_frame(history), hide_index=True, width="stretch")
    st.markdown("**Budgetafvigelser**")
    st.caption("Afvigelse = realiseret − budget.")
    st.dataframe(reporting.budget_deviation_frame(history), hide_index=True, width="stretch")

    st.markdown("**Balance, sidste kvartal**")
    st.dataframe(reporting.balance_frame(history[-1]["report"]), hide_index=True, width="stretch")

    st.markdown("**Refleksioner**")
    questions = [
        ("expected", "Hvad gik som forventet?"),
        ("deviation", "Hvad var den vigtigste afvigelse?"),
        ("cause", "Hvad vurderer du var årsagen?"),
        ("next_change", "Hvad vil du ændre næste kvartal?"),
    ]
    for item in history:
        with st.expander(f"Kvartal {item['quarter']}"):
            for qkey, label in questions:
                st.markdown(f"**{label}**")
                st.write(item["reflection"][qkey])


def main() -> None:
    st.set_page_config(
        page_title="Java & Co. – Økonomistyringsspillet",
        page_icon="☕",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    ensure_state()
    inject_css()
    game = st.session_state.game
    render_sidebar(game)
    render_header(game)
    render_kpis(game)
    render_charts(game)
    st.divider()
    if game["finished"]:
        render_final(game)
    elif game["locked"]:
        render_results(game)
    else:
        render_plan(game)


main()
