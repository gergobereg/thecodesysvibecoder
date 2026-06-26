FUNCTION_BLOCK FB_EtherCATMasterRestart
VAR_INPUT
    xExecute : BOOL; // Rising edge starts a restart/reconfigure of the EtherCAT master connector.
    dwMasterModuleType : DWORD := DWORD#16#40; // IoStandard connector type CT_ETHERCAT_MASTER.
    dwMasterInstance : DWORD := 0; // EtherCAT master connector instance; normally 0 when there is one master.
END_VAR
VAR_OUTPUT
    xBusy : BOOL; // TRUE while IoMgrReconfigure is active.
    xDone : BOOL; // One-cycle pulse when the restart/reconfigure reports ASYNCSTATE_READY.
    xError : BOOL; // TRUE if the master connector cannot be found or reconfigure reports an error.
    xConnectorFound : BOOL; // TRUE when the EtherCAT master connector is found in the IoMgr connector list.
    dwMasterFlags : DWORD; // Raw IoConfigConnector.dwFlags of the master connector.
    udiConfigResult : UDINT; // Return code from IoMgrConfigGetConnectorList.
    udiReconfigureResult : UDINT; // Return code from IoMgrReconfigure.
    udiAsyncState : UDINT; // Async state: 0=pending, 1=active, 2=ready, 3=error, 4=timeout.
END_VAR
VAR
    pConnectorList : POINTER TO IoConfigConnector;
    pMasterConnector : POINTER TO IoConfigConnector;
    pActiveConnector : POINTER TO IoConfigConnector;
    diConnectorCount : DINT;
    xPrevExecute : BOOL; // Previous xExecute value for rising-edge detection.
    xStartRequest : BOOL; // Internal one-cycle request trigger.
    uiState : UINT; // 0=idle, 10=reconfigure active.
END_VAR
