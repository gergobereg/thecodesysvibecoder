# thecodesysvibecoder MCP bridge

This service runs on the Windows computer that already runs CODESYS. It exposes
named convenience tools plus one raw CODESYS-agent passthrough and translates
them into calls to `launcher/Send-CodesysRequest.ps1`. It never exposes a
generic shell command.

## Safety model

- `CODESYS_MCP_API_KEY` is mandatory and must contain at least 32 characters.
- Every authenticated client can use `execute_codesys_action` to call any
  action implemented by `ide_scripts/codesys_agent.py` with raw parameters.
- The recommended startup profile in this README enables write and build tools.
  If the permission variables are omitted, the three named inspection tools and
  `execute_codesys_action` are exposed.
- Named write tools appear only when `CODESYS_MCP_ALLOW_WRITE=true`.
- The named build tool appears only when `CODESYS_MCP_ALLOW_BUILD=true`.
- The authenticated MCP connection is the authorization boundary. Enabled
  write/build tools do not require a second per-call approval credential.
- Write tools save successful changes by default. Callers may explicitly pass
  `save=false` when they intentionally want to leave the project dirty.
- Programs, function blocks, and functions must be sent with both a complete
  declaration and a non-empty executable implementation. The bridge rejects
  empty placeholder creation and verifies the implementation returned by
  CODESYS after each write.
- Dedicated `upsert_function_block`, `upsert_program`, and `upsert_function`
  tools make both code fields mandatory and target the active Application, so
  a smaller model cannot accidentally use the POU itself as its parent.
- The named tools re-inspect the IDE before project-specific operations and pin
  the following request to the returned active project path. The raw tool sends
  exactly the supplied parameters.
- Requests are serialized so parallel LLM tool calls cannot race through the
  mailbox.
- The raw action tool includes online login/control/read/write, deletion,
  import/export, device configuration, library management, and every other
  action implemented by the in-IDE agent. File paths are resolved on the
  Windows computer running CODESYS.
- Arbitrary PowerShell is not exposed.

## Install on Windows

