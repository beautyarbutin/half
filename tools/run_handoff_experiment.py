from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND))

from services.secure_handoff_experiment import (  # noqa: E402
    add_intervention,
    evaluate_run,
    get_run_prompt,
    list_experiments,
    load_run,
    prepare_run,
    secure_arm_options,
    submit_manual_attempt,
    summarize_experiment,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run isolated HALF handoff ablation experiments")
    result.add_argument(
        "--private-root",
        help="Private experiment root; overrides HALF_HANDOFF_EXPERIMENT_PRIVATE_ROOT",
    )
    result.add_argument(
        "--runs-root",
        help="Private run output root; overrides HALF_HANDOFF_EXPERIMENT_RUNS_ROOT",
    )
    subparsers = result.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")
    subparsers.add_parser("arms")

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("experiment_id")
    prepare.add_argument("arm_id")
    prepare.add_argument("--model", default="gpt-5.5")
    prepare.add_argument("--max-attempts", type=int)

    prompt = subparsers.add_parser("prompt")
    prompt.add_argument("run_id")

    submit = subparsers.add_parser("submit")
    submit.add_argument("run_id")
    submit.add_argument("--conversation-id")
    submit.add_argument("--input-tokens", type=int, default=0)
    submit.add_argument("--cached-input-tokens", type=int, default=0)
    submit.add_argument("--output-tokens", type=int, default=0)
    submit.add_argument("--reasoning-tokens", type=int, default=0)
    submit.add_argument("--total-tokens", type=int, default=0)
    submit.add_argument("--notes", default="")
    submit.add_argument("--agent-output-file")

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("run_id")

    show = subparsers.add_parser("show")
    show.add_argument("run_id")

    summary = subparsers.add_parser("summary")
    summary.add_argument("experiment_id")

    intervention = subparsers.add_parser("intervention")
    intervention.add_argument("run_id")
    intervention.add_argument("kind")
    intervention.add_argument("detail")
    intervention.add_argument("--minutes", type=float, default=0)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.private_root:
        os.environ["HALF_HANDOFF_EXPERIMENT_PRIVATE_ROOT"] = args.private_root
    if args.runs_root:
        os.environ["HALF_HANDOFF_EXPERIMENT_RUNS_ROOT"] = args.runs_root

    # Settings are imported above for normal app compatibility. CLI overrides
    # update the singleton explicitly so a single invocation remains predictable.
    from config import settings

    if args.private_root:
        settings.HANDOFF_EXPERIMENT_PRIVATE_ROOT = args.private_root
    if args.runs_root:
        settings.HANDOFF_EXPERIMENT_RUNS_ROOT = args.runs_root

    if args.command == "list":
        value = list_experiments()
    elif args.command == "arms":
        value = secure_arm_options()
    elif args.command == "prepare":
        value = prepare_run(
            args.experiment_id,
            args.arm_id,
            model=args.model,
            max_attempts=args.max_attempts,
        )
    elif args.command == "prompt":
        value = get_run_prompt(args.run_id)
    elif args.command == "submit":
        agent_output = ""
        if args.agent_output_file:
            agent_output = Path(args.agent_output_file).read_text(encoding="utf-8")
        value = submit_manual_attempt(
            args.run_id,
            conversation_id=args.conversation_id,
            usage={
                "input_tokens": args.input_tokens,
                "cached_input_tokens": args.cached_input_tokens,
                "output_tokens": args.output_tokens,
                "reasoning_tokens": args.reasoning_tokens,
                "total_tokens": args.total_tokens,
            },
            notes=args.notes,
            agent_output=agent_output,
        )
    elif args.command == "evaluate":
        value = evaluate_run(args.run_id)
    elif args.command == "show":
        value = load_run(args.run_id)
    elif args.command == "summary":
        value = summarize_experiment(args.experiment_id)
    else:
        value = add_intervention(
            args.run_id,
            kind=args.kind,
            detail=args.detail,
            minutes=args.minutes,
        )
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
