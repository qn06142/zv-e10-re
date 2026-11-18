# Firmware research

Use [current status](../../docs/CURRENT_STATUS.md) to choose a relevant checkpoint. Revision numbers identify experiments and do not imply a verified hardware milestone.

| Area | Location |
| --- | --- |
| Recent hardware observations | [November evidence](evidence/zve10-20261117/README.md) |
| Synthetic VGA transport | [v24p source and report](yuy2_transport_v24p/README.md) |
| Live-source API and ownership work | [RAW/YC source research](raw_frame_source/README.md) |
| Native Bayer receiver candidate | [Receiver component](raw_frame_source/verified_bayer/raw_receiver_v01/README.md) |
| RAW completion and debug gates | [Receiver/completion audit](raw_frame_source/verified_bayer/evidence/native-dump-20261031/REPORT.md) and [gate audit](raw_frame_source/verified_bayer/evidence/raw-pipeline-audit-20261031/REPORT.md) |
| Source lifetime and USB staging | [USB lifetime audit](raw_frame_source/verified_yc/evidence/usb-lifetime-20261029/REPORT.md) |
| 1080p and SuperSpeed candidate | [v43 recipe](yuy2_transport_v43_usb3_hd/README.md) and [later build manifest](evidence/zve10-20261117/transport/manifest.json) |
| Binary regeneration and input hashes | [Patched objects](PATCHED_OBJECTS.md) |

The yuy2_transport_v* directories retain each recipe's source, local verification and relative dependencies. The sequence covers transport bring-up, snapshot experiments, metadata/ownership investigations, resizing and chunk delivery. Historical context is in [USB research](../../docs/usb/README.md).

Root Python scripts in this directory are analysis utilities and inventory generators. Several require local firmware inputs. Use the [research guide](../README.md) and [host analysis guide](../../docs/tools/RETOOL.md) for execution context.
