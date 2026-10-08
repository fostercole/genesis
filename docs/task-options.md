---
cursor:
  subagentId: "bc-372d10fc-4356-5382-b972-9bca60d8a775"
---

# Post-training demo: task options

For Cole. Interview is about one week out from Thu Oct 8, 2026 (Klaviyo AI engineering intern). This doc walks four tasks that clear the bar, plus a short drop list. It does not pick a task, a stack, or a training recipe.

The tool-filter project he is actually running has its own step-by-step plan, with the budget and the Modal / Baseten split: [tool-filter-research-plan.md](tool-filter-research-plan.md).

Live demo is a laptop before/after. He also has to discuss tradeoffs, why each design choice, and what he would improve. Experience so far is LoRA/QLoRA and ML classes, no post-training project yet. Code tasks are out. Budget is a $200 hard cap, lower is better: a small open model, LoRA/QLoRA, a few GPU-hours.

## The four projects, as scenes

Same shape every time. A small model already talks. He shows it a pile of public examples of one job. On the laptop, the “before” answer has a specific, obvious mistake. The “after” answer fixes that mistake. A program, not the interviewer’s taste, counts how often.

Think of post-training as three lessons he could give that model later. Week one is only the first lesson plus the demo. The task has to be able to support the other two afterward.

1. **Copy the right answer.** Show the model inputs paired with a good output. This is supervised fine-tuning.
2. **Prefer this draft over that one.** Show pairs where one answer is the better of the two.
3. **Practice against a checker.** The model writes attempts, a program scores them, and training pushes the score up. Math has an answer key. The other tasks have a label or a rule a program can apply.

**A. Write the text, but only from the product card.** A marketer has a card: Brooks Ghost, $140, no sale. The untuned model sends “GHOSTS 40% OFF THIS WEEKEND” and blows the 160-character text limit. After training, the text names the shoe, stays short, and every number in it is a number from the card. This is the closest thing to Klaviyo’s campaign writer. The score is “obeyed the card and the channel,” which is real and checkable. It is a claim about honesty and format. Public data does not say whether anyone would have opened that text.

**B. Press the button the employee handbook allows.** A customer says “just refund me” or “I want 30% off.” The shoe-store guide says confirm the order before a refund, and the promo cap is 15%. The untuned model does what the customer asked. After training, the next action matches what a trained agent actually did in that chat. This is the closest thing to Klaviyo’s support agent. The score is “right button,” already labeled by people. The reply’s tone is a separate, mushier question. Leave tone alone for the demo. The obvious version of this demo is also the one a strong model can do by reading the handbook in its system prompt. See the note under task B before treating this as a training project.

**C. Tell an exact product from a near miss.** Someone searches “waterproof trail runners.” One result is that shoe. One is a different waterproof runner. One is waterproof socks. One is a lamp. People already labeled those four relationships. The untuned model calls the near miss an exact match, or ranks the lamp first. After training, the label or the order moves toward the human labels. The laptop looks like a search result, not a message. The score is the cleanest commerce number in this set, because the labels are human judgments, not a rule he invented.

**D. Get the final number right.** Contrast only. “A bat and a ball cost $1.10…” The untuned model writes a fluent paragraph and ends on the wrong number. After training, the final number matches the key. Anyone in the room can check one problem by hand. It looks nothing like Klaviyo. It is here because the score is the hardest one to argue with, and because small models still miss these.

The question at the end is which of those four mistakes he wants on the laptop. The rest of this doc is the evidence under each scene: data, the exact score, what a later lesson would need, and how the week or the $200 breaks.

## What Klaviyo’s AI actually does

As of mid-2026 the public product is two agents on one customer profile, plus the older copy helpers.

