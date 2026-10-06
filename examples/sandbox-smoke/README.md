# sandbox-smoke — minimal pilot project

A tiny Python project used to prove the Phase 0 loop end-to-end *before* a real repository is
onboarded: rulebook + ignore files are present, and `./test.sh` returns **exit 0 on success and
exit 1 on failure** (checklist #7 — the self-heal loop depends on this).

```bash
./test.sh                       # → exit 0
SMOKE_FORCE_FAIL=1 ./test.sh    # → exit 1 (simulates a red test for the self-heal loop)
```

It is also the `sandbox-smoke` entry in `config/projects.yaml`, the target of
`make webhook-test`, and the project the daily synthetic check (design §8.4) will use.
Copy it to `workspace/sandbox-smoke/` (or push it to a GitLab test project) to use it with agents.
