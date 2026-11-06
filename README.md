# quartz-pkgs

## Image manifest synchronization

The [manifest sync workflow](.github/workflows/sync-image-manifest.yaml) pulls
upstream `MetroStar/quartz` `main` hourly, at minute 17, and retains its manual
trigger for immediate synchronization or an explicit Quartz ref. GitHub can
delay scheduled runs. Synchronization runs only in `MetroStar/quartz-pkgs`,
serializes writes to package `main`, and uses the built-in `GITHUB_TOKEN`
for package writes and same-repository workflow dispatch.
Private Quartz source checkout uses `QUARTZ_SOURCE_SSH_KEY`, an Actions secret
containing the private half of a **read-only deploy key on Quartz**. The key
grants no repository-write or dispatch access and is not persisted in the
source checkout. No cross-repository `QUARTZ_PKGS_DISPATCH_TOKEN` is needed in
Quartz or its derived infrastructure repositories.

Changed manifests are committed to package `main`, followed by an explicit
same-repository dispatch of the image mirror workflow. This dispatch is
necessary because bot-token commits do not trigger push workflows.
Extraction, push, and dispatch errors fail the run rather than being hidden.
The existing optional Iron Bank registry credentials remain independent of
GitHub dispatch authorization.

Run the workflow contract tests with:

```sh
python3 scripts/test-manifest-sync.py
python3 scripts/test-extracted-images.py
```

The extractor preserves separate registry/repository/name components and
the upstream charts' `v`-prefixed default image tags. Its regressions also
ensure short added/removed-image summaries do not report a successful
extraction as a failure.

## Quartz Evaluator

The image build is defined in
[quartz-evaluator.yaml](.github/workflows/quartz-evaluator.yaml), with the
hardened runtime in [src/quartz-evaluator](src/quartz-evaluator).

- Scanner source: `MetroStar/epyon` branch `demo/quartz-evaluator`, pinned to
  `38e584e3fd6a89ab0ad9e4106ff6cc22a7bbb1fb`.
- Image: `ghcr.io/metrostar/quartz-pkgs/quartz-evaluator:source-38e584e3fd6a-r3`.
  Increment the runtime revision for packaging changes; never overwrite a
  published source/revision tag. Publish and verify it before deploying Quartz.
- Native AMD64 and ARM64 runtime jobs execute the published image without
  privileges or writable root filesystems and verify its toolchain, OCI source/
  digest rejection, real Trivy OCI-layout parsing, retained policy findings
  and structured STIG contract, persistent cache/source invalidation and
  deterministic parallel-batch error visibility.
  Full live application scans remain separate acceptance checks; the controlled
  runtime fixtures are not application scan evidence.
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

The pinned scanner supports source-bound OCI build archives for hardened Jenkins
pods, actual Maven dependency-cache reuse, strict enabled-tool failure
propagation, schema-constrained STIG output, and no-store HTML/logout wiring.
Use `EPYON_REQUIRE_COMPLETE=true` and `EPYON_AI_STRUCTURED_OUTPUT=true` for
complete-scan enforcement against Quartz's Ollama endpoint.

Runtime revision `source-38e584e3fd6a-r3` also fixes native API discovery:
OpenAPI titles/versions are diagnostics, not numeric return values, and absent
frameworks yield exactly one zero count. Both architecture jobs exercise
real OpenAPI/Python, Express, and empty Next.js fixtures and parse the resulting
inventory JSON. API discovery stays enabled; it remains a static inventory,
not a claim that runtime API penetration tests have run.

### EOL database provider

Runtime revision `source-38e584e3fd6a-r4` adds exact keyed STIG response schemas
for reliable multi-control batches while retaining complete catalog assessment,
strict evidence validation, and unchanged exported reports. Local requests select
relevant manual documentation and bound output reservations per control instead
of silently sacrificing half the context window. Native architecture tests reject
duplicate and mismatched response keys. NVD cache and authenticated rate limits
are unchanged; a cold unauthenticated enrichment of 106 CVEs alone exceeds ten
minutes. This performance revision does not resolve the security release
blockers documented below.

Runtime revision `r2` explicitly selects `EPYON_XEOL_DB_SOURCE=endoflife.date`.
Xeol's hosted database suffered an authoritative DNS outage, acknowledged by
HeroDevs in [xeol-io/xeol#607](https://github.com/xeol-io/xeol/issues/607).
The native Xeol binary and mandatory EOL layer remain enabled. The runtime
downloads the complete [endoflife.date API v1 catalog](https://endoflife.date/docs/api/v1/),
converts its published PURL/CPE identifiers and release cycles into Xeol's
schema-1 database, and imports the result using `xeol db import`.

This is a **different, explicitly identified data provider**, not a mirror of
Xeol's proprietary aggregate. Coverage is limited to products and identifiers
published by endoflife.date; it does not claim Xeol's additional vendor,
registry, or vulnerability-count enrichment. Xeol's vulnerability-count field
is not vulnerability clearance; the separate mandatory vulnerability scanners
remain authoritative for that gate.

The archive retains provider attribution, source SHA-256, source generation
timestamp, and product/cycle/identifier counts in `provider.json`. Its age is
the upstream generation time, never a new timestamp applied to stale data.
Catalogs older than five days, future-dated/partial/malformed catalogs, failed
downloads, failed imports, and invalid databases fail the EOL layer. Native
Xeol checksum and age validation are enabled. Maintained releases with no
announced EOL are not incorrectly treated as already EOL. Each scan uses its
own database cache to avoid concurrent-import races.

`EPYON_XEOL_DB_SOURCE=xeol` explicitly restores the original hosted provider
and its valid-cache behavior. There is no automatic provider fallback. An
unknown provider is an error. Both architectures test native database import,
positive/negative EOL matching, and corrupt-database rejection without network
access; catalog conversion regressions run with:

```sh
python3 scripts/test-xeol-db.py
```

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