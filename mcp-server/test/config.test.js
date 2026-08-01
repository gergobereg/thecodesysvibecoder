import assert from "node:assert/strict";
import test from "node:test";

import { loadConfig } from "../src/config.js";

const validKey = "0123456789abcdef0123456789abcdef";

test("loadConfig is read-only and loopback by default", () => {
  const config = loadConfig({ CODESYS_MCP_API_KEY: validKey });
  assert.equal(config.host, "127.0.0.1");
  assert.equal(config.port, 8765);
  assert.equal(config.allowWrite, false);
  assert.equal(config.allowBuild, false);
});

test("loadConfig rejects a short API key", () => {
  assert.throws(
    () => loadConfig({ CODESYS_MCP_API_KEY: "short" }),
    /at least 32 characters/,
  );
});

test("loadConfig enables mutation tools without a second credential", () => {
  const config = loadConfig({
    CODESYS_MCP_API_KEY: validKey,
    CODESYS_MCP_ALLOW_WRITE: "true",
    CODESYS_MCP_ALLOW_BUILD: "true",
  });
  assert.equal(config.allowWrite, true);
  assert.equal(config.allowBuild, true);
});
