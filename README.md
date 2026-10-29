# quartz-pkgs

## Quartz Evaluator

The image build is defined in
[quartz-evaluator.yaml](.github/workflows/quartz-evaluator.yaml), with the
hardened runtime in [src/quartz-evaluator](src/quartz-evaluator).

- Scanner source: `MetroStar/epyon` branch `demo/quartz-evaluator`, pinned to
  `0da9ac4da2a38331786c1cf16396928fb099a8fb`.
- Image: `ghcr.io/metrostar/quartz-pkgs/quartz-evaluator:source-0da9ac4da2a3-r1`.
  Increment the runtime revision for packaging changes; never overwrite a
  published source/revision tag. Publish and verify it before deploying Quartz.
- CI wrapper: [quartz-evaluator-scan.yaml](.github/workflows/quartz-evaluator-scan.yaml).
  It pins the workflow fix from [MetroStar/epyon#187](https://github.com/MetroStar/epyon/pull/187)
  separately from `scanner_ref`, which selects the demo scanner source.
  Refresh the workflow pin after a squash/rebase merge of the upstream fix.
- The upstream repository name, `/app/epyon.sh`, Python modules, and `EPYON_*`
  scanner variables are retained for compatibility; demo branding is not
  proposed for upstream main.

Verify every native-toolchain patch against a checkout of the pinned source:

```sh
python3 scripts/verify-quartz-evaluator.py /path/to/epyon-source
```

Coordinated Quartz/quartzctl changes target fresh installations only. Existing
application pipelines must switch their Jenkins template/container selectors
from `epyon` to `quartz-evaluator` before rollout. Image publication and live
deployment are not performed by opening the coordinated PRs.