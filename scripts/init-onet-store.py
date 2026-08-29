from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from pyoxigraph import RdfFormat, Store

ROOT = Path(__file__).resolve().parent.parent
DATASET = os.getenv("ONET_DATASET", "db_31_0_nt")
SOURCE_DIR = ROOT / "data" / DATASET
STORE_DIR = ROOT / ".cache" / "onet-store"
READY = STORE_DIR / "READY"
SEARCH_INDEX = STORE_DIR / "search.sqlite"
BRIGHT_OUTLOOK = SOURCE_DIR / "BrightOutlook.csv"


def main() -> None:
    sources = sorted(SOURCE_DIR.glob("*.nt"))
    if not sources:
        raise SystemExit("O*NET data is missing. Run scripts/init-onet-data.sh first.")
    if not BRIGHT_OUTLOOK.exists():
        raise SystemExit("Bright Outlook data is missing. Run scripts/init-onet-data.sh first.")
    newest_source = max(path.stat().st_mtime_ns for path in [*sources, BRIGHT_OUTLOOK])
    marker = f"{DATASET}:{len(sources)}:{newest_source}:bright-outlook"
    if READY.exists() and READY.read_text() == marker and SEARCH_INDEX.exists():
        print(f"O*NET SPARQL store is ready ({len(sources)} source files).")
        return

    if not READY.exists() or READY.read_text() != marker:
        shutil.rmtree(STORE_DIR, ignore_errors=True)
        database_dir = STORE_DIR / "oxigraph"
        database_dir.mkdir(parents=True)
        store = Store(str(database_dir))
        for position, path in enumerate(sources, start=1):
            print(f"[{position}/{len(sources)}] Loading {path.name}", flush=True)
            with path.open("rb") as source:
                store.bulk_load(source, format=RdfFormat.N_TRIPLES)
        store.flush()
        triple_count = len(store)
        del store
        READY.write_text(marker)
        print(f"Loaded {triple_count:,} triples into {database_dir}.")

    SEARCH_INDEX.unlink(missing_ok=True)
    sys.path.insert(0, str(ROOT))
    from app.onet import OnetGraph

    graph = OnetGraph(STORE_DIR)
    graph.load()
    print(f"Indexed search features for {graph.occupation_count:,} occupations.")


if __name__ == "__main__":
    main()