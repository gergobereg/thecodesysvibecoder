# thecodesysvibecoder

`thecodesysvibecoder` controls an already-running CODESYS engineering instance
through a small IronPython agent. It can be used locally from PowerShell or
remotely from an authenticated MCP client such as a self-hosted AnythingLLM
instance.

## Quick guide

- Start the in-IDE agent:
    1. Tools / Scripting / Execute Script File
    2. `ide_scripts\run_in_ide_agent.py`
    3. The startup script returns immediately; the registered agent remains active.
- Stop the agent:
    From the repository root, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 stop`.

## Local automation

This workspace contains a small split-runtime automation layer for CODESYS V3.5 SP22 Patch 1.

- `ide_scripts/codesys_agent.py` runs inside the CODESYS ScriptEngine / IronPython environment.
- `ide_scripts/run_in_ide_agent.py` is the preferred path for an already-running CODESYS instance. Run it once inside CODESYS; it registers a UI-thread timer, returns control to the user interface, and then handles requests from this workspace.
- `launcher/Send-CodesysRequest.ps1` writes requests for the in-IDE agent and waits for results. It does not start CODESYS.
- `launcher/Invoke-CodesysAgent.ps1` starts CODESYS with `--runscript` from PowerShell as a fallback for headless/new-instance workflows.
- `launcher/codesys_runner.py` provides the same flow for a working CPython install.
- Requests and results are stored under `.codesys_agent/` for audit/debugging.

For the already-running IDE workflow:

1. In CODESYS, run `ide_scripts\run_in_ide_agent.py` using the built-in scripting command or Python editor.
2. Wait for the script command to return. The registered agent remains active while the CODESYS user interface is available.
3. From this workspace, send requests:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 inspect
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 inspect-tree -Depth 2
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 read-object -Name MyObject
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 add-gvl-var -Gvl GVL -Var xTest -Type BOOL
```

### Non-blocking operation and stopping the agent

`run_in_ide_agent.py` does not keep the CODESYS scripting command open. It
registers a timer on the CODESYS user-interface thread and then returns. The
timer checks the mailbox every 500 milliseconds, so CODESYS remains usable
while the agent is idle. An individual edit, save, or build request can still
make CODESYS briefly busy while that operation executes.

To stop the default agent from the repository root, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\launcher\Send-CodesysRequest.ps1 `
  stop
```

If the PowerShell prompt is already inside the `ide_scripts` directory, use
`..\launcher` instead:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ..\launcher\Send-CodesysRequest.ps1 `
  stop
```

The agent normally detects the stop file within 500 milliseconds, detaches its
timer, and prints `CODESYS in-IDE agent stopped: default`. This does not close
CODESYS, close the project, or stop the separate MCP bridge. To start the agent
again, execute `ide_scripts\run_in_ide_agent.py` inside CODESYS.

For two open CODESYS instances, run one named watcher in each instance:

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

For example, the raw `ensure_library_references` action adds an installed
managed/fixed library by its short name or full resolution:

```json
{
  "action": "ensure_library_references",
  "libraries": ["Standard"],
  "save": true
}
```

Application commands are also exposed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 application-command -AppCommand build
powershell -NoProfile -ExecutionPolicy Bypass -File .\launcher\Send-CodesysRequest.ps1 application-command -AppCommand rebuild
```

The first edit action is idempotent: it creates `GVL` under the active application if needed, ensures `xTest : BOOL;` exists in its declaration, and saves the project unless `-NoSave` is passed.

## Connect two Windows PCs: CODESYS on one, VS Code Copilot on the other

This procedure uses the following names:

| Name | Role |
| --- | --- |
| Computer A | Windows PC running CODESYS, this repository, the in-IDE agent, and the MCP bridge |
| Computer B | Windows PC running VS Code and GitHub Copilot |
| `<COMPUTER_A_IP_ADDRESS>` | LAN IPv4 address of computer A, for example `192.168.1.20` |
| `<COMPUTER_B_IP_ADDRESS>` | LAN IPv4 address of computer B, for example `192.168.1.30` |
| `<COMPUTER_A_HOSTNAME>` | Windows computer name of computer A |
| `<REPOSITORY_ROOT>` | Local path to this repository on computer A |

The two connections serve different purposes:

```text
Computer B                                      Computer A
------------------------------------            ---------------------------------
VS Code workspace  --optional SMB share------> repository/project files
GitHub Copilot     --HTTP MCP, TCP 8765------> MCP bridge
                                                      |
                                                      v
                                               PowerShell mailbox launcher
                                                      |
                                                      v
                                               in-IDE agent -> active CODESYS project
