import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

import { loadConfig } from "../src/config.js";
import { createApp } from "../src/server.js";

const apiKey = "codesys-mcp-smoke-test-key-32-chars";
const config = loadConfig({
  ...process.env,
  CODESYS_MCP_API_KEY: apiKey,
  CODESYS_MCP_HOST: "127.0.0.1",
  CODESYS_MCP_PORT: "8765",
  CODESYS_MCP_ALLOW_WRITE: "false",
  CODESYS_MCP_ALLOW_BUILD: "false",
});

const { app } = createApp(config);
const listener = await new Promise((resolve, reject) => {
  const server = app.listen(0, "127.0.0.1", () => resolve(server));
  server.once("error", reject);
});
const address = listener.address();
const baseUrl = `http://127.0.0.1:${address.port}`;

async function verifyTransport(label, transport) {
  const client = new Client({ name: `codesys-mcp-${label}-smoke`, version: "0.1.0" });
  try {
    await client.connect(transport);
    const tools = await client.listTools();
    const toolNames = tools.tools.map((tool) => tool.name).sort();
    if (toolNames.join(",") !== "inspect_project,inspect_tree,read_object") {
      throw new Error(`${label} exposed unexpected tools: ${toolNames.join(", ")}`);
    }

    const result = await client.callTool({ name: "inspect_project", arguments: {} });
    const text = result.content.find((item) => item.type === "text")?.text;
    const payload = JSON.parse(text);
    if (payload.ok !== true || !payload.data?.project_path) {
      throw new Error(`${label} inspect_project returned an invalid result.`);
    }

    if (label === "streamable-http") {
      const treeResult = await client.callTool({
        name: "inspect_tree",
        arguments: { depth: 1, include_text: false },
      });
      const treePayload = JSON.parse(
        treeResult.content.find((item) => item.type === "text")?.text,
      );
      if (treePayload.ok !== true) {
        throw new Error("inspect_tree returned an invalid result.");
      }

      const objectName =
        payload.data.active_application || payload.data.top_level_objects?.[0];
      const objectResult = await client.callTool({
        name: "read_object",
        arguments: { name: objectName },
      });
      const objectPayload = JSON.parse(
        objectResult.content.find((item) => item.type === "text")?.text,
      );
      if (objectPayload.ok !== true) {
        throw new Error("read_object returned an invalid result.");
      }
    }

    console.log(
      `${label}: ${toolNames.length} tools; active project ${payload.data.project_path}`,
    );
  } finally {
    await client.close();
  }
}

try {
  await verifyTransport(
    "streamable-http",
    new StreamableHTTPClientTransport(new URL(`${baseUrl}/mcp`), {
      requestInit: { headers: { "X-API-Key": apiKey } },
    }),
  );
  await verifyTransport(
    "sse",
    new SSEClientTransport(new URL(`${baseUrl}/sse`), {
      requestInit: { headers: { "X-API-Key": apiKey } },
    }),
  );
} finally {
  await new Promise((resolve) => listener.close(resolve));
}
