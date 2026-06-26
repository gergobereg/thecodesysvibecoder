FUNCTION_BLOCK FB_MD5Hash
VAR_INPUT
    xExecute : BOOL; // Rising edge starts a new MD5 calculation.
    pData : POINTER TO BYTE; // Start address of the data to hash, normally ADR(stYourData).
    udiSize : UDINT; // Number of bytes to hash, normally SIZEOF(stYourData).
    abyExpectedDigest : ARRAY [0..15] OF BYTE; // Optional MD5 digest received from the other controller.
    xCompareExpected : BOOL := TRUE; // When TRUE, xMatch is updated when the local digest is done.
END_VAR
VAR_OUTPUT
    xDone : BOOL; // TRUE after a successful calculation; reset by the next xExecute rising edge.
    xBusy : BOOL; // TRUE while the CAA Memory MD5 block is calculating.
    xError : BOOL; // TRUE if a request is invalid, for example null pointer or zero byte length.
    xMatch : BOOL; // TRUE when the calculated digest equals abyExpectedDigest.
    abyDigest : ARRAY [0..15] OF BYTE; // Calculated 16-byte MD5 digest.
END_VAR
VAR
    fbMd5 : MEM.MD5; // CAA Memory MD5 function block.
    xExecuteOld : BOOL; // Previous xExecute state for rising-edge detection.
    xStart : BOOL; // One-cycle start pulse forwarded to MEM.MD5.
    i : INT; // Digest byte loop index.
END_VAR
