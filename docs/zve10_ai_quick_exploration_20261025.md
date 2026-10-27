# ZV-E10 AI capabilities: quick exploration —25 October2026

Scope: original ZV-E10, official documentation plus saved firmware; no camera access, no patch or inference benchmark. String matches are leads, not proof a particular path is active.

## Confirmed user features

Sony describes Real-time Tracking as using AI including machine learning. Human face/eye detection and tracking are supported. The current official help guide also says animal-eye detection in movies requires system software2.00 or later; animal faces are not detected. This is firmware-dependent; this quick pass did not identify the installed camera's current firmware version.

Sources: [Sony product description](https://www.sony.co.uk/store/product/zve10bdi.eu/Interchangeable-lens-vlog-camera?frt=20), especially Real-time Tracking; [Sony Face/Eye AF help](https://helpguide.sony.net/ilc/2070/v1/en/contents/TP0002053240.html).

## Saved firmware evidence

Scanned printable strings in av-cam.bin, libObj.so and libBizFw.so:138 matching strings preserved in firmware-ai-strings.json. No standard inference runtime/model format was identified by this limited scan. That does NOT establish absence of embedded models, proprietary accelerators or stripped inference code. A filename pass found facedmy.bin(51200 bytes), face-record scenario and face/object-tracking UI resources; file purpose/content not established from names alone.

RTOS av-cam.bin runtime base0x635c6000 has FC/Api/fc_api_monitoring.cpp, fc_api_tracking.cpp, fc_api_face_record.cpp and fc_api_idt.cpp. Concrete labels include EyeDetection, idt_edt_start/get_result, idt_cf_start/get_result, idt_staple_start/stop and separate Object/Animal tracking mode diagnostics. This supports an internal face/eye/tracking subsystem. It does not identify a neural-network architecture or prove accelerator programmability. Staple InitTrain is not evidence of training arbitrary neural models.

Real previously recovered monitoring code0x63b42800..0x63b44200 references Astra GetPrcMemory(address,handle,type), DMM sharing and monitoring sequences. Astra also appears in movie paths; its name must not be treated as an NPU identifier. Linux camera layer contains face-detection events and object-tracking mode controls; SDK has FaceInfo and Remote tracking/frame metadata structures. Metadata reuse for a webcam overlay or crop is a possible extension, not an implemented feature.

## Useful new webcam source lead

Existing monitoring disassembly references StartAll fc_pic[VGA] at code0x63b43eec and StartAll fc_pic[40] at0x63b43f10; corresponding strings0x63fe2c02 and0x63fe2c31. GetPrcMemory label is referenced at0x63b4284c. These imply internal reduced-resolution detector input records worth tracing. VGA is a diagnostic label, not proof of readable640x480 full-color YC: the buffers could be luma-only, processed, proprietary, short-lived or inactive during USB streaming. Prove format, dimensions, memory mapping and stable ownership before using them. Full disassembly: existing workspace outputs/yc-source-re-20261025/fc-monitoring-real.txt.

## Practical conclusions

The camera already performs specialized subject recognition. Our saved Linux CPU evidence is four Cortex-A5 cores, VFPv4-D16, no advertised NEON; it says nothing definitive about a separate vision accelerator. No custom-model loader, general NPU API, compute throughput, model weights or instruction set has been recovered. Reusing detection metadata appears more immediately tractable than running a custom neural network. The detector's VGA input is a useful additional raw-frame research lead; it is not a working webcam source yet.
