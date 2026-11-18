# Pico code audit and diagnostic build

This package is a separate copy of the local v15 Pico sender and host tools. The original repository and the connected Pico were not modified. No camera commands were sent during this audit.

## Conclusion

The audit found reproducible error-handling defects and an important firmware-identification defect. It did **not** establish a parity, baud-rate, carrier, or payload-framing bug in the normal stage-1 transmission path. These fixes are not proof that the camera will now accept injection.

## Findings and changes

1. **Opposite pin mappings have the same identity.** Both locally compiled v15 variants identify as `zve10_uart_od 15`, even though one uses TX=28/reset=27 and the other TX=27/reset=28. The old inspector cannot distinguish them. The audit build has a distinct version, `zve10_uart_od 16 audit`, compile-time assertions for TX=28/reset=27, and a configuration query (command 0x12). Its matching host checks pins, open-drain mode, baud and reset duration before enabling the carrier.
2. **An empty blob produces an invalid PIO count.** `build_bits(..., 0)` calculates zero bits and stores `0xffffffff` after subtracting one. The original accepts the command and marks the transfer pending. The audit build rejects records shorter than 14 bytes, and rejects records whose declared length disagrees with the actual frame length. The normal injector sends records of at least 14 bytes, so this defect is not established as the cause of previous attempts.
3. **A pending transfer bypasses the watchdog.** The original timeout explicitly requires `!blob_pending`. A transmission that never signals completion can therefore remain pending indefinitely. A fault-injection test reproduces this. The audit build aborts a pending transfer after 1.8 seconds and releases TX to input. A maximum-size normal record takes approximately 0.96 seconds including its preamble, leaving margin. No stalled transfer has been proved in the historical logs.
4. **Host diagnostics overstate success and lose failure details.** The old `passed` means only sender completion. The updated logs say `sender_completed` and explicitly retain `camera_execution_confirmed: false`. They capture the original exception and count acknowledged reset commands. Log directories are created automatically; log-write errors do not replace the original exception. Invalid payload sizes or negative timing arguments are rejected before opening the port.

## Checks that passed

- Both original and audit versions of the actual sketch were compiled into a host test harness with hardware calls stubbed. The encoder output was independently decoded for all 256 byte values and 14-, 4098- and 4100-byte records. Start bits, LSB-first data, odd parity, stop bits, and open-drain inversion passed.
- The harness reproduces empty-record acceptance and the pending-transfer watchdog gap in the original, and verifies rejection/recovery in the audit build.
- All 30 generated PIO instructions match a fresh assembly of `serialboot.pio` using the installed assembler. No PIO instructions were changed.
- PIO cycle counting gives a nominal 4 kHz carrier (125 microseconds per half-cycle), 250 microsecond preamble half-cycles and 48,000 data bits/second. These are source-level calculations, not measurements at the camera connector.
- Five host regression tests passed: completion reporting, transmission-error cleanup/logging, legacy-version refusal, invalid-input rejection, and swapped-pin configuration rejection.
- Arduino CLI compiled the actual audit sketch successfully for `rp2040:rp2040:rpipico`, core 6.3.2, with `-DOPEN_DRAIN`. Flash usage: 60,076 bytes; static RAM: 19,496 bytes.

Tests emulate software behavior only. They do not validate the physical waveform, camera reset timing, USB-C contacts, or BootROM execution.

## Files

- `build/zve10_pico_od_reset.ino.uf2`: compiled audit firmware; **not flashed**.
- `firmware/zve10_pico_od_reset/`: audit source and unchanged PIO program/header.
- `inspect_pico.py`, `inject_payload.py`, `pico_link.py`: matching audit host tools. They intentionally refuse old v15 firmware.
- `audit.patch`: exact changes relative to the inspected local source.
- `tests/`: regression tests and original sketch fixture.

## Inspection after a deliberate firmware installation

With the camera disconnected, the matching inspector can query version, configuration and idle state without enabling the carrier or pulsing reset:

```powershell
python -B .\inspect_pico.py --port COM7
```

The expected configuration includes TX=28, reset=27, open-drain=1, baud=48000 and reset_us=10. Firmware installation was outside this audit and has not been performed. The diagnostic changes do not remove the project's resistor requirements.

## Re-running offline tests

From this package directory, with Python and g++ available:

```powershell
python -B .\tests\test_host.py
python -B .\tests\run_firmware_tests.py
```

The C++ runner compiles the preserved original and audit sketches with hardware stubs; it does not access USB devices. Intermediate executables are written to the surrounding workspace's `work` directory.
