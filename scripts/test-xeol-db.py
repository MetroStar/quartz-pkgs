import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "xeol_database", ROOT / "src/quartz-evaluator/prepare-xeol-db.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


def fixture():
    return {
        "schema_version": "1.2.1",
        "generated_at": NOW.isoformat(),
        "total": 1,
        "result": [{
            "name": "python", "label": "Python",
            "links": {"html": "https://endoflife.date/python"},
            "identifiers": [
                {"type": "purl", "id": "pkg:generic/python"},
                {"type": "cpe", "id": "cpe:2.3:a:python:python"},
            ],
            "releases": [
                {
                    "name": "3.14", "isEol": False, "eolFrom": None,
                    "isLts": False, "latest": {"name": "3.14.0", "date": "2025-10-07"},
                    "releaseDate": "2025-10-07",
                },
                {
                    "name": "3.7", "isEol": True, "eolFrom": "2023-06-27",
                    "isLts": False, "latest": None, "releaseDate": "2018-06-27",
                },
                {
                    "name": "2.7", "isEol": True, "eolFrom": None,
                    "isLts": False, "latest": None, "releaseDate": None,
                },
            ],
        }],
    }


class XeolDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "database.tar.gz"

    def build(self, data):
        return module.build_archive(json.dumps(data).encode(), self.archive, now=NOW)

    def test_native_schema_dates_checksums_and_attribution(self):
        provenance = self.build(fixture())
        with tarfile.open(self.archive) as archive:
            archive.extractall(self.root / "db", filter="data")
        database = self.root / "db/xeol.db"
        metadata = json.loads((self.root / "db/metadata.json").read_text())
        self.assertEqual(metadata["checksum"], "sha256:" + hashlib.sha256(database.read_bytes()).hexdigest())
        self.assertEqual(metadata["built"], NOW.isoformat())
        self.assertEqual(provenance["coverage"], {"products": 1, "cycles": 3, "purls": 1, "cpes": 1})
        self.assertEqual(provenance["source"], module.SOURCE)
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute(
                "SELECT release_cycle, eol, eol_bool FROM cycles ORDER BY id"
            ).fetchall(), [
                ("3.14", "9999-12-31", 0),
                ("3.7", "2023-06-27", 0),
                ("2.7", "0001-01-01", 1),
            ])

    def test_stale_data_cannot_be_retimestamped(self):
        data = fixture()
        data["generated_at"] = (NOW - timedelta(days=6)).isoformat()
        with self.assertRaisesRegex(ValueError, "stale"):
            self.build(data)
        self.assertFalse(self.archive.exists())

    def test_future_or_timezone_naive_timestamps_are_rejected(self):
        for value in ((NOW + timedelta(hours=1)).isoformat(), "2026-11-05T12:00:00"):
            with self.subTest(value=value):
                data = fixture()
                data["generated_at"] = value
                with self.assertRaises(ValueError):
                    self.build(data)

    def test_empty_truncated_duplicate_or_changed_catalog_is_rejected(self):
        for change in (
            {"total": 0, "result": []},
            {"total": 2},
            {"schema_version": "2.0.0"},
            {"total": 2, "result": fixture()["result"] * 2},
        ):
            with self.subTest(change=change):
                data = fixture()
                data.update(change)
                with self.assertRaises(ValueError):
                    self.build(data)

    def test_malformed_or_ambiguous_release_data_is_rejected(self):
        for key, value in (("isEol", "false"), ("eolFrom", "yesterday"), ("isEol", True)):
            with self.subTest(key=key, value=value):
                data = fixture()
                data["result"][0]["releases"][1][key] = value
                if key == "isEol" and value is True:
                    data["result"][0]["releases"][1]["eolFrom"] = "2028-01-01"
                with self.assertRaises(ValueError):
                    self.build(data)

    def test_failed_rebuild_does_not_replace_a_verified_archive(self):
        self.build(fixture())
        original = self.archive.read_bytes()
        data = copy.deepcopy(fixture())
        data["result"][0]["identifiers"][0]["id"] = "invalid"
        with self.assertRaises(ValueError):
            self.build(data)
        self.assertEqual(original, self.archive.read_bytes())


if __name__ == "__main__":
    unittest.main()
