# CI triggers and local verification

`.github/workflows/ci.yml` runs hosted verification in two cases:

- A pull request targeting `feature/hla` closes and was merged. GitHub may emit
  the `closed` event for an unmerged PR too, so both jobs require
  `github.event.pull_request.merged == true`. The six Ubuntu/Windows and
  Python 3.11/3.12/3.13 quality configurations remain unchanged;
  `document-release` still waits for `quality` to succeed.
- A maintainer manually dispatches the workflow with `workflow_dispatch`.
  GitHub only offers the **Run workflow** button when the workflow file is on
  the default branch. This PR targets `feature/hla`, while the repository's
  default is `master` and currently has no `ci.yml`; the button will therefore
  be unavailable until this workflow also reaches `master`.

The workflow does not run on draft PR updates or direct pushes to
`feature/hla`. A direct push is not a pull-request merge event. An unmerged PR
close creates a workflow event, but both jobs are skipped. The normal
`actions/checkout` behavior uses the event's ref/SHA; for a merged
`pull_request` close, GitHub sets the ref to the target branch and the SHA to
the merge result, so verification checks the state that landed.

Run the checks locally before merging:

```console
python -m tools.ci quality
python -m tools.ci release
```

The local quality run is the pre-merge gate. Hosted verification checks the
merged `feature/hla` state afterward and runs the same quality matrix followed
by the document-release job. The target branch currently has no protection
rule or ruleset requiring hosted checks.

During rollout, the current `feature/hla` workflow still has `push` and
default pull-request triggers until this PR merges. It can still start jobs
for new commits or PR updates in that interval; the skip marker on this PR's
current head suppresses those push and pull-request runs. The current default
branch `master` has no workflow file, so the manual UI option remains
unavailable until the workflow is added there as well. Keep `[skip ci]` out of
the eventual merge or squash commit message so GitHub can run post-merge
verification.

This uses the ordinary `pull_request` event and does not grant additional
`GITHUB_TOKEN` permissions. `pull_request_target` is unnecessary here because
the workflow only verifies the merged target-branch revision.

References: GitHub's [`pull_request` merge semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#running-your-pull_request-workflow-when-a-pull-request-merges), [`workflow_dispatch` availability](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch), [`actions/checkout` ref behavior](https://github.com/actions/checkout#usage), [secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use), and [commit-message skip behavior](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).
