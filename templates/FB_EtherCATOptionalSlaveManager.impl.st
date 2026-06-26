// Use the EtherCAT driver's optional-slave support instead of disabling
// IoStandard connectors. Disabled connectors can disappear from the runtime
// configuration and may not come back until a controller warm restart.
xDone := FALSE;
xRestartPulse := FALSE;
xApplyRequest := FALSE;
xManualRestartRequest := FALSE;

IF NOT xEnable THEN
    RETURN;
END_IF

IF xApply AND NOT xPrevApply THEN
    xApplyRequest := TRUE;
END_IF

IF xRestart AND NOT xPrevRestart THEN
    xManualRestartRequest := TRUE;
END_IF

IF xAutoApplyOnChange AND (uiRequiredSlaves <> uiPrevRequiredSlaves) THEN
    xApplyRequest := TRUE;
END_IF

xPrevApply := xApply;
xPrevRestart := xRestart;

// These properties must be set before or while the master starts.
EtherCAT_Master.StartConfigWithLessDevice := xStartConfigWithLessDevice;
EtherCAT_Master.AutoSetOperational := xAutoSetOperational;

IF xApplyRequest THEN
    pSlave := EtherCAT_Master.FirstSlave;
    uiIndex := 1;

    WHILE (pSlave <> 0) AND (uiIndex <= uiMaxSlavesToScan) DO
        // Slaves after uiRequiredSlaves remain in the configuration but are optional.
        xOptional := uiIndex > uiRequiredSlaves;
        pSlave^.SetOptional(xOptional);

        pSlave := pSlave^.NextInstance;
        uiIndex := uiIndex + 1;
    END_WHILE

    uiPrevRequiredSlaves := uiRequiredSlaves;
    xDone := TRUE;
END_IF

xDoRestart := xManualRestartRequest OR (xApplyRequest AND xRestartAfterApply);
EtherCAT_Master.xRestart := xDoRestart;
xRestartPulse := xDoRestart;

// The generated master instance must be called for xRestart and status updates.
EtherCAT_Master();

xConfigFinished := EtherCAT_Master.xConfigFinished;
xMasterError := EtherCAT_Master.xError;

uiConfiguredSlaves := 0;
uiOptionalSlaves := 0;
uiOperationalSlaves := 0;
uiFirstNonOperationalIndex := 0;
xAnyNonOperational := FALSE;
eFirstNonOperationalState := ETC_SLAVE_STATE.ETC_SLAVE_BOOT;

pSlave := EtherCAT_Master.FirstSlave;
uiIndex := 1;

WHILE (pSlave <> 0) AND (uiIndex <= uiMaxSlavesToScan) DO
    pSlave^();
    uiConfiguredSlaves := uiConfiguredSlaves + 1;

    xOptional := uiIndex > uiRequiredSlaves;
    IF xOptional THEN
        uiOptionalSlaves := uiOptionalSlaves + 1;
    END_IF

    IF pSlave^.wState = ETC_SLAVE_STATE.ETC_SLAVE_OPERATIONAL THEN
        uiOperationalSlaves := uiOperationalSlaves + 1;
    ELSE
        xAnyNonOperational := TRUE;
        IF uiFirstNonOperationalIndex = 0 THEN
            uiFirstNonOperationalIndex := uiIndex;
            eFirstNonOperationalState := pSlave^.wState;
        END_IF

        // Required slaves are actively stepped toward OP. Optional slaves are
        // handled by AutoSetOperational when they are connected again.
        IF xStepNonOperationalToOp AND xConfigFinished AND NOT xOptional THEN
            CASE pSlave^.wState OF
                ETC_SLAVE_STATE.ETC_SLAVE_INIT:
                    pSlave^.SetOpMode(ETC_SLAVE_STATE.ETC_SLAVE_PREOPERATIONAL);
                ETC_SLAVE_STATE.ETC_SLAVE_PREOPERATIONAL:
                    pSlave^.SetOpMode(ETC_SLAVE_STATE.ETC_SLAVE_SAVEOPERATIONAL);
                ETC_SLAVE_STATE.ETC_SLAVE_SAVEOPERATIONAL:
                    pSlave^.SetOpMode(ETC_SLAVE_STATE.ETC_SLAVE_OPERATIONAL);
            END_CASE
        END_IF
    END_IF

    pSlave := pSlave^.NextInstance;
    uiIndex := uiIndex + 1;
END_WHILE
