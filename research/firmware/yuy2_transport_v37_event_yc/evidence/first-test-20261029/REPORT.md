# Revision 3.7 first hardware test: descriptor rejection before resize

29 October 2026. Installed revision remains 3.7. **Zero frames captured.** No new flash, rollback or deletion occurred during this collection. The user reported controls remained responsive, but USB did not return after selecting Mass Storage, cable reconnect or MTP. Windows found no Sony device; host PnP rescan was denied administrative access. A user-performed restart restored service access. Do not describe that manual restart as an observed spontaneous crash.

## Evidence

Windows enumerated VID054C/PID0DE3 and DirectShow advertised 640x480 YUY2 at 10 fps. A ten-frame FFmpeg request was bounded to20s and killed on timeout (total22.037s including termination). It received0bytes/no complete frames; FFmpeg had not produced its capture header/output file. Format-query, command, capture report and error log are preserved in the parent directory.

Camera logs were recovered after the required manual restart. Fifteen snapshot files total6,212,976B, each verified against camera MD5, plus the1273B manifest. runtime.log1014B MD54dad320283da73c8da8c82acce59fd5b; vga.log751B MD5b88767174a71abdd7555d10d3798e923. Originals and snapshots remain on camera. Current-boot dmesg is not prior-boot crash evidence. ThreadMonitor is empty and binary system logs have not been decoded into a fault PC.

Persisted worker sequence:

```
YC_CONNECT_REQUEST 0035611e 00000000 7fffff37
YC_CONNECTED       0035611e 7fffff37 00000000
YC_CONNECT_STATUS  00000000 0035611e 00000000
YC_FRAME_EVENT     00000001 0000266e 0035611e
EVENT_DESCRIPTOR_REJECTED 0000266e 00000000 00000000
SOURCE_SEARCH_FAILED 00000000 00000000 00000000
QUARANTINED        0000266e 00000000 00002673
TRACE_DROPPED      00000000 00000000 00000000
```

These are historical identities, never handles/queues to replay. The real native YC SEND reached the private receiver. Metadata Open/map succeeded far enough to reach the combined descriptor gate. This proves neither a valid pixel attachment nor a usable image format. No SOURCE_EVENT/RESIZE_ENTER/RESIZE_RETURN/COMPLETE or USB SUBMITTED marker exists. The worker quarantined before pixel acquisition and before any SDF resize.

Runtime also records30 missing-staging polls, FAILURE_EVENT code0x26 (38), then successful original stop/finish returns and retained USB source. The logs lack a shared timestamp axis; these staging messages may overlap mode exit/recovery. Do not call this evidence of DMA failure: the source never reached submission and no USB_DMA_QUARANTINED marker exists.

## What is still unknown

find_source combines a stable-copy comparison, ImageSizeInfo parse, StateInfo parse, absence of Category0x11, expected pixel type0x295, nonzero pixel handle and no metadata/pixel handle alias into one failure message with zero diagnostic arguments. Any can reject a transfer. No raw rejected SDS was saved: dumps are gated on successful resize and clean shutdown. The manual restart discarded the only private RAM copy. This run cannot identify which predicate failed, the actual unit type, category set, dimensions or pixel layout. It is incorrect to relax a check based only on this log.

Code review also shows fault bypasses normal reference return and private-pin disconnect. For this deterministic rejection it retained the metadata transfer and connection; no SEND_COMP or disconnect marker followed. That is a plausible backpressure/teardown problem, but the saved evidence does not prove it caused the missing USB enumeration. The next correction must distinguish known validation refusal from uncertain IPC, capture bounded rejected-descriptor bytes and individual check results, and return/disconnect only according to proven ownership. Do not guess a Free or return an unidentified pixel credit.

## Recovery state

Initial service uptime43.42s after the user's restart; boot IDfae73822-b983-404f-b619-827dbc314499. Installed module/wrapper/kernel hashes still match3.7. ssboot=idle, original logger version01.00.000, no streaming/producer mappings after reboot. Free /tmp5,242,880B, /log347,078,656B, /usr10,765,312B; /tmp write/readback passed. Storage was not full in this collection. Original full kikilog remains MD573b4dc0ac4b8e0b5796baf26694d88c7. Service closed job003 WORKBENCH_CLOSED/Done. No further stream attempt was requested.
