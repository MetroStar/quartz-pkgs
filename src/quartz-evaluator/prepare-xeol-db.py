#!/usr/bin/env python3
"""Build a Xeol schema-1 archive from the public endoflife.date API v1."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import urllib.request


SOURCE = "https://endoflife.date/api/v1/products/full/"
MAX_AGE = timedelta(days=5)
MAX_BYTES = 32 * 1024 * 1024


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Catalog generation timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def date_value(value, default):
    if value is None:
        return default
    datetime.strptime(value, "%Y-%m-%d")
    return value


def build_archive(raw, destination, now=None):
    now = now or datetime.now(timezone.utc)
    catalog = json.loads(raw)
    if not catalog["schema_version"].startswith("1."):
        raise ValueError("Unsupported endoflife.date API schema")
    generated = timestamp(catalog["generated_at"])
    if now - generated > MAX_AGE or generated - now > timedelta(minutes=15):
        raise ValueError("EOL catalog generation timestamp is stale or in the future")
    products = catalog["result"]
    if not products or catalog["total"] != len(products):
        raise ValueError("EOL catalog is empty or incomplete")
    names = [product["name"] for product in products]
    if len(set(names)) != len(names):
        raise ValueError("EOL catalog contains duplicate products")
    counts = {"products": len(products), "cycles": 0, "purls": 0, "cpes": 0}
    built = generated.isoformat()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        directory = Path(directory)
        database = directory / "xeol.db"
        connection = sqlite3.connect(database)
        try:
            connection.executescript("""
                CREATE TABLE id (build_timestamp TEXT NOT NULL, schema_version INTEGER NOT NULL);
                CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, permalink TEXT NOT NULL);
                CREATE TABLE cycles (
                    id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
                    release_cycle TEXT NOT NULL, eol DATETIME NOT NULL, eol_bool BOOLEAN NOT NULL,
                    lts TEXT NOT NULL, latest_release TEXT NOT NULL,
                    latest_release_date DATETIME NOT NULL, release_date DATETIME NOT NULL
                );
                CREATE TABLE purls (product_id INTEGER NOT NULL REFERENCES products(id), purl TEXT NOT NULL);
                CREATE TABLE cpes (product_id INTEGER NOT NULL REFERENCES products(id), cpe TEXT NOT NULL);
                CREATE INDEX purls_lookup ON purls(purl);
                CREATE INDEX cpes_lookup ON cpes(cpe);
            """)
            connection.execute("INSERT INTO id VALUES (?, 1)", (built,))
            for product_id, product in enumerate(products, 1):
                name = product["name"]
                if not isinstance(name, str) or not name or not product["releases"]:
                    raise ValueError("EOL product name or release history is missing")
                permalink = product["links"]["html"]
                if permalink != f"https://endoflife.date/{name}":
                    raise ValueError("EOL product permalink does not match its source")
                connection.execute(
                    "INSERT INTO products VALUES (?, ?, ?)",
                    (product_id, product["label"], permalink),
                )
                seen = set()
                for identifier in product["identifiers"]:
                    kind, value = identifier["type"], identifier["id"]
                    if kind not in {"purl", "cpe"}:
                        continue
                    if not isinstance(value, str) or not value.startswith(
                        "pkg:" if kind == "purl" else "cpe:"
                    ):
                        raise ValueError("Malformed EOL package identifier")
                    if (kind, value) in seen:
                        raise ValueError("Duplicate EOL package identifier")
                    seen.add((kind, value))
                    if kind == "purl":
                        connection.execute("INSERT INTO purls VALUES (?, ?)", (product_id, value))
                        counts["purls"] += 1
                    else:
                        connection.execute("INSERT INTO cpes VALUES (?, ?)", (product_id, value))
                        counts["cpes"] += 1
                releases = set()
                for release in product["releases"]:
                    cycle = release["name"]
                    if not isinstance(cycle, str) or not cycle or cycle in releases:
                        raise ValueError("Missing or duplicate EOL release cycle")
                    releases.add(cycle)
                    if type(release["isEol"]) is not bool or type(release["isLts"]) is not bool:
                        raise ValueError("EOL and LTS flags must be booleans")
                    eol = date_value(release["eolFrom"], None)
                    if eol is not None and (eol < generated.date().isoformat()) != release["isEol"]:
                        raise ValueError("EOL date and current EOL flag disagree")
                    latest = release["latest"]
                    connection.execute(
                        "INSERT INTO cycles VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            product_id, cycle,
                            eol or ("0001-01-01" if release["isEol"] else "9999-12-31"),
                            release["isEol"] and eol is None,
                            "true" if release["isLts"] else "false",
                            latest["name"] if latest else "",
                            date_value(latest["date"] if latest else None, "0001-01-01"),
                            date_value(release["releaseDate"], "0001-01-01"),
                        ),
                    )
                    counts["cycles"] += 1
            if not counts["purls"] or not counts["cpes"]:
                raise ValueError("EOL catalog is missing package or operating-system identifiers")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Generated EOL database failed SQLite integrity validation")
            connection.commit()
        finally:
            connection.close()
        checksum = "sha256:" + hashlib.sha256(database.read_bytes()).hexdigest()
        (directory / "metadata.json").write_text(json.dumps({
            "built": built, "version": 1, "checksum": checksum,
        }))
        provenance = {
            "provider": "endoflife.date",
            "source": SOURCE,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_generated_at": built,
            "source_license": "https://github.com/endoflife-date/endoflife.date/blob/master/LICENSE",
            "coverage": counts,
            "vulnerability_enrichment": "Not supplied; use the mandatory vulnerability scanners",
        }
        (directory / "provider.json").write_text(json.dumps(provenance, indent=2))
        archive_path = directory / "database.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for name in ("xeol.db", "metadata.json", "provider.json"):
                archive.add(directory / name, arcname=name)
        archive_path.replace(destination)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    request = urllib.request.Request(SOURCE, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200 or response.headers.get_content_type() != "application/json":
            raise ValueError("EOL provider did not return a JSON catalog")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("EOL catalog exceeds the maximum supported size")
    print(json.dumps(build_archive(raw, args.archive)))


if __name__ == "__main__":
    main()
