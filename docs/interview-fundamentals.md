---
cursor:
  subagentId: "bc-372d10fc-4356-5382-b972-9bca60d8a775"
---

# What to be able to say

For the tool-filter study. Each answer is the one to give out loud.

## QLoRA

The base weights stay frozen and are stored in 4-bit. The only trained matrices are a low-rank update on top, kept in bf16. Optimizer state exists for those small matrices and not for the 2 billion frozen weights. That is why a 2B fits on a 24 GB L4.

LoRA writes the new weight as the original weight plus the product of two thin matrices. Rank 8 means each update has inner dimension 8. Alpha 16 scales that product by 16/8 = 2, so the update is not tiny relative to the frozen weight. Rank is capacity. Alpha is how hard the update is allowed to push.

The Mac has 16 GB, which is enough to hold the weights and score a list. It is the wrong place to train. The QLoRA implementation in this project uses bitsandbytes, and those 4-bit kernels are CUDA. A Mac can run a different 4-bit LoRA in MLX. That would be a second codebase, and a fanless Air would still take days for the same 50,000 rows. The study uses one QLoRA stack, on Modal.

If they ask what is quantized: the frozen base, not the adapter, and not the loss.

## The model does not write a tool name

The checkpoint is a scalar head on Qwen3.5-2B. Each option gets one number, from a Yes-minus-No style readout. Nothing is generated. Sorting those numbers and cutting at k is the short list. One forward scores the whole list, which is why a batch of requests is cheap next to a frontier model that has to read every schema.

A generator that emits the tool name would be a different project. It would need decoding, it would be slower, and a single generated name throws away the fact that ToolRet marks about 2.3 tools correct per query.

## The loss

For each correct tool, take a softmax whose classes are that one tool plus the negatives in the row. The loss is the average negative log-likelihood of those softmaxes. The other correct tools are left out of that softmax. They each get their own term, so every correct tool is trained, and none of them is treated as a wrong answer for the others.

One softmax over the whole row would make the correct tools fight. Probability mass given to the first correct tool would be taken from the second. The cutoff later needs both of them near the top.

k is not in the loss. After training, sort by the scalar and cut. k is chosen on the dev split, from {3, 5, 10}, and then frozen before the test set is scored.

## The three metrics

They answer different questions. An interviewer who hears only one of them will ask for the other.

Recall at k is the fraction of the correct tools that landed inside the cutoff. Two correct tools, one inside the top 5: recall is one half.

Completeness at k is 1 only when every correct tool is inside the cutoff. The same example scores 0. This is the number that matches the product. A missing tool cannot be called later.

nDCG at 10 cares where a correct tool sits, not only whether it is inside a cutoff. Rank 1 is worth more than rank 10. It is the headline number in the ToolRet paper.

A model can have strong nDCG and weak completeness: the tools it finds are ranked first, and it still drops one. Report all three. The locked k is the operating point. nDCG@10 stays at 10 so it can be compared with the paper.

## Why BM25 runs first

The 2B never reads all 43,000 tools. Its context is 4096 tokens, and it was trained on a query plus a handful of negatives. At test time BM25 proposes 50 tools. The 2B, the original checkpoint, and Voyage all rerank that same 50. BM25 alone is a bar on the chart, so the reranker’s lift is visible.

If someone says the fine-tune should have searched the corpus by itself, the answer is that search and rerank are different jobs, and this training set only teaches the second.

## The negatives are someone else’s mistakes

The negatives in the file were retrieved by NV-Embed. They are tools that embedding model ranked too high. The loss teaches the 2B to rank the correct tools above those. It does not teach it about every other tool in the corpus.

That is why dev completeness is measured on BM25’s 50, not on the negatives stored in the row. The stored list is easier and is a different retriever. A model can look finished on the training negatives and still drop a correct tool once the candidate list changes. That gap is the result to watch.

## What the filter can break

Sonnet only sees the tools the 2B kept, plus read, write, edit, and bash. If a correct tool is cut, the agent cannot call it. No later turn puts it back. The Pi log records two different facts: whether the correct tool was still on the menu, and whether Sonnet actually called it. The scatter uses the call. Be ready to say the menu number too, because a miss on the menu and a miss by Sonnet are different failures.

## The baseline

The original row is the same 2B, same head, before this fine-tune. Beating Voyage does not show that training did the work. The untuned 2B might already have been fine. Beating the original 2B, on the same 50 candidates, is the claim that the weight update mattered.

ToolRet’s labels are the tools the source datasets marked relevant. They are not a recording of Sonnet calling tools. Sonnet is the agent in the loop. It is not the training target.

## A prompt already works

Sonnet, shown all 40 schemas, can pick the tool. This project does not say otherwise. The claim is that most of those schemas can be removed, the bill drops, and the call still happens. The offline table is whether the 2B learned the labeled tools. The scatter is whether the token cut kept the agent’s behavior.

## Overfit, and why 50,000 rows

One epoch, seed 0, no hyperparameter sweep. The dev curve decides whether a second epoch is worth the money. k is locked on dev. The official test set is scored once. Early stopping watches completeness on the BM25 list, not on the stored negatives.

The full 206,000-row file is real. One cautious epoch of it is on the order of $50 and is banned by the stop rule. Fifty thousand rows is the study. If completeness is still climbing at the end of the epoch and the training ledger is under $30, a second epoch of the same 50,000 is allowed. A bigger draw from the file is not.

## The Pi menu is not the corpus

The loop uses 40 tools copied out of the ToolRet corpus, plus the four builtins. That is so the schemas match the kind of text the model trained on, and so thirty tasks have a known correct set. It is not Pi’s real skill list, and it is not an MCP catalog. The retrieval claim is the ToolRet test set. The dollar claim is this closed menu. Say both. A question about skills and MCP servers gets the honest answer: those catalogs were not in the training file, and this week does not pretend they were.

## Where the money goes

Modal bills the GPU, the cores, and the memory while a script is running. The loaded L4 is about $1.43 an hour. The smoke is a T4 for about an hour. The Starter credit, $30, applies to that compute once the account exists. It does not apply to Sonnet or to Voyage.

Sonnet is $2 per million input tokens and $10 per million output tokens. The loop is capped at $25. The chart multiplies logged tokens by those rates.

Voyage `rerank-2.5` is $0.05 per million processed tokens, and the first 200 million on an account are free. Processed tokens count the query once per document, plus the documents.

The 2B next to Pi, on the Air, adds no line item.

## If the tuned model loses

To the original 2B: the fine-tune did not help, and the chart stays in the talk. The baseline was there so this outcome is visible.

To Voyage, while beating the original 2B: the update helped, and a commercial reranker is still stronger. The cost bars then matter. A cheaper filter that still keeps the gold tools in the Pi loop is a result. A cheaper filter that drops them is not.

The next experiment, only if the ledger is under $40, would be a second pass: negatives mined by this 2B, and a loss that requires the worst correct tool to outrank the best negative. That pass is not in this run.
