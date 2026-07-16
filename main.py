"""Control-plane CLI entry points with no runtime dependency beyond Python."""
from __future__ import annotations
import argparse
from pathlib import Path
from core.config import load_experiment_plan

def main() -> None:
    parser=argparse.ArgumentParser(description="Entropy Research Platform control plane")
    commands=parser.add_subparsers(dest="command",required=True)
    validate=commands.add_parser("validate",help="validate an in-memory ExperimentPlan JSON file")
    validate.add_argument("path",type=Path)
    args=parser.parse_args()
    if args.command=="validate":
        plan=load_experiment_plan(args.path)
        print(f"valid plan: {plan.name} ({plan.config_hash()})")
if __name__=="__main__": main()
