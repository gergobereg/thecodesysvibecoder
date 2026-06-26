// Low-level runtime enable/disable for an S10e EtherCAT slave connector.
// The unit is selected by connector instance, so the CODESYS object name is
// not needed at runtime. A cached connector pointer is kept because a disabled
// connector may disappear from the active connector list before it is enabled.
xDone := FALSE;
xStartRequest := FALSE;
xUsingCachedConnector := FALSE;

IF xApply AND NOT xPrevApply THEN
    xStartRequest := TRUE;
END_IF

IF xAutoApplyOnChange AND (xEnableS10e1 <> xPrevEnableS10e1) THEN
    xStartRequest := TRUE;
END_IF

xPrevApply := xApply;
xPrevEnableS10e1 := xEnableS10e1;

udiConfigResult := IoMgrConfigGetConnectorList(
    ppConnectorList := ADR(pConnectorList),
    pnCount := ADR(diConnectorCount));

pFoundConnector := IoMgrConfigGetConnector(
    pConnectorList := pConnectorList,
    pnCount := ADR(diConnectorCount),
    dwModuleType := dwModuleType,
    dwInstance := dwSlaveInstance);

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

                IF xEnableS10e1 THEN
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
