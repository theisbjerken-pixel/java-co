"""Spilmotor for Java & Co.

Alle centrale beregninger ligger her: efterspørgsel, kapacitet, salg,
resultat, likviditet, lager og tilfredshed. Streamlit-koden kalder kun
play_quarter, advance_quarter og decision_preview.
"""

from __future__ import annotations

import copy
import math
import random

import config
import events


class DecisionError(Exception):
    def __init__(self, messages: list[str]):
        self.messages = list(messages)
        super().__init__(" ".join(self.messages))


class QuarterAlreadyCompleted(Exception):
    pass


def initial_state() -> dict:
    return {
        "quarter": 1,
        "locked": False,
        "finished": False,
        "cash": float(config.START_CASH),
        "inventory_units": int(config.START_INVENTORY),
        "inventory_value": float(config.START_INVENTORY * config.START_UNIT_COST),
        "employee_tenures": [4] * config.START_EMPLOYEES,
        "debt": 0.0,
        "customer_satisfaction": float(config.START_CS),
        "employee_satisfaction": float(config.START_ES),
        "automation": False,
        "automation_gross": 0.0,
        "accumulated_depreciation": 0.0,
        "unit_cost": float(config.START_UNIT_COST),
        "wage": float(config.WAGE),
        "price_war": False,
        "recession": False,
        "base_demand": float(config.BASE_DEMAND),
        "market_size": float(config.MARKET_SIZE),
        "cumulative_result": 0.0,
        "history": [],
        "pending_report": None,
        "pending_decisions": None,
        "pending_budget": None,
    }


def price_effect(price: float) -> float:
    """(referencepris / valgt pris) ^ elasticitet."""
    if price <= 0:
        raise ValueError("Prisen skal være positiv.")
    return (config.REFERENCE_PRICE / price) ** config.PRICE_ELASTICITY


def marketing_effect(marketing: float) -> float:
    """1 + loft * (1 - exp(-marketing / skala)). Marginalvirkningen aftager."""
    if marketing < 0:
        raise ValueError("Marketing kan ikke være negativ.")
    lift = config.MARKETING_MAX_LIFT * (1.0 - math.exp(-marketing / config.MARKETING_SCALE))
    return 1.0 + lift


def satisfaction_effect(customer_satisfaction: float) -> float:
    return config.CS_FACTOR_BASE + config.CS_FACTOR_SLOPE * (
        customer_satisfaction / config.SAT_REFERENCE
    )


def service_effect(employee_satisfaction: float) -> float:
    return config.ES_FACTOR_BASE + config.ES_FACTOR_SLOPE * (
        employee_satisfaction / config.SAT_REFERENCE
    )


def quarter_noise(quarter: int) -> float:
    rng = random.Random(config.RANDOM_SEED + quarter * 997)
    return rng.uniform(-config.NOISE_MAX, config.NOISE_MAX)


def demand_components(
    *,
    base_demand: float,
    market_size: float,
    price: float,
    marketing: float,
    customer_satisfaction: float,
    employee_satisfaction: float,
    market_factor: float = 1.0,
    demand_factor: float = 1.0,
    competition_factor: float = 1.0,
    noise: float = 0.0,
) -> dict:
    pe = price_effect(price)
    me = marketing_effect(marketing)
    ce = satisfaction_effect(customer_satisfaction)
    se = service_effect(employee_satisfaction)
    effective_market = int(round(market_size * market_factor))
    core = (
        base_demand
        * market_factor
        * demand_factor
        * competition_factor
        * pe
        * me
        * ce
        * se
        * (1.0 + noise)
    )
    regular = int(round(min(max(0.0, core), effective_market)))
    return {
        "regular_demand": regular,
        "effective_market": effective_market,
        "price_effect": pe,
        "marketing_effect": me,
        "satisfaction_effect": ce,
        "service_effect": se,
        "market_factor": market_factor,
        "demand_factor": demand_factor,
        "competition_factor": competition_factor,
        "noise": noise,
    }


def compute_demand(**kwargs) -> int:
    return demand_components(**kwargs)["regular_demand"]


