# Worktree review on 18 November 2026

The housekeeping pass reviewed the earlier tracked code edits as well as the documentation moves. The original worktree had modified PMCA code, host tooling, build helpers and verification scripts, plus a large collection of untracked experiment material.

| Change family | Review finding | Validation |
| --- | --- | --- |
| PMCA compatibility | Added a missing sys import, preserved regex semantics with explicit escapes, and gated macOS library initialization on Darwin. | Console help succeeded on Windows. The macOS native path was reviewed but was not exercised on macOS. |
| retool | Added executable discovery, virtualenv selection, direct-binary fallback, richer string export and preservation of existing symbols during migration. | Existing retool test module passed within the 79-test targeted run. Engine-dependent behavior retains local input/tool requirements. |
| Build helpers | Resolve repository paths from the script location and discover an ARM compiler. | Reviewed and syntax checked. Historical Cortex-A7 targets remain in the scripts. This pass did not validate a new camera binary or change those targets. |
| Device and lens helpers | Corrected repository roots and relocated helper paths, with missing-file handling. | Mocked verify_zve10.py suite passed. The review performed no camera operations. |
| Documentation | Moved 88 files, retained historical content and imported recent runtime captures with a manifest. | Link/anchor checks and 27 evidence hashes passed. |
| Existing experiment material | Many untracked recipes, disassembly reports and generated results predate this pass. | The new records identify their status and checked recipe inputs. This pass did not independently audit or certify every legacy experiment. |

The targeted command was .venv/Scripts/python.exe -B -m pytest tests/test_retool.py tests/test_uvc_patch.py tests/test_opengate_pipeline.py -q. It passed 79 tests. The separate mocked shell/dumper verification reported ALL PASS. Console and patcher help smoke checks also succeeded.

The new standard-library housekeeping tests exercise evidence tampering, byte-count mismatch, escaping paths, duplicate evidence entries and artifact classification. The dedicated research workflow is ready for a hosted run after the local commits are pushed.

Source/recipe hashes in EXPERIMENT.json identify what was reviewed for navigation and reproduction context. Hardware result and firmware input fields preserve unresolved items explicitly. They do not turn an offline candidate into a camera-tested release.

The remaining legacy untracked files are listed with byte counts and SHA-256 in LOCAL_RESEARCH_INVENTORY_20261118.json. They remain local pending a detailed source/provenance review. This checkpoint covers the reviewed host edits, organized documentation, source identities, imported evidence and housekeeping automation.
