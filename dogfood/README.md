# Run Genesis locally with Pi 0.85.1

This integration runs the tuned 2B selector on your Mac. Pi continues to use your
configured main model. It makes no hosted Jev calls and starts no Modal compute.
Modal is used only to retrieve the saved checkpoint.

Target: Apple M1, 16 GB unified memory, native arm64 Python, and Pi 0.85.1.
The extension, actual Pi 0.85.1 loader, and HTTP protocol have automated tests. Actual M1 model loading,
memory use, numerical parity, and latency still need to be measured on your Mac.

## 1. Install the local environment

From the Genesis repository root:

```bash
bash dogfood/setup-mac.sh
```

Use Python 3.10 through 3.13. Python 3.12 is recommended. If necessary, select it:

```bash
GENESIS_PYTHON=python3.12 bash dogfood/setup-mac.sh
```

The script creates `.venv-dogfood`, installs Mac inference dependencies and the
extension's TypeBox dependency, and pins
Open-Jev to the study's loader commit
`bd4118882f733574a3250a4b65fe4d884130c08b`. It omits CUDA, bitsandbytes, Triton,
and flash-linear-attention. Resolved packages are recorded in
`.cache/dogfood-environment.txt`. Setup needs internet access.

## 2. Download your tuned checkpoint

Use the Modal profile and environment that contain your training volume.
If this Mac is not authenticated, run the first command and complete Modal login:

```bash
.venv-dogfood/bin/modal token new
```

Then download the recorded tuned output. Do this once:

```bash
.venv-dogfood/bin/modal volume ls toolret-h100-train pass1/final
(
  set -e
  mkdir -p checkpoints/genesis/adapter
  for file in model.json head.pt adapter/adapter_config.json adapter/adapter_model.safetensors; do
    .venv-dogfood/bin/modal volume get --force \
      toolret-h100-train "pass1/final/$file" "checkpoints/genesis/$file"
  done
)
```

Download each file to an explicit filename. This avoids Modal's recursive
directory-download path handling, which can treat a new destination directory
as a filename or add an unexpected `final/` level. The `--force` option replaces
only the four named checkpoint files. The subshell stops at the first failure.

The directory must directly contain `model.json`, `head.pt`, and `adapter/`.
`adapter/` must contain `adapter_config.json` and `adapter_model.safetensors`.
The server checks these paths before loading. If Modal reports that the volume is
missing, check your active profile and environment. The repository records this
checkpoint location; this implementation has not verified current account storage.

The base Qwen weights download separately on first load. The checkpoint metadata
selects the pinned base revision. Keep the base and adapter caches for offline use.

## 3. Start the local scorer

In terminal 1, from the Genesis repository root:

```bash
bash dogfood/serve.sh
```

Wait for `Genesis ready`. Then check the server from terminal 2:

```bash
curl --fail http://127.0.0.1:8791/health
```

The default configuration uses MPS, float32, and one candidate per model forward
pass. This limits activation memory. It loads the tuned adapter **and** scalar
head through `DecisionModel.load`. It uses raw score ordering and needs no
`temperature.json`. Returned scores are not calibrated probabilities.

The documented float32 route needs several GB plus runtime and loading overhead.
Close memory-heavy applications for the first test. If loading fails for lack of
memory, stop the process. An optional lower-memory numerical configuration is:

```bash
bash dogfood/serve.sh --dtype float16
```

Float16 is experimental here. Validate finite scores and compare selected tools
on saved queries before using it for filtering. The original training used a
4-bit backbone with bfloat16 computation on CUDA. Float32 and float16 Mac results
are separate numerical configurations; matching the original rankings is not
established. Do not enable `JEV_LOAD_4BIT` on MPS. Leave
`PYTORCH_ENABLE_MPS_FALLBACK` unset so unsupported operations remain visible.

## 4. Start Pi in shadow mode

In terminal 2, change to the project you want Pi to work on. Run the launcher by
its absolute path. For example, if Genesis is in `~/genesis`:

```bash
bash ~/genesis/dogfood/run-pi.sh
```

The launcher adds the extension for this process. It does not change your global
Pi configuration or selected main model. Pi's usual model usage can incur its
normal provider charges. Local Jev inference makes no provider API calls.

By default, the extension scores each new text prompt and logs the hypothetical
selection. All enabled tools remain available in shadow mode. If your Pi session
only has its few built-in tools, selection is skipped. Add the optional tool
extensions you actually use to test a meaningful menu. This integration does not
install connectors or invent a tool catalog.

Use these Pi commands:

| Command | Behavior |
| --- | --- |
| `/genesis status` | Show mode, endpoint, limits, and log path |
| `/genesis shadow` | Log selections; keep the full enabled menu |
| `/genesis filter` | On the next prompt, retain core tools plus the selected optional tools |
| `/genesis off` | Restore the full enabled menu and stop scoring |
| `/genesis all` | Restore the full enabled menu; selection resumes on the next prompt |
| `/genesis export` | Write enabled tool definitions to `~/.pi/agent/genesis/tools.json` |
| `/genesis rate pass` | Record your judgment of the latest task |
| `/genesis rate fail` | Record a failed task |

