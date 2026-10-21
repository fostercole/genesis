# Interviewer handoff: the tool-filter study

For another agent who has to describe this study to a Klaviyo interviewer. Numbers below are the locked ones. Do not round them into a better story. Do not reorder the 87-query result so the tuned 2B looks like it won.

**Say this before any chart.** Hosted Jev matched the frontier full-menu call on **57/87**. The tuned 2B matched on **55/87**. Hosted Jev is ahead on that comparison. A two-query gap on 87 queries is not a ranking to sell.

This checkout’s `main` does not contain `results/`. The retrieval table is in the store note `docs/hosted-jev-dev.md`. The 87-query checkpoint and the hosted-dev file are on GitHub branch `cursor/frontier-87-examples-b320` (commits below). Prefer those committed numbers. They agree with the store docs.

Remote: https://github.com/fostercole/genesis.git

---

## 1. The product claim

A 2B ranks tools. A frontier model still chooses.

The 2B does not emit a tool name. Each candidate gets one scalar from a Yes-minus-No head. Sort the scalars and cut. The frontier model then sees the short menu and makes the call. One forward scores a list. Nothing is decoded.

The cut used everywhere below is **k = 10**, locked on dev completeness before any official test scoring. Completeness@k is 1 only when **every** labeled tool is inside the cut. A tool that misses the cut cannot be called later.

What Cole is claiming is a before/after on that head: the same 2B, the same candidate lists, after one ToolRet QLoRA epoch. He is not claiming a general replacement for a frontier agent, and he is not claiming the tuned 2B beat hosted Jev at choosing the call.

## 2. Three Jevs

Interviewers mix these names. Keep them apart.

| Name | What it is | Training, as stated |
| --- | --- | --- |
| **Jev (TypeSafe, hosted)** | Proprietary decision API. This study’s hosted arm reported **jev-1.13.0**. Input **$0.042 / million tokens**. Output free. | TypeSafe names the method **RLCD**. Reward, optimizer, architecture, and data are not published. |
| **OpenJev (Loop, org `openjev`)** | Independent open-weights **~27B** decision model. Not TypeSafe. Not Zefan-Cai. Merged Qwen3.8-27B. CC BY-NC 4.0. | LoRA, then merge, on public web/desktop agent steps and public classification. Not RLHF, not DPO, not disclosed RLCD. |
| **Open-Jev (Zefan-Cai). Cole’s base is the 2B.** | Community scalar-head model. LoRA rank 8, alpha 16, plus a Yes-minus-No scalar head on `Qwen/Qwen3.5-2B`. Adapter, not a merged base. | **SFT.** Soft cross-entropy + **0.1 Brier**, then a temperature fit on a calibration split only. The README denies reproducing TypeSafe RLCD. |

