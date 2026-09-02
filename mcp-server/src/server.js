import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import express from "express";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { isInitializeRequest } from "@modelcontextprotocol/sdk/types.js";

import { CodesysBridge } from "./codesys-bridge.js";
import { loadConfig } from "./config.js";
import { registerCodesysTools } from "./register-tools.js";
import {
  createAccessMiddleware,
  createHostValidationMiddleware,
} from "./security.js";

function jsonRpcError(response, status, message) {
  response.status(status).json({
    jsonrpc: "2.0",
    error: { code: -32000, message },
    id: null,
  });
}

function createMcpServer(bridge, config) {
  const server = new McpServer({
    name: "codesys-mcp-bridge",
    version: "0.1.0",
  });
  registerCodesysTools(server, bridge, config);
  return server;
}

export function createApp(config, bridge = new CodesysBridge(config)) {
  const app = express();
  const transports = new Map();

  app.disable("x-powered-by");
  app.set("trust proxy", false);
  app.use(createHostValidationMiddleware(config));
  app.use(createAccessMiddleware(config));
  app.use(express.json({ limit: "2mb" }));

  app.get("/health", (_request, response) => {
    response.json({ status: "ok", service: "codesys-mcp-bridge" });
  });

  app.all("/mcp", async (request, response) => {
    try {
      const sessionId = request.get("mcp-session-id");
      let transport;

      if (sessionId) {
        transport = transports.get(`streamable:${sessionId}`);
        if (!(transport instanceof StreamableHTTPServerTransport)) {
          jsonRpcError(response, 400, "Unknown or invalid MCP session.");
          return;
        }
      } else if (request.method === "POST" && isInitializeRequest(request.body)) {
        transport = new StreamableHTTPServerTransport({
          sessionIdGenerator: () => randomUUID(),
          onsessioninitialized: (initializedSessionId) => {
            transports.set(`streamable:${initializedSessionId}`, transport);
          },
        });
        transport.onclose = () => {
          if (transport.sessionId) {
            transports.delete(`streamable:${transport.sessionId}`);
          }
        };
        await createMcpServer(bridge, config).connect(transport);
      } else {
        jsonRpcError(response, 400, "A valid MCP session or initialize request is required.");
        return;
      }

      await transport.handleRequest(request, response, request.body);
    } catch (error) {
      console.error("Streamable HTTP request failed:", error);
      if (!response.headersSent) {
        jsonRpcError(response, 500, "Internal MCP server error.");
      }
    }
  });

  app.get("/sse", async (_request, response) => {
    try {
      const transport = new SSEServerTransport("/messages", response);
      transports.set(`sse:${transport.sessionId}`, transport);
      response.on("close", () => {
        transports.delete(`sse:${transport.sessionId}`);
      });
      await createMcpServer(bridge, config).connect(transport);
    } catch (error) {
      console.error("SSE connection failed:", error);
      if (!response.headersSent) {
        jsonRpcError(response, 500, "Internal MCP server error.");
      }
    }
  });

  app.post("/messages", async (request, response) => {
    const sessionId = String(request.query.sessionId || "");
    const transport = transports.get(`sse:${sessionId}`);
    if (!(transport instanceof SSEServerTransport)) {
      jsonRpcError(response, 400, "Unknown or invalid SSE session.");
      return;
    }
    await transport.handlePostMessage(request, response, request.body);
  });

  app.use((error, _request, response, _next) => {
    console.error("HTTP request failed:", error);
    if (!response.headersSent) {
      response.status(error?.status || 500).json({
        error: error?.type === "entity.too.large" ? "Request body is too large." : "Request failed.",
      });
    }
  });

  return { app, transports };
}

export async function startServer(config = loadConfig()) {
  if (!existsSync(config.launcherPath)) {
    throw new Error(`CODESYS launcher was not found at ${config.launcherPath}`);
  }

  if (
    (config.host === "0.0.0.0" || config.host === "::") &&
    config.allowedHosts.length === 0
  ) {
    console.warn(
      "CODESYS_MCP_ALLOWED_HOSTS is empty while listening on all interfaces. Authentication is active, but an explicit host allowlist is recommended.",
    );
  }

  const { app, transports } = createApp(config);
  const httpServer = await new Promise((resolve, reject) => {
    const listener = app.listen(config.port, config.host, () => resolve(listener));
    listener.once("error", reject);
  });

  console.log(
    `CODESYS MCP bridge listening at http://${config.host}:${config.port}/mcp (SSE fallback: /sse)`,
  );
  console.log(
    `Tools: raw action enabled; named read-only enabled; write=${config.allowWrite}; build=${config.allowBuild}; agent=${config.agent || "default"}`,
  );

  const shutdown = async () => {
    for (const transport of transports.values()) {
      try {
        await transport.close();
      } catch (error) {
        console.error("Failed to close MCP transport:", error);
      }
    }
    transports.clear();
    await new Promise((resolve) => httpServer.close(resolve));
  };

  return { httpServer, shutdown };
}

const isEntryPoint =
  process.argv[1] &&
  path.resolve(fileURLToPath(import.meta.url)).toLowerCase() ===
    path.resolve(process.argv[1]).toLowerCase();

if (isEntryPoint) {
  startServer().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
