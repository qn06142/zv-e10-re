"""Verify a docs restructure preserves every fact, and that its links resolve.

A documentation move is only safe if the content actually arrives, and only
usable if its links work.  Both fail silently, so both are checked here:

  1. every md5 that appeared in any pre-restructure doc still appears in the
     post-restructure tree
  2. every ``[text](file.md)`` link target still resolves
  3. every ``[text](#anchor)`` matches a heading's GitHub slug in that file

Scans ``docs/`` **and the top-level markdown at the repository root**
(``README.md``, ``CREDITS.md``), because a broken link in the README is the first
thing a visitor hits and the least likely to be noticed.

Run before and after a restructure and diff the two reports.  The md5-set
fingerprint is the number to compare; it is order-independent by construction.
"""
import hashlib
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

# The repository root, not just docs/: README.md and CREDITS.md live there and
# are the first thing anyone reads.
ROOT_MD = [ROOT / "README.md", ROOT / "CREDITS.md"]

MD5 = re.compile(r"\b[0-9a-f]{32}\b")
LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")

# GitHub keeps word characters, spaces, hyphens and underscores; everything
# else is dropped before spaces become hyphens.  Note that a dropped character
# sitting between two spaces therefore leaves a DOUBLE hyphen, which is a real
# and easily-missed detail.
_KEEP = re.compile(r"[^0-9A-Za-z _-]")


def slug(text):
    """Reproduce GitHub's heading-anchor slug for one heading."""
    text = text.strip()
    # inline code, emphasis and links are stripped before slugging
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = unicodedata.normalize("NFKD", text)
    text = _KEEP.sub("", text)
    return "#" + text.strip().lower().replace(" ", "-")


def targets():
    """Every markdown file whose links are worth checking."""
    out = sorted(DOCS.rglob("*.md"))
    for p in ROOT_MD:
        if p.exists() and p not in out:
            out.append(p)
    return out


def scan():
    md5s = set()
    links = []
    n_anchor = 0
    for p in targets():
        text = p.read_text(encoding="utf-8", errors="replace")
        md5s |= set(MD5.findall(text))

        anchors = set()
        for line in text.splitlines():
            m = HEADING.match(line)
            if m:
                anchors.add(slug(m.group(2)))

        for m in LINK.finditer(text):
            links.append((str(p.relative_to(ROOT)), m.group(1), m.group(2),
                          anchors))
            if m.group(2).startswith("#"):
                n_anchor += 1
    return md5s, links, n_anchor


def main():
    md5s, links, n_anchor = scan()
    print("markdown scanned: %d files (docs/ plus repo root)" % len(targets()))
    print("distinct md5 values: %d" % len(md5s))
    print()

    broken, bad_anchors = [], []
    for src, label, tgt, anchors in links:
        if tgt.startswith(("http://", "https://", "file:///")):
            continue
        if tgt.startswith("#"):
            if tgt not in anchors:
                bad_anchors.append((src, label, tgt))
            continue
        # resolve relative to the linking file's directory
        cand = (ROOT / src).parent / tgt
        if not cand.exists():
            cand = DOCS / tgt          # tolerate root-relative
        if not cand.exists():
            broken.append((src, tgt))

    n_file = sum(1 for l in links if not l[2].startswith(("http", "file:")))
    print("file links: %d, broken targets: %d" % (n_file, len(broken)))
    for src, tgt in broken:
        print("  BROKEN   %s -> %s" % (src, tgt))

    print("in-page anchors: %d, unmatched: %d" % (n_anchor, len(bad_anchors)))
    for src, label, tgt in bad_anchors:
        print("  NO ANCHOR %s  [%s](%s)" % (src, label, tgt))
    print()

    digest = hashlib.md5("\n".join(sorted(md5s)).encode()).hexdigest()
    print("md5-set fingerprint: %s" % digest)
    return 0 if not broken and not bad_anchors else 1


if __name__ == "__main__":
    sys.exit(main())
