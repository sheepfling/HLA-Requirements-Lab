# Migration tooling

These utilities were used to promote the source corpus into the committed
semantic records. They are retained for reproducibility and historical source
maintenance, but are not part of the active `hla-lab` workflow.

Run one explicitly when a source migration is required:

```powershell
python -m tools.migrations.<module> --help
```

Do not treat migration scripts as a second source of truth. The reviewed JSON
records under `topics/*/semantic/` and the authority manifests under `data/`
remain the active corpus inputs.
