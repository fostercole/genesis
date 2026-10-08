---
cursor:
  subagentId: "bc-372d10fc-4356-5382-b972-9bca60d8a775"
---

# Tool filter: first-pass plan

Prices checked Thu Oct 8, 2026. Training-time hours are estimates. The dollar caps below are the controls. If an estimate is wrong, the cap stops the job.

Locked on Oct 8, 2026. The Air has 16 GB, so local scoring is bf16. Training is QLoRA on a Modal L4, because that is the CUDA stack and the Air does not run it. Pi’s agent is Claude Sonnet 5.5 at $2 / $10 per million tokens. There is no Modal account yet, and the $30 Starter credit is unused. First paid step is creating the account, then the one-hour T4 smoke. The credit pays Modal compute. It does not pay Sonnet or Voyage.

A Pi package, `pi-cursor-agent`, can log in with a Cursor account and claims to use the subscription. Do not build the study on that. The scatter needs token counts priced at Sonnet’s list price. If a trial returns those counts, label the chart “list price, carried by the Cursor login” and skip the Anthropic bill. If it does not return counts, use an Anthropic key and the $25 cap.

The Open-Jev training code is CUDA. If the local server does not start under Metal, the offline numbers still come from Modal, and the thirty-task loop can call a short Modal function for those scores. That is a fallback, not a new design.

Interview answers for this design are in [interview-fundamentals.md](interview-fundamentals.md).

## The job

An agent pastes every tool description into the prompt. The user needed two of them. A 2B decision model reads the request, scores the menu, and keeps a short list. A frontier model inside Pi then chooses from that short list.

This plan trains once, on ToolRet, then compares every version. There is no second training wave.

Versions in the comparison:

