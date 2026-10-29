"""CLI simulator.

    python -m simulators generate               # bangun data simulasi (deterministik)
    python -m simulators publish [--until D]    # kirim ke sistem sumber s/d tanggal D (default: kemarin)
    python -m simulators status
    python -m simulators reset                  # kosongkan sistem sumber
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta

from simulators import publish as pub
from simulators.generate import generate


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="simulators")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate")
    pp = sub.add_parser("publish")
    pp.add_argument("--until", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    sub.add_parser("status")
    sub.add_parser("reset")
    args = p.parse_args()

    if args.cmd == "generate":
        out = generate()
    elif args.cmd == "publish":
        out = pub.publish(args.until)
    elif args.cmd == "status":
        out = pub.read_state() or {"published_until": None}
    else:
        pub.reset()
        out = {"reset": True}
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
