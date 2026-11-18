# Physical-camera tools

The [access guide](../../docs/ACCESS_AND_TOOLS.md) records the verified SSH connection, USB routes, tool paths and trace rearm procedure.

| Tool group | Use |
| --- | --- |
| [zve10_diagnostics](zve10_diagnostics/README.md) | Small ARM register dumper and LiRo trace reader |
| zve10_retry.py and shell helpers | Existing PMCA/Senser command transport |
| analyze_*, inspect_* and probe scripts | Device/service and runtime inspection |
| deploy_* and apply_* | Historical experiment deployment |
| [live_stream_monitor.py](live_stream_monitor.py) | OpenCV/DirectShow capture utility moved from the repo root |

Run the monitor from the repository root with python research/device/live_stream_monitor.py. It requires OpenCV and NumPy and opens the configured host camera when executed. Capture output remains relative to the working directory under .local/captures/live_monitor_v47.

Deployment scripts encode assumptions about firmware, process state and existing patches. Read their source and matching report before running them. The [current checkpoint](../../docs/CURRENT_STATUS.md) identifies the latest evidenced installation.