A fourth name, **OpenJev-RLCD** ([arXiv:2609.38850](https://arxiv.org/abs/2609.38850), [code](https://github.com/ZimmyGao/openjev-rlcd)), is Gao and Wang’s paper on reasoning models (Qwen3-1.7B, GSM8K / MMLU-Pro). That is not how `ZefanCai/Open-Jev-2B` was trained. Their own framing: open Jev-style scorers are typically SFT plus temperature scaling, while TypeSafe’s RLCD algorithm stays undisclosed.

Canonical links:

- TypeSafe launch: https://typesafe.ai/blog/introducing-system-one-models-and-jev
- TypeSafe RLCD page: https://www.jevtypesafeai.com/jev/rlcd
- Loop 27B card: https://huggingface.co/openjev/openjev
- Loop build post: https://www.loopai.com/blog/building-openjev-in-five-days
- Zefan-Cai repo: https://github.com/Zefan-Cai/Open-Jev
- 2B card: https://huggingface.co/ZefanCai/Open-Jev-2B
- 27B v1.1 card: https://huggingface.co/ZefanCai/Open-Jev-27B-v1.1

### Where the base loss is in code

Genesis pins Open-Jev at commit `bd4118882f733574a3250a4b65fe4d884130c08b` (`OPEN_JEV_COMMIT` in `modal_h100_train.py` and `modal_t4_scorer_smoke.py`). Qwen revision `15852e8c16360a2fea060d615a32b45270f8a8fc`.

At that pin, the base objective is in upstream `jev/train.py` (lines 415–416 at that commit):

- The run identity requires `method == "independent_candidate_lora_nll_brier"`.
- The step loss is soft cross-entropy plus a Brier term: `-(target * logits.log_softmax(-1)).sum()`, then `args.brier_weight * ((logits.softmax(-1) - target) ** 2).sum()`.
- `--brier-weight` defaults to **0.1** (the argument in `jev/train.py` next to the other train flags).
- Temperature is fit afterward on the calibration split only (`fit_temperature` in the same file). The 2B card’s saved temperature is **1.518796342858676** on **512** calibration rows.
- The README Train section states the same recipe in words: soft cross-entropy + 0.1 Brier, temperature fitted only on calibration data, head started from the pretrained Yes-minus-No readout, each candidate an independent sequence. The README also says Open-Jev does not reproduce proprietary RLCD.

That base pass is one full pass over frozen `release-v2`: **20,204** optimizer steps, global batch 4, **80,816** consumed rows. The public redistributable train split is **79,116** rows (Wiki rows dropped). It is not byte-identical to the weights’ train set. Those rows are Choice / yes-no / Score decisions: support tickets, Snake, pixels, invoices, arithmetic. **None of them is a ToolRet tool row.** If asked “so it was already a tool router,” the answer is no.

Upstream file, for the interviewer who wants the line: https://github.com/Zefan-Cai/Open-Jev/blob/bd4118882f733574a3250a4b65fe4d884130c08b/jev/train.py

### Where Cole’s loss is in this repo

Cole did not keep training that soft-CE + Brier objective. The ToolRet round replaces it with paper-style **per-target NLL**. For each labeled target, softmax over **that target plus the row’s negatives only**. Other gold tools are not in that softmax, so two correct tools do not compete. Average the NLLs. Sort scalars at inference. No decoding.

In genesis:

- `toolret_smoke/loss.py` — `toolret_nll` (pure Python) and `toolret_nll_torch`.
- `tests/test_toolret_loss.py` — the check that other targets do not compete.
- `toolret_smoke/train_epoch.py` — one QLoRA epoch; imports `toolret_nll_torch`.
- `modal_h100_train.py` — the Modal H100 entrypoint. Refuses a non-H100. Stops a running epoch at an estimated **$28**, under a **$29** ceiling. No second epoch in that app.

The formula, with `sim` replaced by the scalar head, is the ToolRet objective (Shi et al., [arXiv:2503.01763](https://arxiv.org/abs/2503.01763), §7.2): negative log-likelihood of the target tools. The negatives are the ones stored on the row, mined by NV-Embed. Other gold tools stay out of that softmax.

## 3. Cole’s second LoRA round

Starting checkpoint: the released **Open-Jev-2B** adapter and scalar head. One epoch of **QLoRA** on ToolRet-train. Frozen 4-bit base. Trainable LoRA plus the head. Rank **8**, alpha **16** (the existing adapter, continued, not a new rank). Seed **0**. No hyperparameter sweep. No second epoch.

| Fact | Recorded value |
| --- | --- |
| Train / dev | **50,000** train rows / **2,000** held out from **ToolRet-train**. Official ToolRet **test was not touched**. |
| Steps | **3,125** optimizer steps. Effective batch **16** (50,000 / 16). That is one epoch. |
| Learning rate | Base and head **1e-4**. Warmup **94** steps (3% of 3,125), then linear decay. |
| First stage | **BM25 top 50**. Same lists for the original 2B, the tuned 2B, and hosted Jev. |
| Operating point | **k = 10**, locked on **dev completeness**. |
| GPU | One **NVIDIA H100 80GB HBM3**. The train function refuses any other GPU name. |
| App | https://modal.com/apps/fostercole/main/ap-laB3YZqG43nsGSdRH1iOyS |
| Cost gate, before the epoch | Measured **8617.8 tokens/s**. Estimate **$25.16**. Under the $29 line, so it launched. |
| What the step size did | Started at microbatch 2 with checkpointing off. OOM at step 8, shrink to microbatch 1. OOM again at step 1280, then gradient checkpointing on. Finished at microbatch 1, accumulation 16, checkpointing **true**. `oom_retries` **2**. |
| Loss | First logged step loss **3.0319301187992096**. Last step (3125) loss **0.02538099578303088**. The loss jumps between steps because each step is a different 16 rows. A near-zero reading mid-epoch is one batch, not a finished model. |
| Time | **13,411** seconds on the in-job clock (about 3 hours 44 minutes). The archived ledger line says the same duration. |
| Dollars | In-job estimate **$17.06578538963618**. The later archived line for this app is **$16.86 metered** and **$0 billed** after credit. Those are two measurements. Do not collapse them. The estimate never hit the $28 stop. |

Summary file the job wrote: `results/h100_train_summary.json`. The percent log that matches the last step is the store note `internal/h100-train-watch.md`.

Earlier H100 attempts did not become this epoch. One probe exited before the cost gate (`oom_after_probe`, app `ap-4nYlJxYoLzgu1LJZ0eD8qm`, 0 steps). A later image hit a Triton version guard on Hopper and was relaunched with Triton 3.7.1. The finished epoch is the app linked above.

The 2,000-row dev score of the original and tuned 2B, before hosted Jev was added, is a separate Modal job: https://modal.com/apps/fostercole/main/ap-Qs7Ask9JMGOE5f7NhihzE7. Archived cost **$4.75**. That number is not the hosted API bill and not the H100 train bill.

T4 scorer smoke, before any training: 32 dev rows, original checkpoint, zero optimizer steps. Archived cost about **$0.09**. Commit `b254c8bb18beaf78a4d7319d159efaec75f9e73b` on genesis `main`.

What this epoch did not do: refit Open-Jev’s temperature on ToolRet, train the rest of the ToolRet-train file beyond these 50,000 rows, sweep rank or learning rate, or run a second epoch. A low training NLL means the gold scored above **that row’s NV-Embed negatives**. It does not mean the gold rose in a BM25 top 50. That is why the dev table exists.

## 4. Two different problems

Do not answer “what’s the accuracy?” with one number.

| Eval | Question it answers | What it does not answer |
| --- | --- | --- |
| Dev retrieval on 2,000 BM25 top-50 rows | Did the **ToolRet labels** rise inside that 50? | Did an agent call them? |
| 87-query frontier agreement | Did the short menu still produce the **same call** as Qwen2.5-72B-Instruct on the full menu? | Whether the 72B was right. Whether ToolRet labels are Klaviyo tools. |

The full menu in the 87-query loop is the **same BM25 top 50**, not the whole ToolRet catalog. Filter arms keep **10** of those 50. The 72B never saw every tool in the corpus.

### Dev retrieval (ToolRet labels)

Same 2,000 rows. Same BM25 top-50 lists. Original and tuned rows are copied from `results/dev_bm25_top50.json` and were not rescored when hosted Jev was added. Hosted ranks are the API probabilities, highest first. Ties keep menu order. Top-1 is the fraction of rows whose rank-1 tool is a labeled positive.

Rows scored **2000 / 2000**. Rows failed **0**. The $5 cap did not prefix the run. Reported model **jev-1.13.0**. Pre-run estimate **$0.220540**. API spend **$0.218315**. Output tokens free. Exact values: `results/hosted_jev_dev.json` (the table rounds to four decimals). Commit `fd54b34f38db9a3b2cc1f9ae54446ad94f87ea62`.

| model | nDCG@10 | recall@3 | recall@5 | recall@10 | completeness@3 | completeness@5 | completeness@10 | top-1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original 2B | 0.4985 | 0.3971 | 0.5243 | 0.7080 | 0.2375 | 0.3495 | 0.5550 | 0.3155 |
| tuned 2B | 0.6878 | 0.6008 | 0.7229 | 0.8414 | 0.4105 | 0.5525 | 0.7225 | 0.5400 |
| hosted Jev | 0.6313 | 0.5582 | 0.6815 | 0.7849 | 0.3610 | 0.4995 | 0.6415 | 0.4785 |

**On this table the tuned 2B leads hosted Jev on every metric.** Hosted Jev leads the original 2B on every metric. That is retrieval against ToolRet labels. It is not the call-agreement result.

Two footnotes that stay out of the headline. The API’s own choice was probability rank 1 on **0.9940** of scored rows. If that choice is forced to rank 1 even when it was not the highest probability, the top-1 hit rate is **0.4795**, next to the probability-rank top-1 of **0.4785**. The table uses the probability ranking.

### Frontier call-agreement (87 queries)

Ground truth: the tool name **Qwen2.5-72B-Instruct** called when it saw the full menu (the BM25 top 50). Not ToolRet labels.

Model: `Qwen/Qwen2.5-72B-Instruct`, 4-bit AWQ, vLLM quantization `awq_marlin`, revision `698703eae6604af048a3d2f509995dc302088217`. One **H100** (`NVIDIA H100 80GB HBM3`). **n = 87**, **k = 10**.

How the arms differ:

- **Full menu.** The same 72B sees all 50. Its call is the ground truth, so this arm agrees with itself on **87/87**.
- **Keyword search, original Open-Jev-2B, tuned 2B.** Each arm shortens the menu to **10**. The **same 72B** is called again. Agreement means that second call matches the full-menu name.
- **Hosted Jev top 10.** This is **not** the 72B picking from Jev’s list. It is the hosted API’s **own** pick, compared with the 72B full-menu name.

| arm | matched the full-menu call | posted Modal dollars for that arm |
| --- | ---: | ---: |
| full menu | **87/87** | 0.957 |
| hosted Jev top 10 | **57/87** | 0.291 |
| tuned 2B top 10 | **55/87** | 0.344 |
| keyword search | **52/87** | 0.339 |
| original Open-Jev-2B top 10 | **48/87** | 0.330 |

Read the order. Hosted Jev is ahead of the tuned 2B. Keyword search sits between the tuned 2B and the original 2B.

Posted H100 spend for this comparison is **about $2.261**. The three posted app bills are the finished 8 at **$0.3617** (`ap-zPKUUqLg9jSfeMpiTWiqGU`), the continuation to 76 at **$1.4989** (`ap-URz7uchCramlcymRTDCGsl`), and the last 11 at **$0.4003** (`ap-DcwV72eFO60ohov7PjHkku`). Those three sum to about **$2.261**. The per-arm dollars in the table are the same total split across arms, not a second bill.

October billing, last recorded at that checkpoint: metered **$29.94**, credits **$29.87**, billed **$0**, about **$0.06** remaining. The billing API line written with the checkpoint was metered **29.9435**, credits **29.87**, billed **0**, remaining **0.0565**. That meter is the **workspace month** (train, dev scoring, smoke, failed probes, and this comparison). It is not the frontier spend. Do not describe $29.94 as the cost of the 87 queries.

Graph: `/cursor/stores/bc-c73881fc-461b-4a9f-9679-fb150ab43075/media/pi-cost-accuracy.png`

Also in the repo as `results/pi-cost-accuracy.png` on `cursor/frontier-87-examples-b320`. Title on the figure: `Qwen/Qwen2.5-72B-Instruct  n=87  k=10`. Y-axis: accuracy against the full-menu call. X-axis: Modal dollars for the arm. The lexical point is labeled **keyword search**. Do not call that point BM25 while pointing at the figure. The five labels on the figure are `full menu`, `hosted Jev top 10`, `tuned 2B top 10`, `keyword search`, and `original Open-Jev-2B top 10`.

The filename contains “pi”. The plotted comparison is this 72B menu. Describe the chart from the axis labels, not from the filename.

Checkpoint commit: `e18442ef5a99560a41f80e2eb6921246c26ad513` on `cursor/frontier-87-examples-b320`. Message: record the live balance and the three H100 bills for the 87-example checkpoint. Result file: `results/modal_frontier_loop.json`. Transcript of the calls: `results/frontier_transcripts.md`.

## 5. What was not measured

Not measured: Claude, latency, Voyage, the official ToolRet test.

Voyage `rerank-2.5` was in the plan as a paid rerank baseline. There is no locked Voyage score. Do not invent one. The official ToolRet test split was sealed on purpose: dev is 2,000 rows held out of train, and the test file was not scored. No latency distribution was recorded for the 2B or for the 72B.

## 6. Failure modes an interviewer will ask about

Lead with these if they ask what is wrong.

- **Small frontier n.** 87 queries. Hosted 57, tuned 55. That is two queries. It is not a stable ranking of the two systems. The sample was not pre-registered at 87. It grew 8, then 76, then 11 more, and stopped.
- **Two different questions.** The tuned 2B wins the label-ranking table and loses the call-agreement table. Quoting only nDCG@10 0.6878 answers a different question from 55/87. Name the ground truth every time.
- **Credit wall.** The 87-query job stopped because Starter credit was about **$0.06** from gone (`paused_for_balance`, remaining **0.0565**). It did not stop because the comparison was finished. Another GPU was not started. Posted frontier spend about **$2.261** against a month meter of **$29.94** and **$0** billed. The in-job train estimate (~$17.07) and the archived train meter ($16.86) are earlier lines inside that month, not extra frontier cost.
- **Label and chart churn.** There was an 8-query chart and a 76-query chart before this one. Labels overlapped and were pulled apart (commit `c809e8e` on the same branch: separate the 76-query labels). On the first 8, hosted Jev was described as the API’s own choice from the 50-tool menu. Cole required top 10 for new queries. The locked file is hosted Jev **top 10 on all 87**. When you point at the figure, the lexical arm is **keyword search**, even though the dev first stage and the candidate pool are BM25.
- **Hosted key.** The hosted arms need `JEV_API_KEY` in `.env`. An early pass paused because that value was empty. Later scoring, including the 2,000-row dev pass and the 87-query arm, ran with the key present. Do not print the key, the file, or the length. Do not commit `.env`.
- **A100 versus H100.** The posted 87-query comparison is the **H100** AWQ run above. An earlier live frontier app, `ap-jXnsjj4OHb7SyQlK56vRan`, had started inference on an **A100-80GB** and had scored on the order of 14 examples. A still earlier app had scored on the order of 50 and was stopped from the CLI. Those partial runs are not the 87. The training plan itself moved from an L4 to an H100 before the epoch. The finished train and the finished 87 both say H100. Do not attribute the 57/87 or the 55/87 to the A100 app.
- **BM25 is the ceiling.** If the gold tool is not in the 50, neither 2B can recover it, and completeness on that row is 0.
- **Negatives are NV-Embed’s mistakes.** The loss never sees the rest of the catalog. A model can look finished on the stored negatives and still drop a gold tool once the list is BM25’s 50.
- **ToolRet is not Klaviyo.** Web APIs, functions, and app tools. Composer, Customer Agent, and MCP-style catalogs were not in the training file.
- **One epoch, seed 0, no sweep.** Whether dev completeness was still climbing at step 3125 was not measured during training. The dev curve was scored after the epoch.
- **No calibration claim on ToolRet.** Cole sorts. He did not refit the 2B temperature for this dataset. NLL against mined negatives is not a proper score of “this tool is needed.”
- **Name collision.** “I RLCD’d OpenJev” is false. “The tuned 2B beats Jev” is false unless the sentence names the **dev label** table and immediately gives the **87-query** table, where hosted Jev is ahead.

## 7. Six lines Cole can say out loud

1. “A 2B ranks the tools, and a frontier model still makes the call. The 2B does not write a tool name. It scores each candidate with a scalar head, sorts, and cuts at 10.”
2. “Open-Jev-2B is supervised: soft cross-entropy plus a 0.1 Brier term, then a temperature on a calibration split. My second round is one epoch of QLoRA with per-target negative log-likelihood on ToolRet. That is not RLHF, and it is not TypeSafe’s RLCD. Loop’s 27B OpenJev is a different model.”
3. “On 2,000 held-out ToolRet-train rows, same BM25 top 50, the tuned 2B leads hosted Jev on every retrieval number: nDCG@10 0.6878 versus 0.6313 versus 0.4985 for the original, and the same order on recall at 3, 5, and 10, completeness at 3, 5, and 10, and top-1. That table is ToolRet labels. The official test set is still sealed.”
4. “On 87 queries the ground truth is what Qwen2.5-72B-Instruct called on the full menu. Hosted Jev’s top 10 matched that call on 57. My tuned 2B matched on 55. Keyword search matched on 52. The original 2B matched on 48. The full menu matches itself on 87. Hosted is ahead. I would not sell a two-query gap.”
5. “Those are different questions. The dev table asks whether the labeled tools rose inside BM25’s 50. The 87-query table asks whether cutting the menu to 10 still produced the same call. On the filter arms the same 72B picks again. Hosted Jev is the API’s own pick, compared with the 72B’s full-menu name.”
6. “Not measured: Claude, latency, Voyage, the official test. The 87 stopped because the Starter credit was about six cents from gone. One epoch, seed 0, no sweep. If BM25 never retrieved the tool, the 2B cannot put it back.”

Line 4 is the 87-query result. Do not let line 3 stand in for it.

## Repo pointers

GitHub: https://github.com/fostercole/genesis.git

Branch that holds the locked 87-query checkpoint and the hosted dev file: `cursor/frontier-87-examples-b320`

| Commit | What it records |
| --- | --- |
| `e18442ef5a99560a41f80e2eb6921246c26ad513` | Live October balance and the three H100 bills for the 87-example checkpoint. |
| `fd54b34f38db9a3b2cc1f9ae54446ad94f87ea62` | Hosted Jev on the 2,000-row dev BM25 list. |
| `e7faf52` | The 87 examples themselves, including hosted Jev, after the grant ran out. The balance commit sits on top of this. |
| `d7d8abde139d7ec7434a0bd11b408ceaa1a2c347` | The 76-example checkpoint, also reachable as `cursor/frontier-live-balance-c993`. Superseded by the 87. |
| `f4560094f229b27007bc44a3d461b70097a95a3a` | Hosted Jev added on the first 8 queries, branch `cursor/hosted-jev-top10-3198`. Superseded. Do not quote 0.75 from that file as the result. |
| `b254c8bb18beaf78a4d7319d159efaec75f9e73b` | T4 scorer smoke on `main`. |

Result files on `cursor/frontier-87-examples-b320`:

- `results/modal_frontier_loop.json` — 87-query arms, spend, billing snapshot.
- `results/frontier_transcripts.md` — the calls.
- `results/pi-cost-accuracy.png` — the figure.
- `results/hosted_jev_dev.json` and `results/hosted_jev_dev.md` — dev retrieval, exact floats.
- `results/dev_bm25_top50.json` — original and tuned 2B on the same 2,000 lists.
- `results/h100_train_summary.json` — the finished epoch (also on the `main` history that contains the train).

Training and loss files on `main`:

- `toolret_smoke/loss.py`
- `toolret_smoke/train_epoch.py`
- `modal_h100_train.py`
- `tests/test_toolret_loss.py`

Store copies used to check the tables: `docs/hosted-jev-dev.md`, `docs/interview-method-tradeoffs.md`. Graph file: `/cursor/stores/bc-c73881fc-461b-4a9f-9679-fb150ab43075/media/pi-cost-accuracy.png`.

Blob URLs, once the branch is on GitHub:

- https://github.com/fostercole/genesis/blob/cursor/frontier-87-examples-b320/results/modal_frontier_loop.json
- https://github.com/fostercole/genesis/blob/cursor/frontier-87-examples-b320/results/hosted_jev_dev.json
- https://github.com/fostercole/genesis/commit/e18442ef5a99560a41f80e2eb6921246c26ad513
- https://github.com/fostercole/genesis/commit/fd54b34f38db9a3b2cc1f9ae54446ad94f87ea62