For a complete two-computer procedure starting with a clean Windows CODESYS
computer and a local Ollama/AnythingLLM Ubuntu computer, see
[`Connect a local AnythingLLM installation through MCP`](../README.md#connect-a-local-anythingllm-installation-through-mcp).
For GitHub Copilot on a separate Windows computer, see
[`Connect two Windows PCs: CODESYS on one, VS Code Copilot on the other`](../README.md#connect-two-windows-pcs-codesys-on-one-vs-code-copilot-on-the-other).
For routine startup after the one-time setup, see
[`Daily startup after the initial setup`](../README.md#13-daily-startup-after-the-initial-setup).

Node.js 20 or newer is required. From the repository root:

```powershell
Set-Location .\mcp-server
npm.cmd install
```

Create a random API key. Keep it out of the repository:

```powershell
$McpRandom = [Security.Cryptography.RandomNumberGenerator]::Create()
$McpBytes = New-Object byte[] 32
$McpRandom.GetBytes($McpBytes)
$McpRandom.Dispose()
$McpApiKey = ([BitConverter]::ToString($McpBytes)).Replace("-", "")
$env:CODESYS_MCP_API_KEY = $McpApiKey
$McpApiKey.Length
```

The final command must print `64`. Placeholder strings such as
`YOUR_RANDOM_SECRET` are not valid API keys. On a trusted, single-user Windows
account, save the generated key for future PowerShell sessions:

```powershell
[Environment]::SetEnvironmentVariable(
  "CODESYS_MCP_API_KEY",
  $McpApiKey,
  "User"
)
```

On a shared Windows account, omit this persistence step and set the process
environment variable manually whenever the bridge is started. To load the
saved value explicitly in a later PowerShell session:

```powershell
$env:CODESYS_MCP_API_KEY = [Environment]::GetEnvironmentVariable(
  "CODESYS_MCP_API_KEY",
  "User"
)
$env:CODESYS_MCP_API_KEY.Length
```

For a first local-only test:

```powershell
$env:CODESYS_MCP_ALLOW_WRITE = "true"
$env:CODESYS_MCP_ALLOW_BUILD = "true"
.\Start-CodesysMcpBridge.ps1
```

For the Ubuntu AnythingLLM computer to connect, bind to the LAN interface and
restrict the accepted Host header:

```powershell
$env:CODESYS_MCP_HOST = "0.0.0.0"
$env:CODESYS_MCP_ALLOWED_HOSTS = "<WINDOWS_PC_IP_ADDRESS>,<WINDOWS_HOSTNAME>"
$env:CODESYS_MCP_ALLOW_WRITE = "true"
$env:CODESYS_MCP_ALLOW_BUILD = "true"
Remove-Item Env:CODESYS_MCP_ALLOWED_IPS -ErrorAction SilentlyContinue
.\Start-CodesysMcpBridge.ps1
```

The bridge listens on TCP port `8765` by default. Add a Windows Defender
Firewall inbound rule limited to the Ubuntu PC's IP address. Do not expose this
port to the public internet. For communication outside a trusted LAN, put the
endpoint behind a VPN or an HTTPS reverse proxy.

The Windows Firewall rule is the primary client-address restriction. Leave
`CODESYS_MCP_ALLOWED_IPS` unset for the first connection because Docker, a
proxy, or NAT can make the source address observed by Node.js differ from the
expected host address. It can be enabled later with the exact observed address.

Health check from Ubuntu:

```bash
curl http://<WINDOWS_PC_IP_ADDRESS>:8765/health
```

The health endpoint does not contact CODESYS. MCP endpoints require the key:

```bash
curl -i -H "X-API-Key: YOUR_RANDOM_SECRET" \
  http://<WINDOWS_PC_IP_ADDRESS>:8765/mcp
```

## Configure AnythingLLM on Ubuntu

Copy the API key on Windows without printing it. In the same PowerShell window
that generated the key, use:

```powershell
$McpApiKey | Set-Clipboard
```

In a later PowerShell window, load the persisted key before copying it:

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

Copy the `codesys` entry from `anythingllm-mcp.example.json` into
AnythingLLM's `anythingllm_mcp_servers.json`, replacing the Windows IP and API
key. For Docker installations this file is normally in the mounted AnythingLLM
storage directory under `plugins/`.

Paste the copied value in place of `YOUR_RANDOM_SECRET`. If the Ubuntu computer
does not share the Windows clipboard, transfer the key through a trusted
encrypted channel such as a password manager. After saving the configuration,
clear the Windows clipboard:

```powershell
Set-Clipboard -Value ""
```

Current AnythingLLM releases use a Streamable HTTP entry pointing to `/mcp`.
Some releases call the type `streamableHTTP` instead of `streamable`. If the
installed release rejects the example type, use:

```json
{
  "mcpServers": {
    "codesys": {
      "type": "streamableHTTP",
      "url": "http://<WINDOWS_PC_IP_ADDRESS>:8765/mcp",
      "headers": {
        "X-API-Key": "YOUR_RANDOM_SECRET"
      }
    }
  }
}
```

The bridge also provides the older AnythingLLM-compatible SSE transport:

```json
{
  "mcpServers": {
    "codesys": {
      "type": "sse",
      "url": "http://<WINDOWS_PC_IP_ADDRESS>:8765/sse",
      "headers": {
        "X-API-Key": "YOUR_RANDOM_SECRET"
      }
    }
  }
}
```

Restart AnythingLLM or reload its MCP servers, then enable the CODESYS tools for
the intended workspace.

## Recommended write and build profile

Set both permission variables to `"true"` in every normal bridge PowerShell
session:

```powershell
$env:CODESYS_MCP_ALLOW_WRITE = "true"
$env:CODESYS_MCP_ALLOW_BUILD = "true"
.\Start-CodesysMcpBridge.ps1 -ListenAddress 0.0.0.0
```

The bridge registers its tool list at startup, so restart it whenever
permissions change. The permission flags affect only the named convenience
tools; `execute_codesys_action` is always present for an authenticated client.
A recommended prompt policy for the AnythingLLM or Copilot workspace is:

```text
Always inspect the active project first. Read every affected object before
changing it. When creating or updating a program, function block, or function,
use its dedicated upsert tool and send both declaration and implementation in
the same call. Use the smallest necessary change, then read the affected object
again. Build after applying code changes and use compiler errors to correct them.
Never claim a change succeeded unless the CODESYS tool result says ok=true.
```

## Environment variables

The table records the bridge's built-in fallback when a variable is omitted.
The recommended startup commands above explicitly set both permission variables
to `"true"`.

| Variable | Built-in fallback | Purpose |
| --- | --- | --- |
| `CODESYS_MCP_API_KEY` | required | MCP HTTP authentication secret |
| `CODESYS_MCP_HOST` | `127.0.0.1` | Listen address |
| `CODESYS_MCP_PORT` | `8765` | Listen port |
| `CODESYS_MCP_ALLOWED_HOSTS` | loopback only on loopback bind | Comma-separated Host header allowlist |
| `CODESYS_MCP_ALLOWED_IPS` | any authenticated IP | Comma-separated exact client IP allowlist |
| `CODESYS_MCP_AGENT` | default agent | Named mailbox such as `agent1` |
| `CODESYS_MCP_ALLOW_WRITE` | `false` | Register write tools |
| `CODESYS_MCP_ALLOW_BUILD` | `false` | Register build tool |
| `CODESYS_MCP_REQUEST_TIMEOUT_SECONDS` | `60` | Launcher wait timeout, 5-300 seconds |

## Test

```powershell
Set-Location .\mcp-server
npm.cmd test
```

With CODESYS and the in-IDE agent running, exercise both network transports and
the real `inspect_project` and raw `execute_codesys_action` tools:

```powershell
npm.cmd run smoke
```
