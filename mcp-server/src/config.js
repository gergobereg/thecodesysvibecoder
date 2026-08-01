import path from "node:path";
import { fileURLToPath } from "node:url";

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
const defaultRepositoryRoot = path.resolve(moduleDirectory, "..", "..");

function readBoolean(value, defaultValue = false) {
  if (value === undefined || value === "") {
    return defaultValue;
  }

  const normalized = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false;
  }
  throw new Error(`Invalid boolean value "${value}".`);
}

function readInteger(value, defaultValue, minimum, maximum, name) {
  if (value === undefined || value === "") {
    return defaultValue;
  }

  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${name} must be an integer from ${minimum} to ${maximum}.`);
  }
  return parsed;
}

function readList(value) {
  if (!value) {
    return [];
  }
  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function loadConfig(environment = process.env) {
  const apiKey = environment.CODESYS_MCP_API_KEY?.trim() ?? "";
  if (apiKey.length < 32) {
    throw new Error("CODESYS_MCP_API_KEY is required and must contain at least 32 characters.");
  }

  const allowWrite = readBoolean(environment.CODESYS_MCP_ALLOW_WRITE);
  const allowBuild = readBoolean(environment.CODESYS_MCP_ALLOW_BUILD);

  const repositoryRoot = path.resolve(
    environment.CODESYS_MCP_REPOSITORY_ROOT || defaultRepositoryRoot,
  );

  return Object.freeze({
    apiKey,
    allowWrite,
    allowBuild,
    host: environment.CODESYS_MCP_HOST?.trim() || "127.0.0.1",
    port: readInteger(environment.CODESYS_MCP_PORT, 8765, 1, 65535, "CODESYS_MCP_PORT"),
    allowedHosts: readList(environment.CODESYS_MCP_ALLOWED_HOSTS),
    allowedIps: readList(environment.CODESYS_MCP_ALLOWED_IPS),
    repositoryRoot,
    launcherPath: path.join(repositoryRoot, "launcher", "Send-CodesysRequest.ps1"),
    powershellExecutable:
      environment.CODESYS_MCP_POWERSHELL?.trim() || "powershell.exe",
    agent: environment.CODESYS_MCP_AGENT?.trim() || "",
    requestTimeoutSeconds: readInteger(
      environment.CODESYS_MCP_REQUEST_TIMEOUT_SECONDS,
      60,
      5,
      300,
      "CODESYS_MCP_REQUEST_TIMEOUT_SECONDS",
    ),
    maxOutputBytes: readInteger(
      environment.CODESYS_MCP_MAX_OUTPUT_BYTES,
      10 * 1024 * 1024,
      1024,
      50 * 1024 * 1024,
      "CODESYS_MCP_MAX_OUTPUT_BYTES",
    ),
  });
}

export const configInternals = {
  readBoolean,
  readInteger,
  readList,
};
