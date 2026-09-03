#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const claimPath = path.resolve(process.argv[2] ?? 'experiments/needle-realistic-sft/verification/stage-b-acceptance-canary.json');
const receiptPath = path.resolve(process.argv[3] ?? 'experiments/needle-realistic-sft/verification/generated/wolfram-canary-receipt.json');
const rawPath = path.resolve(process.argv[4] ?? 'experiments/needle-realistic-sft/verification/generated/wolfram-canary-raw.json');
const claim = JSON.parse(readFileSync(claimPath, 'utf8'));
const x = claim.inputs;
const wolframCode = `baseCorrect=${x.base_heldout_correct}; replicaCorrect=${x.replica_heldout_correct}; trainCorrect=${x.train_correct}; trainTotal=${x.train_total}; baseReach=${x.base_route_calls}; replicaReach=${x.replica_route_calls}; baseNoCall=${x.base_negative_no_call}; replicaNoCall=${x.replica_negative_no_call}; dominant=${x.dominant_decision_count}; validCalls=${x.valid_heldout_route_calls}; checks=<|"heldout_improvement"->(replicaCorrect-baseCorrect>=6),"train_accuracy"->(trainCorrect/trainTotal>=7/10),"reachability_degradation"->(replicaReach>=baseReach-3),"negative_no_call_degradation"->(replicaNoCall>=baseNoCall-2),"dominant_decision_cap"->(dominant/validCalls<=7/10)|>; ExportString[<|"checks"->checks,"all_pass"->And@@Values[checks],"heldout_improvement_count"->replicaCorrect-baseCorrect,"train_accuracy_exact"->ToString[InputForm[trainCorrect/trainTotal]],"dominant_exact"->ToString[InputForm[dominant/validCalls]]|>,"RawJSON"]`;

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const mcpClientPackage = 'mcporter@0.9.0';
const mcporter = path.join(repoRoot, 'verification/stage-b-sidecars/wolfram/node_modules/.bin/mcporter');
const args = [
  'call',
  'https://agenttools.wolfram.com/mcp.WolframLanguageEvaluator',
  '--args', JSON.stringify({ code: wolframCode, timeConstraint: 30 }),
  '--output', 'json', '--timeout', '45000'
];
const run = spawnSync(mcporter, args, { encoding: 'utf8', timeout: 50000 });
const raw = run.stdout ?? '';
mkdirSync(path.dirname(receiptPath), { recursive: true });
mkdirSync(path.dirname(rawPath), { recursive: true });
writeFileSync(rawPath, raw);

function parseMcporter(stdout) {
  const envelope = JSON.parse(stdout);
  const textBlock = envelope?.content?.find?.((item) => item?.type === 'text');
  if (!textBlock || typeof textBlock.text !== 'string') throw new Error('Wolfram MCP response has no text block');
  const match = textBlock.text.match(/^Out\[\d+\]=\s*("(?:[^"\\]|\\.)*")\s*$/s);
  if (!match) throw new Error(`Unexpected Wolfram evaluator output: ${textBlock.text}`);
  return JSON.parse(JSON.parse(match[1]));
}

const base = {
  schema_version: 'theseus.needle.stage_b_wolfram_canary.v1',
  claim_id: claim.claim_id,
  verifier_kind: 'WolframLanguageEvaluator',
  verifier_interface: 'https://agenttools.wolfram.com/mcp',
  mcp_client: mcpClientPackage,
  input_sha256: createHash('sha256').update(readFileSync(claimPath)).digest('hex'),
  wolfram_code_sha256: createHash('sha256').update(wolframCode).digest('hex'),
  raw_transport_sha256: createHash('sha256').update(raw).digest('hex'),
  raw_transport_path: path.relative(process.cwd(), rawPath),
  transport_exit_code: run.status,
  scope_note: claim.does_not_establish,
};

let receipt;
try {
  if (run.error || run.status !== 0) throw new Error(run.error?.message ?? run.stderr?.trim() ?? `exit ${run.status}`);
  const normalized = parseMcporter(raw);
  receipt = { ...base, transport_status: 'OK', normalized_result: normalized };
  if (!normalized.all_pass) process.exitCode = 1;
} catch (error) {
  receipt = { ...base, transport_status: 'VERIFIER_ERROR', normalized_result: null, error: error.message };
  process.exitCode = 2;
}
writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
console.log(JSON.stringify(receipt, null, 2));
