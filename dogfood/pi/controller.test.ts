import assert from "node:assert/strict";
import { test } from "node:test";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { installDogfood, validateRanking } from "./controller.ts";

const tool = (name: string) => ({ name, description: `${name} tool`, parameters: { type: "object", properties: {} } });

function harness(options: Record<string, any> = {}) {
  const handlers = new Map<string, Function>();
  const commands = new Map<string, any>();
  let all = [tool("read"), tool("bash"), ...Array.from({ length: 15 }, (_, i) => tool(`optional_${i}`)), tool("disabled")];
  let active = all.filter(x => x.name !== "disabled").map(x => x.name);
  const tools = new Map<string, any>();
  const logs: any[] = [];
  const notices: string[] = [];
  const statuses: string[] = [];
  const pi = {
    on(name: string, fn: Function) { handlers.set(name, fn); },
    registerCommand(name: string, command: any) { commands.set(name, command); },
    registerTool(def: any) { tools.set(def.name, def); all.push(def); active.push(def.name); },
    getAllTools() { return all; },
    getActiveTools() { return [...active]; },
    setActiveTools(names: string[]) { active = names.filter(name => all.some(tool => tool.name === name)); },
  };
  const ctx = { ui: { notify(text: string) { notices.push(text); }, setStatus(_key: string, text: string) { statuses.push(text); } } };
  const reply = (_url: URL, init: any) => {
    const body = JSON.parse(init.body);
    const ranking = body.tools.map((item: any, i: number) => ({ name: item.name, score: 100 - i }));
    return Promise.resolve(new Response(JSON.stringify({ selected: ranking.slice(0, body.top_k).map((x: any) => x.name),
      ranking, elapsed_ms: 10, input_count: ranking.length, candidate_count: ranking.length,
      prefilter: "none", score_type: "raw_logit_not_calibrated_probability" })));
  };
  installDogfood(pi as any, {} as any, { env: options.env ?? {}, fetch: options.fetch ?? reply,
    log: options.log ?? (async row => { logs.push(row); }) });
  return { pi, logs, notices, statuses, tools,
    active: () => pi.getActiveTools(),
    run: (prompt = "send an email with a private token abc123") => handlers.get("before_agent_start")!({ prompt }, ctx),
    event: (name: string, event: any) => handlers.get(name)!(event, ctx),
    command: (args: string) => commands.get("genesis").handler(args, ctx),
    expand: () => tools.get("genesis_expand_tools").execute("id", {}, undefined, undefined, ctx),
    add(name: string) { all.push(tool(name)); active.push(name); },
  };
}

test("shadow mode leaves the full enabled menu active and excludes disabled tools", async () => {
  const h = harness();
  const initial = h.active();
  await h.run();
  assert.deepEqual(h.active(), initial);
  const row = h.logs.find(x => x.event === "selection");
  assert.equal(row.mode, "shadow");
  assert.equal(row.selected.length, 10);
  assert(!row.selected.includes("disabled"));
  assert(!JSON.stringify(h.logs).includes("abc123"));
  assert.equal(row.prompt_sha256.length, 64);
  assert(row.schema_bytes_after < row.schema_bytes_before);
});

test("filter keeps core tools and recovery tool; expansion restores original menu", async () => {
  const h = harness({ env: { GENESIS_MODE: "filter" } });
  const initial = h.active();
  await h.run();
  assert.equal(h.active().length, 13);
  assert(h.active().includes("read") && h.active().includes("bash") && h.active().includes("genesis_expand_tools"));
  await h.expand();
  assert.deepEqual(h.active(), initial);
  assert(!h.active().includes("disabled"));
});

test("repeated prompts rank the complete baseline, rather than shrinking previous selections", async () => {
  const h = harness({ env: { GENESIS_MODE: "filter" } });
  await h.run();
  await h.run("second task");
  assert.equal(h.logs.filter(x => x.event === "selection")[1].optional_count, 15);
  await h.command("off");
  assert.equal(h.active().length, 18);
  await h.run();
  assert.equal(h.logs.at(-1).reason, "disabled");
});

test("HTTP failure, invalid response, and timeout all preserve the full menu", async () => {
  for (const fetch of [
    async () => new Response("error", { status: 503 }),
    async () => new Response(JSON.stringify({ selected: ["unknown"] })),
    (_url: unknown, init: any) => new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(Error("aborted")))),
  ]) {
    const h = harness({ env: { GENESIS_MODE: "filter", GENESIS_TIMEOUT_MS: "20" }, fetch });
    const initial = h.active();
    await h.run();
    assert.deepEqual(h.active(), initial);
    assert.equal(h.logs.at(-1).event, "fallback");
  }
});

test("a late scorer response cannot re-enable filtering after /genesis off", async () => {
  let release: Function;
  const h = harness({ env: { GENESIS_MODE: "filter" }, fetch: (_url: URL, init: any) => new Promise(resolve => {
    const body = JSON.parse(init.body);
    release = () => {
      const ranking = body.tools.map((x: any, i: number) => ({ name: x.name, score: 100 - i }));
      resolve(new Response(JSON.stringify({ selected: ranking.slice(0, 10).map((x: any) => x.name), ranking,
        input_count: 15, candidate_count: 15, elapsed_ms: 10, prefilter: "none", score_type: "raw_logit_not_calibrated_probability" })));
    };
  }) });
  const initial = h.active();
  const pending = h.run();
  // Let the task-start log complete so the request is in flight.
  await new Promise(resolve => setImmediate(resolve));
  await h.command("off");
  release!();
  await pending;
  assert.deepEqual(h.active(), initial);
  assert.equal(h.logs.filter(x => x.event === "selection").length, 0);
});

