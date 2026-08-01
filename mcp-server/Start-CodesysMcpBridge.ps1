param(
    [string]$ListenAddress = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$BridgeRoot = $PSScriptRoot

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js 20 or newer is required."
}

if (-not (Test-Path -LiteralPath (Join-Path $BridgeRoot "node_modules"))) {
    throw "Dependencies are not installed. Run npm.cmd install in the mcp-server directory first."
}

if (-not $env:CODESYS_MCP_API_KEY) {
    throw "Set CODESYS_MCP_API_KEY to a random secret of at least 32 characters before starting the bridge."
}

if ($ListenAddress) {
    $env:CODESYS_MCP_HOST = $ListenAddress
}
if ($Port -gt 0) {
    $env:CODESYS_MCP_PORT = [string]$Port
}

& node (Join-Path $BridgeRoot "src\server.js")
