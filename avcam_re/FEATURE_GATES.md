# Feature inventory and enable/disable gates (2026-09-26)

The practical question: what can be turned **on**, rather than pushed past what
the hardware can do. This records the feature system, the gates, and the
concrete enabling leads — with an honest statement of what is identified as a
*gate* versus what has actually been located as *patchable data*.

## The feature system exists and is named

`FC/Feature/` is a real per-feature module directory; the module carries its own
source paths as strings. **21 files:**

```
fc_feature_base_setting        fc_feature_panorama
fc_feature_beauty_effect       fc_feature_panorama_face_meta
fc_feature_capture             fc_feature_pmv
fc_feature_capture_dummy       fc_feature_prc_retouch
fc_feature_develop             fc_feature_re_init
fc_feature_develop_art         fc_feature_rec_face
fc_feature_mon_face            fc_feature_retouch
fc_feature_mon_obj_for_animal  fc_feature_retouch_art
fc_feature_mon_obj_for_face    fc_feature_scalara_oneshot
fc_feature_panorama            fc_feature_touch
                               fc_feature_touch_for_scanaf
                               fc_feature_track_init
```

**38 `Feature*` classes** appear in C++ mangled symbols, including three
configurators that are the enable mechanism itself:

```
tcub::feature::FeatureConfigrator
tcub::feature::StaticFeatureConfigrator     <- per-model, presumably baked in
tcub::feature::DynamicFeatureConfigrator    <- runtime
```

Namespace `tcub::feature`, so features are a first-class, configurable
subsystem rather than scattered flags. `FeatureBase<...>` is templated over
per-feature data types: `DataReInit`, `DataMonFace`, `DataOneshot`,
`DataRecFace`, `DataMonObject`, `DataTrackInit`, `DataPmv`, `DataPrc`,
`DataDummy`, `DataTouch`.

Note `DataDummy` / `FeatureCaptureDummy` / `fc_feature_capture_dummy.cpp` — a
**dummy feature implementation exists in the tree**. That is the shape of a
feature that is compiled but stubbed for some models, and it is the single most
promising lead below.

## The module documents its own API

**155 self-documenting API parameter strings** in `- argN: name [enum]` form.
This is unusually valuable: the firmware ships its own interface reference. The
feature-bearing parameters:

| API parameter | values |
|---|---|
| `arg1: state` | `[0:HdmiInput Disable, 1:HdmiInput Enable]` |
| `arg1: Type` (audio in) | `[0:Off, 1:Int, 2:Shoe, 3:Zoom, 4:Wireless, 5:Ext, 6:Line, 7:XLR-BOX]` |
| `arg1: Type` (audio out) | `[0:Off, 1:Speaker, 2:Line, 4:Headphone, 8:SystemSound]` — a **bitmask** (1/2/4/8) |
| `arg1:MODE` | `[0:IDLE, 1:PB, 2:EE, 3:HIGHLIGHT, 4:HIGHLIGHT_REC, 5:DFS, 6:MIC_ADJUST, 7:DOWNCON, 8:CHK…]` |
| `arg2:streamId` | `[0:DEFAULT, 1:ID0, 2:ID2, 3:ID0+ID2]` |
| `arg1: state` (input) | `[0:Input Disable, 1:Input Enable]` |
| `arg1: 0:ChkframeEdge` | `OFF, ON` |
| `arg2: trim` | `[0:-18dB, 1:-12dB, 2:-6dB, 3:0dB, 4:6dB, 5:12dB]` |
| `arg1: freq` | `[0:32kHz, 1:44.1kHz, 2:48kHz]` |
| `arg1: Mode` (Piroshki) | `[0:Off, 1:Outside(ABB), 2:Inside(PiroshkiOnly)]` |
| `arg2: mode` | `[0:AV_SYNC, 1:ONLY_AUDIO]` |

`MODE` is the camera's top-level state enum: `PB` (playback), `EE` (still
image), `DFS` (dynamic frame rate), `HIGHLIGHT`/`HIGHLIGHT_REC`, `MIC_ADJUST`,
`DOWNCON` (down-conversion), `CHK…`.

## Recording / delivery modes

The recording-mode name table at `fcn.0008f5f8` (`0x8f5f8`) maps 17 ids to
names — an inventory of what the camera *can* be asked to do:

```
SD_SAKUHINKA (SD-card video)   HD_SAKUHINKA   STREAMING
ENC_PROXY                      GEARED_ENC     HILGT_PB_NOAUDIO
HD_SAKUHINKA_NOAUDIO           NAMESURO       BGMCHK
SLIDESHOW_NOAUDIO              (+ a Genlock NULL id at 0x00)
```

`SAKUHINKA` (動画) is Japanese for video/movie. Consecutive id pairs share a
name, so the low bit is a variant selector (audio / no-audio), matching the
`_NOAUDIO` suffixes.

