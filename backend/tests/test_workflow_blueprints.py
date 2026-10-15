from app.workflow_blueprints import BLUEPRINTS, checklist_parts


def test_manual_blueprint_inventory_matches_source_document() -> None:
    assert len(BLUEPRINTS) == 13
    assert sum(len(spec["stages"]) for spec in BLUEPRINTS.values()) == 114
    assert sum(len(spec["fields"]) for spec in BLUEPRINTS.values()) == 145


def test_manual_blueprint_keeps_distinct_design_and_it_ownership() -> None:
    landing_page = BLUEPRINTS["LANDING_PAGE"]
    owners = {name: role for name, role, _ in landing_page["stages"]}

    assert owners["Design"] == "DESIGN_AUDIOVISUAL"
    assert owners["Desenvolvimento"] == "TECH_AUTOMATION"
    assert owners["Integrações"] == "TECH_AUTOMATION"


def test_checklist_acceptance_rule_is_split_into_atomic_confirmations() -> None:
    assert checklist_parts("Problema, regra de negócio e aceite definidos.") == [
        "Problema",
        "Regra de negócio",
        "Aceite definidos",
    ]
