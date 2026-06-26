FUNCTION_BLOCK FB_EtherCATOptionalSlaveManager
VAR_INPUT
    xEnable : BOOL := TRUE; // FALSE leaves the EtherCAT master untouched by this FB.
    uiRequiredSlaves : UINT := 1; // Number of configured slaves that must be present; higher indexed slaves become optional.
    xApply : BOOL; // Rising edge reapplies optional flags and optionally restarts the master.
    xAutoApplyOnChange : BOOL := TRUE; // TRUE reapplies when uiRequiredSlaves changes.
    xRestartAfterApply : BOOL := TRUE; // TRUE pulses EtherCAT_Master.xRestart after optional flags are changed.
    xRestart : BOOL; // Manual rising edge pulses EtherCAT_Master.xRestart.
    xStepNonOperationalToOp : BOOL := TRUE; // TRUE tries INIT->PREOP->SAFEOP->OP for required slaves not yet operational.
    xStartConfigWithLessDevice : BOOL := TRUE; // Allows startup when optional configured slaves are not physically present.
    xAutoSetOperational : BOOL := TRUE; // Lets the master automatically retry optional/returning slaves.
    uiMaxSlavesToScan : UINT := 32; // Loop guard for the generated EtherCAT slave chain.
END_VAR
VAR_OUTPUT
    xDone : BOOL; // One-cycle pulse after optional flags were applied.
    xRestartPulse : BOOL; // TRUE for the cycle in which EtherCAT_Master.xRestart is pulsed.
    xConfigFinished : BOOL; // EtherCAT master reports that configuration download/startup is finished.
    xMasterError : BOOL; // EtherCAT master error output.
    xAnyNonOperational : BOOL; // TRUE when at least one scanned slave is not OP.
    uiConfiguredSlaves : UINT; // Number of slaves reached through EtherCAT_Master.FirstSlave/NextInstance.
    uiOptionalSlaves : UINT; // Number of scanned slaves above uiRequiredSlaves.
    uiOperationalSlaves : UINT; // Number of scanned slaves currently in OP.
    uiFirstNonOperationalIndex : UINT; // 1-based index of the first scanned slave not in OP; 0 when all are OP.
    eFirstNonOperationalState : ETC_SLAVE_STATE; // State of the first non-OP slave.
END_VAR
VAR
    pSlave : POINTER TO ETCSlave;
    uiIndex : UINT;
    xPrevApply : BOOL;
    xPrevRestart : BOOL;
    uiPrevRequiredSlaves : UINT := 65535;
    xApplyRequest : BOOL;
    xManualRestartRequest : BOOL;
    xDoRestart : BOOL;
    xOptional : BOOL;
END_VAR
