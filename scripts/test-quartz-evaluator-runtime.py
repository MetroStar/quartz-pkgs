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


if __name__ == "__main__":
    unittest.main(verbosity=2)
