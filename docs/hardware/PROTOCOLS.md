# Peripheral, accessory and software protocols

A controller base, firmware endpoint, command ID and wire frame describe different layers. This page records the boundary and missing fields for each. No command is sent by these documents or atlas tools.

| Interface | Source-backed controller / protocol evidence | Missing contract |
| --- | --- | --- |
| I2C controllers | GPL UDIF: 0xf2401000 and 0xf2401800, each 0x800 bytes, IRQs 199/200 and CLK4 `IPCLKEN2`/`IPCLKEN4` gates. Offline `i2c.ko` execution recovers 13 16-bit registers, command/FIFO framing, dividers, NACK retry, `CLK4` reset gating and UIPC endpoints. | Live-body `i2c.ko` identity, physical pin mux/pull-ups, board bus wiring, slave addresses, sensor/accessory binding and measured SCL rates remain open. No I2C scan has been run. |
| SPI controllers | GPL UDIF: 0xf2006000 and 0xf2007000, each 0x1000 bytes. | Mode, divider, chip select/pin assignment, transfer/IRQ/abort sequence, and attached device identity. |
| SIO controllers | GPL UDIF: five windows from 0xf2405000 at stride 0x200, each size 0x200. | Serial format, wiring and mapping to lens/panel/accessory clients. A controller name does not identify the connector. |
| E-mount/lens | Firmware contains CAIF relay and LIF framing/error vocabulary. Fallback 750 kbaud appears in a firmware message. | Measured wire rate/levels, exact header/footer bytes, lengths/endianness, checksum algorithm/coverage, sequence/ack/timeout rules and physical controller/pin binding. 750 kbaud is a string-derived fallback, not a measured normal configuration. |
| Lens update/control | Named version, focus, iris and update command families exist. | Exact numeric wire opcodes/payload layouts and independently observed effects for each lens. Firmware-update commands are state-changing, not generic read-only probes. |
| Multi Interface Shoe and other accessories | Connector categories are relevant to future ownership work. | Shoe power/data pin mapping, identification/enumeration, electrical levels, register/controller bindings and packet protocol. No lens-bus assumptions are transferred to the shoe. |
| Analog audio / mic / codec | Native codec and recording services exist. | Analog routing, codec register bus/address, power/mute/clock order and DMA format. A software recording task does not locate audio hardware registers. |
| HDMI and CEC | GPL UDIF declares HDMI at 0xf2a40000, size 0x20000; CEC at 0xf3c10000, size 0x190. | TX/PHY reset and clocks, EDID/DDC path, output timings, CEC framing/IRQ acknowledgement and ownership after shutdown. |
| USB controller | GPL DRD aperture 0xf0200000, global view +0xc100, gadget view +0xc700; wrapper base 0xf2920000. | PHY/clock/reset/power handoff, endpoint/event-ring setup and DMA completion/recovery for a standalone runtime. Existing Linux UVC transport is separate. |
| USB service/host relay | Existing authenticated Senser bridge and raw host tunnel are documented. The latter uses USBC/CBW and a 68-byte camera structure with code at +0x0b and payload length +0x1c. | Raw tunnel framing is not an electrical lens protocol or a sensor register bus. Preserve actual mode/PID and firmware handler identity per operation. |
| Wi-Fi | Linux wlan0/Dropbear access was observed in normal shooting. | Independent Wi-Fi initialization after Linux takeover, firmware loading, SDIO/PCIe binding and power/reset ownership. Existing SSH credentials or a prior lease do not describe a hardware protocol. |

Use [GPL channel declarations](data/platform.json) for source lines and formulas, and the [existing camera interfaces](../reference/08-camera-interfaces.md) for service/tunnel tooling. Earlier interface text groups FirmUpReq with identity queries; treat it as an update request, not a harmless query.

## Firmware messaging is not a wire-level register bus

