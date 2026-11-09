# Sony ZV-E10 UVC containment build

This is an offline 1920×1080 YUY2 High-Speed candidate at 5 fps. It uses
the existing v42 chunk kernel with the stock gadget registration calls
and builds the current YUY2 source without its SuperSpeed speed and DID
overrides. The package includes no replacement common USB library.
The YUY2 module still installs UVC descriptor and Probe/Commit hooks in RAM.

Apply containment.patch to the corresponding source snapshot to reproduce
the source changes. Build using the original v43 recipe and its documented
input library. Use the v42 usbg_video.ko identified by manifest.json.

This bundle is for offline verification. A camera already carrying a
modified libInfraUsbCmn.so needs a separate, independently reachable recovery
path to return that file to its stock hash. This bundle has no installer.

Unicorn reproduced the old kernel overwrite with mocked successful and
failed second registrations. Frontend, producer, capacity, kernel header,
and DMA fence checks passed on the containment build. DMA and USB services
are mocked. Live video, reboot and Senser re-entry are unverified.
SuperSpeed enablement remains unresolved.
