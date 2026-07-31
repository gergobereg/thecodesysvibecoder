# Repository instructions

## Purpose and environment

This repository controls an already-running CODESYS IDE through an IronPython
agent.

- CODESYS V3.5 SP22 Patch 1 is expected to be running already.
- A project is expected to be open and active in the IDE.
- The in-IDE agent is expected to be running from
  `ide_scripts/run_in_ide_agent.py`.
- Treat the repository root as the workspace root.

## Required startup procedure

At the beginning of every task in this repository:

1. Read `README.md`.
2. Read `deep-research-report.md` if it exists. If it is absent, continue using
   `README.md` and mention the missing document only when it affects the task.
3. Inspect the active IDE project before planning or making project changes:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 inspect -NoProjectPathMatch
   ```

4. Treat the inspection result, rather than assumptions about a project path or
   project name, as the source of truth for the active project.

Run commands from the repository root unless a command explicitly requires a
different working directory.

## IDE access rules

- Do not launch another CODESYS instance.
- Do not use `launcher/Invoke-CodesysAgent.ps1` for normal work in this
  repository.
- Do not execute `ide_scripts/run_in_ide_agent.py` from the shell; it runs
  inside the CODESYS ScriptEngine.
- Communicate with the running IDE through
  `launcher/Send-CodesysRequest.ps1`.
- Do not stop the in-IDE agent unless the user explicitly requests it.
- If the initial inspection fails, diagnose the agent/mailbox connection and
  report the failure. Do not work around it by starting another IDE instance.
- Before modifying an IDE object, inspect the relevant project tree or object
  through the agent.

## Public repository hygiene

- Keep committed instructions, examples, logs, and fixtures free of usernames,
  user-profile paths, private project names, credentials, tokens, controller
  addresses, and other machine- or person-specific data.
- Prefer repository-relative paths in documentation and examples.
- Do not commit generated request/result mailbox contents from
  `.codesys_agent/` or temporary working files from `tmp/`.