def capacity_of(tenure: int, *, automated: bool, new_employee_capacity: int) -> int:
    base = new_employee_capacity if tenure <= 0 else config.EXPERIENCED_CAPACITY
    if automated:
        base += config.AUTOMATION_CAPACITY_BONUS
    return int(base)


def total_capacity(tenures: list[int], *, automated: bool, new_employee_capacity: int) -> int:
    return sum(
        capacity_of(tenure, automated=automated, new_employee_capacity=new_employee_capacity)
        for tenure in tenures
    )


def project_workforce(
    tenures: list[int], target: int, max_new_hires: int | None
) -> tuple[list[int], int, list[int]] | None:
    """Returner (ny liste, ansættelser, opsagte ancienniteter). None ved for mange ansættelser."""
    current = len(tenures)
    if target > current:
        hires = target - current
        if max_new_hires is not None and hires > max_new_hires:
            return None
        return list(tenures) + [0] * hires, hires, []
    if target < current:
        fires = current - target
        order = sorted(range(current), key=lambda index: (tenures[index], -index))
        remove = set(order[:fires])
        fired = [tenures[index] for index in range(current) if index in remove]
        kept = [tenure for index, tenure in enumerate(tenures) if index not in remove]
        return kept, 0, fired
    return list(tenures), 0, []


def _number(value, label: str) -> tuple[float | None, str | None]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{label} skal være et tal."
    if not math.isfinite(number):
        return None, f"{label} skal være et tal."
    return number, None


def validate_decisions(state: dict, decisions: dict, context: dict) -> list[str]:
    errors: list[str] = []
    price, price_error = _number(decisions.get("price"), "Salgsprisen")
    if price_error:
        errors.append(price_error)
    elif price < config.PRICE_MIN or price > config.PRICE_MAX:
        errors.append(
            f"Salgsprisen skal ligge mellem {config.PRICE_MIN} og {config.PRICE_MAX} kr."
        )

    marketing, marketing_error = _number(decisions.get("marketing"), "Marketingbudgettet")
    if marketing_error:
        errors.append(marketing_error)
    elif marketing < config.MARKETING_MIN or marketing > config.MARKETING_MAX:
        errors.append("Marketingbudgettet skal ligge mellem 0 og 300.000 kr.")

    employees, employees_error = _number(decisions.get("employees"), "Antal medarbejdere")
    if employees_error:
        errors.append(employees_error)
    elif (
        employees < config.EMPLOYEES_MIN
        or employees > config.EMPLOYEES_MAX
        or not float(employees).is_integer()
    ):
        errors.append(
            f"Antal medarbejdere skal være et helt tal mellem {config.EMPLOYEES_MIN} og {config.EMPLOYEES_MAX}."
        )
    else:
        projected = project_workforce(
            state["employee_tenures"], int(employees), context.get("max_new_hires")
        )
        if projected is None:
            errors.append(
                "Der er mangel på arbejdskraft. I kan højst ansætte "
                f"{config.MAX_HIRES_SHORTAGE} ny medarbejder i dette kvartal."
            )

    purchases, purchases_error = _number(decisions.get("purchases"), "Indkøb")
    if purchases_error:
        errors.append(purchases_error)
    elif purchases < 0 or purchases > config.PURCHASES_MAX or not float(purchases).is_integer():
        errors.append(
            f"Indkøb skal være et helt tal mellem 0 og {config.PURCHASES_MAX:,} enheder.".replace(
                ",", "."
            )
        )

    loan, loan_error = _number(decisions.get("loan_draw"), "Lånebeløbet")
    if loan_error:
        errors.append(loan_error)
    elif loan < 0 or loan > config.MAX_LOAN_DRAW:
        errors.append(
            f"Lånebeløbet skal ligge mellem 0 og {config.MAX_LOAN_DRAW:,} kr.".replace(",", ".")
        )

    repayment, repayment_error = _number(decisions.get("repayment"), "Afdrag")
    if repayment_error:
        errors.append(repayment_error)
    elif repayment < 0:
        errors.append("Afdrag kan ikke være negativt.")
    elif repayment > state["debt"] + 0.001:
        errors.append("I kan ikke afdrage mere end den nuværende gæld.")

    if loan is not None and repayment is not None and loan >= 0 and 0 <= repayment <= state["debt"] + 0.001:
        new_debt = state["debt"] + loan - repayment
        if new_debt > config.MAX_DEBT:
            errors.append("Gælden kan højst være 3.000.000 kr.")

    invest = decisions.get("invest")
    if context["allow_investment"]:
        if invest is None:
            errors.append("I skal vælge, om I vil investere i automatisering.")
    elif invest:
        errors.append("Investering er ikke mulig i dette kvartal.")

    accept = decisions.get("accept_special")
    if context["special_units"] > 0:
        if accept is None:
            errors.append("I skal vælge, om kundeordren accepteres eller afvises.")
    elif accept:
        errors.append("Kundeordren kan kun besvares i kvartal 3.")

    strategy = decisions.get("strategy")
    if state["quarter"] == 8:
        if strategy not in ("vaekst", "konsolidering"):
            errors.append("I skal vælge vækst eller konsolidering i kvartal 8.")
    elif strategy not in (None, ""):
        errors.append("Strategivalget findes kun i kvartal 8.")
    return errors


