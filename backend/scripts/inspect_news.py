import asyncio
from backend.database.session import session_scope
from backend.database.models.security_news import SecurityNewsArticle
from sqlalchemy import select

async def run():
    async with session_scope() as s:
        res = await s.scalars(select(SecurityNewsArticle))
        items = list(res)
        print("COUNT:", len(items))
        for idx, i in enumerate(items[:5]):
            print(f"{idx}: {i.title} | Category: {i.category} | Source: {i.source}")

if __name__ == '__main__':
    asyncio.run(run())
