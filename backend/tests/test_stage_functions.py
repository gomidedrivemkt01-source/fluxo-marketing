import pytest

from app.stage_functions import stage_function_key


@pytest.mark.parametrize(
    "name,key",
    [
        (" Briefing ", "briefing"),
        ("BRIEFING", "briefing"),
        ("Revisão (Criação)", "revisao-criacao"),
        ("  Revisao   (Criacao)  ", "revisao-criacao"),
    ],
)
def test_equivalent_stage_names_share_a_group(name, key):
    assert stage_function_key(name) == key


def test_different_review_phases_do_not_merge_accidentally():
    assert stage_function_key("Revisão (Criação)") != stage_function_key("Revisão (Técnica)")