```

The network share lets Copilot read normal workspace files and repository
instructions. MCP is the control connection that lets Copilot inspect and
change the project currently open in CODESYS. MCP does not require the CODESYS
project file itself to be shared, and sharing a folder does not replace MCP.

Both computers should be on the same trusted private LAN, or connected through
an organization-approved VPN. Do not forward port `8765` through an Internet
router.

### 1. Prepare computer A

Computer A needs:

- Windows 10 or Windows 11.
- CODESYS V3.5 SP22 Patch 1 with scripting support.
- This complete repository; do not copy only `mcp-server`.
- Node.js 20 or newer.

From a normal PowerShell window on computer A, install and test the bridge:

```powershell
Set-Location "<REPOSITORY_ROOT>\mcp-server"
node --version
npm.cmd ci
npm.cmd test
```

Find the active IPv4 address and computer name:

```powershell
ipconfig
$env:COMPUTERNAME
```

Use the IPv4 address of the Ethernet or Wi-Fi adapter connected to computer B.
Avoid a VPN, virtual-machine, Bluetooth, or disconnected adapter address unless
that adapter is intentionally carrying the connection.

### 2. Generate the API key on computer A

Generate one random key. Do not put its value in this repository or in the VS
Code MCP configuration file:

```powershell
$McpRandom = [Security.Cryptography.RandomNumberGenerator]::Create()
$McpBytes = New-Object byte[] 32
$McpRandom.GetBytes($McpBytes)
$McpRandom.Dispose()
$McpApiKey = ([BitConverter]::ToString($McpBytes)).Replace("-", "")
$env:CODESYS_MCP_API_KEY = $McpApiKey
$McpApiKey.Length
```

The final command must print `64`. On a trusted, single-user account, save the
key as a user environment variable so it survives a reboot:

```powershell
[Environment]::SetEnvironmentVariable(
  "CODESYS_MCP_API_KEY",
  $McpApiKey,
  "User"
)
```

Transfer the key once to computer B through a trusted password manager or
another encrypted channel. VS Code will request it through a password input;
it does not need to appear in `mcp.json`.

### 3. Allow computer B through the firewall on computer A

Run `ipconfig` on computer B and note its LAN IPv4 address. Then open
**PowerShell as Administrator on computer A** and create an inbound rule that
accepts only computer B:

```powershell
Get-NetConnectionProfile

$CopilotPcIp = "<COMPUTER_B_IP_ADDRESS>"

New-NetFirewallRule `
  -DisplayName "thecodesysvibecoder MCP from Copilot PC" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8765 `
  -RemoteAddress $CopilotPcIp `
  -Profile Private,Domain
```

The active connection shown by `Get-NetConnectionProfile` should be `Private`
or `DomainAuthenticated`. Do not enable this rule for a `Public` network.

Verify both the port and permitted remote address:

```powershell
Get-NetFirewallRule `
  -DisplayName "thecodesysvibecoder MCP from Copilot PC" |
  Get-NetFirewallPortFilter

Get-NetFirewallRule `
  -DisplayName "thecodesysvibecoder MCP from Copilot PC" |
  Get-NetFirewallAddressFilter
```

Computer B initiates the connection, so it normally needs no inbound firewall
rule and no administrator rights. Administrator access is required only on
computer A to create the inbound rule. If company policy blocks outbound port
`8765` on computer B or prevents an inbound rule on computer A, an administrator
must approve the connection or provide an approved VPN/tunnel.

### 4. Start CODESYS and the in-IDE agent on computer A

1. Start CODESYS normally on computer A.
2. Open the project Copilot should control and make it the active project.
3. Select **Tools > Scripting > Execute Script File** in CODESYS.
4. Select `<REPOSITORY_ROOT>\ide_scripts\run_in_ide_agent.py`.
5. Wait for the script command to return. The registered agent remains active.

Do not execute `run_in_ide_agent.py` from PowerShell and do not start another
CODESYS instance as a workaround.

From the repository root on computer A, verify the real active project:

```powershell
Set-Location "<REPOSITORY_ROOT>"

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\launcher\Send-CodesysRequest.ps1 `
  inspect `
  -NoProjectPathMatch
```

Continue only when the JSON contains `"ok": true` and identifies the expected
project and active application.

### 5. Start the MCP bridge on computer A

Use a normal, non-administrator PowerShell window. Load the saved API key,
allow the IP address and hostname that computer B will use in its URL, enable
the named write/build tools, and start the bridge on all LAN interfaces:

```powershell
Set-Location "<REPOSITORY_ROOT>\mcp-server"

$env:CODESYS_MCP_API_KEY = [Environment]::GetEnvironmentVariable(
  "CODESYS_MCP_API_KEY",
  "User"
)

if ([string]::IsNullOrWhiteSpace($env:CODESYS_MCP_API_KEY) -or
    $env:CODESYS_MCP_API_KEY.Length -lt 32) {
  throw "A valid CODESYS_MCP_API_KEY was not found."
}

$env:CODESYS_MCP_ALLOWED_HOSTS = `
  "<COMPUTER_A_IP_ADDRESS>,<COMPUTER_A_HOSTNAME>"
$env:CODESYS_MCP_ALLOW_WRITE = "true"
$env:CODESYS_MCP_ALLOW_BUILD = "true"

Remove-Item Env:CODESYS_MCP_ALLOWED_IPS -ErrorAction SilentlyContinue

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\Start-CodesysMcpBridge.ps1 `
  -ListenAddress 0.0.0.0 `
  -Port 8765
```

Keep this PowerShell window open. Expected startup output includes:

```text
CODESYS MCP bridge listening at http://0.0.0.0:8765/mcp (SSE fallback: /sse)
Tools: raw action enabled; named read-only enabled; write=true; build=true; agent=default
```

In another PowerShell window on computer A, confirm that the listener exists:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen
```

