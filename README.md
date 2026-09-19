# Poker Math Lab

A local Streamlit application for teaching Texas Hold'em probability, ranges, equity, expected value and decision flow.

## Features

- 2 to 8 handed table configuration
- Hero position and stack depth controls
- Common effective stack or per-seat stacks
- Editable weighted 13x13 range matrix for every opponent
- Hero hand and flop / turn / river inputs
- Weighted multiway Monte Carlo equity
- Pot odds, SPR, call EV and simplified one-street bet EV
- Configurable opponent fold/aggression assumptions
- Teaching/training tab

## Install

Python 3.11 or 3.12 is recommended.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Streamlit will print a local URL, normally `http://localhost:8501`.

## Range grid convention

- diagonal: pairs (`AA`, `KK`, ...)
- upper triangle: suited (`AKs`, `AQs`, ...)
- lower triangle: offsuit (`AKo`, `AQo`, ...)
- each cell is a 0-100 percentage weight

A 50 in `AKs`, for example, means suited ace-king combinations are sampled at half the weight of a cell set to 100.

## EV formulas used in the MVP

Facing a heads-up bet:

`EV(call) = equity * (pot + 2 * call) - call`

For a one-street bet with fold equity `FE`:

`EV(bet) = FE * pot + (1-FE) * [equity_when_called * (pot + 2*bet) - bet]`

The bet formula is intentionally simplified and is labelled as such in the UI. It does not include raises or future-street betting.

## Scope

This is a Flopzilla-style educational analysis MVP, not a full GTO Wizard clone. A production equilibrium solver is a separate subsystem. The clean next step is to add per-combo action frequencies and an explicit action tree, then implement CFR on a small heads-up abstraction.
