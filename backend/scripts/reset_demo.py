"""Reset demo/QA seed data (truncates demo_seed_marker only).

Refuses to run against ENVIRONMENT=production. Only touches the seed
framework table this Phase's seed_demo.py owns — never a real user table.
"""
import argparse
import logging
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from backend.config.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("reset_demo")


def run(dry_run: bool) -> int:
    settings = get_settings()
    if settings.is_production:
        logger.error("Refusing to reset: ENVIRONMENT=production.")
        return 1

    logger.info("Resetting demo seed data environment=%s dry_run=%s", settings.environment, dry_run)
    engine = create_engine(settings.sync_database_url)
    try:
        with engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM demo_seed_marker")).scalar_one()
            prefix = "[dry-run] would " if dry_run else ""
            logger.info("%sdelete %d row(s) from demo_seed_marker", prefix, count)
            if not dry_run:
                conn.execute(text("DELETE FROM demo_seed_marker"))
    except SQLAlchemyError:
        logger.exception("reset_failed")
        return 1
    finally:
        engine.dispose()

    logger.info("Reset complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Log actions without writing.")
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
