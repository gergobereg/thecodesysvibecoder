import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  bridgeInternals,
  CodesysBridge,
  CodesysBridgeError,
} from "../src/codesys-bridge.js";

function config() {
  return {
    launcherPath: "C:\\repo\\launcher\\Send-CodesysRequest.ps1",
    powershellExecutable: "powershell.exe",
    repositoryRoot: "C:\\repo",
    requestTimeoutSeconds: 60,
    maxOutputBytes: 1024 * 1024,
    agent: "",
  };
}

test("parseLauncherJson accepts formatted launcher JSON", () => {
  const value = bridgeInternals.parseLauncherJson(
    '\uFEFF{\n  "ok": true,\n  "data": {"project_path": "C:\\\\test.project"}\n}',
  );
  assert.equal(value.data.project_path, "C:\\test.project");
});

test("parseLauncherJson turns agent errors into bridge errors", () => {
  assert.throws(
    () => bridgeInternals.parseLauncherJson('{"ok":false,"error":"not found"}'),
    (error) => error instanceof CodesysBridgeError && /not found/.test(error.message),
  );
});

test("readObject inspects first and pins the operation to the returned project", async () => {
  const calls = [];
  const runner = async (_executable, argumentsList) => {
    calls.push(argumentsList);
    if (calls.length === 1) {
      return {
        stdout: JSON.stringify({
          ok: true,
          data: { project_path: "C:\\Projects\\Active.project" },
        }),
      };
    }
    return { stdout: JSON.stringify({ ok: true, data: { name: "POU" } }) };
  };

  const bridge = new CodesysBridge(config(), runner);
  const result = await bridge.readObject({ name: "POU" });

  assert.equal(result.data.name, "POU");
  assert.ok(calls[0].includes("-NoProjectPathMatch"));
  assert.ok(calls[1].includes("C:\\Projects\\Active.project"));
  assert.ok(calls[1].includes("POU"));
});

test("executeAgentAction serializes and sends the complete raw request", async () => {
  let request;
  const runner = async (_executable, argumentsList) => {
    const requestPathIndex = argumentsList.indexOf("-RequestJson");
    assert.notEqual(requestPathIndex, -1);
    request = JSON.parse(await readFile(argumentsList[requestPathIndex + 1], "utf8"));
    return {
      stdout: JSON.stringify({ ok: true, action: request.action, data: request }),
    };
  };

  const bridge = new CodesysBridge(config(), runner);
  const result = await bridge.executeAgentAction({
    action: "application_command",
    parameters: {
      action: "ignored_value",
      command: "clean",
      clear_messages: false,
    },
  });

  assert.deepEqual(request, {
    action: "application_command",
    command: "clean",
    clear_messages: false,
  });
  assert.equal(result.action, "application_command");
});
