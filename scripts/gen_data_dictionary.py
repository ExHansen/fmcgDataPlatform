"""Generate docs/data_dictionary.md dari artefak dbt (manifest.json + catalog.json).

    python scripts/run_dbt.py docs generate
    python scripts/gen_data_dictionary.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path(os.environ.get("DBT_TARGET_PATH", ROOT / "dbt" / "target"))
OUT = ROOT / "docs" / "data_dictionary.md"
SCHEMAS = ["marts", "ops"]          # yang dibaca dashboard & analis


def main() -> int:
    manifest = json.loads((TARGET / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((TARGET / "catalog.json").read_text(encoding="utf-8"))
    nodes = [n for n in manifest["nodes"].values()
             if n["resource_type"] == "model" and n["schema"] in SCHEMAS]
    nodes.sort(key=lambda n: (SCHEMAS.index(n["schema"]), n["name"]))

    lines = ["# Kamus Data", "",
             "Di-generate dari dbt oleh `scripts/gen_data_dictionary.py`. Jangan edit manual; ubah deskripsi di "
             "file `_*.yml` / komentar model lalu generate ulang. Lineage lengkap: `python scripts/run_dbt.py docs serve`.",
             ""]
    for schema in SCHEMAS:
        lines += [f"## Schema `{schema}`", ""]
        for n in (x for x in nodes if x["schema"] == schema):
            cat = catalog["nodes"].get(n["unique_id"], {})
            cols = cat.get("columns", {})
            desc = (n.get("description") or "").strip().replace("\n", " ")
            mat = n["config"].get("materialized")
            lines += [f"### `{schema}.{n['name']}`", "", f"{desc or '_(tanpa deskripsi)_'}", "",
                      f"Materialisasi: `{mat}` · Sumber: `{n['original_file_path'].replace(chr(92), '/')}`", "",
                      "| Kolom | Tipe | Deskripsi |", "|---|---|---|"]
            documented = n.get("columns", {})
            for col in sorted(cols.values(), key=lambda c: c["index"]):
                d = (documented.get(col["name"], {}).get("description") or "").replace("\n", " ").replace("|", "\\|")
                lines.append(f"| `{col['name']}` | {col['type']} | {d} |")
            lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(nodes)} model ditulis ke {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