### 6. Test the network from computer B

Run these commands in PowerShell on computer B:

```powershell
Test-NetConnection <COMPUTER_A_IP_ADDRESS> -Port 8765
Invoke-RestMethod http://<COMPUTER_A_IP_ADDRESS>:8765/health
```

`TcpTestSucceeded` must be `True`, and the health request should return a result
equivalent to:

```json
{"status":"ok","service":"codesys-mcp-bridge"}
```

The health endpoint checks only the HTTP bridge. It does not require the API
key and does not prove that the in-IDE agent is running; step 4 verifies that
separate connection.

### 7. Optionally open computer A's folder in VS Code on computer B

If Copilot should also read repository files and `AGENTS.md`, share the desired
folder on computer A using Windows file sharing:

1. In File Explorer on computer A, right-click the repository folder and select
   **Properties > Sharing > Advanced Sharing**.
2. Select **Share this folder**, choose a share name, and open **Permissions**.
3. Grant the Windows account used from computer B **Read** permission. Grant
   **Change** only if that account should intentionally edit repository files.
4. Check the folder's **Security** tab as well; both the share permissions and
   NTFS permissions must allow the intended access.
5. Apply the changes. Creating the share may require administrator approval on
   computer A.

Then, on computer B, select **File > Open Folder** in VS Code and enter a UNC
path such as:

```text
\\<COMPUTER_A_HOSTNAME>\<SHARE_NAME>
```

Read permission is sufficient when all CODESYS changes go through MCP. Grant
Change permission only if Copilot should intentionally edit the repository
files from computer B. Only computer A should open the CODESYS project in the
CODESYS IDE.

The shared folder and MCP endpoint are independent. If the folder is not
shared, Copilot can still operate the active CODESYS project through MCP, but
it will not automatically see the repository instructions or normal files.

### 8. Configure MCP in VS Code on computer B

Use VS Code user configuration so the LAN address stays out of the public
repository:

1. Install VS Code and the GitHub Copilot Chat extension, then sign in.
2. Press `Ctrl+Shift+P` to open the Command Palette.
3. Run **MCP: Open User Configuration**.
4. Merge the following `codesys` server into the opened `mcp.json`, replacing
   `<COMPUTER_A_IP_ADDRESS>` with computer A's real LAN address.

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "codesys-api-key",
      "description": "CODESYS MCP API key",
      "password": true
    }
  ],
  "servers": {
    "codesys": {
      "type": "http",
      "url": "http://<COMPUTER_A_IP_ADDRESS>:8765/mcp",
      "headers": {
        "X-API-Key": "${input:codesys-api-key}"
      }
    }
  }
}
```

If the file already contains other inputs or servers, preserve them and add
only the new entries. Save the file, then:

1. Press `Ctrl+Shift+P` and run **MCP: List Servers**.
2. Select `codesys`, then select **Start Server** or **Restart Server**.
3. Paste the API key when VS Code displays the password prompt.
4. Review and accept the MCP trust prompt if VS Code shows it.
5. Use **Show Output** for `codesys` and confirm the server is running and its
   tools were discovered.
6. Open Copilot Chat in **Agent** mode, open the tools picker, and enable the
   `codesys` tools.

The normal configuration currently exposes 11 tools. The exact count can
change when named tools are added; successful discovery and the presence of
`inspect_project` and `execute_codesys_action` are more important than the
number alone.

### 9. Perform the first Copilot test

Start with a read-only request in Copilot Agent mode:

```text
Use the CODESYS MCP tools. Inspect the active project, report its project path
and active application, then inspect the project tree to depth 3. Do not modify
anything.
```

Compare the returned project with the project visible on computer A. After it
matches, test a build:

```text
Build the active CODESYS application through MCP and report all compiler errors
and warnings. Do not change the project.
```

For actual changes, instruct Copilot to inspect affected objects first, make
the smallest change, read the result back, and build. A successful MCP transport
call is not enough; the returned CODESYS JSON must contain `"ok": true`.

The `execute_codesys_action` tool accepts the exact action name and a raw
`parameters` object. For example, its arguments for a clean are:

```json
{
  "action": "application_command",
  "parameters": {
    "command": "clean"
  }
}
```

It exposes every action implemented by `ide_scripts/codesys_agent.py`, including
clean/generate code, device and library configuration, XML/text import and
export, visualizations, compiler defines, deletion, and online login/control/
read/write. For import/export actions, paths are interpreted on computer A. A
drive letter mapped only on computer B will not work; use a computer-A-local
path or a UNC path that computer A can access.

### 10. Daily startup after the one-time setup

On computer A:

1. Start CODESYS and open the intended project.
2. Run `ide_scripts\run_in_ide_agent.py` inside CODESYS.
3. Run the `inspect -NoProjectPathMatch` command from step 4.
4. Run the bridge startup block from step 5 and leave that PowerShell window
   open.

On computer B:

1. Open the workspace in VS Code.
2. Run **MCP: List Servers** and confirm `codesys` is running.
3. Start a new Copilot Agent chat and verify the active project before editing.

### 11. Restart after bridge or tool changes

When this repository's MCP code or tool descriptions change:

1. Press `Ctrl+C` in the bridge PowerShell window on computer A.
2. Run the bridge startup command from step 5 again.
3. On computer B, run **MCP: List Servers**, select `codesys`, and choose
   **Restart Server**.
4. Run **MCP: Reset Cached Tools** from the Command Palette.
5. Start a new Copilot Agent chat if an existing chat still uses the old tool
   schema.

Restarting the MCP bridge does not restart CODESYS or the in-IDE agent.

### 12. Two-Windows-PC troubleshooting

| Symptom | Check |
| --- | --- |
| `TcpTestSucceeded` is `False` | Confirm the bridge is running with `-ListenAddress 0.0.0.0`, computer A's IP has not changed, both PCs are on the intended network, and the firewall rule on computer A permits computer B's current IP. |
| `/health` works but VS Code reports HTTP `401` | The API key pasted into VS Code does not match `CODESYS_MCP_API_KEY` used when the bridge started. Restart the VS Code server to prompt for it again. |
| VS Code reports HTTP `421` | Add the exact IP address or hostname used in the MCP URL to `CODESYS_MCP_ALLOWED_HOSTS`, then restart the bridge. |
| MCP connects but CODESYS requests time out | Run the inspection command locally on computer A. Re-run `run_in_ide_agent.py` inside the correct CODESYS instance if needed. |
| Copilot sees old tools | Restart the bridge on computer A, restart `codesys` in **MCP: List Servers**, run **MCP: Reset Cached Tools**, and start a new Agent chat. |
| The shared folder cannot be opened | Diagnose Windows file sharing and credentials separately. MCP can still work when SMB sharing does not, and SMB can work while MCP port `8765` is blocked. |
| Computer B has no administrator rights | This is normally fine. The required inbound firewall rule is created on computer A. Corporate outbound restrictions on computer B still require an administrator. |
| Port `8765` cannot be opened on computer A | Direct LAN MCP cannot work until an administrator permits it. Use an organization-approved VPN or authenticated tunnel rather than exposing the port publicly. |

## Connect a local AnythingLLM installation through MCP

This section starts with two clean computers and builds the following setup:

```text
Ubuntu computer                              Windows computer
------------------------------               ------------------------------
Ollama + local model                         CODESYS with an open project
AnythingLLM Docker :3001       --MCP-->       thecodesysvibecoder :8765
MCP client                                   in-IDE IronPython agent
```

AnythingLLM and Ollama remain on Ubuntu. CODESYS, the repository, the mailbox,
PowerShell launcher, and MCP bridge remain on Windows. Only TCP port `8765`
needs to cross from Ubuntu to Windows. Do not forward ports `8765`, `3001`, or
`11434` through the Internet router.

Use these placeholders throughout the instructions:

| Computer | Placeholder |
| --- | --- |
| Ubuntu with Ollama/AnythingLLM | `<UBUNTU_PC_IP_ADDRESS>` |
| Windows with CODESYS | `<WINDOWS_PC_IP_ADDRESS>` |

Reserve both addresses in the router's DHCP settings or configure stable LAN
addresses. Substitute the real addresses in every following command.

If the one-time setup is already complete, skip to
[Daily startup after the initial setup](#13-daily-startup-after-the-initial-setup).

### 1. Prepare the Windows computer

Install these prerequisites:

- Windows 10 or Windows 11.
- CODESYS V3.5 SP22 Patch 1 with scripting support.
- Git, or another way to copy this complete repository.
- Node.js 20 or newer. Verify it with `node --version` and `npm --version`.

Clone the repository into a local directory. Do not copy only `mcp-server/`;
the bridge also requires `launcher/` and `ide_scripts/`.

```powershell
New-Item -ItemType Directory -Path C:\Tools -Force
Set-Location C:\Tools
git clone https://github.com/<OWNER>/<REPOSITORY>.git thecodesysvibecoder
Set-Location .\thecodesysvibecoder
```

If the repository is copied instead of cloned, use its actual directory in the
remaining commands.

Install the pinned MCP bridge dependencies:

```powershell
Set-Location .\mcp-server
npm.cmd ci
npm.cmd test
Set-Location ..
```

### 2. Start and test the in-IDE agent

1. Start CODESYS normally.
2. Open the project that AnythingLLM should control.
3. In CODESYS, select **Tools > Scripting > Execute Script File**.
4. Select `ide_scripts\run_in_ide_agent.py` from this repository.
5. Confirm that the script finishes and the CODESYS user interface becomes available again. The registered agent remains active inside that instance.

Do not run `run_in_ide_agent.py` from PowerShell and do not start a second
CODESYS instance from the launcher.

From the repository root, verify the mailbox connection:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\launcher\Send-CodesysRequest.ps1 `
  inspect `
  -NoProjectPathMatch
```

The JSON response must contain `"ok": true`, the expected `project_path`, and
the expected `active_application`. Fix this local connection before working on
MCP or the firewall.

The idle agent does not hold the scripting command open. CODESYS may still be
briefly busy while an actual request is editing, saving, or building a project,
because those operations execute on the CODESYS user-interface thread.

Optionally exercise the real read-only MCP flow locally:

```powershell
Set-Location .\mcp-server
npm.cmd run smoke
Set-Location ..
```

