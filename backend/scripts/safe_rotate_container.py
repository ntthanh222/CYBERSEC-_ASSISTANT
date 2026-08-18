import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config.settings import get_settings
from backend.core.password_hash import hash_password

# Prevent python from buffering stdout so the message is printed immediately
sys.stdout.reconfigure(line_buffering=True)


async def main():
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    passwords = {
        "demo_user": os.environ.get("DEMO_USER_PASSWORD"),
        "demo_analyst": os.environ.get("DEMO_ANALYST_PASSWORD"),
        "demo_superadmin": os.environ.get("DEMO_SUPERADMIN_PASSWORD"),
        "demo_disabled": os.environ.get("DEMO_USER_PASSWORD"),
    }

    async with engine.begin() as conn:
        for username, pwd in passwords.items():
            if pwd:
                pwd_hash = hash_password(pwd)
                await conn.execute(
                    text("UPDATE local_admin_credentials SET password_hash = :h WHERE username = :u"),
                    {"h": pwd_hash, "u": username},
                )

    print("DB SYNC: SUCCESS")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
