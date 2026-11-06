import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/extract-images.sh").read_text()
EXTRACTION = SOURCE.split(
    '  echo "$CHART_VALUES" | awk -v appver="$APP_VERSION" ', 1
)[1].split('>> "$IMAGES_FILE"', 1)[0]
COMMAND = 'echo "$CHART_VALUES" | awk -v appver="$APP_VERSION" ' + EXTRACTION


class ExtractedImageTests(unittest.TestCase):
    def extract(self, values, version):
        result = subprocess.run(
            ["bash", "-euc", COMMAND],
            env={**os.environ, "CHART_VALUES": values, "APP_VERSION": version},
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.splitlines()

    def test_split_registry_repository_and_name_are_combined(self):
        self.assertEqual(self.extract(
            'image:\n  registry: docker.io\n  repository: library\n'
            '  name: postgres\n  tag: "18.3-alpine"\n', "0.9.4"
        ), ["docker.io/library/postgres:18.3-alpine"])

    def test_chart_default_tags_match_the_rendered_helpers(self):
        for repository, version in (
            ("registry.k8s.io/external-dns/external-dns", "0.21.0"),
            ("nvcr.io/nvidia/k8s-device-plugin", "0.17.1"),
        ):
            with self.subTest(repository=repository):
                self.assertEqual(self.extract(
                    f'image:\n  repository: {repository}\n  tag: ""\n', version
                ), [f"{repository}:v{version}"])

    def test_explicit_tags_and_other_default_tags_are_preserved(self):
        for repository, tag, version, expected in (
            ("nvcr.io/nvidia/k8s-device-plugin", "custom", "0.17.1", "custom"),
            ("registry.k8s.io/external-dns/external-dns", "", "v0.21.0", "v0.21.0"),
            ("docker.io/example/controller", "", "0.21.0", "0.21.0"),
        ):
            with self.subTest(repository=repository, tag=tag):
                self.assertEqual(self.extract(
                    f'image:\n  repository: {repository}\n  tag: "{tag}"\n', version
                ), [f"{repository}:{expected}"])

    def test_name_does_not_leak_into_later_repository_entries(self):
        self.assertEqual(self.extract(
            'first:\n  registry: docker.io\n  repository: library\n'
            '  name: postgres\n  tag: "18.3-alpine"\n'
            'second:\n  repository: quay.io/example/controller\n  tag: "1.2.3"\n',
            "0.9.4",
        ), ["docker.io/library/postgres:18.3-alpine", "quay.io/example/controller:1.2.3"])

    def test_missing_tag_and_app_version_do_not_produce_a_bare_v_tag(self):
        self.assertEqual(self.extract(
            'image:\n  repository: nvcr.io/nvidia/k8s-device-plugin\n  tag: ""\n', ""
        ), [])

    def test_short_diff_summaries_do_not_turn_success_into_failure(self):
        for old, new in (
            (["old"], ["new"]), (["old"], ["old", "new"]),
            (["old", "removed"], ["old"]), (["old"], ["old"]),
        ):
            with self.subTest(old=old, new=new), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "manifest.json"
                output.write_text(json.dumps([{"source": source} for source in new]))
                subprocess.run(
                    ["bash", "-euc", SOURCE[SOURCE.index("FINAL_COUNT="):]],
                    env={
                        **os.environ,
                        "EXISTING_MANIFEST": json.dumps([{"source": source} for source in old]),
                        "OUTPUT_PATH": str(output),
                    },
                    text=True,
                    capture_output=True,
                    check=True,
                )


if __name__ == "__main__":
    unittest.main()