def validate_budget(budget: dict) -> list[str]:
    errors: list[str] = []
    parsed: dict[str, float] = {}
    labels = {
        "volume": "Budgetteret afsætning",
        "revenue": "Budgetteret omsætning",
        "contribution": "Budgetteret dækningsbidrag",
        "result": "Budgetteret resultat",
        "ending_cash": "Budgetteret slutlikviditet",
    }
    for key, label in labels.items():
        number, error = _number(budget.get(key), label)
        if error or number is None:
            errors.append(error or f"{label} mangler.")
            continue
        if abs(number) > config.BUDGET_ABS_MAX:
            errors.append(f"{label} er urealistisk højt.")
            continue
        parsed[key] = number
    if "volume" in parsed and parsed["volume"] < 0:
        errors.append("Budgetteret afsætning kan ikke være negativ.")
    if "revenue" in parsed and parsed["revenue"] < 0:
        errors.append("Budgetteret omsætning kan ikke være negativ.")
    if parsed and all(abs(parsed.get(key, 1)) < 0.001 for key in labels):
        errors.append(
            "Udfyld budgettet, før I gennemfører kvartalet. I må gerne forvente underskud, men 0 i alle felter tæller ikke som et budget."
        )
    return errors


def validate_reflection(reflection: dict) -> list[str]:
    labels = {
        "expected": "Hvad gik som forventet?",
        "deviation": "Hvad var den vigtigste afvigelse?",
        "cause": "Hvad vurderer du var årsagen?",
        "next_change": "Hvad vil du ændre næste kvartal?",
    }
    errors = []
    for key, label in labels.items():
        text = str(reflection.get(key, "")).strip()
        if len(text) < config.REFLECTION_MIN_CHARS:
            errors.append(f"Svar på spørgsmålet: {label}")
    return errors


def _purchase_price(unit_cost: float, automated: bool) -> float:
    price = unit_cost - (config.AUTOMATION_UNIT_COST_REDUCTION if automated else 0.0)
    return max(config.MIN_UNIT_COST, price)


def _satisfaction_deltas(
    *,
    price: float,
    demand: int,
    sales: int,
    capacity: int,
    hires: int,
    fired: list[int],
    accept_special: bool,
    special_units: int,
    sales_special: int,
) -> tuple[float, float]:
    d_cs = (config.REFERENCE_PRICE - price) * config.CS_PRICE_SLOPE
    lost = demand - sales
    if demand > 0 and lost > 0:
        d_cs -= config.CS_LOST_SALES_WEIGHT * (lost / demand)
    d_es = 0.0
    if capacity > 0:
        utilisation = sales / capacity
        if utilisation > config.HIGH_UTILISATION:
            d_cs -= config.CS_HIGH_UTIL_PENALTY
            d_es -= config.ES_HIGH_UTIL_PENALTY
        elif utilisation < config.LOW_UTILISATION:
            d_es -= config.ES_LOW_UTIL_PENALTY
        elif not fired and config.STABLE_UTIL_LOW <= utilisation <= config.STABLE_UTIL_HIGH:
            d_es += config.ES_STABLE_BONUS
    for tenure in fired:
        d_es -= config.ES_FIRE_EXPERIENCED if tenure >= 1 else config.ES_FIRE_NEW
    if hires >= config.HIRE_STRESS_HEAVY_FROM:
        d_es -= config.ES_HIRE_STRESS_4
    elif hires >= config.HIRE_STRESS_FROM:
        d_es -= config.ES_HIRE_STRESS_2
    if accept_special and special_units > 0 and sales_special < special_units:
        d_cs -= config.SPECIAL_SHORTFALL_CS_PENALTY
    return d_cs, d_es


