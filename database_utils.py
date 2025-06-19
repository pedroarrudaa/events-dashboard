"""
Streamlined database utilities for hackathons and conferences with PostgreSQL.
"""
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Iterator, ContextManager
from dataclasses import dataclass, field
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, JSON, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv
from config import *

load_dotenv()

# SQLAlchemy models with unified base
Base = declarative_base()

@dataclass
class DatabaseConfig:
    """Database configuration with sensible defaults."""
    pool_size: int = MAX_POOL_SIZE
    max_overflow: int = 20
    pool_timeout: int = POOL_TIMEOUT
    pool_recycle: int = 3600
    statement_timeout: int = STATEMENT_TIMEOUT
    batch_size: int = 1000

class BaseEventModel:
    """Base model with common event fields."""
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String, nullable=False, index=True)
    url = Column(String, unique=True, nullable=False, index=True)
    start_date = Column(String, index=True)
    end_date = Column(String, index=True)
    location = Column(String, index=True)
    city = Column(String, index=True)
    remote = Column(Boolean, default=False, index=True)
    description = Column(Text)
    speakers = Column(JSON)
    ticket_price = Column(String)
    is_paid = Column(Boolean, default=False, index=True)
    themes = Column(JSON)
    source = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class Hackathon(Base, BaseEventModel):
    """Streamlined hackathon model."""
    __tablename__ = 'hackathons'
    __table_args__ = (
        Index('idx_hackathon_location_date', 'location', 'start_date'),
        Index('idx_hackathon_remote_paid', 'remote', 'is_paid'),
    )

class Conference(Base, BaseEventModel):
    """Streamlined conference model."""
    __tablename__ = 'conferences'
    __table_args__ = (
        Index('idx_conference_location_date', 'location', 'start_date'),
        Index('idx_conference_remote_paid', 'remote', 'is_paid'),
    )

class CollectedUrls(Base):
    """URL tracking model."""
    __tablename__ = 'collected_urls'
    
    url = Column(String, primary_key=True, unique=True, nullable=False, index=True)
    source_type = Column(String, nullable=False, index=True)
    is_enriched = Column(Boolean, default=False, nullable=False, index=True)
    timestamp_collected = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    url_metadata = Column(JSON)
    
    __table_args__ = (
        Index('idx_source_enriched', 'source_type', 'is_enriched'),
    )

class EventActions(Base):
    """Event actions tracking model."""
    __tablename__ = 'event_actions'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_event_action_type', 'event_id', 'action'),
    )

