FUNCTION_BLOCK FB_S10eRuntimeEnable
VAR_INPUT
    xEnableS10e1 : BOOL := TRUE; // Requested runtime state for the selected S10e EtherCAT slave.
    xApply : BOOL; // Optional rising edge that applies the current request immediately.
    xAutoApplyOnChange : BOOL := TRUE; // TRUE applies automatically whenever xEnableS10e1 changes.
    dwSlaveInstance : DWORD := 1; // Connector instance: normally 0=first S10e, 1=second, 2=third, etc.
    dwModuleType : DWORD := DWORD#16#41; // IoStandard module type; 16#41 is an EtherCAT slave connector in this project.
    xUseCachedConnector : BOOL := TRUE; // Allows re-enable when a disabled connector is no longer returned by the active list.
END_VAR
VAR_OUTPUT
    xBusy : BOOL; // TRUE while IoMgrReconfigure is active.
    xDone : BOOL; // One-cycle pulse when reconfiguration reports ASYNCSTATE_READY.
    xError : BOOL; // TRUE if no usable connector exists or reconfiguration reports an error.
    xConnectorFound : BOOL; // TRUE when the connector is found in the current IoMgr connector list.
    xTargetAvailable : BOOL; // TRUE when either the current connector or a cached connector can be used.
    xUsingCachedConnector : BOOL; // TRUE when the FB is using the cached connector pointer for this cycle.
    xCurrentEnable : BOOL; // Current CF_ENABLE + CF_DEVICE_ENABLED flag state on the target connector.
    dwCurrentFlags : DWORD; // Raw IoConfigConnector.dwFlags of the target connector.
    udiConfigResult : UDINT; // Return code from IoMgrConfigGetConnectorList.
    udiReconfigureResult : UDINT; // Return code from IoMgrReconfigure.
    udiAsyncState : UDINT; // Async state: 0=pending, 1=active, 2=ready, 3=error, 4=timeout.
END_VAR
VAR
    pConnectorList : POINTER TO IoConfigConnector;
    pFoundConnector : POINTER TO IoConfigConnector;
    pTargetConnector : POINTER TO IoConfigConnector;
    pCachedConnector : POINTER TO IoConfigConnector;
    pActiveConnector : POINTER TO IoConfigConnector;
    diConnectorCount : DINT;
    xHaveCachedConnector : BOOL; // TRUE after the target connector was found at least once.
    xPrevApply : BOOL; // Previous xApply value for rising-edge detection.
    xPrevEnableS10e1 : BOOL := TRUE; // Previous enable request for auto-apply change detection.
    xStartRequest : BOOL; // Internal one-cycle request trigger.
    uiState : UINT; // 0=idle, 10=reconfigure active.
END_VAR
