"""
`python -m nebula.llm "..."` — the natural-language front end.

    python -m nebula.llm "I need about 9 dB of peaking with the peak near 1.9 GHz"
    python -m nebula.llm "6 dB boost at 2.2 GHz" --out out
    python -m nebula.llm "9 dB at 1.9 GHz" --llm          # use Claude for both ends

Wraps `nebula.design` and adds exactly two things -- a parser in front and an
explanation behind. The sizing loop in between is untouched and never sees the
model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from nebula.llm import client as C
from nebula.llm.explanation import explain as explain_design
from nebula.llm.spec_parse import SpecOutOfRange, parse_request


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m nebula.llm", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("request", help="what you want, in plain English")
    ap.add_argument("--llm", action="store_true",
                    help="use Claude to parse the request and word the "
                         "explanation. Off by default: every path has a "
                         "deterministic fallback so a demo needs no network.")
    ap.add_argument("--method", default="rl-hybrid",
                    choices=("rl-hybrid", "auto", "library", "uniform",
                             "lhs", "grid", "cmaes", "gp_bo", "ppo"),
                    help="rl-hybrid is the default competition product: "
                         "frozen RL proposer, simulator shield, then measured "
                         "bank fallback")
    ap.add_argument("--budget", type=int, default=150)
    ap.add_argument("--robust", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="verify at 45 corners x 3 loads")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        parsed = parse_request(args.request, use_llm=args.llm)
    except SpecOutOfRange as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f'  REQUEST   "{parsed.raw}"')
    print(f"  READ AS   peaking {parsed.target.peaking_db:g} dB, "
          f"peak at {parsed.target.f_peak_hz / 1e9:.4g} GHz"
          f"   [parsed by {parsed.source}]")
    for n in parsed.notes:
        print(f"            note: {n}")
    if args.llm and not C.available():
        print("            note: --llm was asked for but no Anthropic client "
              "is usable; the deterministic paths ran instead")
    print()

    from nebula.design import (
        design, prepare_output_deck, report, write_outputs,
    )

    try:
        d = design(parsed.target.peaking_db, parsed.target.f_peak_hz,
                   method=args.method, budget=args.budget, robust=args.robust,
                   verify=args.verify)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    d["natural_language"] = parsed.as_dict()

    # Export before wording the explanation so its simulation count includes
    # the representative deck. The shared writer below never reruns it.
    deck = None
    if args.out:
        try:
            deck = prepare_output_deck(d)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    text, source = explain_design(d, use_llm=args.llm)
    d["explanation"] = {"text": text, "source": source}

    if args.json:
        print(json.dumps(d, indent=1, default=str))
    else:
        print(report(d))
        print()
        print(f"  EXPLANATION  [{source}]")
        print()
        for line in text.splitlines():
            print(f"    {line}" if line else "")
        print()

    if args.out:
        written, warnings = write_outputs(
            d, args.out, deck=deck,
            extra_files={"explanation.txt": text})
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        print("wrote " + ", ".join(str(path) for path in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