test("small menus skip the local model", async () => {
  const h = harness({ fetch: async () => { throw Error("must not run"); } });
  h.pi.setActiveTools(["read", "bash", "genesis_expand_tools"]);
  await h.run();
  assert.equal(h.logs.at(-1).reason, "small_menu");
});

test("tool search and configured tools are always retained", async () => {
  const h = harness({ env: { GENESIS_MODE: "filter", GENESIS_KEEP_TOOLS: "optional_14" } });
  h.add("mcp__tool_search");
  await h.run();
  assert(h.active().includes("mcp__tool_search"));
  assert(h.active().includes("optional_14"));
});

test("manual tool changes become the new enabled baseline", async () => {
  const h = harness({ env: { GENESIS_MODE: "filter" } });
  await h.run();
  h.pi.setActiveTools(["read", "bash", "optional_14"]);
  await h.run();
  await h.command("all");
  assert.deepEqual(h.active(), ["read", "bash", "optional_14", "genesis_expand_tools"]);
});

test("shadow logs whether actual tool calls were covered, without arguments or outputs", async () => {
  const h = harness();
  await h.run();
  await h.event("tool_call", { toolName: "optional_14", input: { secret: "do-not-log" } });
  await h.event("tool_result", { toolName: "optional_14", isError: false, content: [{ type: "text", text: "private output" }] });
  await h.event("turn_end", { message: { role: "assistant", usage: { input: 100, output: 20, cacheRead: 30, cacheWrite: 0, cost: { total: 0.01 } } } });
  await h.event("agent_settled", {});
  await h.command("rate pass");
  assert.equal(h.logs.find(x => x.event === "tool_call").would_be_available, false);
  assert.equal(h.logs.find(x => x.event === "usage").cost_usd, 0.01);
  assert(h.logs.find(x => x.event === "task_end").wall_ms > 0);
  assert.equal(h.logs.at(-1).rating, "pass");
  assert(!JSON.stringify(h.logs).includes("do-not-log"));
  assert(!JSON.stringify(h.logs).includes("private output"));
});

test("off-mode tasks retain their IDs, usage, latency, and manual ratings", async () => {
  const h = harness({ env: { GENESIS_MODE: "off" } });
  await h.run();
  await h.event("turn_end", { message: { role: "assistant", usage: { input: 100, output: 20, cacheRead: 0, cacheWrite: 0, cost: { total: 0.02 } } } });
  await h.event("agent_settled", {});
  await h.event("agent_settled", {});
  await h.command("rate pass");
  const start = h.logs.find(x => x.event === "task_start");
  assert.equal(h.logs.find(x => x.event === "usage").selection_id, start.selection_id);
  assert.equal(h.logs.find(x => x.event === "quality").selection_id, start.selection_id);
  assert.equal(h.logs.find(x => x.event === "quality").mode, "off");
  assert.equal(h.logs.filter(x => x.event === "task_end").length, 1);
});

test("logging failure does not break the agent", async () => {
  const h = harness({ log: async () => { throw Error("disk full"); } });
  await h.run();
  assert(h.notices.some(x => x.includes("could not write")));
});

test("response validation rejects duplicates, non-finite scores, and mismatched ordering", () => {
  const tools = [tool("a"), tool("b")];
  const value = { input_count: 2, candidate_count: 2, elapsed_ms: 1, prefilter: "none",
    score_type: "raw_logit_not_calibrated_probability", selected: ["a"], ranking: [{ name: "a", score: 2 }, { name: "b", score: 1 }] };
  assert.equal(validateRanking(value, tools, 1).selected[0], "a");
  assert.throws(() => validateRanking({ ...value, selected: ["b"] }, tools, 1));
  assert.throws(() => validateRanking({ ...value, ranking: [{ name: "a", score: 2 }, { name: "a", score: 1 }] }, tools, 1));
  assert.throws(() => validateRanking({ ...value, ranking: [{ name: "a", score: Infinity }, { name: "b", score: 1 }] }, tools, 1));
});

test("real HTTP protocol: Pi controller talks to Python server", async () => {
  const child = spawn("python3", ["-m", "tests.dogfood_http_fixture"], {
    cwd: fileURLToPath(new URL("../..", import.meta.url)), stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  child.stderr.on("data", chunk => { stderr += chunk; });
  const lines = createInterface({ input: child.stdout });
  try {
    const endpoint = await Promise.race([
      once(lines, "line").then(([line]) => line),
      once(child, "exit").then(() => { throw Error(`fixture exited: ${stderr}`); }),
    ]);
    const h = harness({ env: { GENESIS_MODE: "filter", GENESIS_URL: endpoint }, fetch });
    await h.run();
    assert.equal(h.active().length, 13);
    assert(h.active().includes("optional_14"));
    assert(!h.active().includes("optional_0"));
    assert.equal(h.logs.find(x => x.event === "selection").scorer_ms, 1);
  } finally {
    lines.close();
    child.kill();
    await once(child, "exit");
  }
});
