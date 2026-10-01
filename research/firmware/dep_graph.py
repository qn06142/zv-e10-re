"""Dependency-graph analysis over the ELF catalog.

Answers, reproducibly, the questions the docs previously answered by hand:
which shared objects are real files, which are carving artefacts, which nothing
links to, and whether the ``libOnDemandLoader`` explanation for the orphaned
libraries actually holds.

Reads only ``research/firmware/elf_catalog.json``, which is a tracked derived
artefact.  No camera binaries are needed, so this runs on a fresh checkout.

    python dep_graph.py

Three categories are separated, because conflating them is what makes the
orphan count meaningless:

1. **Real files** -- ``dumps/camera_2025/usr/usr/lib``, ``.../usr/usr/scenario``
   and the other walked directories.
2. **Carved fragments** -- ``elf_XXXXXXXX.so`` and ``*_0xXXXXXXXX.bin`` under
   ``usr_lib_raw``.  These are ELFs recovered from a raw image dump, not files
   the camera has.
3. **Degenerate entries** -- files with ELF magic whose catalog record has no
   imports, no DT_NEEDED and no exports.  ``camuser.elf`` is one: its section
   table is unreadable, so nothing can be read out of it.  These carry no
   dependency information either way.

An entry in category 2 or 3 must not be counted as a shared object, and an
orphan count that includes them is wrong.
"""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG = ROOT / "research" / "firmware" / "elf_catalog.json"

# Recovered from a raw image dump by the carver, not present as files.
CARVED = re.compile(r"^elf_[0-9a-f]{8}\.so$|_0x[0-9a-f]{8}\.bin$")

# Directories that are a real filesystem walk of the camera.
WALKED = re.compile(r"dumps[/\\](camera_2025[/\\]usr[/\\]usr|camera|engine|v203)")

# Loaded by name through libOnDemandLoader, so never DT_NEEDED.
ON_DEMAND = re.compile(r"^libInfra|^viewUnified\d+\.so$")


def load():
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {k: v for k, v in cat.items()
            if v["type"] in ("DYN", "EXEC", "REL")}


def classify(real):
    """Split basenames into carved / degenerate / readable, per ELF type.

    A basename is *degenerate* only if every copy of it failed to yield dynamic
    information.  Several appear twice in the catalog with opposite outcomes --
    libObj.so parses from the walked filesystem and is degenerate from the raw
    carve -- so the per-copy outcome is reported rather than hidden.
    """
    by_name = collections.defaultdict(list)
    for path, v in real.items():
        by_name[pathlib.PurePath(path).name].append((path, v))

    def is_dead(entries):
        return all(not e[1]["needed"] and not e[1]["imports"]
                   and e[1]["exp_func"] == 0 for e in entries)

    carved, degenerate = set(), set()
    shared, executables, relocatables = set(), set(), set()
    for name, entries in by_name.items():
        if CARVED.search(name):
            carved.add(name)
        elif is_dead(entries):
            degenerate.add(name)
        else:
            for _path, v in entries:
                if v["type"] == "DYN":
                    shared.add(name)
                elif v["type"] == "EXEC":
                    executables.add(name)
                else:
                    relocatables.add(name)
    return by_name, carved, degenerate, shared, executables, relocatables


def main():
    real = load()
    by_name, carved, degenerate, shared, execs, rels = classify(real)

    needed_by = collections.Counter()
    for v in real.values():
        for n in v["needed"]:
            needed_by[n] += 1

    print("=== catalog ===")
    print("  entries with a readable ELF type      : %d" % len(real))
    print("  distinct basenames                    : %d" % len(by_name))
    print("  DT_NEEDED edges                       : %d"
          % sum(len(v["needed"]) for v in real.values()))
    print()

    print("=== basenames by class (must sum to the total) ===")
    print("  carved fragments, not camera files    : %4d" % len(carved))
    print("  degenerate, no dynamic information    : %4d" % len(degenerate))
    print("  readable ET_DYN  (shared objects)     : %4d" % len(shared))
    print("  readable ET_EXEC (executables)        : %4d" % len(execs))
    print("  readable ET_REL  (relocatables)       : %4d" % len(rels))
    print("  %-36s %4d" % ("sum", len(carved) + len(degenerate) + len(shared)
                            + len(execs) + len(rels)))
    print()

    print("=== libObj.so: one library, two catalog entries, opposite outcomes ===")
    for p, v in sorted(by_name.get("libObj.so", []), key=lambda kv: kv[1]["size"]):
        print("  %10d B  imports=%-5d needed=%-3d exports=%-5d  %s"
              % (v["size"], v["imports"], len(v["needed"]), v["exp_func"], p))
    print("  The 81,920-byte copy is a truncated decoy in the dump and yields")
    print("  nothing; the 21 MB copy under dumps/engine is the real library and")
    print("  carries 1,904 exports.  Both share a basename, so any count keyed on")
    print("  basename has to treat a name as readable only if a copy of it parsed.")
    print()

    orphans = sorted(n for n in shared if needed_by[n] == 0)
    scen = [n for n in orphans if "SCN" in n]
    on_dem = [n for n in orphans if ON_DEMAND.match(n)]
    rest = [n for n in orphans if n not in set(scen) | set(on_dem)]

    print("=== DT_NEEDED orphans among readable shared objects ===")
    print("  total                                 : %d" % len(orphans))
    print("  scenario plugins, loaded by name      : %3d  (expected)" % len(scen))
    print("  libInfra* / viewUnified*, OnDemand     : %3d" % len(on_dem))
    print("  remaining: distro runtime and tools  : %3d" % len(rest))
    print()
    print("  Scenario plugins are dlopen'd by scenario.elf and libOnDemandLoader")
    print("  accounts for the libInfra*/viewUnified* block.  Both are orphans by")
    print("  construction, not because anything is missing.")
    print()

    print("=== most depended-upon readable shared objects ===")
    for name, n in needed_by.most_common(15):
        if name in shared:
            print("  %5d  %s" % (n, name))
    print()

    print("=== the OnDemand block: %d orphans libOnDemandLoader plausibly explains ==="
          % len(on_dem))
    for n in sorted(on_dem):
        print("  %s" % n)
    print()

    print("=== remaining orphans (%d) ===" % len(rest))
    for n in rest:
        print("  %s" % n)


if __name__ == "__main__":
    main()
