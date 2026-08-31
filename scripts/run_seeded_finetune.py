#!/usr/bin/env python3
import argparse
import pathlib

import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run pinned Needle finetune with an explicit NumPy epoch-shuffle seed.")
    p.add_argument("jsonl_path")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--lora-rank", type=int, default=4)
    p.add_argument("--lora-alpha", type=float, default=32.0)
    p.add_argument("--max-len", type=int, required=True)
    p.add_argument("--val-split", type=float, default=0.1)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--checkpoint-dir", default="checkpoints")
    args = p.parse_args()
    args.generate = 0
    args.model = None
    args.workers = 1
    return args


def main() -> None:
    from needle.model.finetune import finetune_local

    args = parse_args()
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    np.random.seed(args.seed)
    print(f"  {'seed':<9} numpy_global {args.seed}", flush=True)
    finetune_local(args)


if __name__ == "__main__":
    main()
