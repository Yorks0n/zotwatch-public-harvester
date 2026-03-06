from __future__ import annotations

import typer

from src.jobs.backfill import run_backfill
from src.jobs.cleanup import run_cleanup
from src.jobs.harvest_all import run_harvest_all
from src.jobs.reindex_candidates import run_reindex_candidates

app = typer.Typer(help="Public literature harvester for ZotWatch.")


@app.command("harvest-all")
def harvest_all_command() -> None:
    """Run all enabled incremental harvesters."""
    run_harvest_all()


@app.command("backfill")
def backfill_command(source: str, start: str, end: str) -> None:
    """Run a bounded backfill for a single source."""
    run_backfill(source=source, start=start, end=end)


@app.command("cleanup")
def cleanup_command() -> None:
    """Delete stale records based on retention settings."""
    run_cleanup()


@app.command("reindex-candidates")
def reindex_candidates_command() -> None:
    """Recompute candidate visibility and clean up seed records."""
    run_reindex_candidates()


if __name__ == "__main__":
    app()