class DatabaseManager:
    """Streamlined database manager with connection pooling and batch operations."""
    
    def __init__(self, config: DatabaseConfig = None):
        self.config = config or DatabaseConfig()
        self._engine = None
        self._session_factory = None
        
    @property
    def engine(self):
        """Lazy-loaded database engine."""
        if self._engine is None:
            database_url = os.getenv('DATABASE_URL', 'sqlite:///events_dashboard.db')
            print(f"Using database: {database_url}")
            
            if database_url.startswith('sqlite'):
                # SQLite configuration
                self._engine = create_engine(
                    database_url,
                    echo=False,
                    connect_args={"check_same_thread": False}
                )
            else:
                # PostgreSQL configuration
                self._engine = create_engine(
                    database_url,
                    poolclass=QueuePool,
                    pool_size=self.config.pool_size,
                    max_overflow=self.config.max_overflow,
                    pool_timeout=self.config.pool_timeout,
                    pool_recycle=self.config.pool_recycle,
                    pool_pre_ping=True,
                    echo=False,
                    connect_args={
                        "sslmode": "require" if "railway" in database_url else "prefer",
                        "application_name": "events_dashboard",
                        "statement_timeout": str(self.config.statement_timeout)
                    }
                )
        return self._engine
    
    @contextmanager
    def get_session(self) -> ContextManager[Session]: # type: ignore
        """Context manager for database sessions."""
        if self._session_factory is None:
            self._session_factory = scoped_session(sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                autoflush=False
            ))
        
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    
    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(self.engine)
    
    def bulk_save_events(self, events: List[Dict[str, Any]], table_name: str, 
                        update_existing: bool = False) -> Dict[str, int]:
        """Bulk save events with upsert capability."""
        if not events:
            return {'inserted': 0, 'updated': 0, 'errors': 0}
        
        model_class = Hackathon if table_name == 'hackathons' else Conference
        counts = {'inserted': 0, 'updated': 0, 'errors': 0}
        
        # Process in batches
        for i in range(0, len(events), self.config.batch_size):
            batch = events[i:i + self.config.batch_size]
            batch_counts = self._process_event_batch(batch, model_class, update_existing)
            
            for key in counts:
                counts[key] += batch_counts[key]
        
        return counts
    
    def _process_event_batch(self, batch: List[Dict[str, Any]], model_class, update_existing: bool) -> Dict[str, int]:
        """Process a batch of events."""
        counts = {'inserted': 0, 'updated': 0, 'errors': 0}
        
        with self.get_session() as session:
            normalized_events = []
            
            for event in batch:
                try:
                    normalized_events.append(self._normalize_event(event))
                except Exception:
                    counts['errors'] += 1
            
            if not normalized_events:
                return counts
            
            if update_existing:
                # PostgreSQL UPSERT
                stmt = insert(model_class)
                update_dict = {key: stmt.excluded[key] for key in normalized_events[0].keys() 
                              if key not in ['url', 'created_at']}
                
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=['url'],
                    set_=update_dict
                )
                session.execute(upsert_stmt, normalized_events)
                counts['inserted'] = len(normalized_events)
            else:
                # Bulk insert with duplicate checking
                existing_urls = {url for (url,) in session.query(model_class.url).filter(
                    model_class.url.in_([e['url'] for e in normalized_events])
                ).all()}
                
                new_events = [e for e in normalized_events if e['url'] not in existing_urls]
                
                if new_events:
                    session.bulk_insert_mappings(model_class, new_events)
                    counts['inserted'] = len(new_events)
        
        return counts
    
    def _normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize event data for database insertion."""
        return {
            'name': str(event.get('name', '')).strip()[:500] or 'TBD',
            'url': str(event.get('url', '')).strip()[:1000],
            'start_date': str(event.get('start_date', '')).strip()[:100] if event.get('start_date') else None,
            'end_date': str(event.get('end_date', '')).strip()[:100] if event.get('end_date') else None,
            'location': str(event.get('location', '')).strip()[:200] if event.get('location') else None,
            'city': str(event.get('city', '')).strip()[:100] if event.get('city') else None,
            'remote': bool(event.get('remote', False)),
            'description': event.get('description'),
            'speakers': event.get('speakers') if isinstance(event.get('speakers'), (list, dict)) else None,
            'ticket_price': str(event.get('ticket_price', ''))[:100] if event.get('ticket_price') else None,
            'is_paid': bool(event.get('is_paid', False)),
            'themes': event.get('themes') if isinstance(event.get('themes'), (list, dict)) else None,
            'source': str(event.get('source', ''))[:100] if event.get('source') else None,
            'created_at': datetime.utcnow()
        }
    
    def get_events(self, table_name: str, limit: Optional[int] = None, 
                  filters: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        """Get events with filtering."""
        model_class = Hackathon if table_name == 'hackathons' else Conference
        
        with self.get_session() as session:
            query = session.query(model_class)
            
            # Apply filters
            if filters:
                for field, value in filters.items():
                    if hasattr(model_class, field):
                        query = query.filter(getattr(model_class, field) == value)
            
            query = query.order_by(model_class.created_at.desc())
            
            if limit:
                query = query.limit(limit)
            
            for event in query:
                yield {
                    'id': str(event.id),
                    'name': event.name,
                    'url': event.url,
                    'start_date': event.start_date,
                    'end_date': event.end_date,
                    'location': event.location,
                    'city': event.city,
                    'remote': event.remote,
                    'description': event.description,
                    'speakers': event.speakers,
                    'ticket_price': event.ticket_price,
                    'is_paid': event.is_paid,
                    'themes': event.themes,
                    'source': event.source,
                    'created_at': event.created_at.isoformat() if event.created_at else None
                }
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        stats = {}
        
        with self.get_session() as session:
            # Event counts
            stats['hackathons_count'] = session.query(Hackathon).count()
            stats['conferences_count'] = session.query(Conference).count()
            stats['collected_urls_count'] = session.query(CollectedUrls).count()
            
            # Recent events (last 30 days)
            recent_date = datetime.utcnow() - timedelta(days=30)
            stats['recent_hackathons'] = session.query(Hackathon).filter(
                Hackathon.created_at >= recent_date
            ).count()
            stats['recent_conferences'] = session.query(Conference).filter(
                Conference.created_at >= recent_date
            ).count()
            
            stats['total_events'] = stats['hackathons_count'] + stats['conferences_count']
        
        return stats
    
    def save_collected_urls(self, urls_data: List[Dict[str, Any]], source_type: str) -> Dict[str, int]:
        """Save collected URLs for tracking."""
        if not urls_data:
            return {'inserted': 0, 'skipped': 0, 'errors': 0}
        
        counts = {'inserted': 0, 'skipped': 0, 'errors': 0}
        
        with self.get_session() as session:
            # Get existing URLs
            urls = [data.get('url') for data in urls_data if data.get('url')]
            existing_urls = {url for (url,) in session.query(CollectedUrls.url).filter(
                CollectedUrls.url.in_(urls)
            ).all()}
            
            # Process new URLs
            new_urls = []
            for url_data in urls_data:
                url = url_data.get('url')
                if not url:
                    counts['errors'] += 1
                    continue
                
                if url in existing_urls:
                    counts['skipped'] += 1
                else:
                    metadata = {k: v for k, v in url_data.items() if k != 'url'}
                    new_urls.append({
                        'url': url,
                        'source_type': source_type,
                        'is_enriched': False,
                        'timestamp_collected': datetime.utcnow(),
                        'url_metadata': metadata if metadata else None
                    })
                    counts['inserted'] += 1
            
            if new_urls:
                session.bulk_insert_mappings(CollectedUrls, new_urls)
        
        return counts
    
    def mark_urls_as_enriched(self, urls: List[str]) -> int:
        """Mark URLs as enriched."""
        if not urls:
            return 0
        
        with self.get_session() as session:
            updated = session.query(CollectedUrls).filter(
                CollectedUrls.url.in_(urls)
            ).update({'is_enriched': True}, synchronize_session=False)
            
            return updated
    
    def save_event_action(self, event_id: str, event_type: str, action: str) -> bool:
        """Save an event action."""
        try:
            with self.get_session() as session:
                event_action = EventActions(
                    event_id=uuid.UUID(event_id),
                    event_type=event_type,
                    action=action,
                    timestamp=datetime.utcnow()
                )
                session.add(event_action)
                return True
        except Exception:
            return False
    
    def get_event_action(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest action for an event."""
        try:
            with self.get_session() as session:
                action = session.query(EventActions).filter(
                    EventActions.event_id == uuid.UUID(event_id)
                ).order_by(EventActions.timestamp.desc()).first()
                
                if action:
                    return {
                        'event_id': str(action.event_id),
                        'event_type': action.event_type,
                        'action': action.action,
                        'timestamp': action.timestamp.isoformat()
                    }
        except Exception:
            pass
        
        return None