def _clamp_score(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 1)


def settle_quarter(state: dict, decisions: dict, context: dict) -> tuple[dict, dict]:
    new = copy.deepcopy(state)
    opening_cash = float(new["cash"])
    opening_debt = float(new["debt"])
    opening_units = int(new["inventory_units"])
    opening_value = float(new["inventory_value"])
    opening_gross = float(new["automation_gross"])
    opening_accum = float(new["accumulated_depreciation"])
    opening_book = round(opening_gross - opening_accum, 2)
    opening_cs = float(new["customer_satisfaction"])
    opening_es = float(new["employee_satisfaction"])

    price = int(round(float(decisions["price"])))
    marketing = int(round(float(decisions["marketing"])))
    purchases = int(round(float(decisions["purchases"])))
    loan_draw = int(round(float(decisions["loan_draw"])))
    repayment = int(round(float(decisions["repayment"])))
    invest = bool(decisions["invest"])
    accept_special = bool(decisions["accept_special"])
    strategy = decisions.get("strategy")

    projected, hires, fired = project_workforce(
        new["employee_tenures"], int(round(float(decisions["employees"]))), context.get("max_new_hires")
    )
    if projected is None:
        raise DecisionError(["Bemandingens ændring er ikke tilladt i dette kvartal."])

    automated = bool(new["automation"] or invest)
    purchase_unit_cost = _purchase_price(float(context["unit_cost"]), automated)
    purchase_cost = round(purchases * purchase_unit_cost, 2)
    available = opening_units + purchases
    capacity = total_capacity(
        projected,
        automated=automated,
        new_employee_capacity=int(context["new_employee_capacity"]),
    )

    noise = context.get("noise")
    if noise is None:
        noise = quarter_noise(int(new["quarter"]))
    components = demand_components(
        base_demand=float(new["base_demand"]),
        market_size=float(new["market_size"]),
        price=price,
        marketing=marketing,
        customer_satisfaction=opening_cs,
        employee_satisfaction=opening_es,
        market_factor=float(context["market_factor"]),
        demand_factor=float(context["demand_factor"]),
        competition_factor=float(context["competition_factor"]),
        noise=float(noise),
    )
    regular_demand = int(components["regular_demand"])
    special_units = int(context["special_units"]) if accept_special else 0
    demand = regular_demand + special_units
    sales = min(demand, capacity, available)
    sales_special = min(special_units, sales)
    sales_regular = sales - sales_special
    lost_to_capacity = max(0, demand - capacity)
    lost_to_inventory = max(0, min(demand, capacity) - available)

    if available == 0:
        avg_cost = purchase_unit_cost
        variable_costs = 0.0
        ending_units = 0
        ending_value = 0.0
    else:
        total_value = opening_value + purchase_cost
        avg_cost = total_value / available
        ending_units = available - sales
        if ending_units == 0:
            variable_costs = round(total_value, 2)
            ending_value = 0.0
        else:
            variable_costs = round(sales * avg_cost, 2)
            ending_value = round(total_value - variable_costs, 2)

    regular_revenue = round(sales_regular * price, 2)
    special_price = float(context["special_price"]) if accept_special else 0.0
    special_revenue = round(sales_special * special_price, 2)
    revenue = round(regular_revenue + special_revenue, 2)
    contribution = round(revenue - variable_costs, 2)

    wages = round(float(context["wage"]) * len(projected), 2)
    rent = round(float(context["rent"]), 2)
    admin = round(float(context["admin"]), 2)
    other = round(float(context.get("other_operating", 0.0)), 2)
    result_before = round(contribution - wages - marketing - rent - admin - other, 2)

    gross = opening_gross + (config.INVESTMENT_COST if invest else 0.0)
    investment_cost = float(config.INVESTMENT_COST if invest else 0.0)
    remaining_book = round(gross - opening_accum, 2)
    if remaining_book > 0:
        scheduled = round(config.INVESTMENT_COST / config.INVESTMENT_LIFE, 2)
        depreciation = min(scheduled, remaining_book)
    else:
        depreciation = 0.0
    accumulated = round(opening_accum + depreciation, 2)
    ending_book = round(gross - accumulated, 2)

    interest_loan = round(opening_debt * config.LOAN_RATE_QUARTER, 2)
    interest_overdraft = round(max(0.0, -opening_cash) * config.OVERDRAFT_RATE_QUARTER, 2)
    interest = round(interest_loan + interest_overdraft, 2)
    period_result = round(result_before - depreciation - interest, 2)

    # Afskrivning trækkes ikke her. Vareforbrug trækkes ikke her, fordi varerne
    # er betalt ved indkøb. Lån og afdrag påvirker kun likviditeten.
    ending_cash = round(
        opening_cash
        + revenue
        - purchase_cost
        - wages
        - marketing
        - rent
        - admin
        - other
        - interest
        + loan_draw
        - repayment
        - investment_cost,
        2,
    )
    ending_debt = round(opening_debt + loan_draw - repayment, 2)

    d_cs, d_es = _satisfaction_deltas(
        price=price,
        demand=demand,
        sales=sales,
        capacity=capacity,
        hires=hires,
        fired=fired,
        accept_special=accept_special,
        special_units=special_units,
        sales_special=sales_special,
    )
    ending_cs = _clamp_score(opening_cs + d_cs + float(context["cs_event"]))
    ending_es = _clamp_score(opening_es + d_es + float(context["es_event"]))

    if ending_units < 0 or sales > demand or sales > capacity or sales > available:
        raise RuntimeError("Intern fejl i salgsbegrænsningerne.")

    experienced = sum(1 for tenure in projected if tenure >= 1)
    cm_ordinary = price - avg_cost
    fixed_operating = wages + marketing + rent + admin + other
    fixed_full = fixed_operating + depreciation + interest
    break_even = fixed_operating / cm_ordinary if cm_ordinary > 0 else None
    break_even_full = fixed_full / cm_ordinary if cm_ordinary > 0 else None
    market_size = int(components["effective_market"])

    new["cash"] = ending_cash
    new["debt"] = ending_debt
    new["inventory_units"] = ending_units
    new["inventory_value"] = ending_value
    new["employee_tenures"] = [tenure + 1 for tenure in projected]
    new["automation"] = automated
    new["automation_gross"] = gross
    new["accumulated_depreciation"] = accumulated
    new["customer_satisfaction"] = ending_cs
    new["employee_satisfaction"] = ending_es
    new["cumulative_result"] = round(float(new["cumulative_result"]) + period_result, 2)
    for key, value in context.get("persist", {}).items():
        new[key] = value

    report = {
        "quarter": int(new["quarter"]),
        "price": price,
        "marketing": marketing,
        "employees": len(projected),
        "experienced_employees": experienced,
        "new_employees": len(projected) - experienced,
        "hires": hires,
        "fires": len(fired),
        "fired_experienced": sum(1 for tenure in fired if tenure >= 1),
        "purchases": purchases,
        "purchase_unit_cost": purchase_unit_cost,
        "purchase_cost": purchase_cost,
        "avg_cost": avg_cost,
        "loan_draw": loan_draw,
        "repayment": repayment,
        "invest": invest,
        "investment_cost": investment_cost,
        "accept_special": accept_special,
        "strategy": strategy,
        "automation": automated,
        "unit_cost": float(context["unit_cost"]),
        "regular_demand": regular_demand,
        "special_demand": special_units,
        "demand": demand,
        "capacity": capacity,
        "available_inventory": available,
        "sales": sales,
        "sales_regular": sales_regular,
        "sales_special": sales_special,
        "lost_sales": demand - sales,
        "lost_to_capacity": lost_to_capacity,
        "lost_to_inventory": lost_to_inventory,
        "opening_inventory_units": opening_units,
        "ending_inventory_units": ending_units,
        "opening_inventory_value": opening_value,
        "ending_inventory_value": ending_value,
        "opening_cash": opening_cash,
        "ending_cash": ending_cash,
        "opening_debt": opening_debt,
        "ending_debt": ending_debt,
        "opening_book_value": opening_book,
        "ending_book_value": ending_book,
        "revenue": revenue,
        "regular_revenue": regular_revenue,
        "special_revenue": special_revenue,
        "variable_costs": variable_costs,
        "contribution": contribution,
        "wages": wages,
        "rent": rent,
        "admin": admin,
        "other_operating": other,
        "result_before_depreciation": result_before,
        "depreciation": depreciation,
        "interest_loan": interest_loan,
        "interest_overdraft": interest_overdraft,
        "interest": interest,
        "period_result": period_result,
        "db_per_order": (contribution / sales) if sales else None,
        "ordinary_cm": cm_ordinary,
        "dg": (contribution / revenue) if revenue else None,
        "break_even_volume": break_even,
        "break_even_volume_full": break_even_full,
        "capacity_utilization": (sales / capacity) if capacity else None,
        "market_share": (sales / market_size) if market_size else None,
        "market_size": market_size,
        "customer_satisfaction": ending_cs,
        "employee_satisfaction": ending_es,
        "customer_satisfaction_start": opening_cs,
        "employee_satisfaction_start": opening_es,
        "cs_delta": round(ending_cs - opening_cs, 1),
        "es_delta": round(ending_es - opening_es, 1),
        "noise": float(noise),
        "factors": {
            "price_effect": components["price_effect"],
            "marketing_effect": components["marketing_effect"],
            "satisfaction_effect": components["satisfaction_effect"],
            "service_effect": components["service_effect"],
            "market_factor": components["market_factor"],
            "demand_factor": components["demand_factor"],
            "competition_factor": components["competition_factor"],
            "noise": float(noise),
        },
        "cumulative_result": new["cumulative_result"],
        "wage_per_employee": float(context["wage"]),
    }
    return new, report


