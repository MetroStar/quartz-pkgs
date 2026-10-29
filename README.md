# quartz-pkgs

## Quartz Evaluator

The image build is defined in
[quartz-evaluator.yaml](.github/workflows/quartz-evaluator.yaml), with the
hardened runtime in [src/quartz-evaluator](src/quartz-evaluator).

- Scanner source: `MetroStar/epyon` branch `demo/quartz-evaluator`, pinned to
  `0da9ac4da2a38331786c1cf16396928fb099a8fb`.
- Image: `ghcr.io/metrostar/quartz-pkgs/quartz-evaluator:source-0da9ac4da2a3-r3`.
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
  5.0.2 and invoked through its `sonar-scanner-npm` executable. Its locked npm
  dependency tree overrides `node-forge` to upstream release 1.4.2, outside
  the affected range of CVE-2026-85393.

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

### Security release blockers

The `r3` AMD64 and ARM64 images were rebuilt and scanned on 2026-10-29 using
Trivy 0.76.1 against their actual runtime filesystems. Each reports 3 critical,
90 high, 111 medium, 13 low, and 16 unknown package findings (0 RHEL OS-package
findings). The released `node-forge` 1.4.2 override removes CVE-2026-85393;
the locked Sonar npm tree also passes `npm audit --omit=dev`.

The images are **not security-clean and must not be released as such**.
Remaining blockers under the upstream-releases-only remediation policy:

| Component | Blocker |
| --- | --- |
| Xeol 0.10.8 | Latest published release still embeds critical CVE-2025-21613 (go-git), CVE-2026-33186 (gRPC), and CVE-2025-68121 (Go stdlib), plus other findings. |
| Syft 1.55.0 / Grype 0.121.0 | Latest published releases still embed affected Go libraries/toolchains. |
| Trivy 0.76.1 / Helm 3.22.1 | Latest compatible releases still embed affected Go libraries/toolchains; Helm 4 is not a drop-in compatibility update. |
| Checkov 3.4.0 | Latest release pins `asteval==1.0.6`; the reported fix is 1.0.9. Overriding it would violate Checkov's declared dependency contract. |
| python-ecdsa 0.19.2 | Latest release has no published fix for CVE-2024-23342. Checkov depends on it for external-check signature verification; removing it would break that feature. |

No findings or scanner layers were suppressed or removed. Resolving the
remaining findings requires compatible upstream releases or a separately
approved source-patching/feature-change strategy, followed by rebuilds and
rescans. A scanner finding is not itself a confirmed exploitability assessment.

Coordinated Quartz/quartzctl changes target fresh installations only. Existing
application pipelines must switch their Jenkins template/container selectors
from `epyon` to `quartz-evaluator` before rollout. Image publication and live
deployment are not performed by opening the coordinated PRs.