"""Replace the hardcoded absolute JSON_PATH / open() paths in the older
research/device scripts with paths derived from the script location.

Those scripts were written on a machine whose home was C:/Users/Minhsnguhoa
and hardcoded it, so they cannot run anywhere else -- including here.  The
newer scripts in this tree already do the right thing
(`Path(__file__).resolve().parents[N]`); this brings the older ones in line.

Idempotent: re-running finds nothing to do.
"""
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
OLD = "C:/Users/Minhsnguhoa/pmca-re/"

IMPORT = "import pathlib\nREPO = pathlib.Path(__file__).resolve().parents[2]\n"


def fix(path):
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if OLD not in text:
        return None

    original = text
    names = set(re.findall(r"'" + re.escape(OLD) + r"([^']+)'", text))
    for name in sorted(names):
        # REPO is a Path, so join with "/" rather than os.path
        text = text.replace("'" + OLD + name + "'",
                            "(REPO / '%s').as_posix()" % name)

    if "REPO = pathlib" not in text:
        # insert after the last top-level import line of the header block
        lines = text.splitlines(keepends=True)
        idx = 0
        for i, line in enumerate(lines[:60]):
            if re.match(r"^(import |from )", line):
                idx = i + 1
        lines.insert(idx, "\n" + IMPORT)
        text = "".join(lines)

    if text == original:
        return None
    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    return sorted(names)


def main():
    targets = sorted((REPO / "research" / "device").glob("*.py"))
    changed = 0
    for p in targets:
        names = fix(p)
        if names:
            changed += 1
            print("  %-28s %s" % (p.name, ", ".join(names)))
    print("%d file(s) changed" % changed)
    # prove it: nothing may still reference the old home
    left = []
    for p in list(targets) + sorted((REPO / "research").rglob("*.py")):
        try:
            if OLD in p.read_text(encoding="utf-8", errors="surrogateescape"):
                left.append(p.name)
        except OSError:
            pass
    if left:
        print("STILL REFERENCING OLD PATH:", ", ".join(sorted(set(left))))
        return 1
    print("no references to %s remain" % OLD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
