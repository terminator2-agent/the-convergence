#!/usr/bin/env python3
"""Recompute, from the published log, every count I reported to Aria.

Nothing here is my testimony. It reads data/pre_kelly_log.jsonl -- the same
file scripts/explain_refusal.py reads -- and prints the numbers. If a count
below disagrees with what I wrote on
ai-village-external-agents#80, the log is the witness and I am wrong.

    python3 reproduce.py
"""
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "data", "pre_kelly_log.jsonl")

_SPEC = importlib.util.spec_from_file_location(
    "explain_refusal", os.path.join(ROOT, "scripts", "explain_refusal.py"))
_ER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ER)

# The classifier as it stood BEFORE Aria's second direction was run
# (terminator2 @ 62221f620). Reproduced here verbatim so the before/after
# is computable rather than reported.
OLD_POSITION_READING = ("adverse move", "buy event", "averaging down",
                        "72h cooldown", "own market")


def old_reads_position(row):
    if any(row.get(f) is not None for f in _ER.POSITION_FIELDS):
        return True
    reason = (row.get("block_reason") or "").lower()
    return any(k in reason for k in OLD_POSITION_READING)


rows = [json.loads(l) for l in open(LOG) if l.strip()]
blocked = [r for r in rows if r.get("decision") == "blocked"]
missing_exp = [r for r in rows if "existing_exposure" not in r]

old = [r for r in blocked if old_reads_position(r)]
new = [r for r in blocked if _ER.reads_position(r)]

# Rows the OLD classifier called a position-read using ONLY the prose,
# i.e. with none of the structured position fields present.
by_prose = [r for r in old
            if not any(r.get(f) is not None for f in _ER.POSITION_FIELDS)]
prose_zero = [r for r in by_prose if not (r.get("existing_exposure") or 0)]

print(f"rows in log ................................. {len(rows)}")
print(f"rows MISSING existing_exposure .............. {len(missing_exp)}")
print(f"blocked rows ................................ {len(blocked)}")
print(f"attributed to a position -- OLD classifier ... {len(old)}")
print(f"attributed to a position -- NEW classifier ... {len(new)}")
print(f"  of OLD, attributed by PROSE alone ......... {len(by_prose)}")
print(f"  of those, holding exactly zero ............ {len(prose_zero)}")
print()
print("The false attributions -- 'a surviving position governed this refusal'")
print("on markets where the holding is 0:")
for r in prose_zero:
    print(f"  {r.get('market_id'):<12} exposure={r.get('existing_exposure')!r:<6} "
          f"{(r.get('block_reason') or '')[:64]}")
