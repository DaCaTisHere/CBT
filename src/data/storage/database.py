"""
Database connection and session management

Provides async database connection using asyncpg and SQLAlchemy.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy import text

from src.core.config import settings
from src.utils.logger import get_logger
from src.data.storage.models import Base


logger = get_logger(__name__)


class Database:
    """
    Database manager class
    
    Provides high-level database operations and connection management.
    """
    
    def __init__(self):
        self.logger = logger
        self.is_connected = False
    
    async def connect(self):
        """Initialize database connection"""
        try:
            await init_database()
            self.is_connected = True
            self.logger.info("[OK] Database connected")
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Close database connection"""
        try:
            await close_database()
            self.is_connected = False
            self.logger.info("[OK] Database disconnected")
        except Exception as e:
            self.logger.error(f"Database disconnect failed: {e}")
    
    async def is_healthy(self) -> bool:
        """Check if database is healthy"""
        return await test_connection()
    
    def get_session(self):
        """Get a database session"""
        return get_db_session()


# Global engine and session factory
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """
    Get database URL with async driver
    
    Converts standard PostgreSQL URL to async version.
    """
    url = settings.DATABASE_URL
    
    # Convert to async URL if needed
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    elif url.startswith("sqlite://"):
        url = url.replace("sqlite://", "sqlite+aiosqlite://")
    
    return url


def get_engine() -> AsyncEngine:
    """Get or create the database engine"""
    global _engine
    
    if _engine is None:
        url = get_database_url()
        
        # SQLite doesn't support pool_size/max_overflow
        if "sqlite" in url:
            _engine = create_async_engine(
                url,
                echo=settings.LOG_LEVEL.value == "DEBUG",
            )
        else:
            _engine = create_async_engine(
                url,
                echo=settings.LOG_LEVEL.value == "DEBUG",
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
        
        logger.info(f"Database engine created: {url.split('@')[-1] if '@' in url else url}")
    
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory"""
    global _async_session_factory
    
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Session factory created")
    
    return _async_session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session (async context manager)
    
    Usage:
        async with get_db_session() as session:
            result = await session.execute(query)
    """
    session_factory = get_session_factory()
    session = session_factory()
    
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        await session.close()


async def init_database():
    """
    Initialize database
    
    Creates all tables if they don't exist.
    WARNING: This should only be used for local development.
    Use Alembic migrations for production!
    """
    try:
        engine = get_engine()
        url = get_database_url()
        
        # Create schemas if using PostgreSQL (SQLite doesn't support schemas)
        if "postgresql" in url:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE SCHEMA IF NOT EXISTS trading"))
                await conn.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))
                logger.info("Database schemas created")
        else:
            logger.info("Using SQLite - schemas not needed")
        
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created")
        
        logger.info("[OK] Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


async def close_database():
    """Close database connections"""
    global _engine
    
    if _engine:
        await _engine.dispose()
        logger.info("Database connections closed")
        _engine = None


async def test_connection() -> bool:
    """
    Test database connection
    
    Returns:
        bool: True if connection successful
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.fetchone()
            
            if row and row[0] == 1:
                logger.info("[OK] Database connection test successful")
                return True
            else:
                logger.error("Database connection test failed")
                return False
                
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


# ==========================================
# Helper Functions
# ==========================================

async def create_token(session: AsyncSession, **kwargs):
    """Helper to create a token"""
    from src.data.storage.models import Token
    
    token = Token(**kwargs)
    session.add(token)
    await session.flush()
    return token


async def create_trade(session: AsyncSession, **kwargs):
    """Helper to create a trade"""
    from src.data.storage.models import Trade
    
    trade = Trade(**kwargs)
    session.add(trade)
    await session.flush()
    return trade


async def create_position(session: AsyncSession, **kwargs):
    """Helper to create a position"""
    from src.data.storage.models import Position
    
    position = Position(**kwargs)
    session.add(position)
    await session.flush()
    return position
