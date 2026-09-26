"""Classify every function by the subsystem its strings identify.

The question this answers is "which code is decode and which is encode", which
cannot be settled by reading 66,805 functions.  It can be settled by evidence:
each function references literal strings, and those strings say what the code
is.  So: resolve every PC-relative reference, read the string at its target,
and label the referencing function from that vocabulary.

Attribution uses the nearest preceding *trusted* function start, because
rizin emits 2,246 bogus functions larger than 64 KB (one spans 7.6 MB) that
would otherwise smear attribution across the whole image.  Coverage is
reported so the result can be judged.

Keywords are listed explicitly and every hit is reported, so a classification
can be audited rather than trusted.
"""
from __future__ import annotations

import re
from bisect import bisect_right

from . import xrefs

# Trusted function size cap; anything larger is a rizin false positive.
MAX_TRUSTED_SIZE = 0x10000

# Subsystem keyword sets.  Case-sensitive unless noted.  Order matters only for
# reporting; a function is labelled by its strongest evidence.
KEYWORDS: dict[str, list[str]] = {
    "DECODE": [
        r"\bDEC_", r"\bdec_\w*decode", r"decode", r"DECODE", r"sfmc_dec",
        r"VIDEO_DEC", r"dec_timing", r"deblock", r"DEBLOCK", r"deblocking",
        r"slc_header", r"slice", r"ref_pic", r"idr", r"\bDPB\b", r"decout",
        r"dec_cmd", r"dec_command", r"decord", r"wait_dec", r"start_dec",
        r"stop_dec", r"decord_pic", r"refidx", r"\bMV\b", r"hevc_dec",
        r"avc_dec", r"dec_init", r"dec_open", r"dec_close",
    ],
    "ENCODE": [
        r"\bENC_", r"encode", r"ENCODE", r"ZIMA", r"DVENC", r"AVC_ENC",
        r"HEVC_ENC", r"h264", r"H264", r"hevc", r"HEVC", r"mpeg",
        r"bitrate", r"BITRATE", r"\bGOP\b", r"gop_", r"rc_", r"rate_ctrl",
        r"enc_cmd", r"enc_init", r"enc_start", r"enc_stop", r"encparam",
        r"qp", r"\bVBR\b", r"\bCBR\b", r"param_bitrate", r"enc_body",
    ],
    "PLAYBACK": [
        r"play_back", r"PLAYBACK", r"playback", r"SLIDESHOW", r"STREAMING",
        r"preview", r"PREVIEW", r"thumbnail", r"STILL", r"still_",
        r"movie_play", r"pb_cmd", r"\bDSTILL", r"continuous", r"burst",
    ],
    "RECORD_MODE": [
        r"SAKUHINKA", r"GEARED_ENC", r"HILGT", r"PROXY", r"BGMCHK",
        r"NAMESURO", r"recmode", r"REC_MODE", r"rec_mode",
    ],
    "MEMORY_DMM": [
        r"\bDMM\b", r"dmm_", r"ERR_DMM", r"osal", r"OSAL", r"valloc",
        r"PowerOnUnit", r"UnitMaxMem", r"ERR_OSAL", r"msgq", r"MSGQ",
        r"\bUIPC\b", r"uipc", r"heap", r"HEAP", r"malloc", r"free\(",
    ],
    "ISP_IMAGE": [
        r"\bISP\b", r"ISP_", r"\bDFE\b", r"dfe_", r"\bAWB\b", r"awb_",
        r"shading", r"SHADING", r"tuning", r"TUNING", r"\bNR\b", r"demosaic",
        r"blacklevel", r"\bLSC\b", r" CCM\b", r"color_matrix", r"gamma",
        r"GInv", r"defect", r"sharp", r"lens_shading",
    ],
    "SENSOR_EXPOSURE": [
        r"sensor", r"SENSOR", r"exposure", r"EXPOSURE", r"\bISO\b", r"\bAE\b",
        r"shutter", r"SHUTTER", r"fps", r"\bFSC\b", r"frame_duration",
        r"readout", r"binning", r"long_exp",
    ],
    "AUDIO": [
        r"\bAAC\b", r"aac_", r"audio", r"AUDIO", r"\bMIC\b", r"mic_",
        r"dmic", r"DMIC", r"\bPCM\b", r"lpcm", r"sampling", r"wav",
    ],
    "CONTROL_MSG": [
        r"\[ADF\]", r"ProcMsg", r"AdfSet", r"AdfTransfer", r"\bBiz\b",
        r"\bAvio\b", r"biz_", r"avio", r"LIRO", r"liro", r"PMCB", r"UPM_CMD",
        r"MSGCARD", r"OpenGate", r"cardctrl",
    ],
    "LENS": [
        r"[Ll]ens", r"LENS", r"lensfile", r"aberration", r"Aberration",
        r"focal", r"zoom", r"ZOOM",
    ],
}

