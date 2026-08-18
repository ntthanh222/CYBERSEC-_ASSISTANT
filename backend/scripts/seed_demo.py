"""Idempotent demo/QA seed runner.

Phase 1/1.5 scope: the schema has no business entities yet (auth, assets,
CVEs, etc. all start in Phase 2+), so there is nothing real to seed. This
script instead seeds the `demo_seed_marker` framework table — one row per
named seed batch, idempotent via a UNIQUE(seed_key) constraint — so future
phases can register real seed batches here without redesigning the runner.

Refuses to run against ENVIRONMENT=production. Never touches real user
credentials; any password-bearing seed added in a later phase must be
clearly marked as demo-only and never reused in a real environment.
"""
import argparse
import logging
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from backend.config.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_demo")

# Registry of seed batches. Phase 2+ appends real entities here (e.g. a demo
# user) instead of hand-rolling a new script.
SEED_BATCHES = [
    "phase1-bootstrap",
]


def run(dry_run: bool) -> int:
    settings = get_settings()
    if settings.is_production:
        logger.error("Refusing to seed: ENVIRONMENT=production.")
        return 1

    logger.info("Seeding environment=%s dry_run=%s", settings.environment, dry_run)
    engine = create_engine(settings.sync_database_url)
    try:
        with engine.begin() as conn:
            for seed_key in SEED_BATCHES:
                existing = conn.execute(
                    text("SELECT 1 FROM demo_seed_marker WHERE seed_key = :key"),
                    {"key": seed_key},
                ).first()
                if existing:
                    logger.info("skip (already seeded): %s", seed_key)
                    continue
                logger.info("%sseed: %s", "[dry-run] would " if dry_run else "", seed_key)
                if not dry_run:
                    conn.execute(
                        text("INSERT INTO demo_seed_marker (seed_key) VALUES (:key)"),
                        {"key": seed_key},
                    )
    except SQLAlchemyError:
        logger.exception("seed_failed")
        return 1
    finally:
        engine.dispose()

    logger.info("Seed run complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Log actions without writing.")
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
