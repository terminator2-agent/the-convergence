#!/usr/bin/env python3
"""Explain WHY an order was refused, by naming the row the guard read.

Read-only. This does not decide whether a guard is right and it cannot place,
resize or unblock anything -- discovering a consequential gate is not evidence
that the gate is mistaken (Aria, ai-village-external-agents#80, 2026-09-17).

The motivating case: a position worth M$6.30 -- nine shares of residue left
after an 87% exit -- is the sole reason a M$494 order on a freshly built thesis
is classified as "averaging down". Its worth is six mana; its authority is the
whole order. A ranking over what a row will PAY cannot see that, because
authority is not a quantity the row carries -- it is a quantity of what READS
the row. So this tool does not value rows. It asks what is downstream of them.

    python3 scripts/explain_refusal.py                # last 30d
    python3 scripts/explain_refusal.py --days 7
    python3 scripts/explain_refusal.py --market CL56c9sqQp

A GATE ROW is a position whose current worth is small in absolute terms but
which has gated an order many times its own size. That ratio is the output.
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "pre_kelly_log.jsonl")
STATE = os.path.join(ROOT, "state", "manifold.json")

# A row is a "gate" when it is too small to matter as a holding and yet decides
# an order this much larger. Deliberately crude: the point is to make the shape
# visible, not to draw a line anyone should trade against.
GATE_WORTH_MAX = 50.0
GATE_RATIO_MIN = 5.0

# Guards that refuse by reading a SURVIVING POSITION. Guards that read only the
# market (entry ceiling, sub-edge, cluster cap, creator block) are not
# row-dependency and are reported separately.
#
# Attribute on the STRUCTURED fields, not the prose. kelly_size only attaches
# these when it has actually analysed my entries on the row, so their presence
# IS the fact "a surviving position was read". Matching the message text instead
# looked like it worked and did not: the adverse-add reason matched only because
# the string "--new-evidence" appears in its remediation advice, so a reworded
# hint would have silently reclassified the guard (c6915).
POSITION_FIELDS = ("avg_entry_side_price", "last_event_side_price", "buy_events", "adverse_pp")
# Prose fallback, for rows logged before kelly_size emitted the structured fields
# above. Lowercased compare. Narrowed c6916 — see PROSE_ERA_END.
POSITION_READING = ("adverse move", "buy event", "averaging down")
# First row in data/pre_kelly_log.jsonl carrying any structured position field.
# At or after this stamp, the ABSENCE of those fields is itself evidence: the
# logger would have written them if a position had been read.
PROSE_ERA_END = "2026-09-02T07:50:15"


def reads_position(block_row):
    """Did this refusal consult a surviving position, or only the market?

    c6916 — Aria's second test direction (hold the prose fixed, vary the
    structured evidence) caught this still answering from the prose. Nine
    blocked rows were attributed to a position by keyword alone, and six of
    them had ``existing_exposure`` 0.0: there was no position to consult. The
    "own market" and "72h cooldown" guards read the market's creator and my
    refusal history respectively, not my entries, so their wording never
    belonged in the fallback at all.

    ``existing_exposure`` is present on every row ever logged. The field that
    settles the question was in the record the whole time; the first version
    asked the sentence instead.
    """
    # No position, no position-reading. This holds regardless of vintage.
    if not (block_row.get("existing_exposure") or 0) > 0:
        return False
    if any(block_row.get(f) is not None for f in POSITION_FIELDS):
        return True
    if (block_row.get("ts") or "") >= PROSE_ERA_END:
        return False        # modern row, fields absent => the guard did not read one
    reason = (block_row.get("block_reason") or "").lower()
    return any(k in reason for k in POSITION_READING)


def _rows(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _positions():
    """market_id -> {worth, shares, price, cost} from the synced position file."""
    by_id = {}
    try:
        with open(STATE) as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return by_id, []
    proposals = list(state.get("pending_limit_proposals", []))
    # The briefing carries the SIZED orders; without them a gate's authority is
    # invisible, which is the exact failure this tool exists to fix.
    try:
        with open(os.path.join(ROOT, "cache", "cycle_briefing.json")) as fh:
            brief = json.load(fh)
        proposals += (brief.get("limit_proposals") or {}).get("proposed_orders", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    for p in state.get("open_positions", []):
        mid = p.get("market_id") or p.get("contract_id")
        if not mid:
            continue
        shares = p.get("shares") or 0.0
        price = p.get("current_prob")
        # A NO row is worth shares*(1-p); a YES row shares*p. side is often
        # absent in the synced file, so fall back to the cost basis rather than
        # inventing a number -- a fabricated worth would defeat the whole point.
        worth = None
        side = (p.get("side") or "").upper()
        if price is not None and shares:
            if side == "NO":
                worth = shares * (1.0 - float(price))
            elif side == "YES":
                worth = shares * float(price)
        by_id[mid] = {
            "worth": worth,
            "cost": p.get("amount"),
            "shares": shares,
            "price": price,
            "question": p.get("question") or "",
        }
    return by_id, proposals


def _governed(market_id, proposals, blocks):
    """Largest order size this row is known to have stood in front of.

    Blocked rows log target_size 0 (the guard fires before sizing), so the
    honest upper bound is the pending proposal that is still waiting on it.
    """
    best, why = 0.0, None
    for pr in proposals:
        if (pr.get("market_id") or "") != market_id:
            continue
        # The briefing's sized orders nest the stake under "proposed"; the
        # state file's pending list carries the thesis but no size.
        sized = pr.get("proposed") or pr
        outcome = sized.get("outcome") or pr.get("outcome") or "?"
        for key in ("amount", "size", "expected_size", "stake"):
            if sized.get(key):
                if float(sized[key]) > best:
                    best, why = float(sized[key]), f"pending proposal ({outcome})"
    for b in blocks:
        for key in ("raw_size", "target_size"):
            if b.get(key) and float(b[key]) > best:
                best, why = float(b[key]), "sized-then-blocked order"
    return best, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--market", help="only this market id")
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    blocked = []
    for r in _rows(LOG):
        if r.get("decision") != "blocked":
            continue
        try:
            ts = datetime.fromisoformat(r["ts"])
        except (KeyError, ValueError):
            continue
        if ts < cutoff:
            continue
        if args.market and r.get("market_id") != args.market:
            continue
        blocked.append(r)

    if not blocked:
        print(f"No refusals in the last {args.days}d"
              + (f" on {args.market}" if args.market else "") + ".")
        return

    positions, proposals = _positions()
    by_market = defaultdict(list)
    for b in blocked:
        by_market[b.get("market_id")].append(b)

    gates, plain = [], []
    for mid, blocks in by_market.items():
        reason = blocks[-1].get("block_reason") or ""
        row_dependent = reads_position(blocks[-1])
        pos = positions.get(mid) or {}
        worth = pos.get("worth")
        if worth is None:
            worth = blocks[-1].get("existing_exposure")
        governed, gsrc = _governed(mid, proposals, blocks)
        ratio = (governed / worth) if (worth and worth > 0 and governed) else None
        entry = {
            "mid": mid, "blocks": blocks, "reason": reason, "pos": pos,
            "worth": worth, "governed": governed, "gsrc": gsrc, "ratio": ratio,
            "reads_position": row_dependent,
        }
        is_gate = (row_dependent and worth is not None and worth < GATE_WORTH_MAX
                   and ratio is not None and ratio >= GATE_RATIO_MIN)
        (gates if is_gate else plain).append(entry)

    gates.sort(key=lambda e: -(e["ratio"] or 0))
    plain.sort(key=lambda e: -len(e["blocks"]))

    print(f"=== REFUSAL PROVENANCE — {len(blocked)} refusal(s) across "
          f"{len(by_market)} market(s), last {args.days}d ===")
    print("Read-only. Naming a gate is not an argument for removing it.\n")

    def render(e, mark=""):
        b = e["blocks"][-1]
        q = (b.get("question") or e["pos"].get("question") or "")[:58]
        print(f"{mark}{e['mid']}  \"{q}\"")
        print(f"    refused {len(e['blocks'])}x — {e['reason'][:110]}")
        if e["reads_position"]:
            worth = e["worth"]
            shares, price = e["pos"].get("shares"), e["pos"].get("price")
            bits = f"M${worth:,.2f}" if worth is not None else "unknown worth"
            if shares and price is not None:
                bits += f" ({shares:,.2f} shares @ {float(price):.1%})"
            print(f"    the guard read a SURVIVING POSITION worth {bits}")
            anchor = b.get("last_event_side_price")
            avg = b.get("avg_entry_side_price")
            if anchor is not None and avg is not None:
                which = "last buy" if abs(anchor - max(anchor, avg)) < 1e-9 else "all-time avg"
                print(f"      anchor used: {which} @ {max(anchor, avg):.1%} "
                      f"(avg {avg:.1%} / last {anchor:.1%}) vs now {b.get('side_price_now', 0):.1%}")
            if b.get("buy_events") is not None:
                print(f"      buy events on the row: {b['buy_events']}")
        else:
            print("    (guard read the MARKET, not a surviving position — no row dependency)")
        if e["governed"]:
            print(f"    it stands in front of M${e['governed']:,.0f} ({e['gsrc']})")
        if e["ratio"]:
            print(f"    → worth:authority = 1 : {e['ratio']:.0f}")
        print()

    if gates:
        print(f"--- GATE ROWS ({len(gates)}) — worth < M${GATE_WORTH_MAX:.0f}, "
              f"authority >= {GATE_RATIO_MIN:.0f}x worth ---")
        print("A holding too small to pay you anything, deciding an order many times its size.\n")
        for e in gates:
            render(e, mark="⚠ ")

    if plain:
        print(f"--- OTHER REFUSALS ({len(plain)}) ---\n")
        for e in plain[:12]:
            render(e)

    tot = sum(e["governed"] for e in gates if e["governed"])
    if tot:
        print(f"TOTAL held behind gate rows: M${tot:,.0f} across {len(gates)} market(s).")
        print("This is a measurement, not a recommendation. If a gate is wrong, the repair is")
        print("a decision about the guard — not a trim to duck under its threshold, which would")
        print("launder an average-down into a fresh entry.")


if __name__ == "__main__":
    main()
