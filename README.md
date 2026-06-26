# Quicguide:

 - Run:
    1. Tools / Scripting / Execute Script File
    2. `ide_scripts\run_in_ide_agent.py`
 - Stop:
    `powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 stop`

# CODESYS IDE Automation

This workspace contains a small split-runtime automation layer for CODESYS V3.5 SP22 Patch 1.

- `ide_scripts/codesys_agent.py` runs inside the CODESYS ScriptEngine / IronPython environment.
- `ide_scripts/run_in_ide_agent.py` is the preferred path for an already-running CODESYS instance. Run it once inside CODESYS, then send requests from this workspace.
- `launcher/Send-CodesysRequest.ps1` writes requests for the in-IDE agent and waits for results. It does not start CODESYS.
- `launcher/Invoke-CodesysAgent.ps1` starts CODESYS with `--runscript` from PowerShell as a fallback for headless/new-instance workflows.
- `launcher/codesys_runner.py` provides the same flow for a working CPython install.
- Requests and results are stored under `.codesys_agent/` for audit/debugging.

For the already-running IDE workflow:

1. In CODESYS, run `ide_scripts\run_in_ide_agent.py` using the built-in scripting command or Python editor.
2. Leave that script running.
3. From this workspace, send requests:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 inspect
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 inspect-tree -Depth 2
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 read-object -Name FB_HydraulicCylinder
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 add-gvl-var -Gvl GVL -Var xTest -Type BOOL
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 hydraulic-cylinder-fb
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 sync-device-from-uint -Name S10e_1 -ConstantObject GVL -ConstantName uiUnits -EnableWhenAtLeast 2
```

For two open CODESYS IDE instances, run one named watcher in each IDE instance:

```text
IDE instance 1: Tools / Scripting / Execute Script File -> ide_scripts\run_in_ide_agent_agent1.py
IDE instance 2: Tools / Scripting / Execute Script File -> ide_scripts\run_in_ide_agent_agent2.py
```

Then target requests with `-Agent`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 inspect -Agent agent1 -NoProjectPathMatch
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 inspect -Agent agent2 -NoProjectPathMatch
```

Confirm each returned `project_path` before editing. After that, keep passing the same `-Agent` value on every command so project-copy operations go to the intended IDE instance. The original `run_in_ide_agent.py` still uses the legacy default `.codesys_agent\` mailbox, so do not run it in two IDE instances at the same time. Named agents use separate mailboxes under `.codesys_agent\agent1\`, `.codesys_agent\agent2\`, and so on.

Stop only one named watcher with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 stop -Agent agent2
```

For online/login work, avoid logging two IDE instances into the same PLC application at the same time. CODESYS SP17 and newer may allow only one engineering login per controller application.

`sync-device-from-uint` changes the IDE project tree before download. For runtime S10e unit-count changes, use `FB_EtherCATOptionalSlaveManager`, not `FB_IoConnectorRuntimeEnable`. The low-level connector FB can disable an EtherCAT slave by clearing IoStandard connector flags, but that can remove the slave from the runtime configuration and it may stay greyed out until a controller warm restart.

`FB_EtherCATOptionalSlaveManager` keeps every configured EtherCAT slave in the project and marks slaves above `GVL.uiUnits` as optional through the EtherCAT driver. It also sets `EtherCAT_Master.StartConfigWithLessDevice := TRUE` and `EtherCAT_Master.AutoSetOperational := TRUE`, so the master tolerates missing optional slaves and retries them when they are connected again. `POU` is wired to this FB: change `GVL.uiUnits`, optionally pulse `xApplyUnitConfig`, and pulse `xRestartEtherCATMaster` only when you want a manual master restart.

The older `FB_IoConnectorRuntimeEnable` and `FB_S10eRuntimeEnable` are left in the project only for reference and non-EtherCAT experiments. Do not use them for S10e runtime selection unless you are prepared to recover with a controller warm restart.

Generic object creation/update is available through `upsert-object`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 upsert-object -Kind function_block -Name FB_New -DeclarationFile .\tmp\FB_New.decl.st -ImplementationFile .\tmp\FB_New.impl.st
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 upsert-object -Kind program -Name PRG_New -DeclarationFile .\tmp\PRG_New.decl.st -ImplementationFile .\tmp\PRG_New.impl.st
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 upsert-object -Kind function -Name F_Add -ReturnType INT -DeclarationFile .\tmp\F_Add.decl.st -ImplementationFile .\tmp\F_Add.impl.st
```

Supported `-Kind` values include `folder`, `gvl`, `persistent_gvl`, `program`, `function_block`, `function`, `dut`, `interface`, `method`, `property`, `action`, and `transition`.

For requests that do not have a dedicated command yet, send raw JSON:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 send-json -RequestJson .\tmp\request.json
```

Application commands are also exposed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 application-command -AppCommand build
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 application-command -AppCommand rebuild
```

To stop the in-IDE watcher:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 stop
```

The first edit action is idempotent: it creates `GVL` under the active application if needed, ensures `xTest : BOOL;` exists in its declaration, and saves the project unless `-NoSave` is passed.
