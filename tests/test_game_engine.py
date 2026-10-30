"""Tests af spilmotoren."""

from __future__ import annotations

import copy

import pytest

import config
import game_engine
import reporting


def budget() -> dict:
    return {
        "volume": 10_000,
        "revenue": 500_000,
        "contribution": 200_000,
        "result": -50_000,
        "ending_cash": 400_000,
    }


def reflection() -> dict:
    return {
        "expected": "Vi forventede et mindre underskud.",
        "deviation": "Afvigelsen lå især i afsætningen.",
        "cause": "Prisen ramte efterspørgslen hårdere end ventet.",
        "next_change": "Vi justerer pris og indkøb næste kvartal.",
    }


def decisions(**overrides) -> dict:
    base = {
        "price": 50,
        "marketing": 0,
        "employees": config.START_EMPLOYEES,
        "purchases": config.DEFAULT_PURCHASES,
        "loan_draw": 0,
        "repayment": 0,
        "invest": False,
        "accept_special": False,
        "strategy": None,
    }
    base.update(overrides)
    return base


def assert_integrity(report: dict) -> None:
    assert report["ending_inventory_units"] >= 0
    assert report["sales"] <= report["demand"]
    assert report["sales"] <= report["capacity"]
    assert report["sales"] <= report["available_inventory"]
    assert report["sales"] == min(
        report["demand"], report["capacity"], report["available_inventory"]
    )
    assert report["lost_sales"] == report["demand"] - report["sales"]
    contribution = report["revenue"] - report["variable_costs"]
    assert report["contribution"] == pytest.approx(contribution, abs=0.05)
    before = (
        report["contribution"]
        - report["wages"]
        - report["marketing"]
        - report["rent"]
        - report["admin"]
        - report["other_operating"]
    )
    assert report["result_before_depreciation"] == pytest.approx(before, abs=0.05)
    result = before - report["depreciation"] - report["interest"]
    assert report["period_result"] == pytest.approx(result, abs=0.05)
    bridge = (
        report["period_result"]
        + report["depreciation"]
        + report["variable_costs"]
        - report["purchase_cost"]
        + report["loan_draw"]
        - report["repayment"]
        - report["investment_cost"]
    )
    assert report["ending_cash"] - report["opening_cash"] == pytest.approx(bridge, abs=0.05)
    opening_equity = (
        report["opening_cash"]
        + report["opening_inventory_value"]
        + report["opening_book_value"]
        - report["opening_debt"]
    )
    ending_equity = (
        report["ending_cash"]
        + report["ending_inventory_value"]
        + report["ending_book_value"]
        - report["ending_debt"]
    )
    assert ending_equity == pytest.approx(opening_equity + report["period_result"], abs=0.05)


def test_cost_parameters_match_the_brief():
    assert config.START_CASH == 500_000
    assert config.START_PRICE == 50
    assert config.START_UNIT_COST == 19
    assert config.WAGE == 95_000
    assert config.RENT == 150_000
    assert config.ADMIN == 55_000
    assert config.START_EMPLOYEES == 6
    assert config.START_CS == 70
    assert config.START_ES == 70
    assert config.REFERENCE_PRICE == 50
    assert config.PRICE_ELASTICITY == 1.4


def test_volume_scale_keeps_the_brief_ratios():
    assert config.EXPERIENCED_CAPACITY == config.BRIEF_EXPERIENCED_CAPACITY * config.VOLUME_SCALE
    assert config.NEW_EMPLOYEE_CAPACITY == config.BRIEF_NEW_CAPACITY * config.VOLUME_SCALE
    assert config.BASE_DEMAND == config.BRIEF_BASE_DEMAND * config.VOLUME_SCALE
    assert config.MARKET_SIZE == config.BRIEF_MARKET_SIZE * config.VOLUME_SCALE
    assert config.START_INVENTORY == config.BRIEF_START_INVENTORY * config.VOLUME_SCALE


def test_reference_price_has_neutral_effect():
    assert game_engine.price_effect(50) == pytest.approx(1.0)


def test_higher_price_lowers_demand():
    low = game_engine.compute_demand(
        base_demand=config.BASE_DEMAND,
        market_size=config.MARKET_SIZE,
        price=40,
        marketing=0,
        customer_satisfaction=70,
        employee_satisfaction=70,
        noise=0,
    )
    high = game_engine.compute_demand(
        base_demand=config.BASE_DEMAND,
        market_size=config.MARKET_SIZE,
        price=65,
        marketing=0,
        customer_satisfaction=70,
        employee_satisfaction=70,
        noise=0,
    )
    assert high < low

    _, simulated_low = game_engine.play_quarter(game_engine.initial_state(), decisions(price=40), budget())
    _, simulated_high = game_engine.play_quarter(game_engine.initial_state(), decisions(price=65), budget())
    assert simulated_high["regular_demand"] < simulated_low["regular_demand"]