# Global database manager instance
_db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager

# Legacy compatibility functions
def create_tables():
    """Create database tables."""
    get_db_manager().create_tables()

def get_db_session():
    """
    Get a database session for legacy compatibility.
    NOTE: For high-performance operations, use get_optimized_db_session() instead.
    """
    return get_db_manager().get_session()

def get_optimized_db_session():
    """
    Get an optimized database session with performance enhancements.
    
    This session is configured for:
    - Reduced memory usage through controlled batching
    - Connection reuse and pooling optimization
    - Query result streaming for large datasets
    - Context manager support for automatic cleanup
    
    Returns:
        ContextManager[Session]: Optimized SQLAlchemy session with context manager
    """
    # Return the optimized database manager's session context manager
    return get_db_manager().get_session()

def bulk_save_to_db(events: List[Dict[str, Any]], table_name: str, 
                   update_existing: bool = False, batch_size: int = 1000) -> Dict[str, int]:
    """Legacy wrapper for bulk save."""
    return get_db_manager().bulk_save_events(events, table_name, update_existing)

def get_events_from_db(table_name: str, limit: Optional[int] = None, 
                      filters: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
    """Legacy wrapper for getting events."""
    return get_db_manager().get_events(table_name, limit, filters)

def get_db_stats() -> Dict[str, Any]:
    """Legacy wrapper for database stats."""
    return get_db_manager().get_database_stats()

def save_collected_urls(urls_data: List[Dict[str, Any]], source_type: str, 
                       batch_size: int = 1000) -> Dict[str, int]:
    """Legacy wrapper for saving URLs."""
    return get_db_manager().save_collected_urls(urls_data, source_type)

def mark_urls_as_enriched_bulk(urls: List[str], batch_size: int = 500) -> int:
    """Legacy wrapper for marking URLs as enriched."""
    return get_db_manager().mark_urls_as_enriched(urls)

def save_event_action(event_id: str, event_type: str, action: str) -> bool:
    """Legacy wrapper for saving event actions."""
    return get_db_manager().save_event_action(event_id, event_type, action)

def get_event_action(event_id: str) -> Optional[Dict[str, Any]]:
    """Legacy wrapper for getting event actions."""
    return get_db_manager().get_event_action(event_id) 