param(
    [Parameter(Position = 0)]
    [ValidateSet("inspect", "inspect-tree", "read-object", "add-gvl-var", "upsert-object", "rename-object", "set-device-enabled", "sync-device-from-uint", "application-command", "hydraulic-cylinder-fb", "send-json", "stop")]
    [string]$Command = "inspect",

    [string]$Project = "",
    [string]$Agent = "",
    [string]$Container = "",
    [switch]$NoSave,
    [switch]$NoProjectPathMatch,
    [int]$TimeoutSeconds = 30,

    [string]$Gvl = "GVL",
    [string]$Var = "",
    [string]$Type = "BOOL",
    [string]$Name = "",
    [string]$Kind = "",
    [string]$ReturnType = "",
    [string]$DutType = "Structure",
    [string]$BaseType = "",
    [string]$Interfaces = "",
    [string]$BaseInterfaces = "",
    [string]$DeclarationFile = "",
    [string]$ImplementationFile = "",
    [string]$OldName = "",
    [string]$NewName = "",
    [bool]$Enabled = $true,
    [string]$ConstantObject = "GVL",
    [string]$ConstantName = "uiUnits",
    [int]$EnableWhenAtLeast = 2,
    [ValidateSet("build", "clean", "generate_code", "rebuild")]
    [string]$AppCommand = "build",
    [int]$Depth = 3,
    [switch]$IncludeText,
    [string]$RequestJson = ""
)

$ErrorActionPreference = "Stop"

function ConvertTo-AgentJson {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Payload
    )

    Add-Type -AssemblyName System.Web.Extensions
    $Serializer = New-Object System.Web.Script.Serialization.JavaScriptSerializer
    $Serializer.MaxJsonLength = [int]::MaxValue
    return $Serializer.Serialize($Payload)
}

function Resolve-AgentStateDir {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [string]$Agent
    )

    $BaseDir = Join-Path $Root ".codesys_agent"
    if ([string]::IsNullOrWhiteSpace($Agent) -or $Agent.ToLowerInvariant() -eq "default") {
        return @{
            AgentId = "default"
            StateDir = $BaseDir
        }
    }

    $SafeAgent = $Agent.Trim() -replace '[^A-Za-z0-9_.-]', '_'
    $SafeAgent = $SafeAgent.Trim([char[]]" .")
    if ([string]::IsNullOrWhiteSpace($SafeAgent) -or $SafeAgent -eq "." -or $SafeAgent -eq "..") {
        throw "Invalid CODESYS agent id '$Agent'. Use letters, digits, dot, underscore, or dash."
    }

    return @{
        AgentId = $SafeAgent
        StateDir = (Join-Path $BaseDir $SafeAgent)
    }
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AgentState = Resolve-AgentStateDir -Root $Root -Agent $Agent
$AgentId = $AgentState.AgentId
$StateDir = $AgentState.StateDir
$InboxDir = Join-Path $StateDir "inbox"
$OutboxDir = Join-Path $StateDir "outbox"
$StopFile = Join-Path $StateDir "stop-agent"

New-Item -ItemType Directory -Force -Path $InboxDir, $OutboxDir | Out-Null

if ($Command -eq "stop") {
    "stop" | Set-Content -Path $StopFile -Encoding ASCII
    Write-Output "Stop file written for CODESYS agent '$AgentId': $StopFile"
    exit 0
}

if ($Command -eq "add-gvl-var" -and -not $Var) {
    throw "The add-gvl-var command requires -Var."
}

if ($Command -eq "upsert-object" -and (-not $Kind -or -not $Name)) {
    throw "The upsert-object command requires -Kind and -Name."
}

if ($Command -eq "read-object" -and -not $Name) {
    throw "The read-object command requires -Name."
}

if ($Command -eq "rename-object" -and (-not $OldName -or -not $NewName)) {
    throw "The rename-object command requires -OldName and -NewName."
}

if ($Command -eq "set-device-enabled" -and -not $Name) {
    throw "The set-device-enabled command requires -Name."
}

if ($Command -eq "sync-device-from-uint" -and -not $Name) {
    $Name = "S10e_1"
}