OSAL/UIPC endpoint addresses identify queues. For example, endpoint 0x00dc0000 and command IDs carried in its payload are different namespaces. Native RAW endpoint 0x012802f1 is a Linux receiver route, not a physical peripheral address. DMM request/reply opcodes manage objects and ownership, not hardware register writes by themselves.

For each recovered message retain transport, sender/receiver, command/subcommand, total length, field offsets/widths/endianness, response/error codes, sync/async behavior and object lifetime. A returned RC=0 can mean message acceptance only. [Messaging reference](../reference/04-messaging.md), [reviewed capture claims](../../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md).

## Expected values and transactions

Record a complete transaction, not a bag of constants: target identity, power/reset/clock prerequisites, controller and pin mux, bus configuration, ordered request bytes/register writes, response or status polling, deadline, error acknowledgement, and cleanup. Mode-specific observations stay separate from documented reset defaults and required programmed values. No complete sensor, shoe or standalone USB initialization transaction is established in this atlas yet.

## I2C controller hardware & UIPC contract (offline camera_2025 i2c.ko)

Original-instruction execution of `i2c.ko` (SHA-256 `37b37633a8cdfd6ce60258d646afc2cf11dc50de67cd71a0b53631584412321e`; `current_body_module_identity_checked=false`) in Unicorn verified the controller register contract and UIPC transport bindings ([i2c-contract.json](data/i2c-contract.json)):

- **Bindings & probe:** `i2c_init` enables `UDIF` `dclk` via `__udif_devio_devclk(..., enable=1, clksel=0)` (`CLK4` `IPCLKEN4` bit 17/18 in `udif/platform.c`) and binds `i2c_handler`/`i2c_tasklet`. `i2cu_probe` reads 1 byte from Backup unit `0x520000` and registers OSAL synchronous UIPC queues `0x00520250` (channel 0, `"i2c_uipc"`) and `0x00520607` (channel 1, `"i2c_uipc_ch1"`).
- **16-bit register block (`0xf2401000` / `0xf2401800`):** The driver dump helper `.text+0x10a4` reads 13 halfword offsets (`+0x00, +0x04, +0x08, +0x0c, +0x10, +0x14, +0x1c, +0x20, +0x24, +0x28, +0x2c, +0x34, +0x38`). Helper `.text+0x1328` polls bit 15 (`0x8000`) clear up to 16 times (`__const_udelay(0xa3d6f8)`) before writing, calling reset `.text+0x119c` on timeout.
- **Command, FIFO & dividers:** `+0x24` is armed (`0x1`), up to 16 bytes are pushed into `+0x0c`, `count - 1` is written to `+0x08`, and `+0x04` starts the phase (`0x80` GO | `0x08` RX | `0x04` TX | `0x02` STOP | `0x01` START). A 7-bit write sends `0x87` with `(addr << 1) | 0` followed by payload bytes; a 7-bit read runs TX address phase `0x85` with `(addr << 1) | 1`, then RX phase `0x8a` reading `((+0x08 >> 4) & 0xf) + 1` bytes from `+0x0c`. Speed dividers written to `(+0x10, +0x14)` are `(0x35, 0x35)` for modes `0`/`0x11` and `(0x09, 0x07)` for modes `1`/`0x10`.
- **IRQ, NACK retry & mode-gated `CLK4` reset:** `i2c_handler` checks/acks `+0x28` bit 0 and schedules `i2c_tasklet`, which W1C-clears `+0x00` bit `0x20` on NACK and re-issues `+0x04` up to 3 retries. Reset `.text+0x119c` checks `+0x38 == 3`, writes `+0x34 = 0` and `+0x20 = 1`, and then inspects `algo + 0x8c` (NOT `ch` at `algo + 0x88`): when `algo + 0x8c == 0` (initial or after `i2c_xfer` modes `0x10`/`0x11`), it writes `(0xf2a30048, 2)`, `(0xf2a300b8, 8)`, `(0xf2a30044, 2)`, `(0xf2a300b4, 8)` regardless of channel; modes `0`/`1` set `algo + 0x8c = 1` and skip `CLK4` writes.