def test_marketing_increases_demand_with_diminishing_effect():
    effect_0 = game_engine.marketing_effect(0)
    effect_1 = game_engine.marketing_effect(100_000)
    effect_2 = game_engine.marketing_effect(200_000)
    effect_3 = game_engine.marketing_effect(300_000)
    assert effect_1 - effect_0 > effect_2 - effect_1 > effect_3 - effect_2 > 0

    _, none = game_engine.play_quarter(game_engine.initial_state(), decisions(marketing=0), budget())
    _, mid = game_engine.play_quarter(game_engine.initial_state(), decisions(marketing=100_000), budget())
    _, high = game_engine.play_quarter(game_engine.initial_state(), decisions(marketing=200_000), budget())
    assert mid["regular_demand"] > none["regular_demand"]
    assert mid["regular_demand"] - none["regular_demand"] > high["regular_demand"] - mid["regular_demand"] > 0


def test_sales_respect_capacity_limit():
    _, report = game_engine.play_quarter(
        game_engine.initial_state(),
        decisions(price=35, marketing=300_000, employees=3, purchases=100_000),
        budget(),
    )
    assert report["capacity"] == 3 * config.EXPERIENCED_CAPACITY
    assert report["demand"] > report["capacity"]
    assert report["sales"] == report["capacity"]
    assert report["ending_inventory_units"] >= 0


def test_sales_respect_inventory_limit_and_inventory_cannot_be_negative():
    state = game_engine.initial_state()
    state["inventory_units"] = 500
    state["inventory_value"] = 500 * config.START_UNIT_COST
    _, report = game_engine.play_quarter(
        state,
        decisions(price=35, marketing=300_000, purchases=0),
        budget(),
    )
    assert report["sales"] == 500
    assert report["sales"] < report["demand"]
    assert report["sales"] <= report["capacity"]
    assert report["ending_inventory_units"] == 0


def test_new_employees_have_lower_capacity_until_next_quarter():
    _, hired = game_engine.play_quarter(
        game_engine.initial_state(),
        decisions(employees=config.START_EMPLOYEES + 1),
        budget(),
    )
    expected = (
        config.START_EMPLOYEES * config.EXPERIENCED_CAPACITY
        + config.NEW_EMPLOYEE_CAPACITY
    )
    assert hired["hires"] == 1
    assert hired["capacity"] == expected

    state = game_engine.initial_state()
    updated, _ = game_engine.play_quarter(state, decisions(employees=7), budget())
    updated = game_engine.advance_quarter(updated, reflection())
    assert all(tenure >= 1 for tenure in updated["employee_tenures"])
    _, next_quarter = game_engine.play_quarter(updated, decisions(employees=7), budget())
    assert next_quarter["capacity"] == 7 * config.EXPERIENCED_CAPACITY


def test_loan_increases_liquidity_but_not_profit():
    _, without = game_engine.play_quarter(game_engine.initial_state(), decisions(loan_draw=0), budget())
    _, with_loan = game_engine.play_quarter(
        game_engine.initial_state(), decisions(loan_draw=200_000), budget()
    )
    assert with_loan["ending_cash"] - without["ending_cash"] == pytest.approx(200_000, abs=0.05)
    assert with_loan["ending_debt"] - without["ending_debt"] == pytest.approx(200_000, abs=0.05)
    assert with_loan["period_result"] == pytest.approx(without["period_result"], abs=0.05)


def test_repayment_reduces_liquidity_but_not_profit():
    without_debt = game_engine.initial_state()
    without_debt["debt"] = 100_000
    with_repayment = copy.deepcopy(without_debt)
    _, kept = game_engine.play_quarter(without_debt, decisions(repayment=0), budget())
    _, repaid = game_engine.play_quarter(with_repayment, decisions(repayment=40_000), budget())
    assert kept["period_result"] == pytest.approx(repaid["period_result"], abs=0.05)
    assert kept["ending_cash"] - repaid["ending_cash"] == pytest.approx(40_000, abs=0.05)
    assert kept["ending_debt"] - repaid["ending_debt"] == pytest.approx(40_000, abs=0.05)