- BM25, the cheap first stage, with no neural reranker
- [ZefanCai/Open-Jev-2B](https://huggingface.co/ZefanCai/Open-Jev-2B) before this fine-tune
- the same 2B after one fine-tune
- Voyage `rerank-2.5`, same candidate list

The 27B general Jev is not in this plan. It needs an 80 GB GPU, and the 2B before-and-after comparison is the one that shows what the fine-tune did.

## Where the 2B runs

**Modal trains and runs the offline ToolRet eval.** A function rents the GPU only while the script is running, billed per second, and the job ends when the script exits. Use an L4 for the real train and the full eval. Use a T4 for the smoke run. Starter includes $30 of compute credit a month. Tokens on Modal’s shared endpoints are not part of that credit. This plan does not use shared endpoints.

**The Pi loop runs the 2B on the same machine as Pi.** Qwen3.5-2B in bf16 is about 4 GB of weights, plus a small LoRA. A 16 GB M1 Air can score a short list locally. An 8 GB Air is tight, because macOS already uses several of those gigabytes, so that machine wants a 4-bit copy for inference. The Open-Jev server listens on localhost. The extension calls that, then `setActiveTools`. Nothing in the loop needs a hosted GPU.

**The M1 Air does not train this run.** Scoring only stores the weights. Training also stores activations for every token in the sequence, and this checkpoint’s training code is CUDA. BitsAndBytes QLoRA does not run on the Mac. A fanless Air that did fit a batch of one would still take on the order of days for the 50,000-row epoch, and the laptop would be busy the whole time. Modal’s L4 does that epoch in hours, for about $13 at the cautious rate, and the Air stays free for Pi.

Baseten is a hosted copy of that same server. It is useful when the laptop cannot load the weights, or when a URL has to stay up after the laptop sleeps. It does not train the model, and it does not change the ToolRet numbers. Skip it for this project. The $8 that line used to cost stays in the cap.

## Prices used

GPU-only rates from [Modal’s pricing page](https://modal.com/pricing). CPU is $0.0000131 per core per second. Memory is $0.00000222 per GiB per second. A loaded L4 in this plan is 8 cores and 32 GiB: about **$1.43 per hour**. A loaded T4 is 4 cores and 16 GiB: about **$0.91 per hour**.

| Piece | Rate | Source |
| --- | --- | --- |
| Modal T4 GPU | $0.59 / hour | modal.com/pricing, Oct 8 2026 |
| Modal L4 GPU | $0.80 / hour | same |
| Modal loaded L4 (GPU + 8 cores + 32 GiB) | ~$1.43 / hour | GPU rate plus the CPU and memory rates on that page |
| Modal loaded T4 (GPU + 4 cores + 16 GiB) | ~$0.91 / hour | same |
| Voyage `rerank-2.5` | $0.05 / million processed tokens, first 200 million free | [Voyage pricing](https://docs.voyageai.com/docs/pricing) |
| Claude Sonnet 5.5, the model inside Pi | $2 / million input, $10 / million output | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |

Processed tokens for Voyage are `(query tokens × number of documents) + document tokens`.

## Budget

The planned spend is about **$64**, or about **$77** if the second epoch runs. The hard cap is $200. A running ledger, written down after every paid job, is part of the project. Stop rules are at the end. The Pi filter itself costs nothing, because it runs locally.

| Job | What you buy | Cost |
| --- | --- | --- |
| Smoke train, 2,000 rows, T4, about 1 hour | Modal | $1 |
| Main train, 50,000 rows, one epoch, L4 | Modal, budgeted at 9 hours | $13 |
| A second epoch, only if the dev curve is still climbing | Modal, another 9 hours | $0 or $13 |
| Offline eval of both 2B models, including one rerun | Modal L4, 3 hours | $5 |
| Voyage on the full test set | API. About 99 million tokens. Free if the account’s 200 million are unused | $0 to $5 |
| Pi loop, 30 tasks, three arms, one full rerun | Sonnet 5.5. The 2B filter is local | $25 cap |
| Failed jobs and a second smoke | Modal | $20 |
| **Planned total** | | **about $64, or about $77 if the second epoch runs** |

The 9-hour train figure is the cautious one. It assumes 50,000 packed examples, about 1,600 tokens each, 80 million tokens, and 2,500 tokens per second on an L4 during QLoRA. If the run is closer to 6,000 tokens per second, the same epoch is about 4 hours and about $6. Pay the actual bill. Do not start the full 206,000-row set. At the cautious rate that epoch is about 37 hours and about $53, and the 50,000-row run is the study.

The $30 Modal credit, if the account still has it, comes off the Modal rows. It is not extra permission to train longer.

## Data, fixed before any GPU spend

ToolRet-train has 205,826 rows. Each row is a query, an instruction, a set of target tools (2.31 on average in the paper’s train table), and a handful of hard negatives (the paper trains with 10; the stats table lists 5). Count whatever is in the file. The test set is 7,600 tasks against a corpus of about 43,000 tools. The test set does not hand you the negatives. You have to retrieve them.

Splits, written to disk before training:

- **Train:** 50,000 rows drawn from ToolRet-train, seed 0. This is the only training set.
- **Dev:** 2,000 different rows from ToolRet-train. Used to pick k and to decide whether a second epoch is worth it. Never trained on.
- **Test:** the official ToolRet test set. Touched once, after k is locked.

Truncate each tool to name, description, and parameter names. The paper’s average tool document is 164 tokens. A query plus instruction is about 100 tokens. Eight tools in one packed example fit in a few thousand tokens. The 2B checkpoint’s server flag is `--max-length 4096`. Drop a tool’s long example block before you drop a target.

## Step by step

### 1. Accounts and the ledger

Open Modal and Baseten. Put $200 in your head as the ceiling, and a note on your machine as the ledger: date, job name, GPU, hours, dollars. Confirm the Modal credit balance. Confirm whether the Voyage account still has free rerank tokens.

Install Pi, the [Open-Jev loader](https://github.com/Zefan-Cai/Open-Jev) (`pip install -e '.[train]'`), and download `Qwen/Qwen3.5-2B` at revision `15852e8c16360a2fea060d615a32b45270f8a8fc` plus `ZefanCai/Open-Jev-2B`. The 2B repo is a LoRA adapter (rank 8, alpha 16) and a scalar decision head. It is not a merged chat model. Plain `AutoPeftModel` generation does not apply that head.

### 2. Build the three splits on a laptop

No GPU. Download ToolRet-train and the ToolRet test split. Write `train_50k.jsonl`, `dev_2k.jsonl`, and a file that records the official test ids. Shuffle with seed 0. Print the average number of targets and negatives so the loss code matches the files.

### 3. Smoke the scorer

On a Modal T4, load the original checkpoint and score 32 dev rows. Each tool gets one scalar from the existing Yes-minus-No head. Check that two runs of the same row match, and that a higher score sorts earlier. If this fails, stop. Do not start training.

### 4. Baseline, original 2B, on the dev split

Still on Modal. For each dev query, take the BM25 top 50 from the ToolRet corpus. Score those 50 with the original 2B. Save scores. This file is the “before” row. It also tells you whether the untuned 2B already does the job.

BM25 is the same first stage for every neural model. The 2B never sees all 43,000 tools.

### 5. Train once

Modal L4, one process, QLoRA on top of the existing adapter, same scalar head. Details are in the training section. Watch dev completeness@5 every few hundred steps. Stop early if it flattens. Save the adapter.

### 6. Lock k on dev

Score the dev split with the tuned model, same BM25 top 50. Sweep k in {3, 5, 10}. Lock the smallest k whose completeness is within a point of the best. Write it down. The test set is still untouched. The talk uses this k. Also report nDCG@10, because that is the paper’s headline, at the paper’s cutoff.

### 7. Test, once

Modal L4. Same BM25 top 50 for every test query. Score with the original 2B and the tuned 2B. Send the same 50 documents to Voyage `rerank-2.5`. Compute nDCG@10, recall@k, and completeness@k for BM25 alone, original 2B, tuned 2B, and Voyage. One run. A second run only to replace a crashed job, not to pick a lucky seed.

### 8. Start the scorer on the laptop

Run the Open-Jev server twice, or once with a flag that switches checkpoints: original, then tuned. Bind it to `127.0.0.1`. The request is a query plus a list of tool texts. The response is a score per tool. Time one list of 20 tools and write that latency into the talk. The loop pays that latency on the machine, and pays no hosting bill.

### 9. Pi loop

Thirty tasks, three arms, Sonnet 5.5 as the agent. The section below is the protocol. Log every turn.

### 10. Plots, then the talk

Make the four graphics from the logs. Do this after the loop, not before. The presentation section says what each chart claims.

## Training

Start from the released Open-Jev-2B adapter and scalar head. Keep training both. A new head would make the before model and the after model different machines.

**Loss.** The ToolRet paper’s objective, on the scalar scores. For each target tool, a softmax over that tool plus the negatives in the row, then the average of those log-losses. Other targets are left out of that softmax, so they do not compete. This is one pass. There is no listwise hinge in this plan.

**Rows.** The 50,000-row train file. Each step uses the targets and the negatives stored in the row. Do not mine new negatives.

**Recipe, the part worth defending.**

- LoRA rank 8, alpha 16, the sizes already in the checkpoint. Train the existing adapter rather than stacking a second one.
- Learning rate 1e-4 on the adapter, 1e-4 on the scalar head, with a 3% warmup and a linear decay. If the loss spikes in the first 200 steps, drop both to 2e-5 and restart from the original checkpoint. Do not keep training through a spike.
- Effective batch 16. The L4 will tell you the microbatch. Gradient checkpointing on.
- Max length 4096. Pack one query and its candidates into one sequence the way the Open-Jev loader already scores a list. If a row does not fit, truncate tool text, and keep every target.
- One epoch. A second epoch only if dev completeness@5 rose by at least one point over the last fifth of the first epoch, and the Modal ledger for training is still under $30.
- Seed 0. One run. No sweep.

Dev completeness@5 is the early-stopping number. Compute it on the BM25 top 50, not on the easy negatives stored in the file. The stored negatives are what the loss sees. The BM25 list is what the eval sees. Stopping on the easy list will look finished while the real list is still wrong.

## Evaluation

Two measurements. They answer different questions. Both go in the talk.

**Offline, on ToolRet test.** Did the short list contain the tools the dataset marks as relevant?

- First stage: BM25 top 50, identical for every system.
- Systems: BM25 alone, original 2B, tuned 2B, Voyage `rerank-2.5`.
- Metrics: nDCG@10, recall at the locked k, completeness at the locked k. Completeness is the strict one: every target tool is inside the cutoff.
- Also record GPU seconds and Voyage tokens, so the quality chart has a cost chart beside it.

**Online, in Pi.** Did a shorter prompt still let the agent call the right tools, and what did that prompt cost?

Ground truth for the offline table is the ToolRet label. Voyage is a baseline, not a label. Sonnet’s tool call is the online outcome, not a replacement for the ToolRet label.

## Pi loop

Build a closed menu of 40 tools taken from the ToolRet corpus, registered as Pi tools, plus the four builtins `read`, `write`, `edit`, and `bash`, which stay on in every arm. Forty is large enough that the schemas cost real tokens, and small enough to run thirty tasks. This is a controlled menu, not the full 43,000. Say that in the talk. The offline table is the full-corpus result. The loop is the dollar result.

Write 30 tasks whose gold tools are inside those 40. A task is one user message that a person could type. Gold tools are the ToolRet targets for that query, restricted to the menu. Drop a query whose targets fall outside the 40.

Three arms, same tasks, same Sonnet 5.5, temperature 0:

1. **Full menu.** All 40 tools in the prompt. No filter.
2. **Original 2B.** BM25 to 20 within the menu, then the original model keeps k, plus the four builtins.
3. **Tuned 2B.** Same, with the tuned model.

The extension runs on `before_agent_start`. It calls the local Open-Jev server for that arm, then `setActiveTools`. Log, per turn: arm, task id, tool names kept, scores, input tokens, output tokens, tools the agent actually called, and whether every gold tool was among the calls. Cap each task at 6 turns. If it has not called the gold tools by then, it failed.

Token budget behind the $25 cap. A tool schema in this menu is about 250 tokens. Forty tools are about 10,000 tokens, plus about 1,500 for the rest of the prompt. Four turns is about 48,000 input tokens and, generously, 800 output tokens: about $0.10 a task on Sonnet 5.5. A filtered turn is about a third of that. Thirty tasks times three arms is about $6. The cap is $25 so a rerun and a longer task still fit. If the ledger for the loop crosses $25, stop and plot what you have.

Start the local server before the first task and leave it up for the session. Log its latency. There is no cold-start bill.

## Presentation

Ten minutes. Six beats. The charts exist only after step 9.

1. **The menu.** One screenshot of a Pi prompt with 40 tool schemas, and the token count. One sentence: this text is what you pay before the model does any work.
2. **The short list.** The same turn after the tuned 2B. The gold tools are marked. This is the product.
3. **Quality on ToolRet.** Grouped bars. X: BM25, original 2B, tuned 2B, Voyage. Y: nDCG@10, recall@k, completeness@k, three groups. Title states the locked k and that every bar reranked the same BM25 top 50.
4. **What the short list costs to build.** Bars or a labeled table. Dollars per 1,000 test queries for the original 2B, the tuned 2B, and Voyage. GPU time converted at the loaded L4 rate. Voyage converted at $0.05 per million, and annotated if it was inside the free 200 million. BM25 is a fourth bar near zero. The point is that the fine-tune’s quality has to be read next to a filter that is already cheap.
5. **The Pi loop, cost against quality.** A scatter with three points, one per arm. X: mean dollars of Sonnet input plus output per task, from the logged token counts at $2 and $10 per million. Y: fraction of the 30 tasks where every gold tool was actually called. Label each point with mean input tokens. If two filter arms land on top of each other in dollars, offset the labels, not the data.
6. **One failure.** A task where the tuned short list dropped a gold tool. Read the tool names. This is the limit of a filter: the agent cannot call what it was not shown.

Save the four numeric charts as images next to the talk. Chart 3 and chart 5 are the ones an interviewer will ask about. Chart 3 is retrieval quality. Chart 5 is whether the token cut kept the agent’s behavior.

Talk track for the result, filled in after the numbers exist:

- If the tuned 2B beats the original 2B on completeness@k, the fine-tune is the result.
- If it also matches or beats Voyage, say so, and show the cost bars.
- If it loses to Voyage on quality and wins on cost, say that. A cheaper filter that keeps the gold tools in the Pi loop is still the product.
- If the tuned model does not beat the original 2B, show the chart anyway. The baseline was the point of running it.

## Stop rules

- Ledger above **$40** before the test eval: skip the second epoch, run the test once, continue to Pi.
- Ledger above **$80** before the Pi loop: run the loop on 10 tasks, not 30, and say so on the scatter.
- Pi loop above **$25**: stop the loop and plot the finished tasks.
- Any single Modal job estimated over **$20** before launch: do not launch it. The full 206,000-row epoch is in this bucket. It does not get run.
- Absolute stop at **$200**.

## Left out on purpose

- A second training wave, hard-negative mining, and a listwise hinge. Later, only if the first pass clearly loses to the original 2B or to Voyage and the ledger is under $40.
- The 27B Jev. Different size, different machine, and it does not explain the fine-tune.
- Training on Sonnet’s or Fable’s tool calls. Those calls are not the ToolRet labels, and there are not enough of them.
- Baseten, and a Modal web endpoint inside the loop. The 2B scores on the laptop. Modal is done before the loop starts. Use Baseten only if the laptop cannot load about 4 GB of weights.
