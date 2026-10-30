"""Kvartalshændelser for Java & Co.

Hændelserne ændrer de tal, spilmotoren regner med. Selve resultat-
og likviditetsberegningen ligger i game_engine.py.
"""

from __future__ import annotations

import math

import config


def _as_float(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _kr(value: float) -> str:
    negative = value < 0
    amount = abs(int(round(value)))
    text = f"{amount:,}".replace(",", ".")
    return f"{'-' if negative else ''}{text} kr."


def _n(value: float) -> str:
    amount = abs(int(round(value)))
    return f"{amount:,}".replace(",", ".")


def _dec(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def shortage_wage() -> int:
    return int(round(config.WAGE * config.WAGE_MULTIPLIER_SHORTAGE))


def depreciation_per_quarter() -> float:
    return config.INVESTMENT_COST / config.INVESTMENT_LIFE


def structural_conditions(state: dict) -> dict:
    """Forhold spilleren kan se, før beslutningen er truffet."""
    quarter = state["quarter"]
    unit_cost = config.SHOCK_UNIT_COST if quarter >= 2 else config.START_UNIT_COST
    wage = shortage_wage() if quarter >= 6 else config.WAGE
    market_factor = config.RECESSION_FACTOR if quarter >= 7 else 1.0
    return {
        "quarter": quarter,
        "unit_cost": unit_cost,
        "wage": wage,
        "market_factor": market_factor,
        "market_size": int(round(state["market_size"] * market_factor)),
        "base_demand": state["base_demand"] * market_factor,
        "rent": config.RENT,
        "admin": config.ADMIN,
        "special_offer": quarter == 3,
        "investment_offer": quarter == 4 and not state["automation"],
        "strategy_choice": quarter == 8,
        "max_new_hires": config.MAX_HIRES_SHORTAGE if quarter == 6 else None,
        "new_employee_capacity": (
            config.SHORTAGE_NEW_CAPACITY if quarter == 6 else config.NEW_EMPLOYEE_CAPACITY
        ),
        "labor_shortage": quarter == 6,
    }


def _competition_factor(quarter: int, price: float) -> float:
    if quarter == 5:
        if price <= config.PRICE_WAR_LOW_THRESHOLD:
            return config.PRICE_WAR_LOW_FACTOR
        if price <= config.PRICE_WAR_MID_THRESHOLD:
            return config.PRICE_WAR_MID_FACTOR
        return config.PRICE_WAR_HIGH_FACTOR
    if quarter >= 6:
        if price <= config.PRICE_WAR_MID_THRESHOLD:
            return config.PRICE_WAR_LINGER_MATCHED
        return config.PRICE_WAR_LINGER_HIGH
    return 1.0


def _demand_factor(quarter: int, strategy: str | None) -> float:
    if quarter != 8:
        return 1.0
    if strategy == "vaekst":
        return config.GROWTH_DEMAND_FACTOR
    if strategy == "konsolidering":
        return config.CONSOLIDATION_DEMAND_FACTOR
    return 1.0


def _satisfaction_events(quarter: int, decisions: dict) -> tuple[float, float]:
    cs_delta = 0.0
    es_delta = 0.0
    price = _as_float(decisions.get("price"), config.START_PRICE)
    if quarter == 4 and decisions.get("invest") is True:
        es_delta += config.INVESTMENT_ES_DELTA
    if quarter == 5 and price > config.PRICE_WAR_CS_PRICE:
        cs_delta += config.PRICE_WAR_CS_PENALTY
    if quarter == 6:
        es_delta += config.SHORTAGE_ES_DELTA
    if quarter == 8 and decisions.get("strategy") == "vaekst":
        es_delta += config.GROWTH_ES_DELTA
    if quarter == 8 and decisions.get("strategy") == "konsolidering":
        cs_delta += config.CONSOLIDATION_CS_DELTA
        es_delta += config.CONSOLIDATION_ES_DELTA
    return cs_delta, es_delta


def build_context(state: dict, decisions: dict) -> dict:
    """Samlet regnegrundlag for ét kvartal."""
    facts = structural_conditions(state)
    quarter = facts["quarter"]
    price = _as_float(decisions.get("price"), config.START_PRICE)
    strategy = decisions.get("strategy")
    admin = facts["admin"]
    if quarter == 8 and strategy == "konsolidering":
        admin = round(config.ADMIN * config.CONSOLIDATION_ADMIN_FACTOR, 2)
    cs_event, es_event = _satisfaction_events(quarter, decisions)
    persist: dict = {}
    if quarter >= 2:
        persist["unit_cost"] = facts["unit_cost"]
    if quarter >= 5:
        persist["price_war"] = True
    if quarter >= 6:
        persist["wage"] = facts["wage"]
    if quarter >= 7:
        persist["recession"] = True
    return {
        **facts,
        "admin": admin,
        "other_operating": 0.0,
        "competition_factor": _competition_factor(quarter, price),
        "demand_factor": _demand_factor(quarter, strategy),
        "special_units": config.SPECIAL_UNITS if quarter == 3 else 0,
        "special_price": config.SPECIAL_PRICE if quarter == 3 else 0,
        "allow_investment": facts["investment_offer"],
        "investment_cost": config.INVESTMENT_COST,
        "cs_event": cs_event,
        "es_event": es_event,
        "noise": decisions.get("noise_override"),
        "persist": persist,
    }


def briefing(quarter: int) -> tuple[str, str]:
    """Overskrift og markdown til markedsbriefingen."""
    dep = _kr(depreciation_per_quarter())
    bonus = _n(config.AUTOMATION_CAPACITY_BONUS)
    if quarter == 1:
        title = "Normal drift"
        body = f"""
Java & Co. er en kaffekæde med {config.START_EMPLOYEES} medarbejdere. Markedet er
stabilt, og der er ingen særordre, priskrig eller investeringstilbud i dette kvartal.

Brug kvartalet til at kende sammenhængen mellem pris, kapacitet, lager og likviditet.

- Referencepris {_kr(config.REFERENCE_PRICE).replace(' kr.', '')} kr. og priselasticitet {_dec(config.PRICE_ELASTICITY)}.
- En erfaren medarbejder leverer {_n(config.EXPERIENCED_CAPACITY)} ordrer. En ny medarbejder leverer {_n(config.NEW_EMPLOYEE_CAPACITY)} i første kvartal.
- Salg kan ikke overstige efterspørgsel, kapacitet eller lager efter indkøb.
- Lageret er allerede betalt. Nye indkøb trækker på likviditeten med det samme, men rammer først resultatet som vareforbrug, når varerne sælges.
- Løn, husleje og administration er faste, når bemandingen er valgt. Marketing er en valgfri fast omkostning i kvartalet.
- Break-even i ordrer = faste omkostninger / dækningsbidrag pr. ordre.

Markedets støj er højst ±{_n(config.NOISE_MAX * 100)} %. Samme valg giver samme resultat.
"""
    elif quarter == 2:
        title = "Råvarepriserne stiger"
        body = f"""
Leverandørerne hæver prisen. Variable omkostninger på **nye indkøb** stiger fra
{_kr(config.START_UNIT_COST)} til **{_kr(config.SHOCK_UNIT_COST)}** pr. enhed. Prisen bliver på det niveau.

Lageret fra tidligere kvartaler beholder sin gamle kostpris. Den gennemsnitlige
kostpris i resultatopgørelsen bliver derfor et vægtet gennemsnit af gammelt og nyt lager.

Dækningsbidraget pr. ordre falder, hvis I ikke ændrer salgsprisen. Vurdér, om pris,
bemanding og indkøb stadig hænger sammen med break-even.
"""
    elif quarter == 3:
        title = "Tilbud om en stor kundeordre"
        body = f"""
En virksomhedskunde vil købe **{_n(config.SPECIAL_UNITS)} enheder til {_kr(config.SPECIAL_PRICE)} pr. enhed**.
I skal acceptere eller afvise ordren, før kvartalet køres.

- Ordren lægges oven i den ordinære efterspørgsel og har førsteret til kapacitet og lager.
- Enheder, I ikke kan levere, sælges ikke. Kundetilfredsheden falder med {_n(config.SPECIAL_SHORTFALL_CS_PENALTY)} point, hvis I accepterer og ikke leverer det hele.
- I kan afvise uden omkostning.
- Sammenlign ordreprisen med den variable kostpris og med dækningsbidraget på en ordinær ordre. En ordre med positivt dækningsbidrag er kun en fordel, hvis den bruger ledig kapacitet. Hvis den fortrænger ordinært salg, skal I sammenligne de to dækningsbidrag.
"""
    elif quarter == 4:
        title = "Mulighed for automatisering"
        body = f"""
En leverandør tilbyder automatisering af bar og bestilling.

- Investering: **{_kr(config.INVESTMENT_COST)}**, som trækkes fra likviditeten i dette kvartal.
- Afskrivning: **{dep} pr. kvartal** i {config.INVESTMENT_LIFE} kvartaler. Afskrivningen reducerer resultatet, ikke likviditeten.
- Kapacitet: **+{bonus} ordrer pr. medarbejder pr. kvartal**, både erfarne og nye. Gælder fra dette kvartal.
- Indkøbspris: **−{_kr(config.AUTOMATION_UNIT_COST_REDUCTION).replace(' kr.', '')} kr. pr. enhed** på nye indkøb.
- Medarbejdertilfredshed: {int(config.INVESTMENT_ES_DELTA)} point i dette kvartal, fordi arbejdet ændres.

Investeringen er kun nyttig, hvis den ekstra kapacitet kan sælges, eller besparelsen på indkøb dækker afskrivningen. I kan finansiere den med et lån. Renter beregnes af gælden ved kvartalets start, så et nyt lån først koster renter fra næste kvartal.
"""
    elif quarter == 5:
        title = "En konkurrent sænker priserne"
        body = f"""
En konkurrent sælger nu kaffe væsentligt billigere. Jeres efterspørgsel ganges med:

- **{_dec(config.PRICE_WAR_LOW_FACTOR)}**, hvis jeres pris er {_kr(config.PRICE_WAR_LOW_THRESHOLD)} eller lavere
- **{_dec(config.PRICE_WAR_MID_FACTOR)}**, hvis prisen er {_n(config.PRICE_WAR_LOW_THRESHOLD + 1)}–{_n(config.PRICE_WAR_MID_THRESHOLD)} kr.
- **{_dec(config.PRICE_WAR_HIGH_FACTOR)}**, hvis prisen er over {_kr(config.PRICE_WAR_MID_THRESHOLD)}

En pris over {_kr(config.PRICE_WAR_CS_PRICE)} koster desuden {_n(abs(config.PRICE_WAR_CS_PENALTY))} point kundetilfredshed i dette kvartal, oven i den almindelige priseffekt.

Fra næste kvartal er eftervirkningen mildere: faktor {_dec(config.PRICE_WAR_LINGER_MATCHED)} ved en pris på {_n(config.PRICE_WAR_MID_THRESHOLD)} kr. eller derunder, og {_dec(config.PRICE_WAR_LINGER_HIGH)} ved en højere pris.
"""
    elif quarter == 6:
        title = "Mangel på arbejdskraft"
        body = f"""
Det er svært at rekruttere.

- I kan **højst ansætte {config.MAX_HIRES_SHORTAGE} ny medarbejder** i dette kvartal. Opsigelser er stadig mulige.
- En ny medarbejder leverer kun **{_n(config.SHORTAGE_NEW_CAPACITY)} ordrer** i kvartalet, plus {_n(config.AUTOMATION_CAPACITY_BONUS)} hvis I har automatiseret.
- Lønnen stiger fra {_kr(config.WAGE)} til **{_kr(shortage_wage())} pr. medarbejder** og bliver på det niveau.
- Medarbejdertilfredsheden falder med {_n(abs(config.SHORTAGE_ES_DELTA))} point på grund af presset på arbejdsmarkedet.

Priskrigens eftervirkning fra kvartal 5 gælder stadig.
"""
    elif quarter == 7:
        title = "Konjunkturnedgang"
        body = f"""
Efterspørgslen i branchen falder. Både grundefterspørgsel og markedsstørrelse ganges med
**{_dec(config.RECESSION_FACTOR)}** i dette kvartal og igen i kvartal 8.

Ledig kapacitet bliver dyr, hvis bemandingen ikke tilpasses. Faste lønninger løber videre,
selv om ordrerne udebliver. Priskrigens eftervirkning gælder stadig.
"""
    elif quarter == 8:
        title = "Vækst eller konsolidering"
        body = f"""
Sidste kvartal. Konjunkturnedgangen gælder stadig (faktor {_dec(config.RECESSION_FACTOR)}),
og priskrigens eftervirkning gælder stadig. Jeres strategivalg lægges oveni.

**Vækst.** Efterspørgsel ganges med {_dec(config.GROWTH_DEMAND_FACTOR)}.
Medarbejdertilfredshed {int(config.GROWTH_ES_DELTA)} point. Væksten kræver kapacitet og lager.

**Konsolidering.** Efterspørgsel ganges med {_dec(config.CONSOLIDATION_DEMAND_FACTOR)}.
Kundetilfredshed +{_n(config.CONSOLIDATION_CS_DELTA)} point. Medarbejdertilfredshed +{_n(config.CONSOLIDATION_ES_DELTA)} point.
Administrationen falder med {_n((1 - config.CONSOLIDATION_ADMIN_FACTOR) * 100)} % i dette kvartal.

Vælg ud fra, om I har ledig kapacitet, stram likviditet eller brug for at genopbygge tilfredshed.
"""
    else:
        title = "Ukendt kvartal"
        body = "Der er ingen hændelse for dette kvartal."
    return title, body.strip()
