"""Rewrite hardcoded repo paths into a location-independent bootstrap.

WHAT THIS ACTUALLY COVERS -- read this before trusting the docstring's older,
looser claim that "the tree" is path-independent.

The tree was written on a machine whose home was ``C:/Users/Minhsnguhoa`` and
many scripts hardcoded it, so they could not run anywhere else.  Those literals
resolve against the repo root via
``ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]``, which is what
``elf_catalog.py`` and ``icon_opx.py`` already did.

That is the *only* class of literal this tool matches.  It does **not** touch:

* ``D:\\02_Development_And_Projects\\pmca-re`` -- the current machine's repo root
* the harness temp directory (``%TEMP%\\opencode``)

Those two are still hardcoded in 152 of the 317 scripts in ``research/``.  The
portable set is 82, and it contains every tool cited in ``docs/``, so the
documentation works on a fresh checkout; the rest are one-shot exploration
scripts kept as a working record.  Extending ``OLD_FORWARD``/``OLD_BACK`` below
to cover the two paths above is the obvious next step if the whole tree needs to
be portable -- but do that deliberately and in small batches, because a bulk
rewrite of scripts nobody has run recently is how a working record quietly
becomes a broken one.

Both spellings occur in the wild: ``"C:/Users/.../pmca-re/out"`` and the raw
form ``r"C:\\Users\\...\\pmca-re\\out"``, and some scripts store the bare repo
root with no trailing component.

Two details this has to get right, both of which fail silently otherwise:

* A literal must be replaced by a bare *expression*, so the surrounding quotes
  and any ``r`` prefix are consumed and not re-emitted.  Otherwise the result
  is ``r"(ROOT_REPO / 'out').as_posix()"`` -- a string literal containing
  source text, which compiles but silently produces garbage.
* The bootstrap is called ``ROOT_REPO``, not ``REPO``.  Several scripts already
  have a variable named ``REPO`` meaning something else (a vendored tool path,
  typically), and a second assignment would overwrite it.

``_selftest()`` pins the first one down and compile-checks every result, so that
failure mode cannot come back unnoticed.

Idempotent, and skips itself: it holds the old home as data.
"""
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]

# Assembled from fragments so this file does not match its own patterns.
_OLD_USER = "Minh" + "snguhoa"
OLD_FORWARD = "C:/Users/%s/pmca-re/" % _OLD_USER
OLD_BACK = "C:\\Users\\" + _OLD_USER + "\\pmca-re"
USER = _OLD_USER

IMPORT = ("import pathlib\n"
          "ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]\n")

BACK_RE = re.compile(
    r'(?P<r>[rR])?(?P<q>["\'])' + re.escape(OLD_BACK)
    + r'(?:\\(?P<n>[^' + r"'\"]*" + r'))?(?P=q)')


def sub_back(m):
    """Replace a hardcoded backslash literal with a bare expression."""
    name = m.group("n")
    if not name:
        return "ROOT_REPO.as_posix()"         # the bare repo root
    return "(ROOT_REPO / %r).as_posix()" % name.replace("\\", "/")


def sub_forward(m):
    """Replace a hardcoded forward-slash literal with a bare expression."""
    return "(ROOT_REPO / '%s').as_posix()" % m.group(1).replace("\\", "/")


def ensure_repo(text):
    """Insert the pathlib/ROOT_REPO bootstrap if it is not already present."""
    if "ROOT_REPO = pathlib" in text:
        return text
    lines = text.splitlines(keepends=True)
    # Insert after the last top-of-file import, so the name is defined before
    # any line that uses it.
    idx = 0
    for i, line in enumerate(lines[:60]):
        if re.match(r"^(import |from )", line):
            idx = i + 1
    lines.insert(idx, "\n" + IMPORT)
    return "".join(lines)


def _selftest():
    """Every literal shape handled here, and the code it must become."""
    cases = [
        ('ROOT = r"C:\\Users\\%s\\pmca-re"' % USER,
         'ROOT = ROOT_REPO.as_posix()'),
        ('ROOT = r"C:\\Users\\%s\\pmca-re\\fw"' % USER,
         "ROOT = (ROOT_REPO / 'fw').as_posix()"),
        ('X = r"C:\\Users\\%s\\pmca-re\\a\\b.py"' % USER,
         "X = (ROOT_REPO / 'a/b.py').as_posix()"),
        ('Y = "C:\\Users\\%s\\pmca-re\\tools"' % USER,
         "Y = (ROOT_REPO / 'tools').as_posix()"),
        ("Z = 'C:/Users/%s/pmca-re/out'" % USER,
         "Z = (ROOT_REPO / 'out').as_posix()"),
    ]
    fwd = re.compile(r"'" + re.escape(OLD_FORWARD) + r"([^']+)'")
    bad = 0
    for src, want in cases:
        got = fwd.sub(sub_forward, src) if "C:/Users" in src \
            else BACK_RE.sub(sub_back, src)
        ok = got == want
        bad += not ok
        print("  %s %s" % ("ok  " if ok else "FAIL", got))
        if not ok:
            print("       expected: %s" % want)
        # the rewritten line must be valid python on its own
        try:
            compile(got, "<t>", "exec")
        except SyntaxError as e:
            print("       SYNTAX ERROR: %s" % e)
            bad += 1
    return bad


def fix(path):
    """Rewrite one file.  Returns the names touched, or None if unchanged."""
    if path.resolve() == pathlib.Path(__file__).resolve():
        return None                          # never rewrite this file
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if USER not in text:
        return None
    original = text
    touched = set()

    for m in re.finditer(r"'" + re.escape(OLD_FORWARD) + r"([^']+)'", text):
        touched.add(m.group(1))
    text = re.sub(r"'" + re.escape(OLD_FORWARD) + r"([^']+)'",
                  sub_forward, text)

    for m in BACK_RE.finditer(text):
        touched.add(m.group("n") or "<root>")
    text = BACK_RE.sub(sub_back, text)

    if text == original:
        return None
    path.write_text(ensure_repo(text), encoding="utf-8", errors="surrogateescape")
    return sorted(touched)


def main():
    print("self-test:")
    if _selftest():
        print("self-test FAILED -- not touching anything")
        return 2
    print()

    targets = []
    for sub in ("research", "avcam_re", "scripts", "verify"):
        d = REPO / sub
        if d.is_dir():
            targets += sorted(d.rglob("*.py"))

    changed = 0
    for p in targets:
        names = fix(p)
        if names:
            changed += 1
            print("  %-36s %s" % (str(p.relative_to(REPO)), ", ".join(names)))
    print("%d file(s) changed" % changed)

    left = []
    for p in targets:
        try:
            if USER in p.read_text(encoding="utf-8", errors="surrogateescape"):
                left.append(str(p.relative_to(REPO)))
        except OSError:
            pass
    if left:
        print("STILL REFERENCING THE OLD HOME (%d):" % len(left))
        for name in left:
            print("   ", name)
        return 1
    print("no references to %s remain" % USER)

    # every rewritten file must still compile
    broken = []
    for p in targets:
        try:
            compile(p.read_text(encoding="utf-8", errors="surrogateescape"),
                    str(p), "exec")
        except SyntaxError as e:
            broken.append("%s: %s" % (p.relative_to(REPO), e))
    if broken:
        print("DOES NOT COMPILE (%d):" % len(broken))
        for b in broken:
            print("   ", b)
        return 1
    print("all %d scripts compile" % len(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
