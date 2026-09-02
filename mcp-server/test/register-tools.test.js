import assert from "node:assert/strict";
import test from "node:test";

import { registerCodesysTools, toolInternals } from "../src/register-tools.js";

function collectTools(config, bridge = {}) {
  const tools = new Map();
  const server = {
    registerTool(name, options, handler) {
      tools.set(name, { options, handler });
    },
  };

  registerCodesysTools(server, bridge, config);
  return tools;
}

test("minimal mode exposes inspection tools and the raw action passthrough", () => {
  const tools = collectTools({ allowWrite: false, allowBuild: false });

  assert.deepEqual([...tools.keys()], [
    "inspect_project",
    "inspect_tree",
    "read_object",
    "execute_codesys_action",
  ]);
});

test("enabled mutation tools do not request a second approval credential", () => {
  const tools = collectTools({ allowWrite: true, allowBuild: true });

  assert.deepEqual([...tools.keys()], [
    "inspect_project",
    "inspect_tree",
    "read_object",
    "execute_codesys_action",
    "upsert_function_block",
    "upsert_program",
    "upsert_function",
    "upsert_object",
    "add_gvl_variable",
    "rename_object",
    "build_project",
  ]);

  for (const name of [
    "upsert_function_block",
    "upsert_program",
    "upsert_function",
    "upsert_object",
    "add_gvl_variable",
    "rename_object",
    "build_project",
  ]) {
    assert.equal(
      Object.hasOwn(tools.get(name).options.inputSchema, "approval_code"),
      false,
    );
  }

  assert.equal(
    tools.get("upsert_function_block").options.inputSchema.implementation.isOptional(),
    false,
  );
  assert.equal(
    tools.get("upsert_program").options.inputSchema.implementation.isOptional(),
    false,
  );
  assert.equal(
    tools.get("upsert_function").options.inputSchema.return_type.isOptional(),
    false,
  );
  assert.throws(
    () => tools.get("upsert_object").options.inputSchema.kind.parse("function_block"),
    /Invalid option/,
  );
  assert.equal(
    tools.get("upsert_function_block").options.inputSchema.save.parse(undefined),
    true,
  );
  assert.equal(tools.get("upsert_object").options.inputSchema.save.parse(undefined), true);
  assert.equal(tools.get("add_gvl_variable").options.inputSchema.save.parse(undefined), true);
  assert.equal(tools.get("rename_object").options.inputSchema.save.parse(undefined), true);
});

test("raw action tool forwards every parameter without permission gating", async () => {
  let received;
  const bridge = {
    async executeAgentAction(argumentsObject) {
      received = argumentsObject;
      return { ok: true, action: argumentsObject.action, data: {} };
    },
  };
  const tools = collectTools({ allowWrite: false, allowBuild: false }, bridge);

  const result = await tools.get("execute_codesys_action").handler({
    action: "application_command",
    parameters: { command: "clean", clear_messages: false },
  });

  assert.equal(result.isError, undefined);
  assert.deepEqual(received, {
    action: "application_command",
    parameters: { command: "clean", clear_messages: false },
  });
  assert.ok(toolInternals.supportedAgentActions.includes("ensure_library_references"));
  assert.match(
    tools.get("execute_codesys_action").options.description,
    /\{"libraries":\["Standard"\]\}/,
  );
});

test("upsert rejects empty executable objects before calling CODESYS", async () => {
  let called = false;
  const bridge = {
    async upsertObject() {
      called = true;
    },
  };
  const tools = collectTools({ allowWrite: true, allowBuild: false }, bridge);

  const result = await tools.get("upsert_function_block").handler({
    name: "FB_Test",
    declaration: "",
    implementation: "",
  });

  assert.equal(result.isError, true);
  assert.match(result.content[0].text, /declaration is required/);
  assert.match(result.content[0].text, /implementation with executable Structured Text is required/);
  assert.equal(called, false);
});

test("upsert rejects using an executable object as its own container", async () => {
  assert.throws(
    () =>
      toolInternals.prepareUpsertArguments({
        kind: "function_block",
        name: "FB_Test",
        container: "FB_Test",
        declaration: "VAR_INPUT\n    xIn : BOOL;\nEND_VAR",
        implementation: "xOut := xIn;",
      }),
    /container must be the parent/,
  );
});

test("upsert normalizes a function block declaration and verifies written code", async () => {
  let received;
  const bridge = {
    async upsertObject(argumentsObject) {
      received = argumentsObject;
      return {
        ok: true,
        data: {
          object: {
            name: "FB_Test",
            implementation: "xOut := xIn;",
          },
        },
      };
    },
  };
  const tools = collectTools({ allowWrite: true, allowBuild: false }, bridge);

  const result = await tools.get("upsert_function_block").handler({
    name: "FB_Test",
    declaration: "VAR_INPUT\n    xIn : BOOL;\nEND_VAR",
    implementation: "xOut := xIn;",
    save: true,
  });

  assert.equal(result.isError, undefined);
  assert.match(received.declaration, /^FUNCTION_BLOCK FB_Test\n/);
  assert.equal(received.implementation, "xOut := xIn;");
  assert.equal(received.save, true);
});
