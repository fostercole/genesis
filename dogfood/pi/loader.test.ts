import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { discoverAndLoadExtensions } from "@earendil-works/pi-coding-agent";

test("actual Pi 0.85.1 loader registers the Genesis extension", async () => {
  const directory = await mkdtemp(join(tmpdir(), "genesis-pi-loader-"));
  try {
    const path = fileURLToPath(new URL("./genesis.ts", import.meta.url));
    const loaded = await discoverAndLoadExtensions([path], directory, directory);
    assert.deepEqual(loaded.errors, []);
    const extension = loaded.extensions.find(item => item.resolvedPath === path || item.path === path);
    assert(extension, "Genesis was loaded by Pi's own TypeScript loader");
    assert(extension.commands.has("genesis"));
    assert(extension.tools.has("genesis_expand_tools"));
    assert(extension.handlers.has("before_agent_start"));
    assert(extension.handlers.has("agent_settled"));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