The filter keeps `read`, `write`, `edit`, `bash`, `powershell`, `grep`, `find`,
and `ls` when they were enabled. It also keeps recognized tool-discovery tools
and its own `genesis_expand_tools`. That recovery tool restores the original
enabled menu when later reasoning identifies a missing capability. Initially
disabled tools stay disabled. External changes to the active menu become the
new baseline. An extension that changes active tools concurrently can therefore
take precedence; test combinations in shadow mode first.

## Selection behavior

1. Capture the enabled tool menu before filtering.
2. Retain core tools and discovery tools separately.
3. If more than 50 optional tools remain, use BM25 to shortlist 50.
4. Score shortlisted candidates with the tuned Open-Jev head.
5. Keep the top 10 optional tools, plus the retained tools.

BM25 uses the current prompt and tool name, description, and parameter names.
It uses no relevance labels and does not inject known positives. A needed tool
can be missed by either stage. The model input uses the same candidate rendering
and description-fitting helper as the study. Oversized queries that cannot fit
are rejected, and the extension retains the full menu. Tool descriptions may be
shortened by the study helper to fit the checkpoint's context limit.

Selection runs once per new user prompt. It does not understand the entire
conversation or rescore after every tool result. Use the recovery tool for
multi-step tasks. This is a dogfood integration, not a reproduction of the study's
offline evaluation or proof of end-to-end cost savings.

Scoring has a 10-second default timeout. Timeout, HTTP errors, invalid scores,
busy server, or invalid responses restore the full enabled menu. The server
checks its budget between candidate batches. A running GPU operation cannot be
interrupted immediately; the server rejects new scoring requests while busy.
Shadow mode also waits for scoring, so it can add latency.

## Measure the Mac before filtering

In Pi, run `/genesis export`. From the Genesis repository root, run:

```bash
.venv-dogfood/bin/python -m dogfood.benchmark \
  --query 'Find the latest customer invoice and draft a follow-up email' \
  --repetitions 3
```

This sends real inference requests to your local server. It does not call Pi's
main model. Use tasks representative of your tools. The report separates the
first request from subsequent requests. Default output is
`.cache/dogfood-benchmark.json`. If scoring takes longer than the Pi timeout,
keep shadow mode while deciding whether the latency tradeoff is acceptable.

Example settings for a fresh Pi process:

```bash
GENESIS_TIMEOUT_MS=20000 GENESIS_TOP_K=10 GENESIS_CANDIDATES=50 \
  bash ~/genesis/dogfood/run-pi.sh
```

| Environment variable | Default |
| --- | --- |
| `GENESIS_MODE` | `shadow` |
| `GENESIS_URL` | `http://127.0.0.1:8791` (loopback only) |
| `GENESIS_TOP_K` | `10` optional tools |
| `GENESIS_CANDIDATES` | `50` optional tools; must be at least top-k |
| `GENESIS_TIMEOUT_MS` | `10000`; maximum `120000` |
| `GENESIS_KEEP_TOOLS` | Empty; comma-separated additional names to retain |
| `GENESIS_LOG` | `~/.pi/agent/genesis/events.jsonl` |
| `GENESIS_CHECKPOINT` | Repository `checkpoints/genesis` (serve script only) |

`GENESIS_LOG` is a literal path. Use `$HOME/...` in your shell for a custom home
path. Tool exports go beside that log. Logs contain tool names, raw scores,
selection and total task latency, schema byte counts, observed tool coverage, errors, user
ratings, and provider-reported token/cost usage. They exclude prompt text, tool
arguments, tool results, and credentials. Prompt hashes correlate identical text.
Tool names and exported definitions can still identify private integrations.

Read a summary from the Genesis repository root:

```bash
.venv-dogfood/bin/python -m dogfood.report
```

For a useful comparison, run the same tasks in off, shadow, and filter modes in
fresh Pi sessions. Record pass/fail after each task. Compare total requests,
input/output/cache tokens, cost, selector delay, and recovery calls. Schema byte
reduction is not a measured token or cost saving. Changing active tools can also
change provider caching behavior.

## Verification and source pins

Run software checks without downloading model weights:

```bash
python3 -m unittest discover -s tests -p 'test_dogfood.py' -v
node --experimental-strip-types --test dogfood/pi/controller.test.ts
```

To type-check against the actual Pi 0.85.1 package, install development
dependencies and run:

```bash
npm ci --prefix dogfood/pi --ignore-scripts
npm run check --prefix dogfood/pi
npm test --prefix dogfood/pi
```

The tests cover raw-score ordering, candidate batching, BM25 caps, HTTP validation,
shadow/filter modes, disabled-tool preservation, full-menu recovery, timeouts,
late-response races, usage logging, and the Python-to-Pi HTTP protocol. The HTTP
integration test uses a deterministic fixture, not the trained model. Node 22.6+
with type stripping is required for these tests. Pi loads the extension through
its own TypeScript loader.

Primary API sources:

- [Pi 0.85.1 extension documentation](https://github.com/earendil-works/pi/blob/v0.85.1/packages/coding-agent/docs/extensions.md)
- [Pi 0.85.1 extension types](https://github.com/earendil-works/pi/blob/v0.85.1/packages/coding-agent/src/core/extensions/types.ts)
- [Pinned Open-Jev loader](https://github.com/Zefan-Cai/Open-Jev/blob/bd4118882f733574a3250a4b65fe4d884130c08b/jev/model.py)
- [Open-Jev Mac deployment guidance](https://github.com/Zefan-Cai/Open-Jev/blob/main/docs/deployment.md)
