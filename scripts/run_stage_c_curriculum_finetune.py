#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import pickle

import numpy as np

NEEDLE_RUNTIME_CONTRACT = "cactus-needle==2.0.8"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run continuous two-phase Needle Stage C curriculum finetuning.")
    p.add_argument("--early-jsonl", required=True)
    p.add_argument("--reduced-jsonl", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--lora-rank", type=int, default=16)
    p.add_argument("--lora-alpha", type=float, default=32.0)
    p.add_argument("--max-len", type=int, default=256)
    p.add_argument("--val-split", type=float, default=0.1)
    p.add_argument("--early-out", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--checkpoint-dir", default="checkpoints")
    return p.parse_args()


def _load_policy(path: str, early_path: str, reduced_path: str, total_epochs: int) -> list[dict]:
    policy = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if policy.get("schema_version") != "needle-stage-c-curriculum-policy-v1":
        raise ValueError("unsupported Stage C curriculum policy")
    phases = policy.get("phases")
    if not isinstance(phases, list) or [p.get("name") for p in phases] != ["early", "reduced"]:
        raise ValueError("Stage C requires exact early and reduced phases")
    if sum(int(p["epochs"]) for p in phases) != int(total_epochs):
        raise ValueError("curriculum epoch total mismatch")
    return [
        {**phases[0], "path": early_path},
        {**phases[1], "path": reduced_path},
    ]



def _write_adapter(path: str, lora: dict, scale: float, checkpoint: str, rank: int, policy_path: str, phase: str) -> None:
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        pickle.dump(
            {
                "lora": {"/".join(p): {"A": np.asarray(v["A"]), "B": np.asarray(v["B"])} for p, v in lora.items()},
                "scale": float(scale),
                "base": checkpoint,
                "rank": rank,
                "stage_c_policy": pathlib.Path(policy_path).name,
                "stage_c_phase": phase,
            },
            handle,
        )

def main() -> None:
    # Adapted narrowly from cactus-needle 2.0.8 finetune_local: one LoRA and
    # optimizer are kept alive while two preregistered datasets run sequentially.
    import jax
    import jax.numpy as jnp
    import optax
    from needle.model.architecture import SimpleAttentionNetwork
    from needle.model.run import load_checkpoint
    from needle.model.finetune import (
        fit_max_len,
        get_tokenizer,
        init_lora,
        load_jsonl,
        lora_target_paths,
        merge_lora,
    )

    args = parse_args()
    phases = _load_policy(args.policy, args.early_jsonl, args.reduced_jsonl, args.epochs)
    np.random.seed(args.seed)

    params, config = load_checkpoint(args.checkpoint)
    config.dtype = "float32"
    params = jax.tree.map(lambda a: np.asarray(a).astype(np.float32), params)
    backend = jax.default_backend().lower()
    if backend == "metal":
        config.flash = False
        config.remat = False
        config.scan_unroll = config.num_layers
    params = jax.device_put(params)

    tokenizer = get_tokenizer(config.vocab_size)
    phase_max = [fit_max_len(phase["path"], tokenizer, args.max_len) for phase in phases]
    max_len = max(phase_max)

    prepared = []
    for phase in phases:
        seqs, masks = load_jsonl(phase["path"], tokenizer, max_len)
        if len(seqs) == 0:
            raise SystemExit("no usable examples in " + phase["path"])
        n_val = min(int(len(seqs) * args.val_split), len(seqs) - 1)
        val_seqs = val_masks = None
        if n_val > 0:
            order = np.random.default_rng(0).permutation(len(seqs))
            seqs, masks = seqs[order], masks[order]
            val_seqs, val_masks = seqs[:n_val], masks[:n_val]
            seqs, masks = seqs[n_val:], masks[n_val:]
        prepared.append({**phase, "seqs": seqs, "masks": masks, "val_seqs": val_seqs, "val_masks": val_masks})

    model = SimpleAttentionNetwork(config)
    paths = lora_target_paths(params)
    scale = args.lora_alpha / args.lora_rank
    lora = init_lora(params, paths, args.lora_rank, jax.random.PRNGKey(0))

    total_steps = 0
    for phase in prepared:
        count = len(phase["seqs"])
        steps_per_epoch = -(-count // args.batch_size)
        total_steps += int(phase["epochs"]) * steps_per_epoch
    warmup = min(max(1, total_steps // 20), total_steps - 1)
    schedule = optax.warmup_cosine_decay_schedule(
        init_value=0.0,
        peak_value=args.lr,
        warmup_steps=warmup,
        decay_steps=total_steps,
    )
    optimizer = optax.chain(optax.clip_by_global_norm(1.0), optax.adamw(schedule))
    opt_state = optimizer.init(lora)

    def loss_fn(lora_state, ids, mask):
        logits = model.apply({"params": merge_lora(params, lora_state, scale)}, ids)
        logits, targets, mask = logits[:, :-1], ids[:, 1:], mask[:, 1:]
        ce = optax.softmax_cross_entropy_with_integer_labels(logits, targets)
        return (ce * mask).sum() / jnp.maximum(mask.sum(), 1.0)

    @jax.jit
    def train_step(lora_state, optimizer_state, ids, mask):
        loss, grads = jax.value_and_grad(loss_fn)(lora_state, ids, mask)
        updates, optimizer_state = optimizer.update(grads, optimizer_state, lora_state)
        return optax.apply_updates(lora_state, updates), optimizer_state, loss

    eval_step = jax.jit(loss_fn)
    step_i = 0
    print(f"runtime {NEEDLE_RUNTIME_CONTRACT}")
    print(f"backend {backend} total_steps {total_steps} max_len {max_len}")
    for phase in phases:
        phase = next(item for item in prepared if item["name"] == phase["name"])
        seqs, masks = phase["seqs"], phase["masks"]
        count = len(seqs)
        print(f"phase {phase['name']} rows {count} epochs {phase['epochs']}")
        for epoch in range(int(phase["epochs"])):
            order = np.random.permutation(count)
            last = 0.0
            for start in range(0, count, args.batch_size):
                idx = order[start:start + args.batch_size]
                lora, opt_state, loss = train_step(
                    lora, opt_state, jnp.asarray(seqs[idx]), jnp.asarray(masks[idx])
                )
                last = float(loss)
                step_i += 1
            if phase["val_seqs"] is not None:
                values = [
                    float(eval_step(lora, jnp.asarray(phase["val_seqs"][i:i + args.batch_size]), jnp.asarray(phase["val_masks"][i:i + args.batch_size])))
                    for i in range(0, len(phase["val_seqs"]), args.batch_size)
                ]
                print(f"phase {phase['name']} epoch {epoch + 1}/{phase['epochs']} loss {last:.4f} val {float(np.mean(values)):.4f}")
            else:
                print(f"phase {phase['name']} epoch {epoch + 1}/{phase['epochs']} loss {last:.4f}")
        if phase["name"] == "early":
            _write_adapter(args.early_out, lora, scale, args.checkpoint, args.lora_rank, args.policy, "early")
            print(f"early_adapter {args.early_out}")

    os.makedirs(args.checkpoint_dir, exist_ok=True)
    _write_adapter(args.out, lora, scale, args.checkpoint, args.lora_rank, args.policy, "final")
    print(f"adapter {args.out}")


if __name__ == "__main__":
    main()
