# Secure handoff ablation experiment v2

This runner prevents successor agents from reading the canonical handoff or
private evaluator. It replaces the legacy collaboration-repository filtering
flow for controlled experiments.

## Isolation model

- Canonical handoff and hidden tests live under
  `HALF_HANDOFF_EXPERIMENT_PRIVATE_ROOT`.
- A run copies the fixture without `.git`, sibling runs, or collaboration data.
- HALF filters the canonical handoff before prompt generation.
- Codex receives only the filtered prompt and the copied source workspace.
- Private tests execute outside the Agent step.
- Omitted-field trace markers are scanned in Agent logs to flag contamination.

Each experiment run must use a new Codex conversation. HALF does not launch or
sandbox Codex. The operator opens the generated workspace in a fresh
conversation and gives that conversation the filtered run prompt.

## Arms

The secure runner defines a full arm, six leave-one-field-out arms, and a
no-handoff negative control:

```text
A_full
B_no_goal
C_no_changed_files
D_no_verification
E_no_unfinished_items
F_no_risks
G_no_next_steps
H_no_handoff
```

## CLI

```powershell
$env:HALF_HANDOFF_EXPERIMENT_PRIVATE_ROOT='D:\experiments\private'
$env:HALF_HANDOFF_EXPERIMENT_RUNS_ROOT='D:\experiments\runs'

python tools/run_handoff_experiment.py list
python tools/run_handoff_experiment.py prepare reservation-v2 A_full --model gpt-5.5
python tools/run_handoff_experiment.py prompt <run-id>
python tools/run_handoff_experiment.py submit <run-id> --conversation-id <id> --total-tokens <count>
python tools/run_handoff_experiment.py show <run-id>
python tools/run_handoff_experiment.py summary reservation-v2
```

After every Agent attempt, `submit` runs public and private pytest suites.
Failed test names are reduced to probe identifiers and returned as a repair
prompt for the same conversation. A new experiment run must always start in a
new conversation; repair attempts stay in that run's conversation.

## Metrics

Each run records:

- first-attempt and final resolved status;
- public and hidden test pass counts;
- per-field probe pass counts;
- interaction rounds and rework count;
- changed and forbidden files;
- Codex input, cached input, output, reasoning, and total tokens;
- human intervention and infrastructure retry events;
- omitted-field canary contamination.

Infrastructure failures must be recorded with kind `infra_retry`; they do not
increase human intervention cost.