if ($Command -eq "send-json" -and -not $RequestJson) {
    throw "The send-json command requires -RequestJson."
}

if ($Command -eq "hydraulic-cylinder-fb" -and -not $Name) {
    $Name = "FB_HydraulicCylinder"
}

if (-not $Project) {
    $Project = Join-Path $Root "FirstProject.project"
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss-ffff"
$RequestPath = Join-Path $InboxDir "$Stamp-$PID.json"
$TempRequestPath = Join-Path $InboxDir "$Stamp-$PID.tmp"
$ResultPath = Join-Path $OutboxDir "$Stamp-$PID.json.result.json"

if ($Command -eq "send-json") {
    $JsonText = Get-Content -Path $RequestJson -Raw
} else {
    $Action = "inspect"
    if ($Command -eq "inspect-tree") {
        $Action = "inspect_tree"
    }
    if ($Command -eq "read-object") {
        $Action = "read_object"
    }
    if ($Command -eq "add-gvl-var") {
        $Action = "add_gvl_var"
    }
    if ($Command -eq "upsert-object") {
        $Action = "upsert_object"
    }
    if ($Command -eq "rename-object") {
        $Action = "rename_object"
    }
    if ($Command -eq "set-device-enabled") {
        $Action = "set_device_enabled"
    }
    if ($Command -eq "sync-device-from-uint") {
        $Action = "sync_device_enabled_from_uint_constant"
    }
    if ($Command -eq "application-command") {
        $Action = "application_command"
    }
    if ($Command -eq "hydraulic-cylinder-fb") {
        $Action = "upsert_function_block"
    }

    $Payload = @{
        action = $Action
        agent_id = $AgentId
        project_path = (Resolve-Path $Project).Path
        require_project_path_match = -not $NoProjectPathMatch.IsPresent
        save = -not $NoSave.IsPresent
    }

    if ($Container) {
        $Payload["container"] = $Container
    }

    if ($Command -eq "inspect-tree") {
        $Payload["depth"] = $Depth
        $Payload["include_text"] = $IncludeText.IsPresent
        if ($Name) {
            $Payload["root"] = $Name
        }
    }

    if ($Command -eq "read-object") {
        $Payload["object_name"] = $Name
    }

    if ($Command -eq "add-gvl-var") {
        $Payload["gvl_name"] = $Gvl
        $Payload["var_name"] = $Var
        $Payload["var_type"] = $Type
    }

    if ($Command -eq "upsert-object") {
        $Payload["object_kind"] = $Kind
        $Payload["object_name"] = $Name
        if ($ReturnType) {
            $Payload["return_type"] = $ReturnType
        }
        if ($DutType) {
            $Payload["dut_type"] = $DutType
        }
        if ($BaseType) {
            $Payload["base_type"] = $BaseType
        }
        if ($Interfaces) {
            $Payload["interfaces"] = $Interfaces
        }
        if ($BaseInterfaces) {
            $Payload["base_interfaces"] = $BaseInterfaces
        }
        if ($DeclarationFile) {
            $Payload["declaration"] = [string](Get-Content -Path $DeclarationFile -Raw)
        }
        if ($ImplementationFile) {
            $Payload["implementation"] = [string](Get-Content -Path $ImplementationFile -Raw)
        }
    }

    if ($Command -eq "rename-object") {
        $Payload["old_name"] = $OldName
        $Payload["new_name"] = $NewName
    }

    if ($Command -eq "set-device-enabled") {
        $Payload["device_name"] = $Name
        $Payload["enabled"] = $Enabled
    }

    if ($Command -eq "sync-device-from-uint") {
        $Payload["device_name"] = $Name
        $Payload["constant_object_name"] = $ConstantObject
        $Payload["constant_name"] = $ConstantName
        $Payload["enable_when_at_least"] = $EnableWhenAtLeast
    }

    if ($Command -eq "application-command") {
        $Payload["command"] = $AppCommand
    }

    if ($Command -eq "hydraulic-cylinder-fb") {
    $Declaration = @"
FUNCTION_BLOCK $Name
VAR_INPUT
    xEnable : BOOL; // Allows movement when TRUE; both outputs stay FALSE when disabled.
    xCalibrate : BOOL; // Rising edge starts endpoint calibration; positioning is suspended while TRUE.
    uiMaxLength : UINT := 100; // Physical full cylinder stroke in mm, used for speed calibration.
    uiActPos : UINT; // Actual cylinder position in mm, updated by the position feedback.
    uiSetPos : UINT; // Requested cylinder target position in mm.
    uiHystereses : UINT := 5; // Position tolerance around the setpoint in mm.
    uiIncrement : UINT := 10; // Maximum commanded movement slice in mm for one pulse.
    uiMoveTimePerMm : UINT := 100; // Manual fallback speed calibration: output ON time in ms per mm.
    uiSettleTime : UINT := 1200; // Output OFF time in ms before checking slow feedback again.
    dwCycleTime : UDINT := 10000; // PLC task cycle time in microseconds.
END_VAR
VAR_OUTPUT
    xUp : BOOL; // Command output for upward movement.
    xDown : BOOL; // Command output for downward movement.
    xCalibrating : BOOL; // TRUE while the automatic endpoint calibration sequence is active.
    xCalibrated : BOOL; // TRUE after a successful calibration run.
    xCalibError : BOOL; // TRUE if calibration cannot calculate a valid speed.
    uiCalibratedMoveTimePerMm : UINT; // Measured output ON time in ms per mm.
END_VAR
VAR
    uiState : UINT; // 0=check position, 10=move up, 20=move down, 30=wait stopped.
    uiCalibState : UINT; // 0=idle, 10=drive down to lower endpoint, 20=drive up to upper endpoint.
    xMoveUp : BOOL; // Direction selected for the current pulse.
    xPrevCalibrate : BOOL; // Previous xCalibrate value for rising-edge detection.
    uiEffectiveIncrement : UINT; // Sanitized movement slice; forced to at least 1 mm.
    uiEffectiveHysteresis : UINT; // Local hysteresis value used for distance checks.
    uiEffectiveMoveTimePerMm : UINT; // Active ms/mm value: calibrated if available, otherwise manual.
    uiLastCalibPos : UINT; // Last observed position during endpoint detection.
    udiDistance : UDINT; // Distance between actual and set position in mm.
    udiMoveDistance : UDINT; // Distance requested for the next movement pulse in mm.
    udiMoveTimeUs : UDINT; // Calculated movement pulse duration in microseconds.
    udiSettleTimeUs : UDINT; // Calculated stopped wait duration in microseconds.
    udiElapsedUs : UDINT; // Elapsed time counter for the current state in microseconds.
    udiCycleTimeUs : UDINT; // Sanitized task cycle time in microseconds.
    udiNoChangeLimitUs : UDINT; // Time without feedback change required to detect an endpoint.
    udiNoChangeElapsedUs : UDINT; // Elapsed time since uiActPos last changed during calibration.
    udiCalibMoveElapsedUs : UDINT; // Elapsed upward movement time during calibration.
    udiTravelTimeUs : UDINT; // Upward movement time minus endpoint confirmation time.
    udiCalculatedMsPerMm : UDINT; // Temporary calibrated speed value before UINT conversion.
END_VAR
"@

    $Implementation = @"
// Default to a safe state. Direction outputs are enabled only in calibration or timed move states.
xUp := FALSE;
xDown := FALSE;

// Sanitize time and distance inputs so the state machine cannot get stuck.
udiCycleTimeUs := dwCycleTime;
IF udiCycleTimeUs = 0 THEN
    udiCycleTimeUs := UDINT#10000;
END_IF

uiEffectiveIncrement := uiIncrement;
IF uiEffectiveIncrement = 0 THEN
    uiEffectiveIncrement := 1;
END_IF

uiEffectiveHysteresis := uiHystereses;
uiEffectiveMoveTimePerMm := uiMoveTimePerMm;
IF xCalibrated AND (uiCalibratedMoveTimePerMm > 0) THEN
    uiEffectiveMoveTimePerMm := uiCalibratedMoveTimePerMm;
END_IF
IF uiEffectiveMoveTimePerMm = 0 THEN
    uiEffectiveMoveTimePerMm := 1;
END_IF

udiSettleTimeUs := UINT_TO_UDINT(uiSettleTime) * UDINT#1000;
udiNoChangeLimitUs := UDINT#3000000;

// Start a new calibration on the rising edge of xCalibrate.
IF xCalibrate AND NOT xPrevCalibrate THEN
    uiState := 0;
    uiCalibState := 10;
    xCalibrated := FALSE;
    xCalibError := FALSE;
    xCalibrating := TRUE;
    uiLastCalibPos := uiActPos;
    udiElapsedUs := UDINT#0;
    udiNoChangeElapsedUs := UDINT#0;
    udiCalibMoveElapsedUs := UDINT#0;
END_IF
xPrevCalibrate := xCalibrate;

// When disabled, stop immediately and abort active calibration or positioning.
IF NOT xEnable THEN
    uiState := 0;
    uiCalibState := 0;
    xCalibrating := FALSE;
    udiElapsedUs := UDINT#0;
    udiNoChangeElapsedUs := UDINT#0;
    RETURN;
END_IF

// Calibration drives to the lower endpoint, then upward to the upper endpoint.
// An endpoint is detected when uiActPos has not changed for about 3 seconds.
IF xCalibrate OR (uiCalibState <> 0) THEN
    CASE uiCalibState OF
        0:
            // Calibration is complete, or xCalibrate is held TRUE after completion.
            xCalibrating := FALSE;

        10:
            // Drive down until the feedback stops changing for the endpoint confirmation time.
            xCalibrating := TRUE;
            xDown := TRUE;
            IF uiActPos <> uiLastCalibPos THEN
                uiLastCalibPos := uiActPos;
                udiNoChangeElapsedUs := UDINT#0;
            ELSE
                udiNoChangeElapsedUs := udiNoChangeElapsedUs + udiCycleTimeUs;
            END_IF

            IF udiNoChangeElapsedUs >= udiNoChangeLimitUs THEN
                xDown := FALSE;
                uiCalibState := 20;
                uiLastCalibPos := uiActPos;
                udiNoChangeElapsedUs := UDINT#0;
                udiCalibMoveElapsedUs := UDINT#0;
            END_IF

        20:
            // Drive up to the upper endpoint and measure the travel time.
            xCalibrating := TRUE;
            xUp := TRUE;
            udiCalibMoveElapsedUs := udiCalibMoveElapsedUs + udiCycleTimeUs;

            IF uiActPos <> uiLastCalibPos THEN
                uiLastCalibPos := uiActPos;
                udiNoChangeElapsedUs := UDINT#0;
            ELSE
                udiNoChangeElapsedUs := udiNoChangeElapsedUs + udiCycleTimeUs;
            END_IF

            IF udiNoChangeElapsedUs >= udiNoChangeLimitUs THEN
                xUp := FALSE;
                uiCalibState := 0;
                xCalibrating := FALSE;
                uiState := 0;
                udiNoChangeElapsedUs := UDINT#0;

                IF uiMaxLength = 0 THEN
                    xCalibError := TRUE;
                    xCalibrated := FALSE;
                ELSE
                    // Remove the 3 second endpoint confirmation time from the measured upward move.
                    IF udiCalibMoveElapsedUs > udiNoChangeLimitUs THEN
                        udiTravelTimeUs := udiCalibMoveElapsedUs - udiNoChangeLimitUs;
                    ELSE
                        udiTravelTimeUs := udiCalibMoveElapsedUs;
                    END_IF

                    udiCalculatedMsPerMm := (udiTravelTimeUs / UDINT#1000) / UINT_TO_UDINT(uiMaxLength);
                    IF udiCalculatedMsPerMm = 0 THEN
                        udiCalculatedMsPerMm := UDINT#1;
                    END_IF

                    IF udiCalculatedMsPerMm > UDINT#65535 THEN
                        uiCalibratedMoveTimePerMm := 65535;
                    ELSE
                        uiCalibratedMoveTimePerMm := UDINT_TO_UINT(udiCalculatedMsPerMm);
                    END_IF

                    xCalibrated := TRUE;
                    xCalibError := FALSE;
                END_IF
            END_IF

    ELSE
        // Unknown calibration state recovery.
        uiCalibState := 0;
        xCalibrating := FALSE;
    END_CASE

    RETURN;
END_IF

xCalibrating := FALSE;

CASE uiState OF
    0:
        // Check the slow actual feedback and decide whether another movement pulse is required.
        IF uiActPos > uiSetPos THEN
            udiDistance := UINT_TO_UDINT(uiActPos - uiSetPos);
            xMoveUp := FALSE;
        ELSE
            udiDistance := UINT_TO_UDINT(uiSetPos - uiActPos);
            xMoveUp := TRUE;
        END_IF

        IF udiDistance <= UINT_TO_UDINT(uiEffectiveHysteresis) THEN
            // Actual position is inside tolerance; stay stopped until the target changes.
            udiElapsedUs := UDINT#0;
        ELSE
            // Command only the remaining distance outside the hysteresis band, capped by uiIncrement.
            udiMoveDistance := udiDistance - UINT_TO_UDINT(uiEffectiveHysteresis);
            IF udiMoveDistance > UINT_TO_UDINT(uiEffectiveIncrement) THEN
                udiMoveDistance := UINT_TO_UDINT(uiEffectiveIncrement);
            END_IF

            // Convert the requested movement slice to a timed output pulse using the speed calibration.
            udiMoveTimeUs := udiMoveDistance * UINT_TO_UDINT(uiEffectiveMoveTimePerMm) * UDINT#1000;
            IF udiMoveTimeUs = 0 THEN
                udiMoveTimeUs := udiCycleTimeUs;
            END_IF

            udiElapsedUs := UDINT#0;
            IF xMoveUp THEN
                uiState := 10;
            ELSE
                uiState := 20;
            END_IF
        END_IF

    10:
        // Timed upward movement pulse. Feedback is intentionally not evaluated while moving.
        xUp := TRUE;
        IF udiElapsedUs >= udiMoveTimeUs THEN
            xUp := FALSE;
            uiState := 30;
            udiElapsedUs := UDINT#0;
        ELSE
            udiElapsedUs := udiElapsedUs + udiCycleTimeUs;
        END_IF

    20:
        // Timed downward movement pulse. Feedback is intentionally not evaluated while moving.
        xDown := TRUE;
        IF udiElapsedUs >= udiMoveTimeUs THEN
            xDown := FALSE;
            uiState := 30;
            udiElapsedUs := UDINT#0;
        ELSE
            udiElapsedUs := udiElapsedUs + udiCycleTimeUs;
        END_IF

    30:
        // Hold both outputs OFF so the cylinder can stop and uiActPos can refresh.
        IF udiElapsedUs >= udiSettleTimeUs THEN
            uiState := 0;
            udiElapsedUs := UDINT#0;
        ELSE
            udiElapsedUs := udiElapsedUs + udiCycleTimeUs;
        END_IF

ELSE
    // Unknown state recovery.
    uiState := 0;
    udiElapsedUs := UDINT#0;
END_CASE
"@

    $Payload["fb_name"] = $Name
    $Payload["declaration"] = $Declaration
    $Payload["implementation"] = $Implementation
    }

    $JsonText = ConvertTo-AgentJson -Payload $Payload
}

$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($TempRequestPath, $JsonText, $Utf8NoBom)
Move-Item -LiteralPath $TempRequestPath -Destination $RequestPath

$Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while (-not (Test-Path $ResultPath) -and (Get-Date) -lt $Deadline) {
    Start-Sleep -Milliseconds 250
}

if (-not (Test-Path $ResultPath)) {
    throw "Timed out waiting for in-IDE CODESYS agent '$AgentId' result. Is the matching ide_scripts\run_in_ide_agent*.py script running inside that CODESYS instance?"
}

Get-Content -Path $ResultPath -Raw
