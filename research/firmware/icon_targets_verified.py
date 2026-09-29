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

# ---------------------------------------------------------------------------
# The photography set, added after the 48 above were verified and patched.
#
# Found by icon_survey.py, which renders the 171 remaining text-label candidates
# at 200 px with 20 px codepoint labels, 60 to a page.  Reading a six-digit hex
# label off a 92 px thumbnail is what produced three wrong codepoints the first
# time round, so the survey is deliberately dull: large cells, large labels, and
# every candidate looked at rather than a sample.
#
# Because every character of a label is replaced by the OPX cycle, a label's
# *spelling* does not affect the result -- only its character count does, since
# that sets how many cells the text is divided into.  So a doubtful reading costs
# nothing but a comment, which is what makes widening the set this far safe.  The
# codepoints still have to be right, and they were read at 200 px.
#
# Excluded on purpose: transport icons, pictograms, the audio labels (48k, LPCM,
# AAC LC, 16b, TG) and the Japanese-only text, since none of them are
# photography and letters in place of a speaker or a play triangle would simply
# look broken.
# ---------------------------------------------------------------------------

# neutral density filter, the exposure accessory.  Two size variants exist --
# 1/4ND, 1/16ND and 1/64ND each appear twice, at U+E4C3.. and again at U+E582..
# -- so both are targeted, or the camera would keep whichever it happens to use.
ND_FILTER = {
    0xE4C3: '1/4ND',
    0xE4C4: '1/16ND',
    0xE4C5: '1/64ND',
    0xE56A: '1/5ND',
    0xE56B: '1/6ND',
    0xE56C: '1/7ND',
    0xE56D: '1/8ND',
    0xE56E: '1/10ND',
    0xE56F: '1/11ND',
    0xE570: '1/13ND',
    0xE571: '1/19ND',
    0xE572: '1/23ND',
    0xE573: '1/27ND',
    0xE574: '1/32ND',
    0xE575: '1/38ND',
    0xE576: '1/45ND',
    0xE577: '1/54ND',
    0xE578: '1/76ND',
    0xE579: '1/91ND',
    0xE57A: '1/108ND',
    0xE57B: '1/128ND',
    0xE582: '1/4ND',
    0xE583: '1/16ND',
    0xE584: '1/64ND',
    0xE194: 'ND',
    0xE5DC: 'ND',
    0xE190: 'ND OFF',
    0xE191: 'ND1',
    0xE192: 'ND2',
    0xE193: 'ND3',
    0xE5DD: 'ECS',
    0xE5DE: 'dB',
}

# sensitivity
SENSITIVITY = {
    0xE488: 'ISO',
    0xE5DF: 'ISO',
    0xE666: 'ISO',
    0xE4A6: 'AGC',
}

# image size and quality
IMAGE_SIZE = {
    0xE03D: 'HOLD',
    0xE053: 'BRK',
    0xE054: 'STD',
    0xE055: 'FINE',
    0xE411: '16M',
    0xE412: '10M',
    0xE413: '5M',
    0xE414: 'VGA',
    0xE415: '12M',
    0xE416: '2M',
    0xE45C: '3M',
    0xE47C: '8M',
    0xE49A: '18M',
    0xE49B: '13M',
}

IMAGE_FORMAT = {
    0xE48E: 'RAW',
    0xE48F: 'RAW+J',
    0xE64B: 'RAW/JPEG',
    0xE64C: 'JPEG/RAW',
    0xE65C: 'RAW',
    0xE5FA: 'Px 4K',
    0xE5FC: 'Px HD',
    0xE5AC: 'HLG',
    0xE58A: 'HD422',
    0xE58B: 'HD420',
    0xE58E: '(1440)',
    0xE5CA: 'APS-C S35',
    0xE5B0: '1080/120p',
    0xE5B1: '1080/100p',
}

# white balance and the picture profile / creative look names
COLOUR = {
    0xE2A9: 'AWB',
    0xE3F3: 'AWB',
    0xE66E: 'CLASSIC',
    0xE66F: 'CLEAN',
    0xE670: 'CHIG',
    0xE671: 'FRESH',
    0xE672: 'MONO',
    0xE673: 'AUTO',
    0xE674: 'GOLD',
    0xE675: 'OCEAN',
    0xE676: 'FOREST',
    0xE61A: 'CINEMA',
}

# focus, stabilisation, framing
FOCUS = {
    0xE5AF: 'AF',
    0xE590: 'FOCUS',
    0xE58F: 'ZOOM',
    0xE5D8: 'min',
    0xE59C: 'DISP',
    0xE4DA: '360',
}

# playback and shooting assists
ASSISTS = {
    0xE2B8: 'DPOF',
    0xE3F4: 'DPOF',
    0xE2F4: 'NR',
    0xE1EB: 'PEAKING',
    0xE37E: 'PEAK R',
    0xE37F: 'PEAK W',
    0xE380: 'PEAK Y',
    0xE1F6: 'TC IN',
}

PHOTO = {}
for _fam in (ND_FILTER, SENSITIVITY, IMAGE_SIZE, IMAGE_FORMAT, COLOUR,
             FOCUS, ASSISTS):
    PHOTO.update(_fam)

TARGETS.update(PHOTO)


def summary():
    lines = ['%d verified targets' % len(TARGETS), '']
    fams = [('bars', BARS), ('formats', FORMATS), ('codec', CODEC),
            ('steadyshot', STEADYSHOT), ('nd filter', ND_FILTER),
            ('sensitivity', SENSITIVITY), ('image size', IMAGE_SIZE),
            ('image format', IMAGE_FORMAT), ('colour', COLOUR),
            ('focus', FOCUS), ('assists', ASSISTS)]
    for name, fam in fams:
        lines.append('%-14s %d' % (name, len(fam)))
        for cp in sorted(fam):
            lines.append('    U+%04X  %s' % (cp, fam[cp]))
        lines.append('')
    return '\n'.join(lines)


if __name__ == '__main__':
    print(summary())