### 3. Generate the MCP API key on Windows

Use one random key on both computers. The following version also works in
Windows PowerShell 5.1:

```powershell
$McpRandom = [Security.Cryptography.RandomNumberGenerator]::Create()
$McpBytes = New-Object byte[] 32
$McpRandom.GetBytes($McpBytes)
$McpRandom.Dispose()
$McpApiKey = ([BitConverter]::ToString($McpBytes)).Replace("-", "")
$env:CODESYS_MCP_API_KEY = $McpApiKey
$McpApiKey.Length
```

The final command must print `64`. Display `$McpApiKey` only when copying it
into AnythingLLM. Never commit the value, paste it into an issue, or include it
in screenshots or logs. Values such as `YOUR_EXISTING_64_CHARACTER_KEY` and
`PASTE_THE_SAME_64_CHARACTER_KEY_HERE` are placeholders, not valid keys.

The variable normally lasts only for the current PowerShell window. On a
trusted, single-user Windows account, store it as a user environment variable
now so the bridge can be started again after closing PowerShell or rebooting:

```powershell
[Environment]::SetEnvironmentVariable(
  "CODESYS_MCP_API_KEY",
  $McpApiKey,
  "User"
)
```

This stores the key for the current Windows user. On a shared Windows account,
omit this persistence step and set `$env:CODESYS_MCP_API_KEY` manually in each
bridge PowerShell session instead.

PowerShell windows opened after the persistent value was saved normally inherit
it. To load it explicitly in a window that was already open, and to verify it,
use:

```powershell
$env:CODESYS_MCP_API_KEY = [Environment]::GetEnvironmentVariable(
  "CODESYS_MCP_API_KEY",
  "User"
)
$env:CODESYS_MCP_API_KEY.Length
```

The key is the authorization boundary for every tool enabled on the bridge.
There is no additional per-edit approval code.

### 4. Create the Windows Firewall rule

First confirm that the Windows connection is a trusted private LAN:

```powershell
Get-NetConnectionProfile
```

If the trusted Ethernet/Wi-Fi connection is incorrectly marked `Public`, use
Windows Settings to change it to `Private`. Do not do this on an untrusted
network.

Open **PowerShell as Administrator**, set the actual Ubuntu address, and create
an inbound rule that accepts port `8765` only from that computer:

```powershell
$UbuntuIp = "<UBUNTU_PC_IP_ADDRESS>"

New-NetFirewallRule `
  -DisplayName "thecodesysvibecoder MCP from Ubuntu" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8765 `
  -RemoteAddress $UbuntuIp `
  -Profile Private
```

Verify the rule:

```powershell
Get-NetFirewallRule -DisplayName "thecodesysvibecoder MCP from Ubuntu" |
  Get-NetFirewallPortFilter
```

If the Ubuntu address changes, remove and recreate this narrowly scoped rule:

```powershell
Remove-NetFirewallRule `
  -DisplayName "thecodesysvibecoder MCP from Ubuntu"
```

Do not create an unrestricted inbound rule and do not expose port `8765` to the
public Internet. Use a VPN or an authenticated HTTPS reverse proxy if the two
computers are not on the same trusted LAN.

### 5. Start the Windows bridge with write and build tools

Use a normal, non-administrator PowerShell window from the repository's
`mcp-server` directory. Keep the API key in the same process environment:

```powershell
Set-Location C:\Tools\thecodesysvibecoder\mcp-server

$WindowsIp = "<WINDOWS_PC_IP_ADDRESS>"
$env:CODESYS_MCP_HOST = "0.0.0.0"
$env:CODESYS_MCP_ALLOWED_HOSTS = "$WindowsIp,$env:COMPUTERNAME"
$env:CODESYS_MCP_ALLOW_WRITE = "true"
$env:CODESYS_MCP_ALLOW_BUILD = "true"

Remove-Item Env:CODESYS_MCP_ALLOWED_IPS -ErrorAction SilentlyContinue

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\Start-CodesysMcpBridge.ps1 `
  -ListenAddress 0.0.0.0 `
  -Port 8765
```

Expected output:

```text
CODESYS MCP bridge listening at http://0.0.0.0:8765/mcp (SSE fallback: /sse)
Tools: raw action enabled; named read-only enabled; write=true; build=true; agent=default
```

The recommended startup profile always enables both write and build tools.
Possession of the API key grants access to every enabled tool, so keep the key
secret and retain the narrowly scoped Windows Firewall rule.

Keep this PowerShell window open. `Ctrl+C` stops only the MCP bridge; it does not
stop CODESYS or the in-IDE agent.

Windows Firewall is the primary source-address restriction. The optional
`CODESYS_MCP_ALLOWED_IPS` application setting is deliberately unset for the
first connection because containers, proxies, and network-address translation
can make the observed source address differ. Add it only after the connection
works and the exact source address is known.

In another Windows PowerShell window, confirm that the bridge is listening:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen
```

### 6. Prepare Ollama on Ubuntu

If Ollama is already installed and AnythingLLM can use it, continue with the
next step. Otherwise follow the current official Linux instructions at
<https://docs.ollama.com/linux>. The standard installation is:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama --version
```