def _plain_decisions(decisions: dict) -> dict:
    return {
        "price": int(round(float(decisions["price"]))),
        "marketing": int(round(float(decisions["marketing"]))),
        "employees": int(round(float(decisions["employees"]))),
        "purchases": int(round(float(decisions["purchases"]))),
        "loan_draw": int(round(float(decisions["loan_draw"]))),
        "repayment": int(round(float(decisions["repayment"]))),
        "invest": bool(decisions["invest"]),
        "accept_special": bool(decisions["accept_special"]),
        "strategy": decisions.get("strategy"),
    }


def _plain_budget(budget: dict) -> dict:
    return {
        "volume": float(budget["volume"]),
        "revenue": float(budget["revenue"]),
        "contribution": float(budget["contribution"]),
        "result": float(budget["result"]),
        "ending_cash": float(budget["ending_cash"]),
    }


def play_quarter(state: dict, decisions: dict, budget: dict) -> tuple[dict, dict]:
    if state.get("finished"):
        raise QuarterAlreadyCompleted("Spillet er afsluttet.")
    if state.get("locked"):
        raise QuarterAlreadyCompleted("Dette kvartal er allerede gennemført.")
    context = events.build_context(state, decisions)
    errors = validate_decisions(state, decisions, context) + validate_budget(budget)
    if errors:
        raise DecisionError(errors)
    new_state, report = settle_quarter(state, decisions, context)
    new_state["locked"] = True
    new_state["pending_report"] = report
    new_state["pending_decisions"] = _plain_decisions(decisions)
    new_state["pending_budget"] = _plain_budget(budget)
    return new_state, report