## Model-specific gating

> **Correction (2026-09-26).** An earlier reading treated `Stage_OpdBranch_BOL310`
> as evidence that OPD means "Optical Pixel Divider" and that BOL310 has Pixel
> Shift. That was an inference from an acronym and it is wrong in the way that
> matters: **this image contains zero occurrences of `IBIS`**, and Sony's Pixel
> Shift Multi Shot is driven by the IBIS sensor-shift actuator, so it cannot
> apply to a body without IBIS. The ZV-E10 has no IBIS. The OPD / MotionShot /
> BDRO stages are therefore stages for *other bodies in the shared build*, not
> features this camera can have. Do not read them as available.

`BOL310`, `BOL373` and `BOL473` are Sony internal body codes. They appear in
only three pipeline stage names plus four runtime log strings:

```
Stage_ReadExecute_AsyncLv_BOL310_BOL473
Stage_OpdBranch_BOL310
Stage_TDReadExecute_BOL373
FW: ImagerSleep not available on BOL310. force replace DISABLE
```

So the firmware carries three sensor-readout implementations and selects by
model; BOL310 additionally has `ImagerSleep` forcibly removed. **BOL310 is not
this camera.** There is no `ZV-`/`ILCE-` string in the image, and — checked at the
byte level — no `IBIS`, `PixelShift` or `PIXEL` occurrence anywhere in the 17 MB.

Worth stating plainly: **`av-cam.bin` contains no model identifier at all.** The
firmware version `30110_05.2025031501` comes from `dumps/version.txt`, a
separate source, and is *not* present in this binary. That is consistent with
the module being model-agnostic: the RTOS selects the per-body path at load
time, so the image itself does not need to know which body it is on. Mapping
`30110` or `BOL310` to a retail name requires Sony's model-code list, not this
file.

Practical consequence: because this binary only ever runs on one camera,
flipping a feature gate cannot break a sibling model. There is no cross-model
safety concern.


## ISP-level function gate

`IMG:ERROR:FuncType:%x is not enable at FuncID:%x`, string at `0x9a32d1`,
referenced from code at `0x1e31fc`. The surrounding function dispatches
`FuncType` ids `0x21`, `0x22` via calls to `0x1e2f84` and returns error `0x230`
on failure. This is a per-ISP-function enable check — a gate on *which ISP
functions run*, keyed by FuncID.

## Concrete enabling candidates, ranked

1. **`FeatureCaptureDummy` / `DataDummy` / `fc_feature_capture_dummy.cpp`** — a
   dummy feature implementation is compiled in. If the real capture feature is
   gated off on this model, the dummy is what runs. The most promising single
   lead: a stub exists precisely so it can be swapped.
2. **HDMI input** — an explicit `state [0:Disable, 1:Enable]` API. Needs only
   the enable call, and the strings show the firmware expects it to be
   switchable at runtime.
3. **XLR-BOX audio input** (audio-in type `7`) — professional mic input, present
   in the enum. Frequently absent on consumer bodies, i.e. a plausible
   per-model gate.
4. **Dual stream** `streamId [3:ID0+ID2]` — simultaneous two-stream output.
5. **Recording modes** — the 17-entry table is a closed enumeration; adding or
   remapping an entry is a small, well-understood data edit.
6. **`DOWNCON` / `DFS` modes** — top-level modes that may simply be suppressed
   by the mode gate.

## What is identified vs what is patchable — read this part

**Identified as gates** (the mechanism is understood, the location is known):
the `Static`/`DynamicFeatureConfigrator` classes, the ISP `FuncID`/`FuncType`
enable check at `0x1e31fc`, the per-model BOL310/BOL473 stage branches, the
recording-mode enumeration, and the documented Enable/Disable APIs.

**Not yet located**: the actual enable *bitmask or flag table*. The three
configurator class names are RTTI strings, not the data they read, and the
feature-enable state was **not** found as a patchable word or byte array. So
nothing here is yet a concrete offset to flip — these are ranked leads with a
known mechanism, not instructions.

**Also not established**: whether a gate is per-model, per-region, or
per-license. The `Static`/`Dynamic` split suggests per-model-baked versus
runtime, but that is inference from the class names.

**The next concrete step** is to reach `StaticFeatureConfigrator`'s vtable
through its RTTI name and follow it to the data it reads. That is bounded and
it is the thing that turns this list into a set of offsets.

## Reproducing

```
retool.cmd xrefs  avcam 0x9a32d1        # the ISP FuncID/FuncType gate string
retool.cmd disasm avcam 0x1e31fc -n 40  # the gate itself
retool.cmd disasm avcam 0x32dfc8 -n 30  # BOL310 ImagerSleep removal
retool.cmd disasm avcam 0x8f5f8  -n 70  # recording-mode table
retool.cmd strings avcam Configrator    # the enable mechanism
```
