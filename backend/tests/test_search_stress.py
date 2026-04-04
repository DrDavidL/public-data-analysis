"""Stress test: 10 diverse queries across all 25 data sources.

Tests search → download → DuckDB load pipeline end-to-end.
Run with: uv run pytest tests/test_search_stress.py -v -s --timeout=120

Each query is designed to exercise different sources and data types.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# -- Config ------------------------------------------------------------------
QUERIES = [
    # 1. Health/demographics — should hit OWID, data.gov, Census, World Bank, CMS
    "life expectancy trends by country",
    # 2. Financial/regulatory — should hit SEC EDGAR, FDIC, FRED, CFPB
    "bank failures and financial stability",
    # 3. Environmental — should hit EPA GHGRP, EIA, OWID
    "greenhouse gas emissions by industry",
    # 4. Government spending — should hit USASpending, data.gov
    "federal defense contract spending",
    # 5. Drug safety — should hit OpenFDA, ClinicalTrials
    "drug adverse events and recalls",
    # 6. Labor/economic — should hit BLS, FRED, OECD, Census
    "unemployment rate trends united states",
    # 7. Housing/urban — should hit HUD, Census, CMAP, Chicago Health Atlas
    "affordable housing and homelessness data",
    # 8. Regulatory/policy — should hit Federal Register, data.gov
    "clean energy executive orders and regulations",
    # 9. Democracy/governance — should hit V-Dem, World Bank
    "corruption and democracy indicators",
    # 10. Clinical/research — should hit ClinicalTrials, Harvard Dataverse, CMS
    "cancer clinical trials enrollment and outcomes",
]

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("stress_test")
logger.setLevel(logging.INFO)


async def run_search(query: str) -> dict:
    """Run a single search query and return structured results."""
    from app.services.dataset_search import ALL_SOURCES, _refine_query, _search_source

    refined = await _refine_query(query)

    source_results = {}
    tasks = []
    for src in ALL_SOURCES:
        name = getattr(src, "source_name", "unknown")
        tasks.append((name, _search_source(src, refined, limit=3)))

    gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

    total = 0
    downloadable = 0
    errors = []
    for (name, _), result in zip(tasks, gathered, strict=True):
        if isinstance(result, Exception):
            errors.append(f"{name}: {type(result).__name__}: {result}")
            source_results[name] = {"count": 0, "downloadable": 0, "error": str(result)}
        else:
            dl = sum(1 for r in result if r.download_url)
            total += len(result)
            downloadable += dl
            if result:
                source_results[name] = {
                    "count": len(result),
                    "downloadable": dl,
                    "titles": [r.title[:80] for r in result[:2]],
                }

    return {
        "query": query,
        "refined": refined,
        "total_results": total,
        "downloadable_results": downloadable,
        "sources_with_results": len(source_results),
        "errors": errors,
        "by_source": source_results,
    }


async def try_download_first(query_result: dict) -> dict:
    """Attempt to download the first downloadable result from a query."""
    import tempfile

    import duckdb

    from app.services.dataset_search import ALL_SOURCES, _search_source
    from app.services.datastore import load_dataset

    # Find first downloadable result
    for src in ALL_SOURCES:
        name = getattr(src, "source_name", "unknown")
        if name not in query_result["by_source"]:
            continue
        info = query_result["by_source"][name]
        if info.get("downloadable", 0) == 0:
            continue

        # Re-search to get full result objects
        results = await _search_source(src, query_result["refined"], limit=3)
        for r in results:
            if not r.download_url:
                continue

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    dest_dir = Path(tmpdir)
                    file_path = await src.download(r.id, dest_dir)
                    if not file_path:
                        return {
                            "status": "download_empty",
                            "source": name,
                            "dataset": r.title[:80],
                        }

                    size = file_path.stat().st_size
                    conn = duckdb.connect()
                    try:
                        table = load_dataset(conn, file_path, r.id)
                        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        cols = conn.execute(f"DESCRIBE {table}").fetchall()
                        return {
                            "status": "success",
                            "source": name,
                            "dataset": r.title[:80],
                            "file_size": size,
                            "file_type": file_path.suffix,
                            "rows": row_count,
                            "columns": len(cols),
                            "column_names": [c[0] for c in cols[:10]],
                        }
                    except Exception as e:
                        return {
                            "status": "load_failed",
                            "source": name,
                            "dataset": r.title[:80],
                            "file_size": size,
                            "file_type": file_path.suffix,
                            "error": str(e)[:200],
                        }
                    finally:
                        conn.close()
            except Exception as e:
                return {
                    "status": "download_failed",
                    "source": name,
                    "dataset": r.title[:80],
                    "error": str(e)[:200],
                }

    return {"status": "no_downloadable_results"}


async def main():
    results = []
    for i, query in enumerate(QUERIES):
        logger.info("--- Query %d/10: %s ---", i + 1, query)

        search_result = await run_search(query)
        logger.info(
            "  Search: %d total, %d downloadable, %d sources, %d errors",
            search_result["total_results"],
            search_result["downloadable_results"],
            search_result["sources_with_results"],
            len(search_result["errors"]),
        )
        for name, info in search_result["by_source"].items():
            if info.get("count", 0) > 0:
                titles = info.get("titles", [])
                first = titles[0] if titles else ""
                logger.info("  %s: %d results — %s", name, info["count"], first)

        # Try downloading first result
        download_result = await try_download_first(search_result)
        status = download_result.get("status", "unknown")
        if status == "success":
            logger.info(
                "  Download OK: %s (%s, %d rows, %d cols, %s)",
                download_result["dataset"],
                download_result["source"],
                download_result["rows"],
                download_result["columns"],
                download_result["file_type"],
            )
        else:
            logger.warning("  Download: %s — %s", status, json.dumps(download_result)[:200])

        results.append(
            {
                "search": search_result,
                "download": download_result,
            }
        )

    # Summary
    logger.info("\n=== SUMMARY ===")
    for i, r in enumerate(results):
        s = r["search"]
        d = r["download"]
        status_icon = "OK" if d["status"] == "success" else "FAIL"
        logger.info(
            "%2d. [%4s] %s — %d results, %d downloadable | %s",
            i + 1,
            status_icon,
            s["query"][:50],
            s["total_results"],
            s["downloadable_results"],
            d.get("source", "none"),
        )
        if d["status"] == "success":
            logger.info(
                "          → %d rows, %d cols (%s)",
                d["rows"],
                d["columns"],
                d["file_type"],
            )
        elif d.get("error"):
            logger.info("          → %s", d["error"][:100])

    # Write full results to file
    out_path = Path(__file__).parent / "stress_test_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    logger.info("\nFull results written to %s", out_path)

    # Exit code based on results
    failures = sum(1 for r in results if r["download"]["status"] != "success")
    if failures:
        logger.warning("%d/%d queries failed to produce a loadable dataset", failures, len(results))
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