def test_investment_reduces_cash_and_depreciation_reduces_profit_only():
    def prepared() -> dict:
        state = game_engine.initial_state()
        state["quarter"] = 4
        state["cash"] = 1_000_000
        state["inventory_units"] = 100_000
        state["inventory_value"] = 100_000 * config.START_UNIT_COST
        state["employee_tenures"] = [4] * 12
        return state

    common = dict(price=70, marketing=0, employees=12, purchases=0, loan_draw=0, repayment=0)
    _, skipped = game_engine.play_quarter(prepared(), decisions(**common, invest=False), budget())
    _, invested = game_engine.play_quarter(prepared(), decisions(**common, invest=True), budget())
    assert skipped["sales"] == invested["sales"]
    assert skipped["demand"] == invested["demand"]
    cash_gap = skipped["ending_cash"] - invested["ending_cash"]
    result_gap = skipped["period_result"] - invested["period_result"]
    assert cash_gap == pytest.approx(config.INVESTMENT_COST, abs=0.05)
    assert result_gap == pytest.approx(invested["depreciation"], abs=0.05)
    assert invested["depreciation"] == pytest.approx(config.INVESTMENT_COST / config.INVESTMENT_LIFE)
    assert cash_gap > result_gap


def test_same_input_and_seed_give_the_same_result():
    state = game_engine.initial_state()
    choice = decisions(price=54, marketing=40_000, purchases=18_000)
    _, first = game_engine.play_quarter(state, choice, budget())
    _, second = game_engine.play_quarter(state, choice, budget())
    assert first["sales"] == second["sales"]
    assert first["revenue"] == second["revenue"]
    assert first["period_result"] == second["period_result"]
    assert first["ending_cash"] == second["ending_cash"]
    assert state["cash"] == config.START_CASH
    assert game_engine.quarter_noise(3) == game_engine.quarter_noise(3)
    assert abs(game_engine.quarter_noise(3)) <= config.NOISE_MAX


def test_invalid_price_and_negative_marketing_are_rejected():
    with pytest.raises(game_engine.DecisionError):
        game_engine.play_quarter(game_engine.initial_state(), decisions(price=10), budget())
    with pytest.raises(game_engine.DecisionError):
        game_engine.play_quarter(game_engine.initial_state(), decisions(price=80), budget())
    with pytest.raises(game_engine.DecisionError):
        game_engine.play_quarter(game_engine.initial_state(), decisions(marketing=-1), budget())
    with pytest.raises(game_engine.DecisionError):
        game_engine.play_quarter(game_engine.initial_state(), decisions(purchases=-5), budget())


def test_same_quarter_cannot_be_completed_twice():
    updated, _ = game_engine.play_quarter(game_engine.initial_state(), decisions(), budget())
    with pytest.raises(game_engine.QuarterAlreadyCompleted):
        game_engine.play_quarter(updated, decisions(), budget())


def test_labor_shortage_limits_hiring():
    state = game_engine.initial_state()
    state["quarter"] = 6
    with pytest.raises(game_engine.DecisionError) as error:
        game_engine.play_quarter(state, decisions(employees=config.START_EMPLOYEES + 2), budget())
    assert any("arbejdskraft" in message for message in error.value.messages)


def test_eight_quarters_keep_accounting_identities():
    state = game_engine.initial_state()
    for _ in range(config.QUARTERS):
        extra = {"employees": len(state["employee_tenures"])}
        if state["quarter"] == 3:
            extra["accept_special"] = True
        if state["quarter"] == 4:
            extra["invest"] = True
            extra["loan_draw"] = 400_000
        if state["quarter"] == 5:
            extra["repayment"] = 50_000
        if state["quarter"] == 8:
            extra["strategy"] = "vaekst"
        state, report = game_engine.play_quarter(state, decisions(**extra), budget())
        assert_integrity(report)
        state = game_engine.advance_quarter(state, reflection())
    assert state["finished"] is True
    assert len(state["history"]) == 8
    total = sum(item["report"]["period_result"] for item in state["history"])
    assert state["cumulative_result"] == pytest.approx(total, abs=0.05)
    profile = reporting.management_profile(state["history"], state)
    assert profile["profile"] in reporting.PROFILE_PRIORITY
    assert profile["rules"]
    with pytest.raises(game_engine.QuarterAlreadyCompleted):
        game_engine.play_quarter(state, decisions(strategy="konsolidering"), budget())
