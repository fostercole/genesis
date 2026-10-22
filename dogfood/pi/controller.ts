import type { ExtensionAPI, ExtensionContext, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { appendFile, mkdir, writeFile } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

type Mode = "shadow" | "filter" | "off";
type MenuTool = { name: string; description: string; parameters: unknown };
type Ranking = { name: string; score: number };
type Selection = { id: string; selected: Set<string>; kept: Set<string> };
type Task = { id: string; mode: Mode; started: number; finished: boolean };
const EXPAND = "genesis_expand_tools";
const CORE = new Set(["read", "write", "edit", "bash", "powershell", "grep", "find", "ls", EXPAND]);

function integer(value: string | undefined, fallback: number, min: number, max: number): number {
  if (value === undefined) return fallback;
  const number = Number(value);
  if (!Number.isInteger(number) || number < min || number > max) throw Error(`invalid Genesis setting: ${value}`);
  return number;
}

export function validateRanking(value: unknown, tools: MenuTool[], topK: number): {
  selected: string[]; ranking: Ranking[]; elapsed_ms: number; candidate_count: number; prefilter: string;
} {
  const result = value as Record<string, any>;
  const names = new Set(tools.map(tool => tool.name));
  if (!result || !Array.isArray(result.selected) || !Array.isArray(result.ranking) ||
      result.input_count !== tools.length || !Number.isFinite(result.elapsed_ms) || result.elapsed_ms < 0 ||
      !Number.isInteger(result.candidate_count) || result.candidate_count < 1 || result.candidate_count > tools.length ||
      !["none", "bm25"].includes(result.prefilter) ||
      result.score_type !== "raw_logit_not_calibrated_probability") throw Error("invalid scorer response");
  const ranked = new Set<string>();
  for (const row of result.ranking) {
    if (!row || !names.has(row.name) || ranked.has(row.name) || !Number.isFinite(row.score)) throw Error("invalid ranking");
    ranked.add(row.name);
  }
  const expectedCount = Math.min(topK, result.candidate_count);
  if (ranked.size !== result.candidate_count || result.selected.length !== expectedCount ||
      new Set(result.selected).size !== expectedCount ||
      result.selected.some((name: unknown, i: number) => name !== result.ranking[i]?.name)) throw Error("invalid shortlist");
  for (let i = 1; i < result.ranking.length; i++) {
    if (result.ranking[i].score > result.ranking[i - 1].score) throw Error("ranking must be descending");
  }
  return result as ReturnType<typeof validateRanking>;
}

export function installDogfood(
  pi: ExtensionAPI,
  parameters: ToolDefinition["parameters"],
  options: { env?: NodeJS.ProcessEnv; fetch?: typeof fetch; log?: (row: Record<string, unknown>) => Promise<void> } = {},
) {
  const env = options.env ?? process.env;
  const endpoint = new URL(env.GENESIS_URL ?? "http://127.0.0.1:8791");
  if (endpoint.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(endpoint.hostname) ||
      endpoint.username || endpoint.password) throw Error("GENESIS_URL must be a local HTTP URL");
  const topK = integer(env.GENESIS_TOP_K, 10, 1, 50);
  const candidateLimit = integer(env.GENESIS_CANDIDATES, 50, topK, 100);
  const timeoutMs = integer(env.GENESIS_TIMEOUT_MS, 10000, 1, 120000);
  const extraKeep = new Set((env.GENESIS_KEEP_TOOLS ?? "").split(",").map(x => x.trim()).filter(Boolean));
  const initialMode = env.GENESIS_MODE ?? "shadow";
  if (!["shadow", "filter", "off"].includes(initialMode)) throw Error("GENESIS_MODE must be shadow, filter, or off");
  let mode = initialMode as Mode;
  const logPath = env.GENESIS_LOG ?? join(homedir(), ".pi", "agent", "genesis", "events.jsonl");
  let baseline: string[] | undefined;
  let applied: string[] | undefined;
  let current: Selection | undefined;
  let task: Task | undefined;
  let inFlight: AbortController | undefined;
  let generation = 0;
  let logWarning = false;
  const runId = randomUUID();
  const same = (a: string[], b: string[]) => a.length === b.length && a.every(x => b.includes(x));
  const keep = (name: string) => CORE.has(name) || extraKeep.has(name) ||
    /(^|__)(tool_search|search_tools|list_tools|discover_tools)$/.test(name);
  const log = async (data: Record<string, unknown>, ctx?: ExtensionContext) => {
    const row = { timestamp: new Date().toISOString(), run_id: runId, ...data };
    try {
      if (options.log) return await options.log(row);
      await mkdir(dirname(logPath), { recursive: true, mode: 0o700 });
      await appendFile(logPath, JSON.stringify(row) + "\n", { mode: 0o600 });
    } catch {
      if (!logWarning) ctx?.ui.notify("Genesis could not write its local log.", "warning");
      logWarning = true;
    }
  };
  const status = (ctx: ExtensionContext, text: string = mode) => ctx.ui.setStatus("genesis", `Genesis: ${text}`);

  function menu(): MenuTool[] {
    const all = pi.getAllTools();
    const registered = new Set(all.map(tool => tool.name));
    const active = pi.getActiveTools().filter(name => registered.has(name));
    // Preserve the pre-filter active set. An external change becomes the new baseline.
    if (!baseline || !applied || !same(active, applied)) baseline = active;
    baseline = [...new Set([...baseline.filter(name => registered.has(name)), EXPAND])];
    return all.filter(tool => baseline!.includes(tool.name)).map(({ name, description, parameters }) =>
      ({ name, description, parameters }));
  }
  function restore() {
    menu();
    pi.setActiveTools(baseline!);
    applied = [...baseline!];
  }
  function cancel() {
    generation++;
    inFlight?.abort();
    inFlight = undefined;
  }

  pi.registerTool({
    name: EXPAND,
    label: "Show all tools",
    description: "Restore the full enabled tool menu when a task needs a tool that Genesis has hidden. Call before concluding that a tool is unavailable.",
    promptSnippet: "Restore all enabled tools when the current menu is insufficient",
    promptGuidelines: ["Call genesis_expand_tools if the current menu lacks a needed capability, including later steps of a task."],
    parameters,
    async execute(_id, _params, _signal, _update, ctx) {
      cancel();
      restore();
      await log({ event: "expand", selection_id: task?.id, active_count: baseline!.length }, ctx);
      status(ctx, `${mode}; full menu restored`);
      return { content: [{ type: "text", text: "All originally enabled tools are active again. Continue with the tool you need." }],
        details: { active_count: baseline!.length } };
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    baseline = undefined;
    applied = undefined;
    current = undefined;
    task = undefined;
    cancel();
    status(ctx);
  });
  pi.on("session_before_switch", async () => { cancel(); if (baseline) restore(); });
  pi.on("session_shutdown", async () => { cancel(); if (baseline) restore(); });

  pi.registerCommand("genesis", {
    description: "Genesis selector: status | shadow | filter | off | all | export | rate pass|fail",
    async handler(args, ctx) {
      const [command = "status", value] = args.trim().split(/\s+/);
      if (["shadow", "filter", "off"].includes(command)) {
        cancel();
        restore();
        mode = command as Mode;
        current = undefined;
        status(ctx);
        await log({ event: "mode", mode }, ctx);
        ctx.ui.notify(`Genesis ${mode}. The next prompt uses this mode.`, "info");
      } else if (command === "all") {
        cancel();
        restore();
        await log({ event: "expand", selection_id: task?.id, source: "command" }, ctx);
        ctx.ui.notify("Full enabled menu restored. Selection resumes on the next prompt.", "info");
      } else if (command === "export") {
        const path = join(dirname(logPath), "tools.json");
        const tools = menu();
        await mkdir(dirname(path), { recursive: true, mode: 0o700 });
        await writeFile(path, JSON.stringify(tools, null, 2) + "\n", { mode: 0o600 });
        ctx.ui.notify(`Exported ${tools.length} tool definitions to ${path}`, "info");
      } else if (command === "rate" && ["pass", "fail"].includes(value)) {
        if (!task) {
          ctx.ui.notify("Run a task before rating it.", "info");
          return;
        }
        await log({ event: "quality", selection_id: task.id, mode: task.mode, rating: value }, ctx);
        ctx.ui.notify(`Recorded task ${value}.`, "info");
      } else {
        ctx.ui.notify(`Genesis ${mode}; top ${topK}; BM25 cap ${candidateLimit}; timeout ${timeoutMs} ms; ${endpoint.origin}; log ${logPath}`, "info");
      }
    },
  });

  pi.on("before_agent_start", async (event, ctx) => {
    cancel();
    const token = generation;
    current = undefined;
    const tools = menu();
    restore();
    const kept = tools.filter(tool => keep(tool.name));
    const optional = tools.filter(tool => !keep(tool.name));
    const id = randomUUID();
    task = { id, mode, started: performance.now(), finished: false };
    await log({ event: "task_start", selection_id: id, mode, menu_count: tools.length }, ctx);
    if (generation !== token) return;
    if (mode === "off" || optional.length <= topK || !event.prompt?.trim()) {
      status(ctx, `${mode}; ${tools.length} tools`);
      await log({ event: "skip", selection_id: id, mode, reason: mode === "off" ? "disabled" :
        !event.prompt?.trim() ? "no_text_prompt" : "small_menu", optional_count: optional.length }, ctx);
      return;
    }
    const controller = new AbortController();
    inFlight = controller;
    const abortFromPi = () => controller.abort();
    ctx.signal?.addEventListener("abort", abortFromPi, { once: true });
    if (ctx.signal?.aborted) controller.abort();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const started = performance.now();
    status(ctx, `${mode}; ranking ${optional.length} tools`);
    try {
      const response = await (options.fetch ?? fetch)(new URL("/rank", endpoint), {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify({ query: event.prompt, top_k: topK, candidate_limit: candidateLimit,
          budget_ms: timeoutMs, tools: optional.map(tool => ({ name: tool.name,
            description: tool.description, parameters: tool.parameters })) }),
      });
      if (!response.ok) throw Error(`scorer returned HTTP ${response.status}`);
      const result = validateRanking(await response.json(), optional, topK);
      if (result.candidate_count > candidateLimit) throw Error("scorer exceeded candidate limit");
      if (generation !== token || controller.signal.aborted) return;
      const selected = new Set(result.selected);
      const hypothetical = tools.filter(tool => keep(tool.name) || selected.has(tool.name));
      current = { id, selected, kept: new Set(kept.map(tool => tool.name)) };
      if (mode === "filter") {
        pi.setActiveTools(hypothetical.map(tool => tool.name));
        applied = hypothetical.map(tool => tool.name);
      }
      await log({ event: "selection", selection_id: id, mode,
        prompt_sha256: createHash("sha256").update(event.prompt).digest("hex"),
        menu_count: tools.length, optional_count: optional.length, kept: kept.map(tool => tool.name),
        selected: result.selected, ranking: result.ranking, prefilter: result.prefilter,
        candidate_count: result.candidate_count, scorer_ms: result.elapsed_ms,
        wall_ms: performance.now() - started,
        schema_bytes_before: Buffer.byteLength(JSON.stringify(tools)),
        schema_bytes_after: Buffer.byteLength(JSON.stringify(hypothetical)),
      }, ctx);
      status(ctx, `${mode}; ${hypothetical.length}/${tools.length} ${mode === "shadow" ? "would be active" : "active"}`);
    } catch (error) {
      if (generation !== token) return;
      restore();
      await log({ event: "fallback", selection_id: id, mode, wall_ms: performance.now() - started,
        reason: controller.signal.aborted ? "timeout_or_abort" :
          error instanceof Error ? error.message.slice(0, 180) : "scorer_failed" }, ctx);
      status(ctx, `${mode}; full menu (scorer unavailable)`);
      ctx.ui.notify("Genesis kept the full tool menu because local scoring did not finish successfully.", "warning");
    } finally {
      clearTimeout(timer);
      ctx.signal?.removeEventListener("abort", abortFromPi);
      if (inFlight === controller) inFlight = undefined;
    }
  });

  pi.on("tool_call", async (event, ctx) => {
    await log({ event: "tool_call", selection_id: task?.id, mode: task?.mode ?? mode, tool: event.toolName,
      would_be_available: current ? current.selected.has(event.toolName) || current.kept.has(event.toolName) : true }, ctx);
  });
  pi.on("tool_result", async (event, ctx) => {
    await log({ event: "tool_result", selection_id: task?.id, tool: event.toolName, is_error: event.isError }, ctx);
  });
  pi.on("turn_end", async (event, ctx) => {
    const message = event.message;
    if (message.role !== "assistant") return;
    await log({ event: "usage", selection_id: task?.id, mode: task?.mode ?? mode,
      input: message.usage.input, output: message.usage.output,
      cache_read: message.usage.cacheRead, cache_write: message.usage.cacheWrite,
      cost_usd: message.usage.cost.total }, ctx);
  });
  pi.on("agent_settled", async (_event, ctx) => {
    if (!task || task.finished) return;
    task.finished = true;
    await log({ event: "task_end", selection_id: task.id, mode: task.mode,
      wall_ms: performance.now() - task.started, aborted: ctx.signal?.aborted ?? false }, ctx);
  });
}
