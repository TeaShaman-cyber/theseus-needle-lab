#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const claimPath = path.resolve(process.argv[2] ?? 'experiments/needle-stage-c-applicability/verification/stage-c-compute-claim.json');
const receiptPath = path.resolve(process.argv[3] ?? 'experiments/needle-stage-c-applicability/verification/generated/compute-verifier-receipt.json');
const rawDir = path.resolve(process.argv[4] ?? 'experiments/needle-stage-c-applicability/verification/generated/raw');
const claimBytes = readFileSync(claimPath);
const claim = JSON.parse(claimBytes);
const x = claim.inputs;
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const mcporter = path.join(repoRoot, 'verification/stage-c-sidecars/node_modules/.bin/mcporter');
const mcpClientPackage = 'mcporter@0.9.0';
mkdirSync(path.dirname(receiptPath), { recursive: true });
mkdirSync(rawDir, { recursive: true });

const sha = (value) => createHash('sha256').update(value).digest('hex');
const expectedManifest = claim.bindings.curriculum_manifest_sha256;
const manifestPath = path.join(repoRoot, 'experiments/needle-stage-c-applicability/manifests/stage-c-curriculum-manifest.json');
const actualManifest = sha(readFileSync(manifestPath));
if (actualManifest !== expectedManifest) {
  const receipt = {
    schema_version: 'theseus.needle.stage_c_compute_verifier.v1',
    authority: 'DIAGNOSTIC_ONLY', backend: null, status: 'INCONCLUSIVE_SIDECAR',
    reason: 'CLAIM_BINDING_MISMATCH', input_sha256: sha(claimBytes),
    expected_manifest_sha256: expectedManifest, actual_manifest_sha256: actualManifest,
  };
  writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
  console.log(JSON.stringify(receipt, null, 2));
  process.exit(0);
}

const normalizedExpected = {
  early_budget_equal: true,
  reduced_budget_equal: true,
  early_recovery_contrast: '3',
  reduced_recovery_contrast: '1',
  reduced_contrast_is_weaker: true,
  reduced_recovery_share_is_lower: true,
  reduced_total_training_exposure_is_lower: true,
};

function runMcporter(args, env = process.env) {
  return spawnSync(mcporter, args, { encoding: 'utf8', timeout: 50000, env });
}

function parseWolfram(stdout) {
  const envelope = JSON.parse(stdout);
  const textBlock = envelope?.content?.find?.((item) => item?.type === 'text');
  if (!textBlock || typeof textBlock.text !== 'string') throw new Error('Wolfram MCP response has no text block');
  const match = textBlock.text.match(/^Out\[\d+\]=\s*("(?:[^"\\]|\\.)*")\s*$/s);
  if (!match) throw new Error(`Unexpected Wolfram evaluator output: ${textBlock.text}`);
  return JSON.parse(JSON.parse(match[1]));
}

const wolframCode = `eaR=${x.early_arm_a_recovery_extras};eaO=${x.early_arm_a_ordinary_extras};ebR=${x.early_arm_b_recovery_extras};ebO=${x.early_arm_b_ordinary_extras};raR=${x.reduced_arm_a_recovery_extras};raO=${x.reduced_arm_a_ordinary_extras};rbR=${x.reduced_arm_b_recovery_extras};rbO=${x.reduced_arm_b_ordinary_extras};base=${x.base_train_rows};earlyEpochs=${x.early_epochs};reducedEpochs=${x.reduced_epochs};checks=<|"early_budget_equal"->(eaR+eaO==ebR+ebO),"reduced_budget_equal"->(raR+raO==rbR+rbO),"early_recovery_contrast"->ToString[InputForm[ebR-eaR]],"reduced_recovery_contrast"->ToString[InputForm[rbR-raR]],"reduced_contrast_is_weaker"->(rbR-raR<ebR-eaR),"reduced_recovery_share_is_lower"->(rbR/(rbR+rbO)<ebR/(ebR+ebO)),"reduced_total_training_exposure_is_lower"->((base+rbR+rbO)*reducedEpochs<(base+ebR+ebO)*earlyEpochs)|>;ExportString[checks,"RawJSON"]`;
const wolframRun = runMcporter(['call','https://agenttools.wolfram.com/mcp.WolframLanguageEvaluator','--args',JSON.stringify({code:wolframCode,timeConstraint:30}),'--output','json','--timeout','45000']);
const wolframRaw = wolframRun.stdout ?? '';
writeFileSync(path.join(rawDir, 'wolfram.json'), wolframRaw);

let backend = null;
let normalized = null;
let backendError = null;
let rawTransport = wolframRaw;
if (!wolframRun.error && wolframRun.status === 0) {
  try {
    normalized = parseWolfram(wolframRaw);
    backend = 'wolfram';
  } catch (error) {
    backendError = `wolfram_parse:${error.message}`;
  }
} else {
  backendError = `wolfram_transport:${wolframRun.error?.message ?? wolframRun.stderr?.trim() ?? `exit ${wolframRun.status}`}`;
}

