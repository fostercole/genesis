# Tool filter

A 2B scorer keeps a short tool list before a frontier agent sees the menu. The study design is in [docs/tool-filter-research-plan.md](docs/tool-filter-research-plan.md). Training, when it happens, is QLoRA on a Modal H100. This checkout does not start that run.

## T4 scorer smoke

The smoke loads the released Open-Jev-2B checkpoint on a Modal T4 and scores 32 dev rows twice. It checks that the two runs match and that a higher score sorts earlier. It does not train.

```bash
python prepare_dev_smoke.py
python -m unittest tests/test_smoke_checks.py
modal run modal_t4_scorer_smoke.py
```

`prepare_dev_smoke.py` needs the public ToolRet training set (`mangopy/ToolRet-Training-20w`) and writes `data/dev_smoke_32.jsonl` plus the seed-0 id lists. The Modal profile must already be logged in. The function refuses any GPU other than a T4, and its timeout caps the GPU bill near half a dollar.

Results land in `results/t4_scorer_smoke.json`. After a paid run, append a line to `ledger.jsonl`.
