# thecodesysvibecoder MCP bridge

This service runs on the Windows computer that already runs CODESYS. It exposes
only named MCP tools and translates them into calls to
`launcher/Send-CodesysRequest.ps1`. It never exposes a generic shell command.

## Safety model

- `CODESYS_MCP_API_KEY` is mandatory and must contain at least 32 characters.
- Only `inspect_project`, `inspect_tree`, and `read_object` are exposed by
  default.
- Write tools appear only when `CODESYS_MCP_ALLOW_WRITE=true`.
- The build tool appears only when `CODESYS_MCP_ALLOW_BUILD=true`.
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
- The bridge re-inspects the IDE immediately before every operation and pins the
  following request to the returned active project path.
- Requests are serialized so parallel LLM tool calls cannot race through the
  mailbox.
- No login, download, PLC start/stop, online write, force, raw JSON, or generic
  PowerShell tool is exposed.

## Install on Windows

For a complete two-computer procedure starting with a clean Windows CODESYS
computer and a local Ollama/AnythingLLM Ubuntu computer, see
[`Connect a local AnythingLLM installation through MCP`](../README.md#connect-a-local-anythingllm-installation-through-mcp).
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
.\Start-CodesysMcpBridge.ps1
```

For the Ubuntu AnythingLLM computer to connect, bind to the LAN interface and
restrict the accepted Host header:

```powershell
$env:CODESYS_MCP_HOST = "0.0.0.0"
$env:CODESYS_MCP_ALLOWED_HOSTS = "<WINDOWS_PC_IP_ADDRESS>,<WINDOWS_HOSTNAME>"
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

Copy the `codesys` entry from `anythingllm-mcp.example.json` into
AnythingLLM's `anythingllm_mcp_servers.json`, replacing the Windows IP and API
key. For Docker installations this file is normally in the mounted AnythingLLM
storage directory under `plugins/`.

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

## Enable controlled changes later

Keep the first connection read-only until Gemma reliably follows the inspection
workflow. To enable editing in a new PowerShell session:

```powershell
$env:CODESYS_MCP_ALLOW_WRITE = "true"
.\Start-CodesysMcpBridge.ps1 -ListenAddress 0.0.0.0
```

To enable build/rebuild as well:

```powershell
$env:CODESYS_MCP_ALLOW_BUILD = "true"
```

Restart the bridge whenever permissions change. A recommended prompt policy for
the AnythingLLM workspace is:

```text
Always inspect the active project first. Read every affected object before
changing it. When creating or updating a program, function block, or function,
use its dedicated upsert tool and send both declaration and implementation in
the same call. Use the smallest necessary change, then read the affected object
again. Build after applying code changes and use compiler errors to correct them.
Never claim a change succeeded unless the CODESYS tool result says ok=true.
```

## Environment variables

| Variable | Default | Purpose |
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
the real read-only `inspect_project` tool:

```powershell
npm.cmd run smoke
```
