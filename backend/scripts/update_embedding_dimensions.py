"""Update database schema for 8192-dimensional Qwen3 embeddings.

This script:
1. Adds new embedding columns with 8192 dimensions
2. Preserves existing data
3. Can be run safely multiple times (idempotent)
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core'))

from sqlalchemy import text
from database.db_manager import DatabaseManager
from utils.logger import get_logger
from config import Config

logger = get_logger(__name__)


def update_schema():
    """Update database schema for Qwen3 embeddings."""
    db = DatabaseManager()
    
    logger.info("Updating database schema for 8192-dimensional embeddings...")
    
    with db.get_session() as session:
        try:
            # Check if pgvector extension exists
            result = session.execute(
                text("SELECT * FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()
            
            if not result:
                logger.info("Creating pgvector extension...")
                session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                session.commit()
            
            # Update messages table
            logger.info("Updating messages table...")
            
            # Check if qwen_embedding column exists
            check_col = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='messages' AND column_name='qwen_embedding'
            """)
            
            result = session.execute(check_col).fetchone()
            
            if not result:
                logger.info("Adding qwen_embedding column to messages...")
                session.execute(text("""
                    ALTER TABLE messages 
                    ADD COLUMN IF NOT EXISTS qwen_embedding vector(8192)
                """))
                session.commit()
                
                # Create HNSW index for vector similarity search (supports high dimensions)
                logger.info("Creating HNSW vector index on messages...")
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS messages_qwen_embedding_idx 
                    ON messages 
                    USING hnsw (qwen_embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                """))
                session.commit()
            else:
                logger.info("qwen_embedding column already exists on messages")
            
            # Update gmail_messages table
            logger.info("Updating gmail_messages table...")
            
            check_col = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='gmail_messages' AND column_name='qwen_embedding'
            """)
            
            result = session.execute(check_col).fetchone()
            
            if not result:
                logger.info("Adding qwen_embedding column to gmail_messages...")
                session.execute(text("""
                    ALTER TABLE gmail_messages 
                    ADD COLUMN IF NOT EXISTS qwen_embedding vector(8192)
                """))
                session.commit()
                
                # Create HNSW index for vector similarity search (supports high dimensions)
                logger.info("Creating HNSW vector index on gmail_messages...")
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS gmail_messages_qwen_embedding_idx 
                    ON gmail_messages 
                    USING hnsw (qwen_embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                """))
                session.commit()
            else:
                logger.info("qwen_embedding column already exists on gmail_messages")
            
            # Create full-text search indexes if not exists
            logger.info("Creating full-text search indexes...")
            
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS messages_text_idx 
                ON messages 
                USING gin(to_tsvector('english', text))
            """))
            
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS gmail_messages_text_idx 
                ON gmail_messages 
                USING gin(to_tsvector('english', 
                    COALESCE(subject, '') || ' ' || COALESCE(body_text, '')))
            """))
            
            session.commit()
            
            logger.info("✓ Database schema updated successfully!")
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. Run: python backend/scripts/generate_embeddings.py")
            logger.info("   This will generate Qwen3 embeddings for all existing data")
            logger.info("")
            logger.info("2. Start the API server: uvicorn backend.api.main:app --reload")
        
        except Exception as e:
            logger.error(f"Error updating schema: {e}")
            session.rollback()
            raise


if __name__ == "__main__":
    update_schema()
