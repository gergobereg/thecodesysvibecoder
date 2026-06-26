param(
    [Parameter(Position = 0)]
    [ValidateSet("inspect", "add-gvl-var")]
    [string]$Command = "inspect",

    [string]$CodesysExe = "C:\Program Files\CODESYS 3.5.22.10\CODESYS\Common\CODESYS.exe",
    [string]$Profile = "CODESYS V3.5 SP22 Patch 1",
    [string]$Project = "",
    [string]$Container = "",
    [switch]$NoUi,
    [switch]$NoSave,
    [switch]$NoProjectPathMatch,
    [int]$TimeoutSeconds = 180,

    [string]$Gvl = "GVL",
    [string]$Var = "",
    [string]$Type = "BOOL"
)

$ErrorActionPreference = "Stop"

function Quote-Arg([string]$Value) {
    return '"' + ($Value -replace '"', '\"') + '"'
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AgentScript = Join-Path $Root "ide_scripts\codesys_agent.py"

if (-not $Project) {
    $Project = Join-Path $Root "FirstProject.project"
}

if ($Command -eq "add-gvl-var" -and -not $Var) {
    throw "The add-gvl-var command requires -Var."
}

$StateDir = Join-Path $Root ".codesys_agent"
$RequestDir = Join-Path $StateDir "requests"
$ResultDir = Join-Path $StateDir "results"
New-Item -ItemType Directory -Force -Path $RequestDir, $ResultDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RequestPath = Join-Path $RequestDir "$Stamp-$PID.json"
$ResultPath = Join-Path $ResultDir "$Stamp-$PID.result.json"

$Action = if ($Command -eq "add-gvl-var") { "add_gvl_var" } else { "inspect" }
$Payload = [ordered]@{
    action = $Action
    project_path = (Resolve-Path $Project).Path
    require_project_path_match = -not $NoProjectPathMatch.IsPresent
    save = -not $NoSave.IsPresent
    result_path = $ResultPath
}

if ($Container) {
    $Payload.container = $Container
}

if ($Command -eq "add-gvl-var") {
    $Payload.gvl_name = $Gvl
    $Payload.var_name = $Var
    $Payload.var_type = $Type
}

$Payload | ConvertTo-Json -Depth 8 | Set-Content -Path $RequestPath -Encoding UTF8

$ArgumentParts = @(
    "--profile=$(Quote-Arg $Profile)",
    "--runscript=$(Quote-Arg $AgentScript)",
    "--scriptargs:$(Quote-Arg $RequestPath)"
)

if ($NoUi) {
    $ArgumentParts += "--noUI"
}

$StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
$StartInfo.FileName = $CodesysExe
$StartInfo.Arguments = ($ArgumentParts -join " ")
$StartInfo.UseShellExecute = $false
$StartInfo.RedirectStandardOutput = $true
$StartInfo.RedirectStandardError = $true

$Process = [System.Diagnostics.Process]::Start($StartInfo)
$Deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while (-not (Test-Path $ResultPath) -and (Get-Date) -lt $Deadline) {
    Start-Sleep -Milliseconds 500
}

if (-not $Process.HasExited) {
    $RemainingMs = [int][Math]::Max(0, ($Deadline - (Get-Date)).TotalMilliseconds)
    if ($RemainingMs -gt 0) {
        [void]$Process.WaitForExit($RemainingMs)
    }
}

$TimedOut = -not $Process.HasExited
if ($TimedOut) {
    try {
        $Process.Kill()
    } catch {
    }
}

$Stdout = ""
$Stderr = ""
if ($Process.HasExited) {
    $Stdout = $Process.StandardOutput.ReadToEnd()
    $Stderr = $Process.StandardError.ReadToEnd()
}

$Output = [ordered]@{
    command = ('"{0}" {1}' -f $CodesysExe, $StartInfo.Arguments)
    request_path = $RequestPath
    result_path = $ResultPath
    process_exited = $Process.HasExited
    exit_code = if ($Process.HasExited) { $Process.ExitCode } else { $null }
    stdout = $Stdout
    stderr = $Stderr
}

if (Test-Path $ResultPath) {
    $Output.agent_result = Get-Content -Path $ResultPath -Raw | ConvertFrom-Json
} else {
    $Output.agent_result = $null
    $Output.error = "Timed out waiting for CODESYS agent result."
}

$Output | ConvertTo-Json -Depth 12

if ($Output.agent_result -and -not $Output.agent_result.ok) {
    exit 1
}

if (-not $Output.agent_result) {
    exit 1
}

if ($Process.HasExited -and $Process.ExitCode -ne 0) {
    exit $Process.ExitCode
}
