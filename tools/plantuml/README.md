# Pinned PlantUML renderer

The state-chart source exporter writes deterministic `.puml` files. The release
renderer is pinned in `plantuml.lock.json`. On Windows, PlantUML 1.2024.6 is
invoked with UTF-8 input and EPS output, then MiKTeX `epstopdf` converts the
vector EPS into the PDF consumed by LaTeX.

Example:

```powershell
python -m hla_lab.diagrams.plantuml_render `
  --jar .tools/plantuml/plantuml-1.2024.6.jar `
  --output-dir topics/ieee/hla-1516.1-2025/output/plantuml `
  topics/ieee/hla-1516.1-2025/output/semantic/state-machine-normal-activity-permitted.puml
```

The PlantUML jar itself is a local tool artifact and is intentionally not
checked into the repository.
