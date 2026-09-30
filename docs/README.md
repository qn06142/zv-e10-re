# Documentation

Reverse engineering of the Sony ZV-E10, firmware 2.02/2.03.

Two kinds of document live here, and they are kept separate on purpose.

| | for | when |
|---|---|---|
| `01`–`08` + this file | humans | working a subject in depth; every table, every derivation |
| [`agents/`](agents/) | an agent picking the thread back up | you need the whole state on one page and must not have to open eight files |

`90-session/` is a **quarantine**: dated session logs kept for provenance. Nothing
there is cited as fact — it exists so that a retracted claim is not silently
re-derived, and so that the reasoning behind a number can be traced. Durable facts
were extracted from it into the topic docs.

Start here:

- **Cold, and you want the state of play** → [`agents/STATE.md`](agents/STATE.md)
- **Cold, and you want the facts** → [`agents/REFERENCE.md`](agents/REFERENCE.md)
- **Working on one subject** → the table below
- **Coding** → [`research/README.md`](../research/README.md)

## The topic docs

| | doc | what it settles |
|---|---|---|
| 01 | [hardware.md](01-hardware.md) | SoC, the two operating systems, firmware images, how to dump one, Windows gotchas |
| 02 | [service-shell.md](02-service-shell.md) | everything reachable from the root shell: mounts, persistence, boot chain, `im.elf`, code execution |
| 03 | [binaries.md](03-binaries.md) | the ELF inventory, the plugin architecture, the `av-cam.bin` RTOS command engine, VDF display |
| 04 | [messaging.md](04-messaging.md) | the bus, the id spaces, `libSysDef.so` tables, the MWF and scenario vocabularies, the APICD registry |
| 05 | [formats.md](05-formats.md) | the `.uxc` container, view files, `global.xdb`, the string table, the colour palette |
| 06 | [method.md](06-method.md) | the nine decoding traps, and why they all fail silently |
| 07 | [modification.md](07-modification.md) | what is writable, the applied and verified changes, the updater door, the file transport |
| 08 | [camera-interfaces.md](08-camera-interfaces.md) | USB modes, the shell bridge, the raw tunnel, the lens protocol, `sndcmd`/`rcvcmd` |

## Conventions used throughout

- **Verified** means checked against a positive control, not merely not-contradicted.
- **Negative results** get their own section. A refuted claim with its null model
  is worth more than a confirmed one without, because it stops the same work being
  redone.
- Everything is labelled as **measured**, **inferred** or **hypothesised**. A
  hypothesis that was never tested says so where it is stated.
- Side effects that were not quantified say so, rather than being omitted.
- Scripts are named by path from the repo root and run as
  `& ".venv\Scripts\python.exe" -B research\firmware\<name>.py`.
  Pass `-B`: stale bytecode bit us once.

## Checking the docs

```powershell
& ".venv\Scripts\python.exe" -B research\firmware\check_docs.py
```

Reports the md5 set fingerprint, the file count and any broken markdown links.
Run it after editing anything here.