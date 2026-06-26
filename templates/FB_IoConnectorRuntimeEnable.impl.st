// Generic low-level runtime enable/disable for an IoStandard connector.
// For S10e EtherCAT slaves in this project, use dwModuleType 16#41 and select
// the unit by dwInstance. The CODESYS object name is not needed at runtime.
xDone := FALSE;
xStartRequest := FALSE;
xUsingCachedConnector := FALSE;

IF xApply AND NOT xPrevApply THEN
    xStartRequest := TRUE;
END_IF

IF xAutoApplyOnChange AND (xEnable <> xPrevEnable) THEN
    xStartRequest := TRUE;
END_IF

xPrevApply := xApply;
xPrevEnable := xEnable;

udiConfigResult := IoMgrConfigGetConnectorList(
    ppConnectorList := ADR(pConnectorList),
    pnCount := ADR(diConnectorCount));

pFoundConnector := IoMgrConfigGetConnector(
    pConnectorList := pConnectorList,
    pnCount := ADR(diConnectorCount),
    dwModuleType := dwModuleType,
    dwInstance := dwInstance);

IF pFoundConnector <> 0 THEN
    xConnectorFound := TRUE;
    pTargetConnector := pFoundConnector;
    pCachedConnector := pFoundConnector;
    xHaveCachedConnector := TRUE;
ELSE
    xConnectorFound := FALSE;

    IF xUseCachedConnector AND xHaveCachedConnector THEN
        pTargetConnector := pCachedConnector;
        xUsingCachedConnector := TRUE;
    ELSE
        pTargetConnector := 0;
    END_IF
END_IF

IF pTargetConnector <> 0 THEN
    xTargetAvailable := TRUE;
    dwCurrentFlags := pTargetConnector^.dwFlags;
    xCurrentEnable := (pTargetConnector^.dwFlags AND DWORD#16#5) = DWORD#16#5;
ELSE
    xTargetAvailable := FALSE;
    dwCurrentFlags := DWORD#0;
    xCurrentEnable := FALSE;
END_IF

CASE uiState OF
    0:
        xBusy := FALSE;
        udiReconfigureResult := UDINT#0;

        IF xStartRequest THEN
            IF (udiConfigResult <> UDINT#0) OR NOT xTargetAvailable THEN
                xError := TRUE;
            ELSE
                xError := FALSE;
                udiAsyncState := UDINT#16#FFFFFFFF;

                IF xEnable THEN
                    pTargetConnector^.dwFlags := pTargetConnector^.dwFlags OR DWORD#16#5;
                ELSE
                    pTargetConnector^.dwFlags := pTargetConnector^.dwFlags AND DWORD#16#FFFFFFFA;
                END_IF

                pActiveConnector := pTargetConnector;
                pCachedConnector := pTargetConnector;
                xHaveCachedConnector := TRUE;
                dwCurrentFlags := pTargetConnector^.dwFlags;
                xCurrentEnable := (pTargetConnector^.dwFlags AND DWORD#16#5) = DWORD#16#5;
                uiState := 10;
            END_IF
        END_IF

    10:
        xBusy := TRUE;
        IF pActiveConnector = 0 THEN
            xBusy := FALSE;
            xError := TRUE;
            uiState := 0;
        ELSE
            udiReconfigureResult := IoMgrReconfigure(
                pConnector := pActiveConnector,
                pudiState := ADR(udiAsyncState));

            dwCurrentFlags := pActiveConnector^.dwFlags;
            xCurrentEnable := (pActiveConnector^.dwFlags AND DWORD#16#5) = DWORD#16#5;

            IF udiReconfigureResult <> UDINT#0 THEN
                xBusy := FALSE;
                xError := TRUE;
                uiState := 0;
            ELSIF udiAsyncState = UDINT#2 THEN
                xBusy := FALSE;
                xDone := TRUE;
                xError := FALSE;
                uiState := 0;
            ELSIF (udiAsyncState = UDINT#3) OR (udiAsyncState = UDINT#4) THEN
                xBusy := FALSE;
                xError := TRUE;
                uiState := 0;
            END_IF
        END_IF

ELSE
    xBusy := FALSE;
    xError := TRUE;
    uiState := 0;
END_CASE
