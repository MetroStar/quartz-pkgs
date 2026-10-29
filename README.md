# quartz-pkgs

## Quartz Evaluator

The image build is defined in
[quartz-evaluator.yaml](.github/workflows/quartz-evaluator.yaml), with the
hardened runtime in [src/quartz-evaluator](src/quartz-evaluator).

- Scanner source: `MetroStar/epyon` branch `demo/quartz-evaluator`, pinned to
  `0da9ac4da2a38331786c1cf16396928fb099a8fb`.
- Image: `ghcr.io/metrostar/quartz-pkgs/quartz-evaluator:source-0da9ac4da2a3-r2`.
  Increment the runtime revision for packaging changes; never overwrite a
  published source/revision tag. Publish and verify it before deploying Quartz.
- CI wrapper: [quartz-evaluator-scan.yaml](.github/workflows/quartz-evaluator-scan.yaml).
  It pins the workflow fix from [MetroStar/epyon#187](https://github.com/MetroStar/epyon/pull/187)
  separately from `scanner_ref`, which selects the demo scanner source.
  Refresh the workflow pin after a squash/rebase merge of the upstream fix.
- The upstream repository name, `/app/epyon.sh`, Python modules, and `EPYON_*`
  scanner variables are retained for compatibility; demo branding is not
  proposed for upstream main.
- The runtime clears the base image's interactive Python entrypoint so the API
  and Jenkins commands run as UID 1000. SonarQube Scanner for NPM is pinned to
  5.0.2 and invoked through its `sonar-scanner-npm` executable.

Verify every native-toolchain patch against a checkout of the pinned source:

```sh
python3 scripts/verify-quartz-evaluator.py /path/to/epyon-source
```

After building each architecture locally, check its default entrypoint,
non-root scan writes, Python dependencies, and installed scanner executables:

```sh
python3 scripts/verify-quartz-evaluator.py /path/to/epyon-source --image quartz-evaluator:validation-amd64
python3 scripts/verify-quartz-evaluator.py /path/to/epyon-source --image quartz-evaluator:validation-arm64
```

These smoke checks do not replace API/importer persistence tests, vulnerability
scanning, or live SSO/SonarQube/AI acceptance.

Coordinated Quartz/quartzctl changes target fresh installations only. Existing
application pipelines must switch their Jenkins template/container selectors
from `epyon` to `quartz-evaluator` before rollout. Image publication and live
deployment are not performed by opening the coordinated PRs.