"""
Database connection and operations using AsyncPG and SQLAlchemy
"""

import asyncio
from typing import Optional, Dict, Any, List
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text

from src.core.config import settings
from src.utils.logger import get_logger


logger = get_logger(__name__)
Base = declarative_base()


class Database:
    """
    Database connection manager
    """
    
    def __init__(self):
        """Initialize database manager"""
        self.logger = logger
        self.engine = None
        self.session_maker = None
        self.pool: Optional[asyncpg.Pool] = None
        
        # Convert SQLAlchemy URL to asyncpg format
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgresql://"):
            self.async_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
        else:
            self.async_url = db_url
    
    async def connect(self):
        """Establish database connection"""
        try:
            self.logger.info("[CONNECT] Connecting to database...")
            
            # Create SQLAlchemy engine
            self.engine = create_async_engine(
                self.async_url,
                echo=settings.LOG_LEVEL.value == "DEBUG",
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,  # Test connections before using
            )
            
            # Create session maker
            self.session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            # Test connection with SQLAlchemy only
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            
            self.logger.info("[OK] Database connected successfully")
            
        except Exception as e:
            self.logger.error(f"[ERROR] Database connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Close database connection"""
        try:
            if self.pool:
                await self.pool.close()
                self.logger.info("[CONNECT] Database pool closed")
            
            if self.engine:
                await self.engine.dispose()
                self.logger.info("[CONNECT] Database engine disposed")
                
        except Exception as e:
            self.logger.error(f"Error closing database: {e}")
    
    async def is_healthy(self) -> bool:
        """Check database health"""
        try:
            if not self.engine:
                return False
            
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
            
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return False
    
    def get_session(self) -> AsyncSession:
        """Get a database session"""
        if not self.session_maker:
            raise RuntimeError("Database not connected")
        return self.session_maker()
    
    async def execute_raw(self, query: str, *args) -> List[Dict]:
        """Execute raw SQL query"""
        if not self.engine:
            raise RuntimeError("Database not connected")
        
        async with self.engine.begin() as conn:
            result = await conn.execute(text(query), args)
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]
    
    async def execute_one(self, query: str, *args) -> Optional[Dict]:
        """Execute query and return single result"""
        if not self.engine:
            raise RuntimeError("Database not connected")
        
        async with self.engine.begin() as conn:
            result = await conn.execute(text(query), args)
            row = result.fetchone()
            return dict(row._mapping) if row else None
    
    async def execute_modify(self, query: str, *args) -> str:
        """Execute INSERT/UPDATE/DELETE query"""
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def create_tables(self):
        """Create all tables from models"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self.logger.info("[OK] Tables created")
        except Exception as e:
            self.logger.error(f"Error creating tables: {e}")
            raise

