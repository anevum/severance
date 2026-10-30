"""Run as: python -m worldstate demo --out output, or python -m worldstate verify FILE"""
import argparse
import json
from .engine import World
from .scenarios import run_demo
from .stress import run_stress
from .demo_expanded import run_expanded_demo
from .demo_v03 import run_v03_demo
from .stress_v03 import run_v03_stress


def main() -> None:
    p = argparse.ArgumentParser(description="Severance offline world-state lab (NOT the game server)")
    sub = p.add_subparsers(dest="cmd", required=True)
    demo = sub.add_parser("demo", help="Build, export and replay a canonical test world")
    demo.add_argument("--out", default="output")
    verify = sub.add_parser("verify", help="Rebuild and verify a JSONL event trace")
    verify.add_argument("trace")
    expanded = sub.add_parser("expanded-demo", help="Run V0.2 integrated civic/medical/cargo story")
    expanded.add_argument("--out", default="output/expanded")
    stress = sub.add_parser("stress", help="Bounded randomized offline supply runs (not network load)")
    stress.add_argument("--out", default="output")
    stress.add_argument("--seed", type=int, default=8619)
    stress.add_argument("--rounds", type=int, default=250)
    v03 = sub.add_parser('v03-demo', help='V0.3 consent, timed rescue, multi-hop cargo and replay')
    v03.add_argument('--out', default='output/v03')
    stress3 = sub.add_parser('v03-stress', help='Seeded offline V0.3 convoy stress (not users)')
    stress3.add_argument('--out', default='output/v03_stress')
    stress3.add_argument('--seed', type=int, default=20261029)
    stress3.add_argument('--rounds', type=int, default=100)
    args = p.parse_args()
    if args.cmd == "demo":
        print(json.dumps(run_demo(args.out), indent=2))
    elif args.cmd == "expanded-demo":
        print(json.dumps(run_expanded_demo(args.out), indent=2))
    elif args.cmd == "stress":
        print(json.dumps(run_stress(args.out,seed=args.seed,rounds=args.rounds), indent=2))
    elif args.cmd == 'v03-demo':
        print(json.dumps(run_v03_demo(args.out), indent=2))
    elif args.cmd == 'v03-stress':
        print(json.dumps(run_v03_stress(args.out, seed=args.seed, rounds=args.rounds), indent=2))
    elif args.cmd == "verify":
        with World.replay_jsonl(args.trace) as w:
            print(json.dumps({"ledger": w.verify_chain(), "state_sha256": w.state_hash()}, indent=2))


if __name__ == "__main__":
    main()