- **Composer** (announced Mar 24, 2026; public beta Jun 30, 2026) takes a plain-language brief and drafts a campaign or flow: audience, timing, and channel copy. Channels called out include email, SMS, mobile push, WhatsApp, and RCS. Nothing sends until a person approves. Their own example is a lapsed-customer reactivation across email and text. Sources: [Composer newsroom, Mar 24, 2026](https://www.klaviyo.com/newsroom/composer), [agents newsroom, Jun 30, 2026](https://www.klaviyo.com/newsroom/CRM-agents), [Composer product page](https://www.klaviyo.com/composer), [launch blog](https://www.klaviyo.com/blog/klaviyo-composer-customer-agent-launch).
- **Customer Agent** handles service across web chat, email, SMS, RCS, and WhatsApp, including order tracking, returns and exchanges, subscription edits, and loyalty lookup. Resolved chats write preferences and intent back onto the profile Composer uses. Same sources as above.
- **SMS / campaign helpers** generate on-brand text from a prompt, and a separate feature tests message variants. Source: [AI for SMS](https://www.klaviyo.com/solutions/ai/sms-marketing).

A task is Klaviyo-shaped when the laptop shows one of those jobs: channel copy grounded in a product and an audience, or a support action that has to follow a policy. Product search relevance is commerce-adjacent. Grade-school math is not.

## Bar used to keep a task

Kept only if all of these hold:

- An automatic metric an interviewer can recompute. ROUGE, BLEU, and “an LLM said it was better” do not count.
- Plenty of public data, with a name, a size, a license, and a link.
- A visible before/after on a laptop.
- Trainable inside a week on a small model with LoRA/QLoRA, inside about $200.
- Room for 2–3 later stages (for example SFT, then a preference method, then a verifier or reward). This doc names which stages the data can support. It does not pick the stages.

Prices below were checked Oct 8, 2026. They are list rates, not a quote, and they move.

| Platform | What the rate is | Figure | Source |
| --- | --- | --- | --- |
| Modal | GPU only, per second. CPU and memory are extra. Starter plan includes monthly compute credit. | L4 about $0.80/hr, L40S about $1.95/hr, A100 40GB about $2.10/hr, A100 80GB about $2.50/hr, H100 about $3.95/hr | [modal.com/pricing](https://modal.com/pricing) |
| Tinker (Thinking Machines) | LoRA only, per million tokens: prefill, sample, train. SFT and RL. Checkpoint storage $0.10/GB-month. Current small end of the catalog is about 4B–8B, not a 0.5B. | Qwen3-8B: train $0.44, sample $0.60, prefill $0.195. Qwen3.5-4B: train $0.737, sample $1.005. GPT-OSS-20B: train $0.396, sample $0.45. | [Models and pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/models_and_pricing/) |
| Baseten | Per minute of wall-clock for serving and for training jobs. Instance price includes CPU and RAM. | H100 $0.10833/min (about $6.50/hr). An L4 instance is about $0.85/hr (`L4:4x16` at $0.01414/min). | [Instance list](https://docs.baseten.co/deployment/resources), [billing](https://docs.baseten.co/organization/billing) |

Rough bands, same for every task, so the per-task notes only say what pushes a task out of band:

- One SFT pass on a few tens of thousands of short examples: about **$5–40**.
- A preference pass on pairs that are already built: about **$10–50**.
- A short verifier loop with short outputs: about **$20–120**.
- The same loop with long traces, many samples, or many iterations: **past $200**.

Illustration, not a plan: 20k examples × 512 tokens is about 10M train tokens, about $4.40 on Tinker’s Qwen3-8B train rate. 5k prompts × 4 samples × 256 tokens × 5 rounds is about 26M sample tokens, about $15 at $0.60/M. 7.5k prompts × 8 samples × 1,024-token solutions × 15 rounds is about 900M sample tokens, about $550 at that same rate. The second loop is how the cap breaks. A few hours on a Modal L40S is about $6–20 of GPU before CPU and memory.

Platform fit is a note, not a vendor pick. He has no accounts yet. Modal fits “bring a small model and a training script.” Tinker fits “write the data and the loss, they run LoRA,” and only for models on that price sheet. Baseten fits serving the before/after and also bills training by the minute; the H100 rate is the expensive way to spend this budget.

## Snapshot

| Task | Laptop before → after | Metric the interviewer can recompute | Klaviyo | Stages the data can support | Usual way it breaks |
| --- | --- | --- | --- | --- | --- |
| A. Catalog-grounded channel copy | SMS or subject invents a discount or runs long → stays on the product card and inside the channel limit | Deterministic checker: length, required brand, no number that is not on the card | Strong. This is Composer’s copy step. | SFT, preference, verifier | Claiming open-rate lift, or a checker that is easy to game |
| B. Retail policy agent | Agent offers a 30% promo the guide caps at 15%, or refunds before validating the order → next action matches the guide | Exact action accuracy; cascading success if he wants the whole turn | Strong. This is Customer Agent, on a shoe retailer. | SFT, preference, verifier | Scoring intent (already ~90% in 2021) instead of the action |
| C. Shopping relevance | A substitute is labeled Exact → the label or the rank moves | 4-way micro-F1, or nDCG with published gains | Partial. Product choice, not the message. | SFT, preference, verifier | Training the full 2.6M-row multilingual set in week one |
| D. Math, contrast only | Wrong final number → right final number | Exact match on the final answer | Weak. Allowed only because math was not banned. | SFT, preference, outcome verifier, and a process reward if he uses PRM800K | GSM8K on a 3B+ instruct model that is already in the 80s–90s, or an RL sample bill |

## A. Catalog-grounded channel copy

The model is a junior marketer who has the product card and still invents a sale. Training teaches it to write only what the card supports, inside one text or one subject line.

**Demo.** Same product card in, two drafts out. Before: an SMS over the character budget, or a percent-off that the card never states. After: brand is present, length fits the channel, and every number on the draft appears on the card. A small scoreboard shows pass rate on a held-out slice.

**Data.**

- Primary text: [Amazon Shopping Queries / ESCI](https://github.com/amazon-science/esci-data), Apache-2.0. Each judgment includes product title, description, and bullets (also brand and color). Large release: 130,652 queries, 2,621,738 judgments. English slice of that release: 97,345 queries, 1,819,105 judgments. Products repeat across queries, so dedupe before training. Paper: [arXiv:2206.06588](https://arxiv.org/pdf/2206.06588).
- Optional larger catalog, license not granted: [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/) (McAuley Lab), 48.19M items and 571.54M reviews, May 1996–Sep 2023. Metadata includes title, feature bullets, description, price, and a details dict. The lab says it cannot assign a license and releases the data primarily for research ([HF discussion](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1)). A third-party “non-commercial” file on a trimmed mirror is not the official terms. Fine for a class project if he accepts that gap. ESCI is the clean default.
- There is no public corpus of real lifecycle email/SMS with open or click labels at a size worth training on. See the drop list.

**Metric.** A program checks three things on the model’s string: channel length (SMS at 160 characters is the obvious one; subject length is his call), the brand string from the card appears, and any number in the draft also appears on the card. Re-running the checker on the same outputs gives the same score.

What he can claim: constraint pass rate and unsupported-number rate. What he cannot claim: open rate, click rate, or “better marketing.” An interviewer who says “compliance is not persuasion” is right. The answer is that persuasion labels do not exist in public at this scale, and the checker is the claim.

**Klaviyo.** This is the Composer moment: a brief plus a product, channel-specific copy, a person still approves the send. It is not audience building, send-time, or A/B winner selection. Those need outcome logs he does not have.

**Stages the data can support.**

- **SFT.** Needs input fields (title, brand, bullets, description) and a target string. The product description is a real target for “write from the card.” Channel limits are not labeled in ESCI; they enter as instructions in the prompt.
- **Preference.** Needs pairs. No public human preference set for this copy. Pairs can be built from the checker (pass vs fail) or from a small set he labels himself. Say that out loud: constructed pairs teach the checker, they do not teach taste.
- **Verifier / reward.** Needs the same checker, plus the source card. No learned reward model is required for this claim. A learned judge of “which SMS is more persuasive” would need labels he does not have, and an interviewer can dismiss it.

**Cost and what blows it.** SFT on a deduped English slice, short outputs, sits in the $5–40 band. The week goes if he tries to download all of Amazon Reviews 2023 (the full HF release is on the order of 750GB) or if he designs a checker, a judge model, and three training stages. The budget goes if the verifier stage samples long emails for many rounds. Keep outputs to a subject line or one SMS.

**Design choice to defend.** What the checker counts as faithful. Exact string match misses a true paraphrase and also misses a sneaky reworded discount. He should be able to say why he chose string match, what it gets wrong, and what a later version would add (normalized attributes, a banned-claim list) without pretending the v1 score is persuasion.

**Platform note.** Short sequences. Modal or Tinker both fit an SFT or preference pass. Baseten is a natural place to host the live before/after, and a costly place to explore on an H100.

## B. Retail policy agent (ABCD)

The model is a new support hire who wants to be helpful and skips the handbook. Training teaches the next button a real agent pressed, given the customer’s words and the store’s rules.

**Demo.** A customer asks for 30% off, or for a refund on an order that has not been validated. Before: the model emits the customer’s request as the next action. After: the next action is the one the agent guide allows (promo at the allowed amount, or validate-purchase before refund). Show the guide sentence next to the action so the room can see the rule.

**Data.** [Action-Based Conversations Dataset](https://github.com/asappresearch/abcd), MIT. Paper: [NAACL 2021](https://aclanthology.org/2021.naacl-main.239/). 10,042 human–human chats with an online retailer’s agent, 8,034 of them in the train split reported in the paper’s Table 2. 55 intents, 30 actions, 231 slots, about 22 turns per dialogue, about 3.7 actions per train dialogue. Dev and test splits are in `abcd_v1.1.json`. The agent guidelines are part of the release. This is one shoe-store policy, not 200,000 brands. It is enough text for a week of LoRA. It is not web-scale.

**Metric.** Action accuracy: the predicted action matches the labeled action. Paper Table 3 (Action State Tracking): pipeline 32.3%, BERT 59.5%, ALBERT 59.2%, RoBERTa 65.8%. Value accuracy for RoBERTa is 67.2%. Cascading dialogue success (partial credit across the remaining steps) tops out at 31.9% for RoBERTa-Large versus 82.7% human (Table 4). Intent accuracy in that same table is already about 89–90%. Those baselines are 2021 encoders, not chat LLMs. A current 1B–8B instruct model may walk in higher. Measure the base model before promising a big jump. The number itself is exact match, so the interviewer cannot wave it off. They can ask whether exact action match is the same as a good reply. It is not. Utterance ranking in this dataset is Recall@k over 100 canned replies, which is a weaker demo.

**Klaviyo.** Customer Agent’s retail skills are this shape: returns, order status, subscriptions, with a policy in the middle and a write-back to the profile. ABCD has the policy and the action labels. It does not have Klaviyo’s profile store, and the domain is one retailer from 2021. Composer-style campaign copy is a different task (A).

**Stages the data can support.**

- **SFT.** Needs dialogue context, the guideline text, and the labeled next action plus slot values. Utterance text is there too if he later wants the reply, but the clean label is the action.
- **Preference.** Needs pairs of actions or partial trajectories. He can build them from the labels: the annotated action versus a plausible wrong one (the customer’s requested discount, a refund before validation). No separate preference corpus is required.
- **Verifier / reward.** Needs the action id and slot values, which are labeled. Exact match is the reward. Cascading success is a sparser reward over the rest of the dialogue. A learned reward is optional, not required, for the action claim.

**Cost and what blows it.** SFT on 8k dialogues is inside the cheap band if he trains on the action turn rather than full 22-turn generations. The week goes to learning the 30-action ontology and the cascading metric, or to overfitting one store’s guide and then discovering the demo only works on that guide. The budget goes if a later RL stage rolls out full chats (long context × many samples). Prefer the single next-action label until a later stage.

**Could a system prompt do this?** Yes, for the demo as written. ABCD is one shoe-store handbook, short enough to paste. A strong instruction-following model (Fable, or anything in that class) with that handbook in the system prompt, plus a list of legal buttons, will often refuse the 30% promo and refuse to refund before validation. There is no published Fable score on ABCD, so this is a prior, not a measurement. He should assume an interviewer will try the paste in the room. If the pasted model gets the chat right, the fine-tune has not earned its place.

Leaving the handbook out of the prompt does not answer that. It turns the project into “memorize one 2021 manual,” which is a worse product. Klaviyo would put the brand’s policy in the prompt or retrieve the relevant paragraph. The 2021 paper’s own ablation is about BERT, not a 2026 chat model: cascading success was 30.6% with the guidelines in the input and 31.3% without. That only shows “paste the guide” was not a free win for BERT. It says nothing about Fable.

The handbook idea stays a training project only if a measurement says the prompt is not enough:

- Run the same held-out chats three ways before training anything: small model with the handbook in the prompt, small model without it, and a frontier model with the handbook and the button list in the prompt. The laptop story is the gap that is left.
- The gap worth training is usually not the one-line rule. It is a later turn, where the customer keeps pushing and the model agrees, or the model explains the rule in prose and still emits a button name the software cannot call. Cascading success in the paper is about 32% against a human 82.7%. That gap is the interesting one. The single “30% off” screenshot is the one prompting eats.
- A real reason to train a small model anyway, even if Fable is right: every support chat would otherwise send the whole handbook to a frontier API. That is a cost, latency, and data-leaving argument. It is a good interview sentence only after he has shown that the small model, after training, actually catches the cases the prompt missed. If the prompted frontier model is already at the ceiling, this task is the wrong demo.

Task A has the same shape. “Stay under 160 characters, include the brand, do not invent a number” is a system prompt. Task C is a judgment people made, not a short rule, so a prompt can state the definitions and still miss the near-miss cases. Task D is a skill. Pasting instructions does not hand a 0.5B model the answer key.

**Design choice to defend.** Score the next button, not the helpfulness of the prose. And say, in the first minute, why this is not “paste the handbook into Fable.” The honest version is a measured gap on multi-step chats or on exact button names. The weak version is one screenshot of a 30% discount.

**Platform note.** Context is a few thousand tokens, not 100k. Modal is the straightforward fit, including a sub-4B model. Tinker works if the base model is on the current list (Qwen3-8B at 32k context is enough). Baseten serving is a good live demo; training on H100 burns the cap faster than L4/L40S elsewhere.

## C. Shopping relevance (ESCI)

The model is picking what to put in front of a shopper. It confuses “almost the same product” with “the product they asked for.” Training teaches the distinction people already marked on millions of Amazon search results.

**Demo.** One shopper query, a handful of products. Before: a substitute (same need, different product) is called Exact, or an irrelevant item ranks first. After: the label or the order matches the human judgments more often. The scoreboard is micro-F1 or nDCG on a fixed query set, computed in the room if the slice is small.

**Data.** Same [ESCI release](https://github.com/amazon-science/esci-data) as task A, Apache-2.0. Use it here for the human labels, not for writing copy.

- Reduced set (harder queries kept): 48,300 queries and about 1.12 million judgments (repo README: 1,118,011; paper table: 1,118,170). English in that set: 29,844 queries, 601,462 judgments.
- Large set: 130,652 queries, 2,621,738 judgments. English: 97,345 queries, 1,819,105 judgments.
- Locales: English, Spanish, Japanese. Labels: Exact, Substitute, Complement, Irrelevant.
- Train and public test are query-stratified. Paper: [arXiv:2206.06588](https://arxiv.org/pdf/2206.06588).

Plenty of data. Week one only needs the English train split, and not all of it.

**Metric.** Two published ones, both recomputable from the labels.

- Task 1, ranking: nDCG. Gains in the paper are 1.0, 0.1, 0.01, and 0.0 for Exact, Substitute, Complement, Irrelevant. Public-test baselines in Table 4: BM25 0.563 overall (English 0.675; Japanese 0.136 pulls the average down). Neural row: 0.852 overall, English 0.857 with a fine-tuned cross-encoder, Spanish 0.849 and Japanese 0.840 with MPNet. The repo’s earlier BERT note lists nDCG 0.83 for task 1. Cite the paper’s Table 4 if he quotes a number.
- Task 2, 4-way classification: micro-F1. Frozen BERT MLP in Table 4: 0.656 overall, 0.685 English. Macro-F1 in the repo baseline table is 0.23 against micro-F1 0.62, which is the class-imbalance story he should know before he quotes micro-F1 alone.

These baselines are rankers and classifiers, not generative LLMs. A chat model asked to emit a label can start well below 0.85. That gap is the demo. nDCG and micro-F1 are not hand-wavy. The gain vector is a choice, and micro-F1 hides rare classes. Both are fair interview questions, and both have a concrete answer.

**Klaviyo.** Real, and narrower than A or B. Klaviyo recommends products inside campaigns and flows. Deciding Exact versus Substitute versus Irrelevant is that decision with the message stripped off. It will not look like Composer or Customer Agent on the laptop. It will look like a scoreboard. Use it when he wants the argument to be about the number.

**Stages the data can support.**

- **SFT.** Needs query, product text, and the E/S/C/I label (classification) or a target order (ranking). All of that is in the release.
- **Preference.** Needs pairs. For a query, a higher-nDCG ordering versus a worse one, or Exact versus Irrelevant as chosen and rejected. Built from the judgments. No extra human study.
- **Verifier / reward.** Needs those same judgments. Label exact-match or nDCG of a produced ranking is the reward. A generative “explain the label” variant can still be checked against the label. A learned reward is optional.

**Cost and what blows it.** Subsampled English SFT is the cheap band. The week blows by training every locale and all 2.6M rows, or by building a full retrieval stack (candidate generation plus ranker) instead of a rerank or a label over a given short list. The budget blows if a reward stage generates long rationales for every judgment. Score the label or the order. Keep the rationale for the laptop, not for the training loop.

**Design choice to defend.** nDCG with the paper’s gains, versus micro-F1 on the four labels. nDCG matches “what should the email feature first.” Micro-F1 matches “did you name the relation correctly” and is easier to explain in five minutes. Macro-F1 is the honest companion number because Complement and Irrelevant are rarer. He should pick one primary number and show the other as a check.

**Platform note.** Same as A: short text, any of the three platforms can train or serve a small LoRA. The dataset is large on disk relative to ABCD; downloading and deduping is the time cost, not the GPU.

## D. Math word problems (contrast only)

The model sounds sure and lands on the wrong number. Training teaches it to land on the number in the answer key. Labeled contrast on purpose. He did not ban math. The score is the cleanest of the four, and the Klaviyo story is the weakest. This is a reasoning demo, not a marketing task that happens to contain numbers.

**Demo.** A grade-school word problem. Before: a fluent solution with the wrong final number. After: the final number matches the key. The room checks one problem by hand and the scoreboard checks the rest.

**Data.**

- [GSM8K](https://huggingface.co/datasets/openai/gsm8k), MIT. 7,473 train, 1,319 test. Final answers are the metric. Step-by-step solutions are the SFT targets.
- Harder set, same task family: [MATH](https://github.com/hendrycks/math), MIT. 7,500 train, 5,000 test, each with a worked solution. Paper: [arXiv:2103.03874](https://arxiv.org/pdf/2103.03874).
- Process labels, only if a later stage needs them: [PRM800K](https://github.com/openai/prm800k), MIT, about 800,000 step-level labels on solutions to MATH. The release uses a nonstandard split and holds out 500 MATH test problems. Easy to contaminate the official MATH test if he ignores that note.

**Metric.** Exact match on the final answer. An interviewer can recompute it. They can still argue that a correct number with a bad derivation is a miss. That is the process-versus-outcome point, and PRM800K exists so he can talk about it without inventing a labeling scheme. They cannot argue that exact match is subjective.

Published Qwen2.5 scores, so he does not pick a saturated starting point by accident ([Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/); the page’s math protocol is GSM8K 4-shot and MATH 4-shot):

| Checkpoint | GSM8K | MATH | License note |
| --- | --- | --- | --- |
| Qwen2.5-0.5B base | 41.6 | 19.5 | Apache-2.0 |
| Qwen2.5-0.5B-Instruct | 49.6 | 34.4 | Apache-2.0 |
| Qwen2.5-1.5B base | 68.5 | 35.0 | Apache-2.0 |
| Qwen2.5-1.5B-Instruct | 73.2 | 55.2 | Apache-2.0 |
| Qwen2.5-3B base | 79.1 | 42.6 | Qwen Research license, not Apache |
| Qwen2.5-3B-Instruct | 86.7 | 65.9 | Qwen Research license |
| Qwen2.5-7B-Instruct | 91.6 | 75.5 | Apache-2.0 |

A 7B instruct model at 91.6 on GSM8K is a bad before/after. Headroom on GSM8K sits at 0.5B–1.5B, or on MATH at those sizes. His eval should be the same protocol before and after. Do not compare his 0-shot run with their 4-shot table.

**Klaviyo.** None, beyond “the team does measured post-training.” Say that in the first minute if this is the task, then spend the time on the method.

**Stages the data can support.**

- **SFT.** Needs questions and worked solutions. GSM8K and MATH both have them.
- **Preference.** Needs a correct solution and a wrong one. He can sample wrong traces, or use PRM800K’s positive versus negative steps on MATH. Sampled pairs are outcome-level. PRM800K is step-level and human.
- **Verifier / reward.** Needs the final-answer key. That is outcome supervision, and it does not need a learned reward model. A process reward needs step labels (PRM800K) or a checker he trusts less than the answer key.

**Cost and what blows it.** SFT on 7.5k short problems at 0.5B–1.5B is the bottom of the cost band on a Modal L4 or L40S. The budget breaks on RL: math traces are long, and the sample-token illustration above is this task. The week breaks by chasing GSM8K leaderboard numbers on a model that started at 85, or by mixing PRM800K’s test problems into training and then reporting the official MATH test.

**Design choice to defend.** Final-answer exact match versus step correctness, and GSM8K versus MATH. Exact match is the demo. MATH is where a slightly larger model still has room. Also defend base versus instruct as the start: a base 0.5B makes the before look worse and the method look more responsible for the gain.

**Platform note.** The interesting starting models (0.5B, 1.5B) are not on Tinker’s price sheet as checked Oct 8, 2026. That sheet starts around Qwen3.5-4B, Qwen3-8B, and GPT-OSS-20B. Those are a better MATH bet than a GSM8K bet, and their sample rates make a sloppy RL loop the expensive option. Modal (or Baseten’s cheaper L4, not an H100) is the fit for a sub-4B QLoRA run.

## Considered and dropped

- **Open-rate subject lines.** [XCampaign](https://huggingface.co/datasets/zidcenek/XCampaignDataset) (CIKM 2025) has 14,908,085 interaction rows, 131,918 users, 160 mailshots, global open rate 9.09%. It does not provide the email text as a training target. A 400-row A/B file is too small. Public “subject line” sets in the 5k–60k range that turned up are synthetic or unlabeled for outcomes. Fails “plenty of public data” for a copy model with an outcome metric.
- **AESLC subject-line generation.** [Yale-LILY/aeslc](https://huggingface.co/datasets/Yale-LILY/aeslc), 14,436 / 1,960 / 1,906, Enron internal mail. Upstream license [CC BY-NC-SA 4.0](https://github.com/ryanzhumich/AESLC). The usual metric is ROUGE. Wrong domain, and ROUGE is hand-wavy. Fails the metric bar.
- **IFEval as the task.** [google/IFEval](https://huggingface.co/datasets/google/IFEval), Apache-2.0, 541 prompts, 25 verifiable constraint types. The checker is excellent. The set is an eval, not a training corpus. Fails “plenty of public data” as a thing to train on. The constraint idea is already inside task A.
- **MAVE attribute extraction.** [google-research-datasets/MAVE](https://github.com/google-research-datasets/MAVE): 2.2M products, about 3M attribute-value annotations, 1,257 categories. Labels are public; the product text requires a separate Amazon Review Data (2018) request. The repo is archived and the license field is “Other.” Span F1 would be a stronger metric than task A’s string checker, and the join can eat the week. Drop unless that text is already in hand.
- **Synthetic marketing email/SMS sets** (for example Marketing-Emails at 16,440 rows, sms-synthetic at 5,000). Too small, and model-written. A demo trained on them is easy to dismiss.

## What a system prompt cannot do

Niche and unseen is the wrong test. A frontier model is good at reading a document it has never trained on. The shoe-store handbook is niche, and that is why pasting it works. If the job is “apply this text,” unfamiliar text is an argument for a prompt, not for a training run. Public niche datasets are also a bad bet for “the labs have not seen this”: ABCD and GSM8K have been on the internet for years.

A prompt fails when there is nothing to paste.

- **The behavior is a skill, and this model does not have it.** You can write “solve the problem step by step” at the top of a 0.5B model and it still ends on the wrong number. The context does not install the procedure. A frontier model already has the procedure, so prompting Fable solves the user’s math problem by using Fable. It does not teach the small model. This is task D. Take it only if the interview claim is “here is a weight update on a model a prompt does not fix,” not “Fable could not do this.”
- **The right answer was never written as a rule.** Exact versus substitute is a pile of human judgments, not a paragraph of definitions. You can paste the definitions. The close calls are still in the labels. This is task C. A prompted frontier model may already be good at it. Spend an hour on that bake-off before spending the week. If Fable is already near the ceiling, the same objection is back.
- **The signal does not fit in one customer’s context.** “What should we show this person” often depends on what similar customers did, across a catalog too big to paste. One shopper’s history is context, and a frontier model can guess from it. The rest of the customer base is the part a prompt never sees. That is a different project from A–D: next purchase from public review histories (Amazon Reviews 2023, same license caveat as in task A). The score is a hit rate against what they actually bought next. The laptop is a product suggestion changing, which is quieter than an SMS. Klaviyo sells this kind of prediction. An interviewer can still say “use a recommender, not an LLM.” The defense is that titles and reviews are text, and a pure id model is the baseline to beat. No baseline number is claimed here.

Cost and latency are a fourth reason people train, and they are real at Klaviyo’s volume. They are not an answer to “could a prompt do this.” A prompt on Fable does it. Training is how you stop paying Fable to do it. Say that only after the small model actually works.

## Ideal project

Asked for a pick. This is the pick.

**Teach a small model to tell an exact product from a near miss, on the hard English slice of ESCI.** The definitions of Exact, Substitute, Complement, and Irrelevant go in the system prompt of the before model and stay there after training. The prompt is not the thing being tested. The human labels are.

Why this one:

- The handbook and the SMS rules are documents. He already saw that a frontier model can read them. This judgment was never a document. Pasting the four definitions is the whole instruction, and the close calls are still in the labels.
- Math is the cleaner skill demo, and the wrong interview. Fable already solves it, and a Klaviyo loop will spend the hour on whether he understands their product. “What should this campaign feature” is that product with the copy stripped off.
- Next-purchase-from-everyone-else is the purest “it does not fit in the prompt” story, and the worse week: the Amazon review license is unsettled, the laptop is a product id changing, and the fair baseline is a recommender, not a chat model.

What the laptop shows: one hard query, four products. Before, the near-miss shoe is called Exact. After, it is called Substitute, and Complement stops getting swallowed by the majority class. The scoreboard is macro-F1 first, micro-F1 second. Micro-F1 alone lets a model that says Exact for everything look smart. Published floor, not a target: frozen BERT micro-F1 about 0.68 English on the public test, and the repo’s macro-F1 on the four-way task is about 0.23. Those are 2022 classifiers. A prompted frontier model will beat them. The week is about the gap that remains on the reduced set, which was built by dropping the easy queries (48,300 queries, about 1.12 million judgments, English 29,844 queries; Apache-2.0).

Day one, before any training spend: same prompt, small model and a frontier model, on a few hundred hard English test queries. If the frontier model is already near the ceiling on macro-F1, stop. Switch to math on a 0.5B–1.5B model and say the commerce task was promptable. If the small model is the one that fails the close calls, train that. Qwen2.5-0.5B or 1.5B are Apache-2.0. A 7B instruct model is a bad before, because it may already be fine.

Later stages the same labels support, not scheduled for this week: preference pairs from the judgments (Exact over Irrelevant, or a higher-graded ranking over a worse one), then a reward that is label match or nDCG if the model emits an order. SFT on a subsample of the English hard set, short labels, sits in the $5–40 band. Training all 2.6 million multilingual rows is how the week disappears.

The sentence in the room: Composer can be told the brand rules in a prompt. Choosing which product is actually the one the shopper meant is the part the labels teach.

## His idea: a Jev tool filter

Sound, with a narrower shape than “Jev replaces the agent.”

Cursor and Claude Code spend real input tokens on skill text, MCP tool schemas, and tool definitions. Anthropic already ships a [tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool): tools can be deferred, Claude searches, and about 3–5 definitions load instead of a catalog that can be ~55k tokens, which they describe as an 85% cut. Those definitions are still sent to their API for the search. A local filter is a different savings: the frontier request never contains the unused skills.

OpenJev is a decision model, not a writer. The official weights are [openjev/openjev](https://huggingface.co/openjev/openjev), a fine-tune of Qwen3.8-27B, about 54 GB in bf16, served in FP8 on one 80 GB GPU. It assigns each option a letter and reads that letter’s score at the first output position. One pass covers 52 options; larger sets are groups of 52, then a pass over the winners. Weights are CC BY-NC 4.0 (research and other non-commercial use; commercial use needs a discussion on that repo). Helper code is Apache-2.0. A Jev-compatible server that is not those weights is [razorback16/openjev](https://github.com/razorback16/openjev) (Apache-2.0), including a 4B letter-readout model (JevK5) and other small classifiers. Community LoRA decision adapters also exist, such as [ZefanCai/Open-Jev-2B](https://huggingface.co/ZefanCai/Open-Jev-2B) on Qwen3.5-2B. Those are the QLoRA-sized starting points. QLoRA on the 27B checkpoint is a big-GPU project, and a generic chat-style QLoRA misses the actual objective: the loss has to land on the correct option letter, including under reordered options.

The training target “agree with Claude” is right only if Claude chose while it could see the full catalog. That call is the label. If Claude only chose inside an already filtered list, the label does not teach retrieval. Agreement is also not success: Claude can call a bad tool. Recall@n of Claude’s tool is the training metric. Task success, and tokens actually removed, are the metrics that justify the money.

A 27B forward pass every agent loop can cost more than the tokens it saves. The catalog has to be large. Fifteen skills do not pay for a router. The loop that can pay is: a cheap lexical or embedding pass to about 50 candidates, Jev keeps n of them, the frontier model selects inside those n. Public evidence that this retrieval step is not solved by a generic search model: [ToolRet](https://github.com/mangopy/tool-retrieval-benchmark) (ACL 2025), 7.6k tasks, 43k tools, plus a training set of more than 200k instances drawn from ToolACE, APIGen, and ToolBench. They report that strong ordinary retrievers do poorly, and that training them raises both retrieval and downstream pass rate. That set is the free label source. Calling Claude to relabel it is how the $200 disappears.

This is a developer-tool project. It is not the Klaviyo product story. It is a better match to the “a prompt cannot install this” test than the handbook was, because the thing being learned is which tool the expert called from a large catalog, and that choice is not a document you can paste.

Follow-up, after he asked about Laya, ToolRet, Claude Code, and Pi:

- [Laya](https://github.com/NandhaKishorM/laya) is a 421M ModernBERT decision model (322M multilingual). It scores request-time options in one pass, same job as Jev, and the docs include a fine-tune path. The English checkpoint’s context is 512 tokens; the typed-decisions checkpoint is 1,024. A catalog of real skill bodies does not fit. It is the right model when each option is a name plus a short line. The 2B letter-readout model is the one that can read longer descriptions.
- [ToolRet-train](https://huggingface.co/datasets/mangopy/ToolRet-Training-20w) does not contain Claude Code sessions. Each row is a query, an instruction, the tool JSON that should be retrieved, and about 10 negative tools, built from ToolACE, APIGen, and ToolBench. Those tools are public APIs, not Claude Code’s Read, Edit, Bash, or skill files. It is enough to train the retrieval shape without calling Claude. Copying Claude specifically still needs a separate, smaller trace set.
- Inside interactive Claude Code, `--system-prompt` and `--append-system-prompt` change instructions and do not remove skill descriptions or tool schemas from the request. Skill descriptions load every session unless a skill is statically turned off (`disable-model-invocation`, or `skillOverrides`). That is a fixed setting, not a per-turn Jev decision, so the token cut does not show up. The Agent SDK can start a session with an explicit `skills` list and `tools` list, which is a wrapper around Claude, not a prompt edit in the CLI.
- [Pi](https://pi.dev/) can. An extension on `before_agent_start` may call `setActiveTools` and narrow `systemPromptOptions.skills` before the request is built. `SYSTEM.md` replaces the default prompt. That is the harness where a 2B filter changes what gets billed. Skills and tools are different lists: Pi advertises each skill by name and description, and loads the body only if the model asks. MCP tools, once registered, are tools and can be left inactive until `setActiveTools` adds them. A keyword ToolSearch adapter already does that second step. The trained 2B would replace the keyword step.

### Decide these before training

Skills, tools, and MCPs are one scoring problem and three catalogs. An option is a name plus a description. ToolRet only has the tool catalog: public API JSON, not Pi skills and not MCP server manifests. Train on ToolRet. Do not block on a ToolRet-sized skill set. Build a small skill list and a small MCP tool list by hand for the demo, and run the same before/after/frontier comparison on them. Say out loud that those two are a transfer check, not the training distribution.

ToolRet rows often have more than one correct tool. A single “pick one” question throws that away. Score each candidate yes or no, or rank and keep top-n. Yes/no questions are also what runs in parallel.

The 2B cannot read 43,000 tools in one pass. OpenJev scores 52 options per pass. Decide the first stage that proposes the 50: BM25 or an embedding. The fine-tune is a reranker over that shortlist. All three systems being compared must see that same shortlist. Otherwise the frontier model is taking a different test.

### Current plan, corrected

Post-train one ~2B decision model on ToolRet so it *filters*. It does not call the tool. Pi keeps read, write, edit, and bash always on, asks the 2B which of the long-tail tools, skills, and MCP tools are worth showing, and the frontier model chooses inside that short list. That is the product. A T4 (16 GB) is enough to QLoRA a 2B. One card, not a pool. Long tool JSON makes the T4 tight. An L4 (24 GB) is the same job with more room for sequence length. The 27B checkpoint does not fit this plan.

Training does not include the frontier model. A ToolRet row is already a query, the correct tool or tools, and about 10 negatives. The 2B learns to score that list. The frontier model is used twice, later: once to measure the filter, and once inside Pi as the thing that actually calls a tool.

The 2B is the second stage, not the scan of 43,000 tools. Training rows are already a list of about 11. At demo time a cheap BM25 or embedding pass proposes about 50, the 2B keeps k, and the frontier model picks inside those k. Skipping the cheap pass means many groups of 52 through a model that was trained on 10 negatives, which are easier than the near-misses a retriever returns.

“Are all the correct tools in the top k?” is the number to report. It is not a loss. The files do not contain a loss. A row is a query, a set of target tools, and a handful of hard negatives mined by NV-Embed. The benchmark averages 2.17 targets per query. The training-set stats table averages 2.31 targets, and that same table lists 5 negatives per query, while the training section says they mine 10 and set K to 10. Count the lists in the files. They are not one success and ten failures, and the other 43,000 tools are unlabeled, not marked wrong.

Softmax still has one winner. The paper runs a separate softmax for each target, and that target is the winner of its own softmax. The other targets are left out of that denominator, so they do not compete. The model itself never emits a class. It emits a score per tool. Softmax is only the training penalty. At test time you sort those scores and cut at k.

One query, targets A and B, negatives X and Y:

```text
scores:  A 2.4    B 1.8    X 0.3    Y -0.5

softmax for A, classes {A, X, Y} only     B is absent
softmax for B, classes {B, X, Y} only     A is absent
loss = average of those two log-losses

one softmax over {A, B, X, Y} would make A and B fight
```

The objective in the paper is the right loss for a top-k filter. For each target tool, take a softmax over that tool plus the negatives, and average the log-likelihood across the targets. Each target is pulled above those negatives, and targets do not compete with each other. If that succeeds, the targets sit at the top of the list, so a cutoff of k keeps them whenever k is at least the number of targets. It does not contain k, and it never sees the tools that were not in the negative list. At test time, sort by score and cut at k. The paper’s headline number is nDCG@10. Recall@k and completeness@k (every target inside the cutoff) sit next to it. Sweep k on a validation slice. With a bit over two targets on average, a cutoff near 5 is the place to start.

Eval ground truth is the ToolRet test set, 7.6k tasks with annotated target tools. A frontier model on about 100 prompts is a second, smaller check: did the tool it actually called survive in the top k, and does it still call that tool when it only sees those k schemas. It is not the label the model was trained to match. A Voyage reranker, same candidates in, is the commercial baseline.

The comparison that always runs is the 2B you start from, scored before this fine-tune and after, on the same candidate list and the same k. That checkpoint is the public 2B decision model (community Open-Jev-2B on Qwen3.5-2B), not the official 27B release. It fits the same GPU as training. If the tuned 2B beats that original 2B on nDCG@10, recall@k, and completeness@k, the fine-tune is the reason. Voyage sits on that same table as the commercial reranker.

The 27B general Jev is an extra row, not a requirement. Same list, same k, tool filtering only. One 27B pass is the expensive eval line. Score a fixed slice if the full 7.6k does not fit the cap, and say how big the slice was. If that row never gets run, the 2B before and after is still a complete study.

Second wave, after the first loss has converged. Two changes, one extra run, no new labels.

The negatives in the file were mined by NV-Embed. Wave 1 teaches the 2B to beat those. Its own mistakes are a different set. Run the wave-1 model over a larger pool and keep the non-targets it scores above a true target. Those replace the stored negatives.

The loss changes too. Wave 1 never looks at the list as a list: each target is scored against the negatives on its own, so a query can have one target safely on top and another buried. Wave 2 uses a listwise hinge. The lowest-scoring target has to outrank the highest-scoring negative, by a margin. When that holds, every target is above every negative, which is completeness. Weight the hinge more when the miss is near the cutoff you will actually use (around 5), so a swap at rank 40 counts less than a swap at rank 5. That is the same idea as LambdaRank, pointed at nDCG and completeness instead of another copy of the per-target NLL.

Report the table three times: the original 2B, after wave 1, after wave 2. If wave 2 does not move completeness@k, say so and keep wave 1. Do not add a preference stage on generated text, and do not train on the frontier calls. Those calls are the small second eval.

The three-way comparison is not three models doing one job.

- Before versus after, same shortlist: recall@k of the ToolRet tools. That says whether the fine-tune improved the filter.
- Frontier, two checks. Did the tool it would have called survive inside the 2B’s top k? And if it only sees those k schemas, does it still call the right tool as often as when it sees the longer list? The second check is the claim that the context cut did not hurt the decision. Do both on a test slice. Do not relabel the 200k training rows.

Leave Pi’s read, write, edit, and bash always on. Filter the long tail: extra tools, skill blurbs, and MCP tools.

Parallel does not mean many GPUs. One 2B on one GPU, with vLLM batching concurrent questions. The OpenJev-style server reads questions in chunks of about 12, with a default of 64 sequences in flight and a cap around 256 questions per request. A thousand questions are many batches on that one GPU. A 2B fits an L4 (24 GB). The 27B checkpoint wants an 80 GB GPU. That is the wrong machine to sit in the agent loop, and the right one to score once for the comparison.

Modal is the cloud GPU, billed per second. It is not a second thing on top of renting one. One warm function loads the 2B once and answers batches. Pi’s extension calls that URL on `before_agent_start`, then sets the active tools and the skill list. A cold start on every turn costs more than the tokens removed, so the demo replica stays up. Training is a separate short job on the same kind of GPU. A local GPU with about 16 GB also runs the 2B. Modal is the path if there is no local GPU. The Starter plan includes a monthly compute credit.

## Shortlist, and the question that picks

A and B fail the test he just named. Both are documents a prompt can carry. Under that test, three shapes remain, still with no winner:

1. **C, ESCI**, if he wants a commerce judgment that was never written down as a rule. Confirm a prompted frontier model still misses the close calls before committing the week.
2. **D, math on a small model**, if he wants a skill a prompt does not install. The claim is about the small model. Prompting Fable already solves the math.
3. **Next purchase from other customers’ behavior**, if he wants a case where the needed context cannot be pasted. Quieter demo, and he has to beat a simple recommender, not only a prompted LLM.

One question:

**Are you trying to beat a frontier model that already has the document, or teach a small model something a prompt cannot install?**

Beating Fable-with-a-handbook is the wrong week. Teaching the small model, and being able to say why the answer was not sitting in the prompt, is the week.
