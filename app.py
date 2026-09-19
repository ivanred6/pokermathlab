from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from poker_engine import (
    GRID,
    RANKS,
    bet_ev,
    call_ev,
    monte_carlo_equity,
    parse_cards,
    pot_odds_required,
    range_from_grid,
    spr,
)

st.set_page_config(page_title="Poker Math Lab", page_icon="♠", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stMetricValue"] {font-size: 1.7rem;}
.small-note {font-size: 0.86rem; opacity: 0.75;}
.cardbox {border:1px solid rgba(128,128,128,.35); border-radius:10px; padding:.8rem 1rem;}
</style>
""",
    unsafe_allow_html=True,
)

POSITIONS = {
    2: ["BTN/SB", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["CO", "BTN", "SB", "BB"],
    5: ["HJ", "CO", "BTN", "SB", "BB"],
    6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"],
    7: ["UTG", "UTG+1", "HJ", "CO", "BTN", "SB", "BB"],
    8: ["UTG", "UTG+1", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
}


def blank_range() -> dict[str, float]:
    return {label: 0.0 for row in GRID for label in row}


def preset_range(name: str) -> dict[str, float]:
    w = blank_range()
    if name == "Tight":
        labels = ["77", "88", "99", "TT", "JJ", "QQ", "KK", "AA", "ATs", "AJs", "AQs", "AKs", "KQs", "AQo", "AKo"]
    elif name == "Broadway+Pairs":
        labels = [r+r for r in RANKS] + [
            "ATs", "AJs", "AQs", "AKs", "KTs", "KJs", "KQs", "QTs", "QJs", "JTs",
            "AJo", "AQo", "AKo", "KQo"
        ]
    elif name == "Loose":
        labels = [
            "22","33","44","55","66","77","88","99","TT","JJ","QQ","KK","AA",
            "A2s","A3s","A4s","A5s","A6s","A7s","A8s","A9s","ATs","AJs","AQs","AKs",
            "K7s","K8s","K9s","KTs","KJs","KQs","Q8s","Q9s","QTs","QJs","J8s","J9s","JTs",
            "T8s","T9s","98s","87s","76s","65s","54s","ATo","AJo","AQo","AKo","KJo","KQo","QJo"
        ]
    else:
        return w
    for x in labels:
        w[x] = 100.0
    return w


def grid_df(weights: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame([[weights[label] for label in row] for row in GRID], index=RANKS, columns=RANKS)


def df_to_weights(df: pd.DataFrame) -> dict[str, float]:
    return {GRID[i][j]: float(df.iloc[i, j]) for i in range(13) for j in range(13)}


def combo_count(weights: dict[str, float]) -> float:
    total = 0.0
    for label, pct in weights.items():
        combos = 6 if len(label) == 2 else (4 if label.endswith("s") else 12)
        total += combos * pct / 100.0
    return total


if "ranges" not in st.session_state:
    st.session_state.ranges = {}
if "profiles" not in st.session_state:
    st.session_state.profiles = {}

st.title("♠ Poker Math Lab")
st.caption("Local Hold'em range, equity and EV explorer for teaching probability, logic and decision-making.")

with st.sidebar:
    st.header("Table")
    n_players = st.slider("Players", 2, 8, 6)
    positions = POSITIONS[n_players]
    hero_pos = st.selectbox("Hero position", positions, index=min(len(positions)-1, 3))
    hero_index = positions.index(hero_pos)
    villain_positions = [p for i, p in enumerate(positions) if i != hero_index]

    same_stack = st.toggle("Same effective stack for all", True)
    if same_stack:
        effective_stack = st.number_input("Effective stack (bb)", min_value=1.0, value=100.0, step=5.0)
        stacks = {p: effective_stack for p in positions}
    else:
        stacks = {p: st.number_input(f"{p} stack (bb)", min_value=1.0, value=100.0, step=5.0, key=f"stack_{p}") for p in positions}
        effective_stack = min(stacks.values())

    st.divider()
    st.header("Hand / board")
    hero_text = st.text_input("Hero hand", "As Kh", help="Examples: As Kh or AsKh")
    flop_text = st.text_input("Flop", "Qh 7d 2c")
    turn_text = st.text_input("Turn", "", help="One card, e.g. Js")
    river_text = st.text_input("River", "", help="One card, e.g. 4s")

    st.divider()
    st.header("Simulation")
    trials = st.select_slider("Monte Carlo trials", [1000, 2500, 5000, 10000, 20000, 50000, 100000], value=20000)
    seed = st.number_input("Random seed", min_value=0, value=42, step=1)

# Ensure seats have state
for p in villain_positions:
    if p not in st.session_state.ranges:
        st.session_state.ranges[p] = preset_range("Broadway+Pairs")
    if p not in st.session_state.profiles:
        st.session_state.profiles[p] = {"fold_to_bet": 45, "aggression": 50}

setup_tab, analysis_tab, trainer_tab, notes_tab = st.tabs(["1. Ranges", "2. Equity & EV", "3. Trainer", "4. Teaching notes"])

with setup_tab:
    left, right = st.columns([1, 3])
    with left:
        selected_villain = st.selectbox("Edit opponent", villain_positions)
        preset = st.selectbox("Load preset", ["Custom", "Tight", "Broadway+Pairs", "Loose"])
        if st.button("Apply preset", use_container_width=True):
            if preset != "Custom":
                st.session_state.ranges[selected_villain] = preset_range(preset)
                st.rerun()
        prof = st.session_state.profiles[selected_villain]
        prof["fold_to_bet"] = st.slider("Fold to bet %", 0, 100, int(prof["fold_to_bet"]), key=f"ftb_{selected_villain}")
        prof["aggression"] = st.slider("Aggression index", 0, 100, int(prof["aggression"]), key=f"agg_{selected_villain}")
        st.session_state.profiles[selected_villain] = prof
        st.metric("Weighted combos", f"{combo_count(st.session_state.ranges[selected_villain]):.1f} / 1326")
        st.caption("Matrix convention: diagonal = pairs, upper triangle = suited, lower triangle = offsuit. Enter 0–100 for combo weight.")
    with right:
        st.subheader(f"{selected_villain} range matrix")
        edited = st.data_editor(
            grid_df(st.session_state.ranges[selected_villain]),
            key=f"grid_{selected_villain}",
            hide_index=False,
            width="stretch",
            height=535,
            column_config={r: st.column_config.NumberColumn(r, min_value=0.0, max_value=100.0, step=5.0, format="%.0f") for r in RANKS},
        )
        st.session_state.ranges[selected_villain] = df_to_weights(edited)

    st.divider()
    with st.expander("Copy one opponent range/profile to all other seats"):
        source = st.selectbox("Source seat", villain_positions, key="copy_source")
        if st.button("Copy to all opponents"):
            for p in villain_positions:
                st.session_state.ranges[p] = dict(st.session_state.ranges[source])
                st.session_state.profiles[p] = dict(st.session_state.profiles[source])
            st.rerun()

with analysis_tab:
    try:
        hero = parse_cards(hero_text)
        flop = parse_cards(flop_text)
        turn = parse_cards(turn_text)
        river = parse_cards(river_text)
        board = flop + turn + river
        if len(hero) != 2:
            raise ValueError("Enter exactly two hero cards.")
        if len(flop) not in (0, 3):
            raise ValueError("Flop must be blank or exactly three cards.")
        if len(turn) > 1 or len(river) > 1:
            raise ValueError("Turn and river accept one card each.")
        if river and not turn:
            raise ValueError("Enter a turn before a river.")
        if len(set(hero + board)) != len(hero + board):
            raise ValueError("Hero and board cannot share a card.")

        active_ranges = [range_from_grid(st.session_state.ranges[p]) for p in villain_positions]
        empty = [p for p, r in zip(villain_positions, active_ranges) if not r]
        if empty:
            raise ValueError("Empty range for: " + ", ".join(empty))

        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            pot = st.number_input("Pot before action (bb)", min_value=0.1, value=10.0, step=0.5)
        with c2:
            facing_bet = st.number_input("Facing bet (bb)", min_value=0.0, value=5.0, step=0.5)
        with c3:
            hero_bet = st.number_input("Hero bet size (bb)", min_value=0.0, value=6.5, step=0.5)

        if st.button("Run equity simulation", type="primary", use_container_width=True):
            with st.spinner("Simulating legal weighted combinations and runouts..."):
                res = monte_carlo_equity(hero, board, active_ranges, trials=int(trials), seed=int(seed))
                st.session_state.last_result = res

        res = st.session_state.get("last_result")
        if res:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Hero equity", f"{res.equity:.2%}")
            m2.metric("Win rate", f"{res.win_rate:.2%}")
            m3.metric("Tie frequency", f"{res.tie_rate:.2%}")
            m4.metric("Trials", f"{res.trials:,}")

            st.subheader("Decision-point EV")
            q1, q2, q3, q4 = st.columns(4)
            call_value = call_ev(res.equity, pot, facing_bet) if facing_bet > 0 else 0.0
            required = pot_odds_required(pot, facing_bet) if facing_bet > 0 else 0.0
            avg_fold = sum(st.session_state.profiles[p]["fold_to_bet"] for p in villain_positions) / len(villain_positions) / 100.0
            # For multiple opponents, independent-fold approximation. This is intentionally shown as an approximation.
            all_fold = avg_fold ** len(villain_positions)
            bet_value = bet_ev(res.equity, pot, hero_bet, all_fold) if hero_bet > 0 else 0.0
            q1.metric("Call EV", f"{call_value:+.2f} bb")
            q2.metric("Break-even equity", f"{required:.2%}")
            q3.metric("Bet EV*", f"{bet_value:+.2f} bb")
            q4.metric("SPR", f"{spr(effective_stack, pot):.2f}")
            st.caption("*Bet EV uses a deliberately simple one-street model: opponents fold independently at the configured fold-to-bet rate, otherwise call; no raises or future betting. This is pedagogical EV, not a solved equilibrium strategy.")

            st.subheader("Street sensitivity")
            st.write("Change the flop, turn or river in the sidebar and rerun. With a fixed seed and trial count, differences are easier to discuss as board-driven changes rather than random noise.")

            if res.rejected:
                st.caption(f"Rejected {res.rejected:,} attempted deals because sampled weighted ranges conflicted with dead cards or other sampled hands.")

    except Exception as exc:
        st.error(str(exc))

with trainer_tab:
    st.subheader("Opponent-response trainer")
    st.write("This tab converts your opponent assumptions into a simple decision drill. It is exploitative training, not a claim about optimal GTO play.")
    target = st.selectbox("Opponent model", villain_positions, key="trainer_target")
    profile = st.session_state.profiles[target]
    weighted_combos = combo_count(st.session_state.ranges[target])
    a, b, c = st.columns(3)
    a.metric("Range width", f"{weighted_combos / 1326:.1%}")
    b.metric("Fold to bet", f"{profile['fold_to_bet']}%")
    c.metric("Aggression index", f"{profile['aggression']} / 100")

    scenario = st.radio("Scenario", ["Facing a bet", "Considering a bet"], horizontal=True)
    if scenario == "Facing a bet":
        tp = st.number_input("Current pot (bb)", min_value=0.5, value=12.0, step=0.5, key="tp1")
        tb = st.number_input("Opponent bet (bb)", min_value=0.5, value=8.0, step=0.5, key="tb1")
        req = pot_odds_required(tp, tb)
        st.info(f"A call needs {req:.1%} equity before considering future-street effects. Ask the mentee to estimate equity first, then compare with the simulation.")
    else:
        tp = st.number_input("Current pot (bb)", min_value=0.5, value=12.0, step=0.5, key="tp2")
        tb = st.number_input("Proposed bet (bb)", min_value=0.5, value=8.0, step=0.5, key="tb2")
        breakeven_bluff = tb / (tp + tb)
        st.info(f"A pure bluff of {tb:.1f} bb into {tp:.1f} bb needs folds more than {breakeven_bluff:.1%} of the time to show immediate profit. Compare that with the opponent model's {profile['fold_to_bet']}% fold assumption.")

    st.markdown("**Teaching prompt:** identify the inputs that are measured/assumed (range, fold frequency, bet size), the random variable (unknown cards), and the output (expected value). Then change one input at a time.")

with notes_tab:
    st.subheader("What this MVP does")
    st.markdown(
        """
- Editable weighted 13×13 preflop range matrix for every opponent seat.
- 2–8 handed table setup, hero position and either common or per-seat stack depths.
- Explicit hero hand plus flop / turn / river inputs.
- Multiway Monte Carlo equity using legal weighted hand combinations and dead-card removal.
- Simple, inspectable call EV, pot-odds, SPR and one-street bet EV calculations.
- Configurable opponent fold/aggression assumptions and a teaching/training view.
        """
    )
    st.subheader("What it intentionally does not pretend to do")
    st.markdown(
        """
- It is **not yet a GTO solver**. A GTO solver needs a betting game tree, action abstractions, range propagation, counterfactual regret minimisation (or another equilibrium algorithm), convergence/error reporting and usually substantial compute/precomputation.
- The displayed bet EV is a simplified one-street model. Raises, future streets and range changes after actions are not included yet.
- Range weights currently describe how often a combo exists in a seat's current range; they are not yet action-frequency matrices such as 30% fold / 50% call / 20% raise per combo.
        """
    )
    st.subheader("Recommended next engineering steps")
    st.markdown(
        """
1. Add per-combo **fold / call / raise frequencies** and propagate ranges after each action.
2. Add an action-tree builder (bet sizes, raises, stack caps) and recursively calculate terminal EVs.
3. Cache board/range evaluations and optionally move hot loops to NumPy/Numba/Cython/Rust if profiling shows a need.
4. Add saved scenarios and hand-history import for repeatable mentoring exercises.
5. Add a separate heads-up CFR solver for small postflop abstractions before attempting larger GTO trees.
        """
    )

st.divider()
st.caption("Educational analysis tool. EV outputs depend on the ranges and behavioural assumptions you enter.")