if (!backend) {
  const tmp = mkdtempSync(path.join(os.tmpdir(), 'stage-c-sympy-'));
  const cfg = path.join(tmp, 'mcporter.json');
  writeFileSync(cfg, JSON.stringify({mcpServers:{sympy:{command:process.env.STAGE_C_SYMPY_PYTHON ?? 'python3',args:['-m','mcp_sympy'],description:'Stage C local SymPy fallback'}}}));
  const env = {...process.env};
  const calls = {};
  const expressions = {
    early_recovery_contrast: `${x.early_arm_b_recovery_extras}-${x.early_arm_a_recovery_extras}`,
    reduced_recovery_contrast: `${x.reduced_arm_b_recovery_extras}-${x.reduced_arm_a_recovery_extras}`,
    early_budget_equal: `(${x.early_arm_a_recovery_extras}+${x.early_arm_a_ordinary_extras}) == (${x.early_arm_b_recovery_extras}+${x.early_arm_b_ordinary_extras})`,
    reduced_budget_equal: `(${x.reduced_arm_a_recovery_extras}+${x.reduced_arm_a_ordinary_extras}) == (${x.reduced_arm_b_recovery_extras}+${x.reduced_arm_b_ordinary_extras})`,
    reduced_contrast_is_weaker: `(${x.reduced_arm_b_recovery_extras}-${x.reduced_arm_a_recovery_extras}) < (${x.early_arm_b_recovery_extras}-${x.early_arm_a_recovery_extras})`,
    reduced_recovery_share_is_lower: `Rational(${x.reduced_arm_b_recovery_extras},${x.reduced_arm_b_recovery_extras+x.reduced_arm_b_ordinary_extras}) < Rational(${x.early_arm_b_recovery_extras},${x.early_arm_b_recovery_extras+x.early_arm_b_ordinary_extras})`,
    reduced_total_training_exposure_is_lower: `(${x.base_train_rows}+${x.reduced_arm_b_recovery_extras+x.reduced_arm_b_ordinary_extras})*${x.reduced_epochs} < (${x.base_train_rows}+${x.early_arm_b_recovery_extras+x.early_arm_b_ordinary_extras})*${x.early_epochs}`,
  };
  try {
    for (const [key, expr] of Object.entries(expressions)) {
      const run = runMcporter(['--config',cfg,'call','sympy.sympy_simplify','--args',JSON.stringify({expr}),'--output','json','--timeout','20000'],env);
      if (run.error || run.status !== 0) throw new Error(run.error?.message ?? run.stderr?.trim() ?? `exit ${run.status}`);
      calls[key] = JSON.parse(run.stdout).result;
    }
    normalized = {
      early_budget_equal: calls.early_budget_equal === 'True',
      reduced_budget_equal: calls.reduced_budget_equal === 'True',
      early_recovery_contrast: calls.early_recovery_contrast,
      reduced_recovery_contrast: calls.reduced_recovery_contrast,
      reduced_contrast_is_weaker: calls.reduced_contrast_is_weaker === 'True',
      reduced_recovery_share_is_lower: calls.reduced_recovery_share_is_lower === 'True',
      reduced_total_training_exposure_is_lower: calls.reduced_total_training_exposure_is_lower === 'True',
    };
    backend = 'sympy';
    rawTransport = JSON.stringify(calls, null, 2);
    writeFileSync(path.join(rawDir, 'sympy.json'), `${rawTransport}\n`);
  } catch (error) {
    backendError = `${backendError ?? ''};sympy:${error.message}`;
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

const matches = backend ? Object.keys(normalizedExpected).every((key) => normalized?.[key] === normalizedExpected[key]) : false;
const receipt = {
  schema_version: 'theseus.needle.stage_c_compute_verifier.v1',
  authority: 'DIAGNOSTIC_ONLY',
  backend,
  status: backend ? (matches ? 'VERIFIED' : 'VERIFIER_DISAGREEMENT') : 'INCONCLUSIVE_SIDECAR',
  verifier_interface: backend === 'wolfram' ? 'https://agenttools.wolfram.com/mcp' : (backend === 'sympy' ? 'stdio:mcp-sympy==0.1.0' : null),
  mcp_client: mcpClientPackage,
  input_sha256: sha(claimBytes),
  curriculum_manifest_sha256: actualManifest,
  raw_transport_sha256: sha(rawTransport),
  normalized_result: normalized,
  expected_result: normalizedExpected,
  backend_error: backendError,
  scope_note: claim.does_not_establish,
};
writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
console.log(JSON.stringify(receipt, null, 2));
process.exitCode = 0;
