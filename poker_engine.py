from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import random
from typing import Dict, Iterable, List, Sequence, Tuple

import eval7

RANKS = "AKQJT98765432"
SUITS = "shdc"


def hand_class(r1: str, r2: str, suited: bool | None = None) -> str:
    i1, i2 = RANKS.index(r1), RANKS.index(r2)
    if i1 == i2:
        return r1 + r2
    hi, lo = (r1, r2) if i1 < i2 else (r2, r1)
    return hi + lo + ("s" if suited else "o")


def matrix_labels() -> List[List[str]]:
    out: List[List[str]] = []
    for i, r1 in enumerate(RANKS):
        row = []
        for j, r2 in enumerate(RANKS):
            if i == j:
                row.append(r1 + r2)
            elif i < j:
                row.append(r1 + r2 + "s")
            else:
                row.append(r2 + r1 + "o")
        out.append(row)
    return out


GRID = matrix_labels()


def class_to_combos(label: str) -> List[Tuple[str, str]]:
    r1, r2 = label[0], label[1]
    if len(label) == 2:
        return [(r1 + s1, r2 + s2) for s1, s2 in combinations(SUITS, 2)]
    if label[2] == "s":
        return [(r1 + s, r2 + s) for s in SUITS]
    return [(r1 + s1, r2 + s2) for s1 in SUITS for s2 in SUITS if s1 != s2]


def parse_cards(text: str) -> List[str]:
    text = text.replace(",", " ").strip()
    if not text:
        return []
    tokens = text.split()
    if len(tokens) == 1 and len(tokens[0]) in (4, 6, 8, 10):
        raw = tokens[0]
        tokens = [raw[i:i+2] for i in range(0, len(raw), 2)]
    cards = []
    for token in tokens:
        token = token.strip()
        if len(token) != 2:
            raise ValueError(f"Invalid card '{token}'. Use notation like As, Kh, 7d.")
        rank = token[0].upper()
        suit = token[1].lower()
        if rank not in RANKS or suit not in SUITS:
            raise ValueError(f"Invalid card '{token}'. Ranks: AKQJT98765432; suits: s/h/d/c.")
        cards.append(rank + suit)
    if len(set(cards)) != len(cards):
        raise ValueError("A card cannot appear twice.")
    return cards


def range_from_grid(weights: Dict[str, float]) -> List[Tuple[Tuple[str, str], float]]:
    combos: List[Tuple[Tuple[str, str], float]] = []
    for label, pct in weights.items():
        w = max(0.0, min(100.0, float(pct))) / 100.0
        if w <= 0:
            continue
        for combo in class_to_combos(label):
            combos.append((combo, w))
    return combos


def weighted_choice_legal(
    combos: Sequence[Tuple[Tuple[str, str], float]], dead: set[str], rng: random.Random
) -> Tuple[str, str] | None:
    legal = [(combo, w) for combo, w in combos if combo[0] not in dead and combo[1] not in dead]
    if not legal:
        return None
    total = sum(w for _, w in legal)
    x = rng.random() * total
    running = 0.0
    for combo, w in legal:
        running += w
        if running >= x:
            return combo
    return legal[-1][0]


def score7(cards: Sequence[str]) -> int:
    return eval7.evaluate([eval7.Card(c) for c in cards])


@dataclass
class SimulationResult:
    equity: float
    win_rate: float
    tie_rate: float
    trials: int
    rejected: int


def monte_carlo_equity(
    hero: Sequence[str],
    board: Sequence[str],
    opponent_ranges: Sequence[Sequence[Tuple[Tuple[str, str], float]]],
    trials: int = 20000,
    seed: int | None = None,
) -> SimulationResult:
    if len(hero) != 2:
        raise ValueError("Hero must have exactly two hole cards.")
    if len(board) > 5:
        raise ValueError("Board may contain at most five cards.")
    known = list(hero) + list(board)
    if len(set(known)) != len(known):
        raise ValueError("Hero and board contain duplicate cards.")
    if not opponent_ranges:
        raise ValueError("At least one opponent range is required.")

    rng = random.Random(seed)
    deck = [r + s for r in RANKS for s in SUITS]
    wins = ties = completed = rejected = 0
    equity_sum = 0.0

    attempts = 0
    max_attempts = max(trials * 20, 1000)
    while completed < trials and attempts < max_attempts:
        attempts += 1
        dead = set(known)
        villain_hands: List[Tuple[str, str]] = []
        ok = True
        for vrange in opponent_ranges:
            combo = weighted_choice_legal(vrange, dead, rng)
            if combo is None:
                ok = False
                break
            villain_hands.append(combo)
            dead.update(combo)
        if not ok:
            rejected += 1
            continue

        remaining = [c for c in deck if c not in dead]
        need = 5 - len(board)
        if len(remaining) < need:
            rejected += 1
            continue
        runout = rng.sample(remaining, need)
        full_board = list(board) + runout

        hero_score = score7(list(hero) + full_board)
        scores = [score7(list(vh) + full_board) for vh in villain_hands]
        best = max([hero_score] + scores)
        winners = 1 + sum(1 for s in scores if s == best) if hero_score == best else 0

        if hero_score == best:
            share = 1.0 / winners
            equity_sum += share
            if winners == 1:
                wins += 1
            else:
                ties += 1
        completed += 1

    if completed == 0:
        raise ValueError("No legal simulations completed. Check ranges and dead cards.")
    return SimulationResult(
        equity=equity_sum / completed,
        win_rate=wins / completed,
        tie_rate=ties / completed,
        trials=completed,
        rejected=rejected,
    )


def call_ev(equity: float, pot_before_bet: float, facing_bet: float) -> float:
    """Net EV from the decision point when calling a heads-up bet.

    final pot = pot_before_bet + facing_bet + our call.
    EV = equity * final_pot - call_cost.
    """
    final_pot = pot_before_bet + 2.0 * facing_bet
    return equity * final_pot - facing_bet


def bet_ev(equity_when_called: float, pot: float, bet: float, fold_equity: float) -> float:
    """Simple heads-up one-street bet EV from current decision point.

    Assumes: opponent folds with FE; otherwise calls; no future betting.
    """
    fe = max(0.0, min(1.0, fold_equity))
    called_ev = equity_when_called * (pot + 2.0 * bet) - bet
    return fe * pot + (1.0 - fe) * called_ev


def pot_odds_required(pot_before_bet: float, facing_bet: float) -> float:
    return facing_bet / (pot_before_bet + 2.0 * facing_bet) if facing_bet > 0 else 0.0


def spr(effective_stack: float, pot: float) -> float:
    return effective_stack / pot if pot > 0 else float("inf")
