"""Remediate existing email records where received_at was populated with sync run timestamp.

Updates received_at to sent_at for existing incoming emails where sent_at is present
and received_at is noticeably after sent_at (> 10 minutes difference caused by sync execution time).
"""
import asyncio
import logging
import os
from pathlib import Path
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.core.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def remediate_timestamps():
    async with AsyncSessionLocal() as session:
        # Check how many emails have corrupted received_at
        count_stmt = text("""
            SELECT count(*) 
            FROM emails 
            WHERE sent_at IS NOT NULL 
              AND received_at IS NOT NULL 
              AND received_at > sent_at + interval '10 minutes';
        """)
        res = await session.execute(count_stmt)
        count = res.scalar() or 0
        logger.info("Found %d emails with sync-stamped received_at.", count)

        if count > 0:
            update_stmt = text("""
                UPDATE emails 
                SET received_at = sent_at 
                WHERE sent_at IS NOT NULL 
                  AND received_at IS NOT NULL 
                  AND received_at > sent_at + interval '10 minutes';
            """)
            await session.execute(update_stmt)
            await session.commit()
            logger.info("Successfully updated %d emails to use accurate sent_at as received_at.", count)
        else:
            logger.info("No emails require remediation.")


if __name__ == "__main__":
    asyncio.run(remediate_timestamps())
