import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path("/app/scripts/shell")


class EvaluatorRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.target = self.root / "source"
        self.target.mkdir()
        (self.target / "README").write_text("Controlled OCI runtime fixture\n")
        subprocess.run(["git", "init", "--initial-branch=main", str(self.target)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.target), "add", "README"], check=True, capture_output=True)
        subprocess.run([
            "git", "-C", str(self.target), "-c", "user.name=Quartz Runtime Test",
            "-c", "user.email=runtime@example.invalid", "-c", "commit.gpgsign=false",
            "commit", "-m", "Create controlled runtime fixture",
        ], check=True, capture_output=True)
        self.revision = subprocess.check_output(
            ["git", "-C", str(self.target), "rev-parse", "HEAD"], text=True,
        ).strip()

    def archive(self, revision, corrupt=False):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as layer:
            body = b"Controlled runtime fixture\n"
            member = tarfile.TarInfo("app/marker.txt")
            member.size = len(body)
            layer.addfile(member, io.BytesIO(body))
        layer_bytes = stream.getvalue()
        members = {}

        def blob(body, media_type):
            digest = hashlib.sha256(body).hexdigest()
            members["blobs/sha256/" + digest] = body
            return {"digest": "sha256:" + digest, "size": len(body), "mediaType": media_type}

        config = blob(json.dumps({
            "architecture": "arm64" if platform.machine() == "aarch64" else "amd64",
            "os": "linux",
            "config": {"Labels": {"org.opencontainers.image.revision": revision}},
            "rootfs": {"type": "layers", "diff_ids": ["sha256:" + hashlib.sha256(layer_bytes).hexdigest()]},
        }).encode(), "application/vnd.oci.image.config.v1+json")
        layer = blob(layer_bytes, "application/vnd.oci.image.layer.v1.tar")
        manifest = blob(json.dumps({
            "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": config, "layers": [layer],
        }).encode(), "application/vnd.oci.image.manifest.v1+json")
        members["index.json"] = json.dumps({
            "schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [manifest],
        }).encode()
        members["oci-layout"] = b'{"imageLayoutVersion":"1.0.0"}'
        if corrupt:
            members["blobs/sha256/" + layer["digest"].split(":")[1]] = b"tampered"
        archive = self.root / "image.tar"
        with tarfile.open(archive, mode="w") as output:
            for name, body in members.items():
                member = tarfile.TarInfo(name)
                member.size = len(body)
                output.addfile(member, io.BytesIO(body))
        return archive

    def run_import(self, archive):
        return subprocess.run([
            sys.executable, str(SCRIPTS / "import-build-archive.py"),
            str(archive), str(self.target), str(self.root / "build"),
        ], capture_output=True, text=True, timeout=30)

    def test_native_toolchain_executes(self):
        for command in (
            ["git", "--version"], ["node", "--version"], ["java", "-version"],
            ["trivy", "--version"], ["grype", "version"], ["syft", "version"],
            ["clamscan", "--version"], ["nmap", "--version"],
        ):
            with self.subTest(command=command):
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_image_imports_source_bound_oci(self):
        result = self.run_import(self.archive(self.revision))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads((self.root / "build/build-summary.json").read_text())
        self.assertEqual(summary["source_revision"], self.revision)
        self.assertEqual(summary["mode"], "container_build")
        self.assertEqual(summary["runtime"], "external_oci_builder")

    def test_wrong_source_is_rejected(self):
        result = self.run_import(self.archive("wrong-source"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source revision", result.stderr)
        self.assertFalse((self.root / "build/build-summary.json").exists())

    def test_native_trivy_reads_verified_oci_layout(self):
        layout = self.root / "oci-layout"
        result = subprocess.run([
            sys.executable, str(SCRIPTS / "import-build-archive.py"),
            str(self.archive(self.revision)), str(self.target), str(self.root / "build"),
            "--oci-layout", str(layout),
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run([
            "trivy", "image", "--input", str(layout), "--scanners", "secret",
            "--offline-scan", "--skip-db-update", "--skip-java-db-update",
            "--skip-check-update", "--format", "json",
        ], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["ArtifactType"], "container_image")

    def test_corrupt_layer_is_rejected(self):
        result = self.run_import(self.archive(self.revision, corrupt=True))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "build/build-summary.json").exists())

    def test_actual_image_structured_stig_contract(self):
        spec = importlib.util.spec_from_file_location("runtime_stig", SCRIPTS / "run-stig-assessment.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        os.environ["EPYON_AI_STRUCTURED_OUTPUT"] = "true"
        control = {"vuln_id": "V-1"}
        options = module._structured_kwargs(module._assessment_schema([control]))
        self.assertEqual(options["reasoning_effort"], "none")
        self.assertEqual(options["response_format"]["type"], "json_schema")
        valid = {"vuln_id": "V-1", "status": "Open", "evidence": "Controlled fixture evidence", "confidence": 90}
        self.assertEqual(module._validate_batch([valid], [control]), [valid])
        with self.assertRaises(ValueError):
            module._validate_batch([valid, valid], [control])
        with self.assertRaises(ValueError):
            module._validate_batch([{**valid, "confidence": 101}], [control])

    def test_completed_policy_findings_are_retained(self):
        (self.target / "README.md").write_text("# Controlled model card with missing sections\n")
        (self.target / "Dockerfile").write_text("FROM scratch\nUSER root\n")
        for script, tool in (
            ("run-modelcard-check.sh", "modelcard"),
            ("run-inference-security-scan.sh", "inference-security"),
        ):
            with self.subTest(tool=tool):
                scan = self.root / tool
                result = subprocess.run(
                    ["bash", str(SCRIPTS / script), "--report-only"],
                    env=dict(os.environ, TARGET_DIR=str(self.target), SCAN_DIR=str(scan), SCAN_ID="fixture"),
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads((scan / tool / (tool + "-results.json")).read_text())
                self.assertTrue(report["findings"])

    def test_persistent_cache_and_stig_invalidation(self):
        spec = importlib.util.spec_from_file_location("runtime_performance", SCRIPTS / "run-stig-assessment.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cache = module._scan_cache_module().JsonCache(self.root / "cache", ttl=60)
        cache.put("CVE-2026-1234", {"id": "CVE-2026-1234"})
        self.assertEqual(cache.get("CVE-2026-1234"), {"id": "CVE-2026-1234"})
        with patch.dict(os.environ, {"EPYON_STIG_MODEL_REVISION": "a" * 64}):
            key = module._stig_reuse_key(str(self.target), {"model": "fixture"})
            self.assertIsNotNone(key)
            self.assertEqual(key, module._stig_reuse_key(str(self.target), {"model": "fixture"}))
            (self.target / "README").write_text("Changed security source\n")
            self.assertNotEqual(key, module._stig_reuse_key(str(self.target), {"model": "fixture"}))

    def test_parallel_batch_order_and_failure_visibility(self):
        spec = importlib.util.spec_from_file_location("runtime_parallel", SCRIPTS / "run-stig-assessment.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        def result(batch):
            if batch == 2:
                raise ValueError("Controlled incomplete batch")
            return batch

        results = list(module._initial_batch_calls([1, 2, 3], result, workers=2))
        self.assertEqual(results[0], 1)
        self.assertIsInstance(results[1], ValueError)
        self.assertEqual(results[2], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
