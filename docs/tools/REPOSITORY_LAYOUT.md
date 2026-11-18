# Repository layout

The root has seven visible source directories. Local firmware, output and external checkouts are grouped under .local. Dot directories retain Git metadata, CI configuration and Python environments.

| Root directory | Contents |
| --- | --- |
| docs | Current system overview, topic references and historical reports |
| research | Camera-facing tools, analysis, experiments, symbols and measured evidence |
| scripts | Build/deployment commands, host tools and staging recipes |
| tests | Offline tests |
| retool | Importable binary-analysis Python package |
| pmca | Upstream PMCA package and its bundled certificate resources |
| updatershell | Upstream device-shell and update components |

## Research and tools

| Current path | Previous root path |
| --- | --- |
| research/avcam | avcam_re |
| research/symbols | re_symbols |
| research/verify | verify |
| research/captures | Tracked metadata from captures |
| scripts/tools | tools |
| scripts/staging | bin |
| pmca/resources/certs | certs |

Run commands from the repository root. The verification harness is now python -B research/verify/verify_zve10.py. The log decoder is python -B scripts/tools/decode_app_log.py. The retool launchers retain their root command paths and use reconf.toml for the current symbols and input locations.

## Local data

| Path | Contents |
| --- | --- |
| .local/dumps | Camera firmware, partition images and extracted inputs |
| .local/captures | Frame payloads and new capture-session output |
| .local/out and .local/outputs | Generated experiment packages and output |
| .local/build_sysroot | Local ARM build libraries |
| .local/kmod and .local/udtrbody_extract | Extracted kernel modules and updater material |
| .local/work and .local/scratch | Intermediate work |
| .local/vendor | Existing fwtool and nex-hack checkouts |
| .local/cache | Pytest and moved Python caches |
| .local/re_out | Future retool project caches and exports |

The outputs junction retains its original external target. Vendor directories were relocated as complete checkouts. These moves preserve the stored data. Repository source and configuration use the new paths. External scripts that embed an old absolute root path need the corresponding location from this table.

The old index contained 776 local firmware/settings inputs despite the ignore rules. Their relocated copies matched the previous Git object identities. Their old paths were removed from the current index. Earlier commits still contain their historical blobs.

The [move record](../archive/ROOT_LAYOUT_20261118.json) records the directory changes and capture-metadata moves. Earlier evidence manifests and inventory records retain their original source paths as historical provenance.
