import { z } from "zod";

const objectKinds = [
  "folder",
  "gvl",
  "persistent_gvl",
  "program",
  "function_block",
  "function",
  "dut",
  "interface",
  "method",
  "property",
  "action",
  "transition",
];

const executableObjectKinds = new Set(["program", "function_block", "function"]);
const genericObjectKinds = objectKinds.filter(
  (kind) => !executableObjectKinds.has(kind),
);

const supportedAgentActions = [
  "inspect",
  "inspect_tree",
  "read_object",
  "export_object_text_files",
  "update_object_text_files",
  "describe_object",
  "describe_device_details",
  "export_object_xml",
  "import_object_xml",
  "describe_script_symbol",
  "describe_device_parameters",
  "export_device_internal_config",
  "import_device_internal_config",
  "describe_device_driver_info",
  "set_device_parameter_value",
  "set_device_diagnosis_enabled",
  "delete_objects",
  "add_gvl_var",
  "upsert_object",
  "upsert_visualization",
  "inspect_libraries",
  "ensure_library_placeholders",
  "remove_library_references",
  "configure_library_redirections",
  "inspect_device_versions",
  "update_device_version",
  "upsert_function_block",
  "rename_object",
  "set_device_enabled",
  "sync_device_enabled_from_uint_constant",
  "application_command",
  "inspect_build_properties",
  "ensure_compiler_defines",
  "project_check_all_pool_objects",
  "online_status",
  "online_login",
  "online_control",
  "online_read",
  "online_write",
];

function normalizeText(value) {
  return String(value ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
}

function prepareUpsertArguments(argumentsObject) {
  const prepared = {
    ...argumentsObject,
    kind: normalizeText(argumentsObject.kind),
    name: normalizeText(argumentsObject.name),
    container: normalizeText(argumentsObject.container),
    declaration: normalizeText(argumentsObject.declaration),
    implementation: normalizeText(argumentsObject.implementation),
    return_type: normalizeText(argumentsObject.return_type),
  };

  if (!executableObjectKinds.has(prepared.kind)) {
    return prepared;
  }

  const problems = [];
  if (!prepared.declaration) {
    problems.push("declaration is required");
  }
  if (!prepared.implementation) {
    problems.push("implementation with executable Structured Text is required");
  }
  if (
    prepared.container &&
    prepared.container.toLocaleLowerCase() === prepared.name.toLocaleLowerCase()
  ) {
    problems.push(
      "container must be the parent (for example Application), never the object itself; omit it for the active Application",
    );
  }

  if (prepared.kind === "function" && !prepared.return_type) {
    const returnTypeMatch = prepared.declaration.match(
      /(?:^|\n)\s*FUNCTION\s+\S+\s*:\s*([^\s;]+)/i,
    );
    if (returnTypeMatch) {
      prepared.return_type = returnTypeMatch[1];
    } else {
      problems.push("return_type is required when creating a function");
    }
  }

  if (problems.length > 0) {
    throw new Error(
      `Invalid ${prepared.kind} request: ${problems.join("; ")}. ` +
        "Send the complete declaration and implementation together in one call.",
    );
  }

  const keyword = {
    program: "PROGRAM",
    function_block: "FUNCTION_BLOCK",
    function: "FUNCTION",
  }[prepared.kind];
  const hasHeader = new RegExp(`(?:^|\\n)\\s*${keyword}\\s+`, "i").test(
    prepared.declaration,
  );
  if (!hasHeader) {
    const returnType = prepared.kind === "function" ? ` : ${prepared.return_type}` : "";
    prepared.declaration = `${keyword} ${prepared.name}${returnType}\n${prepared.declaration}`;
  }

  return prepared;
}

function verifyExecutableWrite(result, argumentsObject) {
  if (!executableObjectKinds.has(argumentsObject.kind)) {
    return result;
  }

  const object = result?.data?.object;
  if (!object || normalizeText(object.name) !== argumentsObject.name) {
    throw new Error("CODESYS did not return the expected object after the write.");
  }
  if (normalizeText(object.implementation) !== argumentsObject.implementation) {
    throw new Error(
      "CODESYS returned success, but the implementation read back from the object does not match the requested code.",
    );
  }
  return result;
}

async function executeUpsert(bridge, argumentsObject) {
  const prepared = prepareUpsertArguments(argumentsObject);
  const result = await bridge.upsertObject({
    kind: prepared.kind,
    name: prepared.name,
    container: prepared.container,
    declaration: prepared.declaration,
    implementation: prepared.implementation,
    returnType: prepared.return_type,
    dutType: prepared.dut_type,
    baseType: prepared.base_type,
    interfaces: prepared.interfaces,
    baseInterfaces: prepared.base_interfaces,
    save: prepared.save,
  });
  return verifyExecutableWrite(result, prepared);
}

function toolResult(value) {
  return {
    content: [{ type: "text", text: JSON.stringify(value, null, 2) }],
  };
}

function toolError(error) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          null,
          2,
        ),
      },
    ],
    isError: true,
  };
}

