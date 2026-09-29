"""Regenerate the layout table and the index in research/README.md.

The counts and file lists in that README were written by hand and drifted as
scripts were added.  This rewrites both from what is actually on disk, so
they cannot drift again without someone choosing to.

Everything outside the two generated regions is preserved verbatim: the prose,
the firmware-location table, and the "Running a script" section.
"""
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
RESEARCH = REPO / "research"
README = RESEARCH / "README.md"

PURPOSE = {
    "common": "Helpers shared across topics. `senser_fix` and `zve10_dumpall` are "
              "imported from `device/`, `diag/` and `isp/` alike, so they cannot "
              "live in any one of those. Each importer puts this directory *and* "
              "the repository root (for the `pmca` package) on `sys.path`.",
    "device": "Talking to the camera over USB: PTP/MTP, mass storage, "
              "enumeration, card and firmware pulling. The only group that needs "
              "a physical ZV-E10 attached.",
    "firmware": "Firmware image structure: format analysis, carving, "
                "decompression, decryption, payload extraction.",
    "disasm": "Per-subsystem disassembly. Superseded for `av-cam.bin` by the "
              "`retool` package, kept for the other images.",
    "scan": "Byte/string sweeps over firmware images looking for structure.",
    "diag": "Diagnostics: offset, padding and size checks on carved regions.",
    "crypt": "Brute-force and cryptanalysis of the update/crypter paths.",
    "lens": "Lens protocol: query, trigger and lensfile handling.",
    "updater": "The firmware update command surface.",
    "isp": "ISP / sensor command work.",
}


def tracked(rel):
    """Tracked .py files under a directory, sorted by name."""
    out = subprocess.run(["git", "ls-files", "--", str(rel.relative_to(REPO))],
                         cwd=REPO, capture_output=True, text=True, check=True)
    names = [p.name for p in rel.glob("*.py") if p.is_file()]
    for line in out.stdout.splitlines():
        p = pathlib.Path(line)
        if p.suffix == ".py" and p.parent == rel:
            names.append(p.name)
    return sorted(set(names))


def dirs():
    return sorted([d for d in RESEARCH.iterdir() if d.is_dir()],
                  key=lambda d: (-len(tracked(d)), d.name))


def layout_table(ds):
    rows = ["| Directory | Files | Purpose |", "|---|---:|---|"]
    for d in ds:
        n = len(tracked(d))
        rows.append("| `research/%s/` | %d | %s |"
                    % (d.name, n, PURPOSE.get(d.name, "")))
    return "\n".join(rows)


def index(ds):
    out = []
    for d in ds:
        names = tracked(d)
        if not names:
            continue
        out.append("<details><summary><code>research/%s/</code> — %d files</summary>\n"
                   % (d.name, len(names)))
        out.append("")
        for n in names:
            out.append("- `%s`" % n)
        out.append("")
        out.append("</details>")
        out.append("")
    return "\n".join(out)


def main():
    text = README.read_text(encoding="utf-8")
    ds = dirs()

    # replace the layout table: from the header row to the blank line before
    # the next heading
    new_table = layout_table(ds)
    text, n = re.subn(r"\| Directory \| Files \| Purpose \|.*?\n\n",
                      new_table + "\n\n", text, count=1, flags=re.S)
    if not n:
        print("could not find the layout table")
        return 1

    # replace the index: everything from the first <details> to the end
    i = text.find("<details>")
    if i < 0:
        print("could not find the index")
        return 1
    text = text[:i] + index(ds)

    README.write_text(text, encoding="utf-8", newline="\n")
    print("rewrote %s: %d directories, %d scripts"
          % (README.relative_to(REPO), len(ds),
             sum(len(tracked(d)) for d in ds)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