def advance_quarter(state: dict, reflection: dict) -> dict:
    if state.get("finished"):
        raise QuarterAlreadyCompleted("Spillet er afsluttet.")
    if not state.get("locked"):
        raise DecisionError(["Kvartalet er ikke gennemført endnu."])
    errors = validate_reflection(reflection)
    if errors:
        raise DecisionError(errors)
    new = copy.deepcopy(state)
    new["history"].append(
        {
            "quarter": new["quarter"],
            "decisions": new["pending_decisions"],
            "budget": new["pending_budget"],
            "report": new["pending_report"],
            "reflection": {
                key: str(reflection.get(key, "")).strip() for key in config.REFLECTION_KEYS
            },
        }
    )
    new["pending_report"] = None
    new["pending_decisions"] = None
    new["pending_budget"] = None
    new["locked"] = False
    if new["quarter"] >= config.QUARTERS:
        new["finished"] = True
    else:
        new["quarter"] += 1
    return new


def decision_preview(state: dict, decisions: dict) -> dict:
    """Cost- og kapacitetstal til regnehjælpen. Indeholder ikke efterspørgslen."""
    context = events.build_context(state, decisions)
    errors = validate_decisions(state, decisions, context)
    employees_raw = decisions.get("employees")
    try:
        target = int(round(float(employees_raw)))
    except (TypeError, ValueError):
        target = len(state["employee_tenures"])
    if target < config.EMPLOYEES_MIN or target > config.EMPLOYEES_MAX:
        projected = None
    else:
        projected = project_workforce(
            state["employee_tenures"], target, context.get("max_new_hires")
        )
    invest = decisions.get("invest") is True
    automated = bool(state["automation"] or (invest and context["allow_investment"]))
    if projected is None:
        tenures = list(state["employee_tenures"])
        hires = 0
        fired: list[int] = []
        capacity = None
    else:
        tenures, hires, fired = projected
        capacity = total_capacity(
            tenures,
            automated=automated,
            new_employee_capacity=int(context["new_employee_capacity"]),
        )
    experienced = sum(1 for tenure in tenures if tenure >= 1)
    new_employees = len(tenures) - experienced
    purchase_price = _purchase_price(float(context["unit_cost"]), automated)
    try:
        price = float(decisions.get("price"))
    except (TypeError, ValueError):
        price = config.START_PRICE
    try:
        marketing = float(decisions.get("marketing"))
    except (TypeError, ValueError):
        marketing = 0.0
    try:
        purchases = float(decisions.get("purchases"))
    except (TypeError, ValueError):
        purchases = 0.0
    wages = float(context["wage"]) * len(tenures)
    fixed = wages + marketing + float(context["rent"]) + float(context["admin"])
    cm = price - purchase_price
    if invest and context["allow_investment"]:
        gross = float(state["automation_gross"]) + config.INVESTMENT_COST
    else:
        gross = float(state["automation_gross"])
    remaining = gross - float(state["accumulated_depreciation"])
    if remaining > 0:
        depreciation = min(config.INVESTMENT_COST / config.INVESTMENT_LIFE, remaining)
    else:
        depreciation = 0.0
    interest = state["debt"] * config.LOAN_RATE_QUARTER + max(0.0, -state["cash"]) * config.OVERDRAFT_RATE_QUARTER
    return {
        "errors": errors,
        "purchase_price": purchase_price,
        "cm_per_order": cm,
        "capacity": capacity,
        "experienced": experienced,
        "new_employees": new_employees,
        "experienced_capacity": capacity_of(
            1, automated=automated, new_employee_capacity=int(context["new_employee_capacity"])
        ),
        "new_capacity": capacity_of(
            0, automated=automated, new_employee_capacity=int(context["new_employee_capacity"])
        ),
        "hires": hires,
        "fires": len(fired),
        "wages": wages,
        "fixed_costs": fixed,
        "break_even": (fixed / cm) if cm > 0 else None,
        "purchase_cash": max(0.0, purchases) * purchase_price,
        "interest": interest,
        "depreciation": depreciation,
        "competition_factor": context["competition_factor"],
        "demand_factor": context["demand_factor"],
        "market_factor": context["market_factor"],
        "admin": context["admin"],
    }
