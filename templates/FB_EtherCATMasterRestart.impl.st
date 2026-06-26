// Restart/reconfigure the complete EtherCAT master connector.
// IoMgrReconfigure performs an asynchronous disable/enable/update-mapping
// sequence for the connector, which is the closest runtime "master restart"
// available through IoStandard.
xDone := FALSE;
xStartRequest := FALSE;

IF xExecute AND NOT xPrevExecute THEN
    xStartRequest := TRUE;
END_IF
xPrevExecute := xExecute;

udiConfigResult := IoMgrConfigGetConnectorList(
    ppConnectorList := ADR(pConnectorList),
    pnCount := ADR(diConnectorCount));

pMasterConnector := IoMgrConfigGetConnector(
    pConnectorList := pConnectorList,
    pnCount := ADR(diConnectorCount),
    dwModuleType := dwMasterModuleType,
    dwInstance := dwMasterInstance);

IF pMasterConnector <> 0 THEN
    xConnectorFound := TRUE;
    dwMasterFlags := pMasterConnector^.dwFlags;
ELSE
    xConnectorFound := FALSE;
    dwMasterFlags := DWORD#0;
END_IF

CASE uiState OF
    0:
        xBusy := FALSE;
        udiReconfigureResult := UDINT#0;

        IF xStartRequest THEN
            IF (udiConfigResult <> UDINT#0) OR NOT xConnectorFound THEN
                xError := TRUE;
            ELSE
                xError := FALSE;
                udiAsyncState := UDINT#16#FFFFFFFF;
                pActiveConnector := pMasterConnector;
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

            dwMasterFlags := pActiveConnector^.dwFlags;

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