Pull an installed model that supports reliable tool/function calling. Replace
`<MODEL_TAG>` with the exact tag selected for the machine:

```bash
ollama pull <MODEL_TAG>
ollama list
```

When AnythingLLM runs in Docker bridge networking, it cannot reach a host
service through the container's own `127.0.0.1`. One supported arrangement is
to make Ollama listen on the Ubuntu host and use Docker's host-gateway name.
Create a systemd override:

```bash
sudo systemctl edit ollama.service
```

Add:

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

Then apply it:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
curl http://127.0.0.1:11434/api/tags
```

Ollama does not provide API authentication on this local endpoint. Do not add a
router port-forward for `11434`; restrict it to the trusted host/Docker network
with the Ubuntu firewall when required by the local network policy.

### 7. Install Docker and AnythingLLM on Ubuntu

Install Docker Engine using the current official Ubuntu procedure:
<https://docs.docker.com/engine/install/ubuntu/>. On a supported Ubuntu release,
add Docker's official package repository and install Docker Engine:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

Verify Docker before continuing:

```bash
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

The commands below use `$HOME/anythingllm/storage` as persistent storage:

```bash
mkdir -p "$HOME/anythingllm/storage/plugins"
touch "$HOME/anythingllm/storage/.env"
cd "$HOME/anythingllm"
nano compose.yaml
```

Create this Compose file:

```yaml
services:
  anythingllm:
    image: mintplexlabs/anythingllm:latest
    container_name: anythingllm
    restart: unless-stopped
    ports:
      - "<UBUNTU_PC_IP_ADDRESS>:3001:3001"
    cap_add:
      - SYS_ADMIN
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      STORAGE_DIR: /app/server/storage
    volumes:
      - ./storage:/app/server/storage
      - ./storage/.env:/app/server/.env
```

Start it:

```bash
sudo docker compose up -d
sudo docker ps --filter name=anythingllm
sudo docker logs --tail 100 anythingllm
```

Open `http://<UBUNTU_IP>:3001` in a browser and complete the AnythingLLM setup.
Configure Ollama as the LLM provider with this base URL:

```text
http://host.docker.internal:11434
```

Select the model installed with `ollama pull`. A model that can generate text
but does not reliably support tool calls will not be able to operate the MCP
tools consistently.

Replace the example address in the Compose `ports` entry with the real Ubuntu
address. Docker-published ports can bypass some Ubuntu firewall rules, so bind
only the intended address, enable AnythingLLM authentication, and do not create
an Internet-facing router port-forward for `3001`.

The official AnythingLLM Docker guide is available at
<https://github.com/Mintplex-Labs/anything-llm/blob/master/docker/HOW_TO_USE_DOCKER.md>.

### 8. Verify Ubuntu-to-Windows connectivity

With the Windows bridge running, test from the Ubuntu host:

```bash
curl --connect-timeout 5 http://<WINDOWS_PC_IP_ADDRESS>:8765/health
```

Expected response:

```json
{"status":"ok","service":"codesys-mcp-bridge"}
```

This proves only that the network, listener, Host allowlist, and firewall work.
The health endpoint deliberately does not contact CODESYS and does not require
the API key.

Check authentication without printing the key in the command history by
reading it interactively:

```bash
read -rsp "MCP API key: " CODESYS_KEY; echo
curl -i -H "X-API-Key: $CODESYS_KEY" \
  http://<WINDOWS_PC_IP_ADDRESS>:8765/mcp
unset CODESYS_KEY
```

An HTTP `400` response saying that a valid MCP session or initialize request is
required is expected for this plain GET request. It proves the key passed
authentication. HTTP `401` means the two configured keys do not match.

### 9. Configure the remote MCP server in AnythingLLM

On Windows, copy the API key without printing it. If the key was generated in
the current PowerShell window, use:

```powershell
$McpApiKey | Set-Clipboard
```

If the key was persisted earlier and this is a new PowerShell window, load,
validate, and copy it with:

```powershell
$McpApiKey = [Environment]::GetEnvironmentVariable(
  "CODESYS_MCP_API_KEY",
  "User"
)

if ([string]::IsNullOrWhiteSpace($McpApiKey) -or $McpApiKey.Length -lt 32) {
  throw "A valid persisted CODESYS_MCP_API_KEY was not found."
}

$McpApiKey | Set-Clipboard
```

`Set-Clipboard` produces no output. Paste the value into the `X-API-Key`
field shown below, replacing the placeholder. When Ubuntu is managed through
an SSH terminal on Windows, the Windows clipboard can be pasted directly into
the terminal editor. If the computers do not share a clipboard, transfer the
key through a trusted encrypted channel such as a password manager; do not send
it through email or chat.

For the Compose layout above, edit:

```bash
nano "$HOME/anythingllm/storage/plugins/anythingllm_mcp_servers.json"
```

If AnythingLLM was installed differently, identify the host directory mapped
to `/app/server/storage`:

```bash
sudo docker inspect anythingllm \
  --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

Place `anythingllm_mcp_servers.json` inside that storage directory's `plugins`
folder. Merge the `codesys` entry with any existing `mcpServers`; do not erase
other configured servers.

```json
{
  "mcpServers": {
    "codesys": {
      "type": "streamable",
      "url": "http://<WINDOWS_PC_IP_ADDRESS>:8765/mcp",
      "headers": {
        "X-API-Key": "PASTE_THE_SAME_64_CHARACTER_KEY_HERE"
      }
    }
  }
}
```

Protect and validate the file:

```bash
chmod 600 "$HOME/anythingllm/storage/plugins/anythingllm_mcp_servers.json"
python3 -m json.tool \
  "$HOME/anythingllm/storage/plugins/anythingllm_mcp_servers.json" \
  >/dev/null
```

After the key has been pasted and the file saved, clear the Windows clipboard:

```powershell
Set-Clipboard -Value ""
```

Restart AnythingLLM so it reloads the file:

```bash
sudo docker restart anythingllm
sudo docker logs --since 2m anythingllm 2>&1 | grep -i -E 'mcp|codesys'
```

Open AnythingLLM's MCP/Agent Skills settings, confirm that `codesys` is online,
and enable the desired CODESYS tools for the workspace. Start a new agent chat
after every tool-schema change; an existing chat may retain old schemas.

If an older AnythingLLM release rejects `"type": "streamable"`, try
`"type": "streamableHTTP"`. As a compatibility fallback, this bridge also
supports:

```json
{
  "mcpServers": {
    "codesys": {
      "type": "sse",
      "url": "http://<WINDOWS_PC_IP_ADDRESS>:8765/sse",
      "headers": {
        "X-API-Key": "PASTE_THE_SAME_64_CHARACTER_KEY_HERE"
      }
    }
  }
}
```

Prefer Streamable HTTP at `/mcp` for a new installation.

### 10. Test the connection before making changes

With the recommended startup profile, the MCP server exposes all supported
read, write, and build tools listed in the next section.

Although write and build tools are enabled, make the first test request
read-only. Use AnythingLLM agent mode and ask:

```text
Inspect the active CODESYS project, show the project path and active
application, inspect the tree to depth 3, and do not modify anything.
```

Compare the response with the project visibly open in CODESYS. Do not request
changes until the correct project is consistently selected.

### 11. Write and build permissions

The startup commands in this README always set both permission variables to
`"true"`. Confirm this line whenever the bridge starts:

```text
Tools: raw action enabled; named read-only enabled; write=true; build=true; agent=default
```

No additional approval credential is needed. Possession of the API key grants
access to the raw action tool and every named tool enabled by these startup
flags.

The complete enabled tool set is:

- `inspect_project`
- `inspect_tree`
- `read_object`
- `execute_codesys_action`
- `upsert_function_block`
- `upsert_program`
- `upsert_function`
- `upsert_object`
- `add_gvl_variable`
- `rename_object`
- `build_project`

The dedicated POU tools require both a declaration and a non-empty executable
Structured Text implementation, save successful writes by default, and verify
the implementation returned by CODESYS. They do not accept a `container`
argument and target the active Application.

`execute_codesys_action` passes its `action` and `parameters` directly to the
in-IDE agent. It is available whenever the authenticated MCP bridge is running,
independent of the named write/build flags. It does not execute arbitrary
PowerShell, but it exposes all actions implemented by `codesys_agent.py`,
including online login/control/read/write and file-based import/export.

### 12. Recommended AnythingLLM workspace instruction

Add this policy to the AnythingLLM workspace or include it in requests:

```text
Always call inspect_project first and verify the active project. Inspect the
tree and read every affected object before modifying it. For a program,
function block, or function, use its dedicated upsert tool and send the full
declaration and executable implementation together in one call. Read the
object again after writing it. Build the project, report every compiler error,
correct the code, and rebuild. Never report success based only on the tool-call
transport message; verify that the returned CODESYS JSON contains ok=true. For
an operation without a dedicated named tool, call execute_codesys_action with
the exact action and raw parameters used by ide_scripts/codesys_agent.py.
```

### 13. Daily startup after the initial setup

Use this procedure after a reboot or whenever CODESYS, the bridge, or
AnythingLLM has been stopped. The installation, firewall, API key, Compose
file, and AnythingLLM MCP configuration must already be complete.

#### A. Start the Windows CODESYS side

1. Start CODESYS normally and open the project that AnythingLLM should control.
2. In CODESYS, select **Tools > Scripting > Execute Script File** and run
   `ide_scripts\run_in_ide_agent.py` from this repository. Do not run it from
   PowerShell.
3. In a normal PowerShell window, go to the repository root and verify the
   active project:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\launcher\Send-CodesysRequest.ps1 `
  inspect `
  -NoProjectPathMatch
```

Continue only when the response contains `"ok": true` and identifies the
expected project and application.

4. Load the persisted API key and check its length:

```powershell
$env:CODESYS_MCP_API_KEY = [Environment]::GetEnvironmentVariable(
  "CODESYS_MCP_API_KEY",
  "User"
)

if ([string]::IsNullOrWhiteSpace($env:CODESYS_MCP_API_KEY)) {
  throw "CODESYS_MCP_API_KEY is not stored for this Windows user. Complete the API-key setup first."
}

$env:CODESYS_MCP_API_KEY.Length
```

The length must be at least `32`; a key generated by step 3 prints `64`.

