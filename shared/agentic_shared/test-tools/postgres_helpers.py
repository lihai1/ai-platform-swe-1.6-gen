"""PostgreSQL helpers for integration testing"""
import asyncio
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
import asyncpg


class PostgresTestClient:
    """Test wrapper for PostgreSQL client with auto-cleanup"""
    
    def __init__(self, dsn: str = "postgresql://agentic:agentic@localhost:5433/agentic"):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(self.dsn)
    
    async def close(self) -> None:
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
    
    async def execute(self, query: str, *args) -> str:
        """Execute SQL query"""
        if not self.pool:
            raise RuntimeError("PostgreSQL not connected")
        
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> list:
        """Fetch rows from query"""
        if not self.pool:
            raise RuntimeError("PostgreSQL not connected")
        
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[dict]:
        """Fetch single row from query"""
        if not self.pool:
            raise RuntimeError("PostgreSQL not connected")
        
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def cleanup_table(self, table_name: str) -> None:
        """Clean up all data from a table"""
        await self.execute(f"TRUNCATE TABLE {table_name} CASCADE")


@asynccontextmanager
async def postgres_client(dsn: str = "postgresql://agentic:agentic@localhost:5433/agentic"):
    """Context manager for PostgreSQL test client"""
    client = PostgresTestClient(dsn)
    try:
        await client.connect()
        yield client
    finally:
        await client.close()


async def wait_for_postgres(dsn: str = "postgresql://agentic:agentic@localhost:5433/agentic", max_retries: int = 10) -> bool:
    """Wait for PostgreSQL to be ready"""
    for _ in range(max_retries):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            return True
        except Exception:
            await asyncio.sleep(1)
    return False
