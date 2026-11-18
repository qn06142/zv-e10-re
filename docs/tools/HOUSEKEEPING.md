# Repository housekeeping

Run these checks from the repository root. They use the Python standard library and do not contact the camera.

```powershell
python -B research/firmware/check_docs.py --portable
python -B scripts/check_research.py
python -B -m unittest discover -s tests -p test_housekeeping.py
```

The [research workflow](../../.github/workflows/research-checks.yml) runs the same checks on pushes and pull requests. Documentation portable mode allows declared local firmware/build input links. Ordinary missing source and evidence links still fail. The evidence validator checks exact bytes and SHA-256 against each dated session manifest and rejects paths outside the checkout.

## Artifacts

| Location | Tracking convention |
| --- | --- |
| .local/work | Local scratch and intermediate build inputs |
| .local/captures | Local payloads |
| research/captures | Reviewable JSON, Markdown and TSV capture metadata |
| scripts/staging | Reviewable staging scripts/configuration with local compiled objects |
| research | Authored source and measured evidence with generated binary formats ignored |
| .local/dumps and .local/outputs | Existing local firmware and build/capture storage |

The index check rejects tracked .local content, generated objects in scripts/staging and research, and frame payloads in research/captures. The [artifact audit](../archive/ARTIFACT_AUDIT_20261118.json) identifies the payloads and the two generated objects removed from the Git index. The [layout guide](REPOSITORY_LAYOUT.md) lists their current locations.

## Experiment records

Each revision directory listed in the [registry](EXPERIMENTS.md) contains EXPERIMENT.json. Record status, hashed source/recipe inputs, confirmed firmware hashes, reproduction command and working directory, hardware outcome, rollback context and evidence paths. Use an explicit unresolved reason where the old invocation or firmware identity has not been established.

Status values are historical, offline-candidate, hardware-observed and failed. Hardware-observed can describe an installation/readback checkpoint. Describe the exact observation in hardware_result.

Source/recipe identities normalize CRLF to LF before hashing, so checkout line endings do not alter the identity. Captured evidence uses exact bytes, preserved by .gitattributes. When updating a recipe, review the record and refresh its source-input hashes. For a new revision, create its record before checkpointing the directory. Preserve the previous test evidence and record a fresh result when hardware is tested again.

## Git checkpoints

Review the staged diff and run the relevant checks before making a focused commit. Keep the source changes, artifact policy, documentation and experiment records understandable in history. The [November review](../archive/WORKTREE_REVIEW_20261118.md) records the scope and limits of the earlier development changes reviewed during this housekeeping pass.
