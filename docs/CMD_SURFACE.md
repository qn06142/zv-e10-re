# ZV-E10 av-cam.bin — Command / Dispatch Surface (extracted from strings)

> Scripts mentioned below by bare filename now live under `research/`;
> see `research/README.md` for the index.

Extracted offline from D:\02_Development_And_Projects\pmca-re\fw\av-cam.bin (161,595 strings).
No camera needed. See cmd_surface.py.

## CMD_ID_* (12) — the top-level command namespace
CMD_ID_SDF_ALL
CMD_ID_SDF_CANCEL
CMD_ID_SDF_CLOSE
CMD_ID_SDF_EXEC        <-- executes something; prime audit target
CMD_ID_SDF_INPUT
CMD_ID_SDF_OPEN
CMD_ID_SDF_OUTPUT
CMD_ID_SDF_PAUSE
CMD_ID_SDF_RESTART
CMD_ID_SDF_START
CMD_ID_SDF_STOP
CMD_ID_SDF_UNKNOWN

## SDF_* subsystem (57) — error/state codes confirm it's a real execution engine
SDF_ERR_*         : OK / PARAM / TIMEOUT / MEMORY / HW_TROUBLE / NOT_SUPPORTED /
                    REQ_OVERFLOW / UNEXPECTED / UNIQUEID / SDS / SET_PARAM / CANCEL_*
SDF_INTRA_ERR_*   : same family w/ JPEG_QVALUE, ENCODE_SIZE_OVER, EXTENT, SA, PIN_CONNECT
SDF_RECMODE_*     : STILL_REC / OPAL_DUAL_REC / HW_DUAL_REC
=> SDF = a media/still/codec pipeline engine with OPEN->INPUT/OUTPUT->EXEC->START->
   STOP/CANCEL/RESTART/CLOSE lifecycle. EXEC feeds it data/commands to run.

## Exec* dispatch symbols (164) — handler functions for the message bus
Notable families:
  ExecApi*     : ExecApiExecBaseSetting, ExecApiExecIdtVerification, ExecApiNotify*,
                 ExecApiStart*, ExecApiCancel*  (external API entry points)
  ExecSens*    : ExecSensCmd, ExecSensComp, ExecSensMsg        (sensor subsystem)
  ExecSdf*     : ExecSdfMsg, ExecSdfMsgParallel, ExecPinSdfMsg (SDF pipeline msgs)
  ExecJpeg*    : ExecJpegOpen/Close/Ready/Encode/TanzEncode    (JPEG pipeline)
  ExecMovie*   : ExecMovieCodecMsg, ExecMovieCodecResponse      (movie codec)
  ExecRc*      : ExecRcAcquire/Release/Resize/DistCorrection*   (recomposition/zoom)
  ExecTanz*    : ExecTanzaku, ExecTanzSrcDistCalc, ExecTanzRcDistCalc* (Tanzaku=panorama?)
  ExecVfx*     : ExecVfxEffect*, ExecVfxStart/Open/Close        (video effects)
  ExecPin*     : ExecPinCmd/Get/MsgResponce/Send/YCPin*         (pin/connection mgmt)
  ExecConnect/ExecDisconnect/ExecRequestConnect/ExecRequestDisconnect
  ExecCmd, ExecSendCommand, ExecReceive, ExecMain, Execute*, ExecTrigger
  ExecGuard/ExecGard/ExecPathSequenceGard/ExecTimeTypeGard       (GARD = guarded exec)

## *Handler / *Msg symbols (sample)
  *Handler : ~98 (e.g. ExecModeHandler, ExecRawDevHandler, ExecReleaseHandler)
  *Msg     : hundreds (Proc*ProcMsg*, *MsgSet*, *MsgChk* — the IPC message names)

## Observations for vuln hunting
1. CMD_ID_SDF_EXEC + the SDF lifecycle = a "run this pipeline" primitive. The
   interesting question is what EXEC accepts as its target/argument and whether
   it's validated. Gated behind authenticated service shell -> not cold-boot.
2. Exec*Handler / Exec*Msg names describe a rich message-passing RTOS. Each is a
   potential parse/dispatch bug if a malformed message reaches it. Reachable
   only via the uipc bus (liro<->Linux) or the authenticated shell.
3. NO numeric opcode table found in plaintext strings (only symbolic names) ->
   the actual command IDs live in code, not the string table. To map ID->handler
   you'd need to disassemble av-cam.bin's dispatch switch (the encrypted body).
4. GARD/Gard symbols suggest Sony added guarded-execution wrappers (probably
   after an earlier bug) — implies exec validation was a known soft spot.

## Next step if pursuing this
Disassemble the av-cam.bin dispatch (needs decrypting the body, OR finding the
plaintext loader stub that still references the handler table). The 4KB LIRO
header + any plaintext init code may contain the CMD_ID -> handler mapping.
