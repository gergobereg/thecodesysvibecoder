import assert from "node:assert/strict";
import test from "node:test";

import { loadConfig } from "../src/config.js";
import { createApp } from "../src/server.js";

const apiKey = "0123456789abcdef0123456789abcdef";

async function withHttpServer(operation) {
  const config = loadConfig({ CODESYS_MCP_API_KEY: apiKey });
  const bridge = {
    inspectProject: async () => ({ ok: true, data: { project_path: "C:\\test.project" } }),
  };
  const { app } = createApp(config, bridge);
  const listener = await new Promise((resolve, reject) => {
    const server = app.listen(0, "127.0.0.1", () => resolve(server));
    server.once("error", reject);
  });

  try {
    const address = listener.address();
    await operation(`http://127.0.0.1:${address.port}`);
  } finally {
    await new Promise((resolve) => listener.close(resolve));
  }
}

test("health endpoint reveals no CODESYS state and needs no credential", async () => {
  await withHttpServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/health`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {
      status: "ok",
      service: "codesys-mcp-bridge",
    });
  });
});

test("MCP endpoint rejects a missing API key", async () => {
  await withHttpServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/mcp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: "2025-11-25",
          capabilities: {},
          clientInfo: { name: "test", version: "1.0.0" },
        },
      }),
    });
    assert.equal(response.status, 401);
  });
});
