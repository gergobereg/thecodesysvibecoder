import { execFile } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export class CodesysBridgeError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "CodesysBridgeError";
    this.details = details;
  }
}

export function runProcess(executable, argumentsList, options) {
  return new Promise((resolve, reject) => {
    execFile(executable, argumentsList, options, (error, stdout, stderr) => {
      if (error) {
        error.stdout = stdout;
        error.stderr = stderr;
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

function validateText(value, name, maximumLength = 4096, allowEmpty = false) {
  const text = String(value ?? "");
  if (!allowEmpty && !text.trim()) {
    throw new CodesysBridgeError(`${name} is required.`);
  }
  if (text.length > maximumLength) {
    throw new CodesysBridgeError(`${name} exceeds ${maximumLength} characters.`);
  }
  if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.test(text)) {
    throw new CodesysBridgeError(`${name} contains unsupported control characters.`);
  }
  return text;
}

function parseLauncherJson(stdout) {
  const text = String(stdout || "").replace(/^\uFEFF/, "").trim();
  const firstBrace = text.indexOf("{");
  const lastBrace = text.lastIndexOf("}");
  if (firstBrace < 0 || lastBrace < firstBrace) {
    throw new CodesysBridgeError("The CODESYS launcher returned no JSON result.");
  }

  let result;
  try {
    result = JSON.parse(text.slice(firstBrace, lastBrace + 1));
  } catch (error) {
    throw new CodesysBridgeError(`The CODESYS launcher returned invalid JSON: ${error.message}`);
  }

  if (!result || result.ok !== true) {
    const message = result?.error || result?.message || "The CODESYS agent rejected the request.";
    throw new CodesysBridgeError(String(message), { result });
  }
  return result;
}

export class CodesysBridge {
  constructor(config, processRunner = runProcess) {
    this.config = config;
    this.processRunner = processRunner;
    this.queueTail = Promise.resolve();
  }

  inspectProject() {
    return this.#enqueue(() => this.#invoke("inspect", ["-NoProjectPathMatch"]));
  }

  inspectTree({ depth = 3, root = "", includeText = false } = {}) {
    return this.#withActiveProject("inspect-tree", async (projectPath) => {
      const argumentsList = ["-Project", projectPath, "-Depth", String(depth)];
      if (root) {
        argumentsList.push("-Name", validateText(root, "root", 256));
      }
      if (includeText) {
        argumentsList.push("-IncludeText");
      }
      return this.#invoke("inspect-tree", argumentsList);
    });
  }

  readObject({ name }) {
    return this.#withActiveProject("read-object", (projectPath) =>
      this.#invoke("read-object", [
        "-Project",
        projectPath,
        "-Name",
        validateText(name, "name", 256),
      ]),
    );
  }

  addGvlVariable({ gvl = "GVL", variable, type = "BOOL", save = true }) {
    return this.#withActiveProject("add-gvl-var", async (projectPath) => {
      const argumentsList = [
        "-Project",
        projectPath,
        "-Gvl",
        validateText(gvl, "gvl", 256),
        "-Var",
        validateText(variable, "variable", 256),
        "-Type",
        validateText(type, "type", 1024),
      ];
      if (!save) {
        argumentsList.push("-NoSave");
      }
      return this.#invoke("add-gvl-var", argumentsList);
    });
  }

  upsertObject({
    kind,
    name,
    container = "",
    declaration = "",
    implementation = "",
    returnType = "",
    dutType = "Structure",
    baseType = "",
    interfaces = "",
    baseInterfaces = "",
    save = true,
  }) {
    return this.#withActiveProject("upsert-object", async (projectPath) => {
      const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), "codesys-mcp-"));
      try {
        const argumentsList = [
          "-Project",
          projectPath,
          "-Kind",
          validateText(kind, "kind", 64),
          "-Name",
          validateText(name, "name", 256),
        ];
        if (container) {
          argumentsList.push("-Container", validateText(container, "container", 256));
        }
        if (returnType) {
          argumentsList.push("-ReturnType", validateText(returnType, "returnType", 1024));
        }
        if (dutType) {
          argumentsList.push("-DutType", validateText(dutType, "dutType", 64));
        }
        if (baseType) {
          argumentsList.push("-BaseType", validateText(baseType, "baseType", 1024));
        }
        if (interfaces) {
          argumentsList.push("-Interfaces", validateText(interfaces, "interfaces", 4096));
        }
        if (baseInterfaces) {
          argumentsList.push(
            "-BaseInterfaces",
            validateText(baseInterfaces, "baseInterfaces", 4096),
          );
        }
        if (declaration) {
          const declarationPath = path.join(temporaryDirectory, "declaration.st");
          await writeFile(
            declarationPath,
            validateText(declaration, "declaration", 1024 * 1024),
            "utf8",
          );
          argumentsList.push("-DeclarationFile", declarationPath);
        }
        if (implementation) {
          const implementationPath = path.join(temporaryDirectory, "implementation.st");
          await writeFile(
            implementationPath,
            validateText(implementation, "implementation", 1024 * 1024),
            "utf8",
          );
          argumentsList.push("-ImplementationFile", implementationPath);
        }
        if (!save) {
          argumentsList.push("-NoSave");
        }
        return await this.#invoke("upsert-object", argumentsList);
      } finally {
        await rm(temporaryDirectory, { recursive: true, force: true });
      }
    });
  }

  renameObject({ oldName, newName, save = true }) {
    return this.#withActiveProject("rename-object", async (projectPath) => {
      const argumentsList = [
        "-Project",
        projectPath,
        "-OldName",
        validateText(oldName, "oldName", 256),
        "-NewName",
        validateText(newName, "newName", 256),
      ];
      if (!save) {
        argumentsList.push("-NoSave");
      }
      return this.#invoke("rename-object", argumentsList);
    });
  }

  buildProject({ command = "build" } = {}) {
    return this.#withActiveProject("application-command", (projectPath) =>
      this.#invoke("application-command", [
        "-Project",
        projectPath,
        "-AppCommand",
        validateText(command, "command", 32),
      ]),
    );
  }

  #withActiveProject(operationName, operation) {
    return this.#enqueue(async () => {
      const inspection = await this.#invoke("inspect", ["-NoProjectPathMatch"]);
      const projectPath = inspection?.data?.project_path;
      if (!projectPath) {
        throw new CodesysBridgeError(
          `Cannot run ${operationName}: the active CODESYS project has no saved path.`,
        );
      }
      return operation(projectPath);
    });
  }

  #enqueue(operation) {
    const queued = this.queueTail.then(operation, operation);
    this.queueTail = queued.catch(() => undefined);
    return queued;
  }

  async #invoke(command, commandArguments) {
    const argumentsList = [
      "-NoProfile",
      "-NonInteractive",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      this.config.launcherPath,
      command,
      "-TimeoutSeconds",
      String(this.config.requestTimeoutSeconds),
    ];
    if (this.config.agent) {
      argumentsList.push("-Agent", this.config.agent);
    }
    argumentsList.push(...commandArguments);

    try {
      const { stdout } = await this.processRunner(
        this.config.powershellExecutable,
        argumentsList,
        {
          cwd: this.config.repositoryRoot,
          encoding: "utf8",
          maxBuffer: this.config.maxOutputBytes,
          timeout: (this.config.requestTimeoutSeconds + 10) * 1000,
          windowsHide: true,
        },
      );
      return parseLauncherJson(stdout);
    } catch (error) {
      if (error instanceof CodesysBridgeError) {
        throw error;
      }
      const stderr = String(error.stderr || "").trim();
      const stdout = String(error.stdout || "").trim();
      const detail = stderr || stdout || error.message || "Unknown launcher error";
      throw new CodesysBridgeError(`CODESYS launcher failed: ${detail}`);
    }
  }
}

export const bridgeInternals = {
  parseLauncherJson,
  validateText,
};
