"""The verified replacement targets, and the corrections that produced them.

Every codepoint here was confirmed by rendering it large and reading it.  That
matters more than usual in this file, because the first attempt at this list was
built by transcribing labels off 92-pixel contact sheets and three of its
thirty-four entries were wrong:

    claimed U+E506 = STD     actually U+E505 = STD
    claimed U+E528 = 60      actually U+E52B = 60
    claimed U+E558 = 2160/30p  actually 2160/30p is U+E55B, and U+E558 is a
                           pictogram of a landscape with arrows
    claimed U+E2D1 = waving hand  actually a person holding a camera

Separately, U+E03D is HOLD, not U+E02D, which was misread as 3D-as-2D earlier
and put a hand-and-warning pictogram into a list of text labels.

The families were therefore re-derived by shape rather than by reading, which is
also how they were completed.  The bar family is found by looking for two
full-width rules with a figure between them, matched against each other in
length rather than against the glyph, so the wide labels such as HD XP are
included; that test took the family from 19 to 28, of which 27 are real and
U+E609 is a metering pictogram of a person beside three rules.  The recording
formats are found by looking for a slash component and then split by advance
width, which separates them from the 1/xND shutter family that otherwise
matches the same test.

Nothing here is a guess and nothing is left unread.
"""

# --- 1. bars above and below: image size, quality, frame rate, ISO ----------
# found by icon_bars.py, read at 260 px
BARS = {
    0xE03E: 'SP',
    0xE03F: 'HQ',
    0xE040: 'LP',
    0xE041: '16:9',
    0xE095: '4:3',
    0xE0DC: 'HD SP',
    0xE0DD: 'HD LP',
    0xE0DE: 'HD HQ',
    0xE0DF: 'HD HQ+',
    0xE101: 'XP',
    0xE102: 'HD XP',
    0xE103: 'HQ+',
    0xE146: 'FX',
    0xE147: 'FH',
    0xE148: 'FS',
    0xE247: 'STD HQ',
    0xE248: 'STD SP',
    0xE249: 'STD LP',
    0xE326: 'PS',
    0xE505: 'STD',
    0xE52B: '60',
    0xE52C: '50',
    0xE539: '35',
    0xE53A: '25',
    0xE540: '100',
    0xE5B3: '16',
    0xE5EC: '30',
}

# rejected: U+E609 is a person beside three rules, a metering pictogram that the
# bar test matches on shape alone.  Recorded so it is not "fixed" later.

# --- 2. recording formats: the line rates the camera offers ----------------
# found by icon_res_sheet.py, split by advance width, read at 300 px
FORMATS = {
    0xE1F8: '1080/60i',
    0xE1F9: '1080/30p',
    0xE1FA: '1080/24p',
    0xE1FB: '720/60p',
    0xE1FC: '480/60i',
    0xE1FD: '480/30p SCAN',
    0xE1FE: '480/24p SCAN',
    0xE1FF: '1080/50i',
    0xE200: '1080/25p',
    0xE201: '720/50p',
    0xE202: '576/50i',
    0xE203: '576/25p SCAN',
    0xE3E8: '1080/60p',
    0xE3E9: '1080/50p',
    0xE55B: '2160/30p',
    0xE55C: '2160/25p',
    0xE55D: '2160/24p',
}

# --- 3. codec --------------------------------------------------------------
CODEC = {
    0xE536: 'AVCHD',
    0xE537: 'XAVC',
    0xE538: 'XAVC S',
}

# --- 4. steadyshot ---------------------------------------------------------
# the user identified this by the waving-hand pictogram that accompanies it; the
# pictogram itself is U+E2D1, which is a person holding a camera, and is not a
# target
STEADYSHOT = {
    0xE21C: 'STEADYSHOT',
}

TARGETS = {}
TARGETS.update(BARS)
TARGETS.update(FORMATS)
TARGETS.update(CODEC)
TARGETS.update(STEADYSHOT)


def summary():
    lines = ['%d verified targets' % len(TARGETS), '']
    for name, fam in (('bars', BARS), ('formats', FORMATS),
                      ('codec', CODEC), ('steadyshot', STEADYSHOT)):
        lines.append('%-12s %d' % (name, len(fam)))
        for cp in sorted(fam):
            lines.append('    U+%04X  %s' % (cp, fam[cp]))
        lines.append('')
    return '\n'.join(lines)


if __name__ == '__main__':
    print(summary())
