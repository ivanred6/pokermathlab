from poker_engine import class_to_combos, parse_cards, pot_odds_required, call_ev


def test_combo_counts():
    assert len(class_to_combos("AA")) == 6
    assert len(class_to_combos("AKs")) == 4
    assert len(class_to_combos("AKo")) == 12


def test_cards():
    assert parse_cards("As Kh") == ["As", "Kh"]
    assert parse_cards("AsKh") == ["As", "Kh"]


def test_pot_odds():
    # call 5 into a pot that was 10 before villain's 5 bet => final pot 20
    assert abs(pot_odds_required(10, 5) - 0.25) < 1e-12
    assert abs(call_ev(0.25, 10, 5)) < 1e-12
