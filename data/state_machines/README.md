# State-machine data

This directory is reserved for canonical, renderer-independent representations
of extracted state-machine diagrams. The current prose-derived pilot lives in
`topics/ieee/hla-1516.1-2025/semantic/`. The JSON contract is defined in
[`schemas/state_machine.schema.json`](../../schemas/state_machine.schema.json).

The source image remains provenance only. TikZ, Graphviz, Mermaid, and other
formats should be generated from these records rather than edited directly.
The manifest also records source-scope outcomes; for example,
`reviewed_no_state_diagrams` means the current reconstructed source bundle was
audited and produced no state-machine candidates, not that an absent image
directory was silently treated as empty.

Use the repository-level inventory and metrics commands from the root:

```powershell
python -m scripts.inventory_state_machines `
  --source hla-1516.1=topics/ieee/hla-1516.1-2025/assets/extracted `
  --source hla-1516.2=topics/ieee/hla-1516.2-2025/assets `
  --manifest data/state_machines/manifest.json --write

python -m scripts.reconcile_state_machine_manifest `
  --manifest data/state_machines/manifest.json `
  --models topics/ieee/hla-1516.1-2025/semantic `
  --reviews reviews/state_machines --write

python -m scripts.state_machine_metrics `
  --manifest data/state_machines/manifest.json `
  --models topics/ieee/hla-1516.1-2025/semantic
```
