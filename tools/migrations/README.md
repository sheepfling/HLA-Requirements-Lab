# Migration tooling

These utilities were used to promote the source corpus into the committed
semantic records. They are retained for reproducibility and historical source
maintenance, but are not part of the active `hla-lab` workflow.

Migration modules import without a configured workspace. When running a
historical migration, supply an explicit document root if that command accepts
one, or set `HLA_LAB_ROOT` to the workspace before invoking it. No module
infers the workspace from its install path or the current directory. Commands
that expose an argument parser can show their options with:

```powershell
python -m tools.migrations.<module> --help
```

Do not treat migration scripts as a second source of truth. The reviewed JSON
records under `topics/*/semantic/` and the authority manifests under `data/`
remain the active corpus inputs.
