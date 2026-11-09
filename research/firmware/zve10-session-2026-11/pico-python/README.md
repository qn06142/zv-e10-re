# GP28 TX / GP27 reset Pico tools

Recovered from the 3 November Pico audit; copied without code changes.

The Python scripts run on the Windows PC. The Pico uses the included compiled
Arduino/PIO firmware, not MicroPython. Its configured pins are GP28 TX
(open-drain), GP27 reset, 48,000 bit/s and a 10-microsecond reset pulse.

These host scripts require `zve10_uart_od 16 audit`. Legacy v15 variants used
opposite pin mappings with the same version identity. Do not infer installed
pin mapping from the v15 name. The included UF2 is the matching audit build;
this retrieval has not flashed it or issued any camera command.

Install the host dependency if needed:

```powershell
python -m pip install pyserial
```

List serial ports (does not open a serial connection):

```powershell
python -m serial.tools.list_ports -v
```

From this directory, inspect the matching firmware (replace COM7 with the actual
Pico port). This queries identity, configuration and state, without sending
reset/carrier commands:

```powershell
python inspect_pico.py --port COM7
```

Payload injection is an active operation that enables the carrier and normally
pulses camera reset. For deliberate use after firmware/pin verification:

```powershell
python inject_payload.py --port COM7 --file PATH_TO_PAYLOAD.bin --duration 90
```

A sender-completed result does not prove camera execution. See AUDIT.md for the
software tests, compatibility details and remaining hardware limitations.

## Isolate reset or carrier

With the Pico idle, issue one GP27 reset without sending carrier or payload:

```powershell
python diagnose_link.py --port COM7 --reset-only
```

To briefly enable the carrier and read GP28 edge intervals:

```powershell
python diagnose_link.py --port COM7 --carrier-test
```

Both actions require an explicit flag. Running without either flag only queries
identity/configuration/status. A reset ACK does not prove that the camera reset;
GPIO transitions do not prove the waveform at the camera connector.

If no carrier edges are detected, physically unplug the camera-facing connector
and run this isolated test. It temporarily enables GP28's weak internal pull-up,
samples the carrier, then stops the carrier and disables the pull-up. No reset
or payload is sent, and no firmware update is required:

```powershell
python diagnose_link.py --port COM7 --isolated-self-test
```

Only use this option with the camera disconnected. A pass verifies GP28 locally,
not GP27, continuity to the connector, or camera boot-ROM compatibility. An
open-drain output needs a pull-up to produce a readable high level; zero edges
without a pull-up do not establish that the PIO failed.