5. Set the Windows address and enable the write and build permissions, then
   start the MCP bridge:

```powershell
$WindowsIp = "<WINDOWS_PC_IP_ADDRESS>"
$env:CODESYS_MCP_ALLOWED_HOSTS = "$WindowsIp,$env:COMPUTERNAME"
$env:CODESYS_MCP_ALLOW_WRITE = "true"
$env:CODESYS_MCP_ALLOW_BUILD = "true"

Remove-Item Env:CODESYS_MCP_ALLOWED_IPS -ErrorAction SilentlyContinue

Set-Location .\mcp-server
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\Start-CodesysMcpBridge.ps1 `
  -ListenAddress 0.0.0.0 `
  -Port 8765
```

The normal startup profile enables both write and build tools. Keep this
PowerShell window open; `Ctrl+C` stops the bridge.

#### B. Start Ollama and AnythingLLM on Ubuntu

After the Windows bridge is listening, run from the Ubuntu computer:

```bash
sudo systemctl start docker ollama
cd "$HOME/anythingllm"
sudo docker compose up -d
sudo docker compose ps
```

`docker compose up -d` is safe to run when the container already exists. With
the supplied `restart: unless-stopped` setting, AnythingLLM may already be
running after reboot; the command ensures it is started with the configured
Compose project.

Verify Ollama, the bridge, and AnythingLLM:

```bash
curl http://127.0.0.1:11434/api/tags
curl --connect-timeout 5 http://<WINDOWS_PC_IP_ADDRESS>:8765/health
sudo docker logs --tail 100 anythingllm
```

Open `http://<UBUNTU_PC_IP_ADDRESS>:3001`, enter the configured AnythingLLM
workspace, and confirm that the `codesys` MCP server is online. Start a new
agent chat after changing bridge permissions or MCP tool definitions.

The MCP bridge does not start CODESYS or the in-IDE agent. AnythingLLM does not
start the Windows MCP bridge; both sides must be running.

### 14. Rotate the API key

1. Generate a new key on Windows.
2. Stop the Windows bridge.
3. Replace the key in AnythingLLM's MCP JSON.
4. Restart AnythingLLM.
5. Start the bridge with the new key.
6. Repeat the authenticated connectivity test.
7. Ensure the obsolete key is no longer stored in any old AnythingLLM file,
   startup script, note, or backup that does not need it.

There is no transition period: the two computers must use the same key.

### Troubleshooting

#### `inspect` times out on Windows

The matching `ide_scripts\run_in_ide_agent*.py` script is not running in the
active CODESYS instance, the wrong named agent is selected, or the repository
mailbox is not shared by the launcher and script. Run the agent inside CODESYS;
do not launch another CODESYS instance as a workaround.

#### Ubuntu cannot reach `/health`

Check each layer in order:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen
Get-NetFirewallRule -DisplayName "thecodesysvibecoder MCP from Ubuntu"
```

Then confirm the URL uses the current Windows address and that the Windows
network profile is `Private`.

#### `/health` works but MCP does not

- HTTP `401`: the API keys differ or the header is missing.
- HTTP `403`: `CODESYS_MCP_ALLOWED_IPS` contains the wrong observed client IP.
  Remove it, restart the bridge, and rely on the scoped Windows Firewall rule
  until the correct address is known.
- HTTP `421`: the hostname or IP used in the URL is absent from
  `CODESYS_MCP_ALLOWED_HOSTS`.
- HTTP `400` on a plain authenticated GET to `/mcp`: expected; a real MCP client
  must initialize a session.

#### AnythingLLM shows no MCP server

Verify the storage mount, filename, JSON syntax, file permissions, and container
restart. The exact filename is `anythingllm_mcp_servers.json`. Check that the
file is inside the host directory mapped to `/app/server/storage/plugins`.

#### Only read tools appear

Set both `CODESYS_MCP_ALLOW_WRITE=true` and
`CODESYS_MCP_ALLOW_BUILD=true` before starting the Windows bridge. Restart both
the bridge and AnythingLLM, then use a new agent chat.

#### A function block is created without code

AnythingLLM is probably using an old cached schema or the generic tool. Restart
AnythingLLM, start a new chat, and use `upsert_function_block`. Its
`declaration` and `implementation` arguments are mandatory. The bridge rejects
empty executable objects and verifies the code after writing.

#### AnythingLLM says a tool “completed successfully” but the task failed

That message can mean only that the MCP transport call completed. Inspect the
returned JSON. The operation succeeded only when the returned CODESYS result
contains `"ok": true` and the requested object/code is present.

### Additional bridge reference

See [`mcp-server/README.md`](mcp-server/README.md) for the environment-variable
table, transport details, safety model, and bridge-specific tests.

Official upstream references:

- [VS Code MCP server configuration](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Windows Defender Firewall `New-NetFirewallRule`](https://learn.microsoft.com/powershell/module/netsecurity/new-netfirewallrule)
- [AnythingLLM Docker guide](https://github.com/Mintplex-Labs/anything-llm/blob/master/docker/HOW_TO_USE_DOCKER.md)
- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Ollama on Linux](https://docs.ollama.com/linux)
- [MCP server transport guide](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/server.md)
