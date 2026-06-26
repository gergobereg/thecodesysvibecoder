// Create a one-cycle start pulse. The wrapped MEM.MD5 block starts on a rising edge.
xStart := xExecute AND NOT xExecuteOld;
xExecuteOld := xExecute;

IF xStart THEN
    xDone := FALSE;
    xError := FALSE;
    xMatch := FALSE;
END_IF

// Reject invalid requests before forwarding the start pulse to the library block.
IF xStart AND ((pData = 0) OR (udiSize = 0)) THEN
    xError := TRUE;
END_IF

fbMd5(
    xExecute := xStart AND NOT xError,
    pMemoryBlock := pData,
    udiNumberOfBytes := udiSize
);

xBusy := fbMd5.xBusy;

IF fbMd5.xDone THEN
    // Copy the library digest to stable wrapper outputs.
    FOR i := 0 TO 15 DO
        abyDigest[i] := fbMd5.abyDigest[i];
    END_FOR

    xDone := TRUE;

    // Compare byte-for-byte with the digest supplied by the communication peer.
    IF xCompareExpected THEN
        xMatch := TRUE;
        FOR i := 0 TO 15 DO
            IF abyDigest[i] <> abyExpectedDigest[i] THEN
                xMatch := FALSE;
            END_IF
        END_FOR
    END_IF
END_IF
