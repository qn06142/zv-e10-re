"""retool — portable, reproducible RE pipeline for pmca-re binaries.

Canonical addressing is FILE OFFSET (base 0x0), matching the addresses already
recorded in avcam_re/pipeline.md and RE_STATE.md.  The runtime load address
(0x635c6000 for av-cam.bin) is reported alongside, never used as the key.
"""

__version__ = "1.0.0"