function guarded(name, operation) {
  return async (argumentsObject) => {
    const startedAt = Date.now();
    try {
      const result = await operation(argumentsObject);
      console.log(
        JSON.stringify({
          timestamp: new Date().toISOString(),
          tool: name,
          ok: true,
          duration_ms: Date.now() - startedAt,
        }),
      );
      return toolResult(result);
    } catch (error) {
      console.error(
        JSON.stringify({
          timestamp: new Date().toISOString(),
          tool: name,
          ok: false,
          duration_ms: Date.now() - startedAt,
          error: error instanceof Error ? error.message : String(error),
        }),
      );
      return toolError(error);
    }
  };
}

function registerExecutableTool(server, bridge, kind, title) {
  const inputSchema = {
    name: z.string().min(1).max(256),
    declaration: z
      .string()
      .min(1)
      .max(1024 * 1024)
      .describe(
        "Complete IEC declaration with all VAR sections. The object header is added automatically if omitted.",
      ),
    implementation: z
      .string()
      .min(1)
      .max(1024 * 1024)
      .describe("Required executable IEC Structured Text body, not variable declarations."),
    save: z.boolean().optional().default(true),
  };

  if (kind === "function") {
    inputSchema.return_type = z.string().min(1).max(1024);
  }
  if (kind === "function_block") {
    inputSchema.base_type = z.string().max(1024).optional().default("");
    inputSchema.interfaces = z.string().max(4096).optional().default("");
  }

  const toolName = `upsert_${kind}`;
  server.registerTool(
    toolName,
    {
      title,
      description:
        `${title} in the active CODESYS Application. ` +
        "Always send the complete declaration and executable implementation together in this one call. The write is read back and verified, and saves by default.",
      inputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    guarded(toolName, (argumentsObject) =>
      executeUpsert(bridge, {
        ...argumentsObject,
        kind,
        container: "",
        return_type: argumentsObject.return_type ?? "",
        dut_type: "Structure",
        base_type: argumentsObject.base_type ?? "",
        interfaces: argumentsObject.interfaces ?? "",
        base_interfaces: "",
      }),
    ),
  );
}

export function registerCodesysTools(server, bridge, config) {
  server.registerTool(
    "inspect_project",
    {
      title: "Inspect active CODESYS project",
      description:
        "Read the active CODESYS project identity, dirty state, active application, and top-level objects. Call this first.",
      inputSchema: {},
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    guarded("inspect_project", () => bridge.inspectProject()),
  );

  server.registerTool(
    "inspect_tree",
    {
      title: "Inspect CODESYS project tree",
      description:
        "Read the active project tree. Use a small depth first; request object text only when it is needed.",
      inputSchema: {
        depth: z.number().int().min(0).max(8).default(3),
        root: z.string().max(256).optional().default(""),
        include_text: z.boolean().optional().default(false),
      },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    guarded("inspect_tree", ({ depth, root, include_text }) =>
      bridge.inspectTree({ depth, root, includeText: include_text }),
    ),
  );

  server.registerTool(
    "read_object",
    {
      title: "Read a CODESYS object",
      description:
        "Read one named CODESYS object, including its declaration and implementation when textual content is available.",
      inputSchema: {
        name: z.string().min(1).max(256),
      },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    guarded("read_object", ({ name }) => bridge.readObject({ name })),
  );

  server.registerTool(
    "execute_codesys_action",
    {
      title: "Execute any CODESYS agent action",
      description:
        "Pass an action and its parameters directly to the in-IDE CODESYS agent without per-action restrictions or validation. " +
        `Current actions: ${supportedAgentActions.join(", ")}. ` +
        "Parameter names are the keys read by ide_scripts/codesys_agent.py. Paths refer to the Windows computer running CODESYS, not the remote MCP client.",
      inputSchema: {
        action: z
          .string()
          .min(1)
          .max(256)
          .describe("The exact CODESYS agent action name."),
        parameters: z
          .record(z.string(), z.unknown())
          .optional()
          .default({})
          .describe(
            "The remaining raw request fields for the action. Do not repeat the action key here.",
          ),
      },
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: false,
        openWorldHint: false,
      },
    },
    guarded("execute_codesys_action", ({ action, parameters }) =>
      bridge.executeAgentAction({ action, parameters }),
    ),
  );

  if (config.allowWrite) {
    registerExecutableTool(
      server,
      bridge,
      "function_block",
      "Create or update a CODESYS function block",
    );
    registerExecutableTool(
      server,
      bridge,
      "program",
      "Create or update a CODESYS program",
    );
    registerExecutableTool(
      server,
      bridge,
      "function",
      "Create or update a CODESYS function",
    );

    server.registerTool(
      "upsert_object",
      {
        title: "Create or update another CODESYS object",
        description:
          "Create or update a folder, GVL, persistent GVL, DUT, interface, method, property, action, or transition. Use the dedicated upsert_function_block, upsert_program, or upsert_function tool for executable top-level POUs. The container is the parent, never the object name. Successful writes save by default.",
        inputSchema: {
          kind: z.enum(genericObjectKinds),
          name: z.string().min(1).max(256),
          container: z
            .string()
            .max(256)
            .optional()
            .default("")
            .describe(
              "Parent container such as Application or a folder. Never use the object name itself. Omit for the active Application.",
            ),
          declaration: z
            .string()
            .max(1024 * 1024)
            .optional()
            .default("")
            .describe(
              "Complete IEC declaration. Required for programs, function blocks, and functions. A missing PROGRAM/FUNCTION_BLOCK/FUNCTION header is added automatically.",
            ),
          implementation: z
            .string()
            .max(1024 * 1024)
            .optional()
            .default("")
            .describe(
              "Executable IEC Structured Text body. Required and non-empty for programs, function blocks, and functions.",
            ),
          return_type: z
            .string()
            .max(1024)
            .optional()
            .default("")
            .describe("Required for functions; not used for programs or function blocks."),
          dut_type: z.enum(["Structure", "Enumeration", "Union", "Alias"]).default("Structure"),
          base_type: z.string().max(1024).optional().default(""),
          interfaces: z.string().max(4096).optional().default(""),
          base_interfaces: z.string().max(4096).optional().default(""),
          save: z.boolean().optional().default(true),
        },
        annotations: {
          readOnlyHint: false,
          destructiveHint: true,
          idempotentHint: true,
          openWorldHint: false,
        },
      },
      guarded("upsert_object", (argumentsObject) =>
        executeUpsert(bridge, argumentsObject),
      ),
    );

    server.registerTool(
      "add_gvl_variable",
      {
        title: "Add a CODESYS GVL variable",
        description:
          "Ensure that a variable exists in a GVL. Inspect the project first. Successful writes save by default.",
        inputSchema: {
          gvl: z.string().min(1).max(256).default("GVL"),
          variable: z.string().min(1).max(256),
          type: z.string().min(1).max(1024).default("BOOL"),
          save: z.boolean().optional().default(true),
        },
        annotations: {
          readOnlyHint: false,
          destructiveHint: true,
          idempotentHint: true,
          openWorldHint: false,
        },
      },
      guarded("add_gvl_variable", (argumentsObject) =>
        bridge.addGvlVariable(argumentsObject),
      ),
    );

    server.registerTool(
      "rename_object",
      {
        title: "Rename a CODESYS object",
        description:
          "Rename one CODESYS object. Read the object first. Successful writes save by default.",
        inputSchema: {
          old_name: z.string().min(1).max(256),
          new_name: z.string().min(1).max(256),
          save: z.boolean().optional().default(true),
        },
        annotations: {
          readOnlyHint: false,
          destructiveHint: true,
          idempotentHint: false,
          openWorldHint: false,
        },
      },
      guarded("rename_object", ({ old_name, new_name, save }) => {
        return bridge.renameObject({ oldName: old_name, newName: new_name, save });
      }),
    );
  }

  if (config.allowBuild) {
    server.registerTool(
      "build_project",
      {
        title: "Build the active CODESYS application",
        description:
          "Build or rebuild the active CODESYS application and return compiler messages.",
        inputSchema: {
          command: z.enum(["build", "rebuild"]).default("build"),
        },
        annotations: {
          readOnlyHint: false,
          destructiveHint: false,
          idempotentHint: false,
          openWorldHint: false,
        },
      },
      guarded("build_project", ({ command }) => bridge.buildProject({ command })),
    );
  }
}

export const toolInternals = {
  executeUpsert,
  executableObjectKinds,
  genericObjectKinds,
  prepareUpsertArguments,
  objectKinds,
  supportedAgentActions,
  toolError,
  toolResult,
  verifyExecutableWrite,
};