_COMPILED = {k: [re.compile(p) for p in v] for k, v in KEYWORDS.items()}


def _match_subsystem(s: str) -> list[str]:
    hits = []
    for name, pats in _COMPILED.items():
        for p in pats:
            m = p.search(s)
            if m:
                hits.append((name, m.group(0)))
                break
    return hits


def classify(data: bytes, funcs: list[dict]) -> dict:
    """Label each function from the strings it references."""
    trusted = sorted((int(f["offset"]), int(f["size"]), f["name"])
                     for f in funcs
                     if int(f["size"]) <= MAX_TRUSTED_SIZE)
    starts = [t[0] for t in trusted]

    strings: dict[int, list[str]] = {}
    unattributed = 0
    for ldr, add, slot, tgt in xrefs.iter_references(data):
        s = xrefs.read_cstring(data, tgt, maxlen=64)
        if not s:
            continue
        i = bisect_right(starts, add) - 1
        if i < 0:
            unattributed += 1
            continue
        strings.setdefault(trusted[i][0], []).append(s)

    labels: dict[str, list[str]] = {}
    label_evidence: dict[str, list[tuple[str, str]]] = {}
    for off, sset in strings.items():
        tally: dict[str, int] = {}
        ev: dict[str, tuple[str, str]] = {}
        for s in sset:
            for name, tok in _match_subsystem(s):
                tally[name] = tally.get(name, 0) + 1
                ev.setdefault(name, (s[:60], tok))
        if not tally:
            continue
        # decode/encode are mutually exclusive; break ties by count then by a
        # fixed priority so the result is deterministic
        best = max(sorted(tally), key=lambda k: (tally[k], k == "DECODE", k == "ENCODE"))
        off_name = trusted[bisect_right(starts, off) - 1][2]
        labels[off_name] = [best]
        label_evidence[off_name] = [ev[best]]

    return {
        "labels": labels,
        "evidence": label_evidence,
        "unattributed": unattributed,
        "trusted_functions": len(trusted),
        "trusted": trusted,
    }


def propagate(trusted, labels, max_gap=0x20000):
    """Extend labels to unlabelled functions by nearest labelled neighbour.

    Firmware subsystems are laid out in contiguous code blocks, so a function
    sitting between two identically-labelled seeds almost certainly belongs to
    the same subsystem.  Returns (assignments, distances) where distances is
    the byte gap to the seed used, so weak inferences are visible.
    """
    seed_idx = [i for i, (off, _, _) in enumerate(trusted) if trusted[i][2] in labels]
    if not seed_idx:
        return {}, {}
    assign: dict[str, str] = {}
    dist: dict[str, int] = {}
    for i, (off, _, name) in enumerate(trusted):
        if name in labels:
            assign[name] = labels[name][0]
            dist[name] = 0
            continue
        # nearest seed by index
        j = bisect_right(seed_idx, i)
        best = None
        for k in (j - 1, j):
            if 0 <= k < len(seed_idx):
                cand = seed_idx[k]
                gap = abs(trusted[cand][0] - off)
                if best is None or gap < best[0]:
                    best = (gap, cand)
        if best and best[0] <= max_gap:
            sname = trusted[best[1]][2]
            assign[name] = labels[sname][0]
            dist[name] = best[0]
    return assign, dist
