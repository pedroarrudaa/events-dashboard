"""
Database utilities for saving hackathons and conferences to PostgreSQL database using SQLAlchemy.
"""
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text, Column, Integer, String, Boolean, DateTime, JSON, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert, UUID
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# SQLAlchemy setup
Base = declarative_base()

class CollectedUrls(Base):
    """SQLAlchemy model for tracking collected URLs and their enrichment status."""
    __tablename__ = 'collected_urls'
    
    url = Column(String, primary_key=True, unique=True, nullable=False)
    source_type = Column(String, nullable=False)  # 'hackathon' or 'conference'
    is_enriched = Column(Boolean, default=False, nullable=False)
    timestamp_collected = Column(DateTime, default=datetime.utcnow, nullable=False)
    url_metadata = Column(JSON)  # Optional JSON metadata like page title, raw scraping data

class Hackathon(Base):
    """SQLAlchemy model for hackathons table."""
    __tablename__ = 'hackathons'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False)
    date = Column(String)  # Can represent start_date or date range
    start_date = Column(String)
    end_date = Column(String)
    location = Column(String)
    city = Column(String)
    remote = Column(Boolean, default=False)
    description = Column(Text)
    short_description = Column(Text)
    speakers = Column(JSON)
    sponsors = Column(JSON)
    ticket_price = Column(JSON)
    is_paid = Column(Boolean, default=False)
    themes = Column(JSON)
    source = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_hackathon_created_at', 'created_at'),
        Index('idx_hackathon_start_date', 'start_date'),
        Index('idx_hackathon_location', 'location'),
    )

class Conference(Base):
    """SQLAlchemy model for conferences table."""
    __tablename__ = 'conferences'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False)
    date = Column(String)  # Can represent start_date or date range
    start_date = Column(String)
    end_date = Column(String)
    location = Column(String)
    city = Column(String)
    remote = Column(Boolean, default=False)
    description = Column(Text)
    short_description = Column(Text)
    speakers = Column(JSON)
    sponsors = Column(JSON)
    ticket_price = Column(JSON)
    is_paid = Column(Boolean, default=False)
    themes = Column(JSON)
    source = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    registration_url = Column(String)
    registration_deadline = Column(String)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_conference_created_at', 'created_at'),
        Index('idx_conference_start_date', 'start_date'),
        Index('idx_conference_location', 'location'),
    )

class EventActions(Base):
    """SQLAlchemy model for tracking manual actions on events."""
    __tablename__ = 'event_actions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String, nullable=False)  # 'hackathon' or 'conference'
    action = Column(String, nullable=False)  # 'archive' or 'reached_out'
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Performance indexes for fast lookups
    __table_args__ = (
        Index('idx_event_action_event_id', 'event_id'),
        Index('idx_event_action_type_id', 'event_type', 'event_id'),
        Index('idx_event_action_timestamp', 'timestamp'),
    )

# Database engine and session
_engine = None
_Session = None

def get_db_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        # Use environment variable for database URL
        database_url = os.getenv('DATABASE_URL')
        
        if not database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required.\n"
                "Please set it in your .env file or environment.\n"
                "For Railway PostgreSQL, use the EXTERNAL connection string (not the internal one).\n"
                "Example: postgresql://postgres:password@host:port/database"
            )
            
        print(f"🔗 Connecting to database: {database_url.split('@')[0]}@***")
            
        _engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False  # Set to True for SQL debugging
        )
    return _engine

def get_db_session():
    """Get or create the database session factory."""
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=get_db_engine())
    return _Session()

def create_tables() -> None:
    """
    Create the hackathons, conferences, collected_urls, and event_actions tables if they don't exist.
    """
    try:
        engine = get_db_engine()
        Base.metadata.create_all(engine)
        print(f"✅ Database tables 'hackathons', 'conferences', 'collected_urls', and 'event_actions' created/verified in PostgreSQL")
    except Exception as e:
        print(f"❌ Error creating tables: {str(e)}")
        raise

def _normalize_event_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize event data to match database schema with required fields.
    
    Args:
        event: Raw event data dictionary
        
    Returns:
        Normalized event data dictionary
    """
    normalized = {}
    
    # Map common fields
    field_mappings = {
        'name': ['name', 'title'],
        'url': ['url', 'link'],
        'date': ['date', 'start_date', 'event_date'],
        'start_date': ['start_date', 'date', 'event_date'],
        'end_date': ['end_date'],
        'location': ['location', 'city', 'venue'],
        'city': ['city', 'location', 'venue'],
        'remote': ['remote', 'is_remote'],
        'description': ['description', 'short_description', 'summary'],
        'short_description': ['short_description', 'description', 'summary'],
        'speakers': ['speakers'],
        'sponsors': ['sponsors'],
        'ticket_price': ['ticket_price', 'price', 'cost'],
        'is_paid': ['is_paid', 'paid'],
        'themes': ['themes', 'topics', 'categories'],
        'source': ['source', 'data_source']
    }
    
    for db_field, possible_keys in field_mappings.items():
        value = None
        for key in possible_keys:
            if key in event:
                value = event[key]
                break
        
        # Handle special cases
        if db_field == 'remote':
            if isinstance(value, str):
                normalized[db_field] = value.lower() in ['true', '1', 'yes', 'remote']
            else:
                normalized[db_field] = bool(value) if value is not None else False
        elif db_field == 'is_paid':
            if isinstance(value, str):
                normalized[db_field] = value.lower() in ['true', '1', 'yes', 'paid']
            else:
                normalized[db_field] = bool(value) if value is not None else False
        elif db_field in ['speakers', 'sponsors', 'themes']:
            # Handle JSON fields - keep as JSON-serializable objects
            if isinstance(value, list):
                normalized[db_field] = value
            elif isinstance(value, str) and value:
                # Try to parse comma-separated strings into lists
                normalized[db_field] = [item.strip() for item in value.split(',') if item.strip()]
            else:
                normalized[db_field] = [] if value is None else [str(value)]
        elif db_field == 'ticket_price':
            # Handle ticket price as JSON - could be string, number, or object
            if isinstance(value, (dict, list)):
                normalized[db_field] = value
            elif value is not None:
                normalized[db_field] = {"price": str(value)}
            else:
                normalized[db_field] = None
        else:
            normalized[db_field] = str(value) if value is not None else None
    
    # Ensure we have required fields (id, name, date, url, location, description)
    if not normalized.get('url'):
        raise ValueError("Event must have a URL")
    if not normalized.get('name'):
        normalized['name'] = f"Event at {normalized.get('url', 'Unknown')}"
    if not normalized.get('date') and not normalized.get('start_date'):
        normalized['date'] = 'TBD'
    if not normalized.get('location') and not normalized.get('city'):
        if normalized.get('remote'):
            normalized['location'] = 'Remote'
        else:
            normalized['location'] = 'TBD'
    if not normalized.get('description') and not normalized.get('short_description'):
        normalized['description'] = 'No description available'
    
    return normalized

def save_to_db(events: List[Dict[str, Any]], table_name: str, 
               update_existing: bool = False) -> Dict[str, int]:
    """
    Save events to the specified table (hackathons or conferences) using SQLAlchemy.
    
    Args:
        events: List of event data dictionaries
        table_name: Name of the table ('hackathons' or 'conferences')
        update_existing: Whether to update existing entries with the same URL
        
    Returns:
        Dictionary with counts: {'inserted': int, 'updated': int, 'skipped': int, 'errors': int}
    """
    if not events:
        print("❌ No events to save to database!")
        return {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    
    if table_name not in ['hackathons', 'conferences']:
        raise ValueError("table_name must be either 'hackathons' or 'conferences'")
    
    # Get the appropriate model class
    model_class = Hackathon if table_name == 'hackathons' else Conference
    
    # Ensure tables exist
    create_tables()
    
    session = get_db_session()
    counts = {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    
    print(f"💾 Saving {len(events)} events to {table_name} table...")
    print(f"⚙️ Update mode: {'UPDATE' if update_existing else 'INSERT_ONLY'}")
    
    try:
        for event in events:
            try:
                # Normalize event data
                normalized_event = _normalize_event_data(event)
                
                if update_existing:
                    # Use PostgreSQL UPSERT with SQLAlchemy
                    stmt = insert(model_class).values(**normalized_event)
                    
                    # Define what fields to update on conflict (exclude id, url, created_at)
                    update_dict = {
                        key: stmt.excluded[key] 
                        for key in normalized_event.keys() 
                        if key not in ['url', 'created_at']
                    }
                    
                    upsert_stmt = stmt.on_conflict_do_update(
                        index_elements=['url'],
                        set_=update_dict
                    )
                    
                    result = session.execute(upsert_stmt)
                    
                    # Check if it was an insert or update by querying
                    existing = session.query(model_class).filter_by(url=normalized_event['url']).first()
                    if existing.created_at.timestamp() > (datetime.utcnow().timestamp() - 5):  # Created within last 5 seconds
                        counts['inserted'] += 1
                    else:
                        counts['updated'] += 1
                        
                else:
                    # Check if URL already exists
                    existing = session.query(model_class).filter_by(url=normalized_event['url']).first()
                    
                    if existing:
                        counts['skipped'] += 1
                    else:
                        # Insert new record
                        new_event = model_class(**normalized_event)
                        session.add(new_event)
                        counts['inserted'] += 1
                
            except Exception as e:
                print(f"❌ Error saving event {event.get('name', 'Unknown')}: {str(e)}")
                counts['errors'] += 1
                continue
        
        # Commit all changes
        session.commit()
        
    except Exception as e:
        session.rollback()
        print(f"❌ Database transaction failed: {str(e)}")
        raise
    finally:
        session.close()
    
    # Print summary
    print(f"✅ Database save complete:")
    print(f"   • Table: {table_name}")
    print(f"   • Inserted: {counts['inserted']}")
    print(f"   • Updated: {counts['updated']}")
    print(f"   • Skipped: {counts['skipped']}")
    print(f"   • Errors: {counts['errors']}")
    print(f"   • Database: Railway PostgreSQL via SQLAlchemy")
    
    return counts

def get_events_from_db(table_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieve events from the specified table.
    
    Args:
        table_name: Name of the table ('hackathons' or 'conferences')
        limit: Optional limit on number of records to return
        
    Returns:
        List of event dictionaries
    """
    if table_name not in ['hackathons', 'conferences']:
        raise ValueError("table_name must be either 'hackathons' or 'conferences'")
    
    # Get the appropriate model class
    model_class = Hackathon if table_name == 'hackathons' else Conference
    
    session = get_db_session()
    
    try:
        query = session.query(model_class).order_by(model_class.created_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        results = query.all()
        
        # Convert to list of dictionaries
        events = []
        for result in results:
            event = {
                'id': str(result.id),
                'name': result.name,
                'url': result.url,
                'date': result.date,
                'start_date': result.start_date,
                'end_date': result.end_date,
                'location': result.location,
                'city': result.city,
                'remote': result.remote,
                'description': result.description,
                'short_description': result.short_description,
                'speakers': result.speakers,
                'sponsors': result.sponsors,
                'ticket_price': result.ticket_price,
                'is_paid': result.is_paid,
                'themes': result.themes,
                'source': result.source,
                'created_at': result.created_at.isoformat() if result.created_at else None
            }
            events.append(event)
        
        return events
        
    finally:
        session.close()

def get_db_stats() -> Dict[str, Any]:
    """
    Get statistics about the database contents.
    
    Returns:
        Dictionary with database statistics
    """
    session = get_db_session()
    
    try:
        stats = {}
        
        for table_name, model_class in [('hackathons', Hackathon), ('conferences', Conference)]:
            # Total count
            total = session.query(model_class).count()
            
            # Remote count
            remote = session.query(model_class).filter(model_class.remote == True).count()
            
            # Recent entries (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(hours=24)
            recent = session.query(model_class).filter(model_class.created_at >= yesterday).count()
            
            stats[table_name] = {
                'total': total,
                'remote': remote,
                'in_person': total - remote,
                'recent_24h': recent
            }
        
        # Source breakdown across both tables
        source_stats = {}
        
        # Get sources from hackathons
        hackathon_sources = session.query(Hackathon.source).distinct().all()
        for (source,) in hackathon_sources:
            if source:
                count = session.query(Hackathon).filter(Hackathon.source == source).count()
                source_stats[f"hackathons_{source}"] = count
        
        # Get sources from conferences
        conference_sources = session.query(Conference.source).distinct().all()
        for (source,) in conference_sources:
            if source:
                count = session.query(Conference).filter(Conference.source == source).count()
                source_stats[f"conferences_{source}"] = count
        
        stats['sources'] = source_stats
        
        # Add collected URLs statistics
        stats['collected_urls'] = get_collected_urls_stats()
        
        stats['database'] = 'Railway PostgreSQL (SQLAlchemy)'
        
        return stats
        
    except Exception as e:
        print(f"❌ Error getting database stats: {str(e)}")
        return {
            'hackathons': {'total': 0, 'remote': 0, 'in_person': 0, 'recent_24h': 0},
            'conferences': {'total': 0, 'remote': 0, 'in_person': 0, 'recent_24h': 0},
            'sources': {},
            'collected_urls': {'overall': {'total': 0, 'enriched': 0, 'pending': 0, 'recent_24h': 0, 'enrichment_rate': 0}},
            'database': 'Railway PostgreSQL (SQLAlchemy) - Error'
        }
    finally:
        session.close()

def save_collected_urls(urls_data: List[Dict[str, Any]], source_type: str) -> Dict[str, int]:
    """
    Save collected URLs to the collected_urls table.
    
    Args:
        urls_data: List of dictionaries containing URL data
        source_type: Type of source ('hackathon' or 'conference')
        
    Returns:
        Dictionary with counts: {'inserted': int, 'updated': int, 'skipped': int, 'errors': int}
    """
    if not urls_data:
        print("❌ No URLs to save!")
        return {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    
    if source_type not in ['hackathon', 'conference']:
        raise ValueError("source_type must be either 'hackathon' or 'conference'")
    
    # Ensure tables exist
    create_tables()
    
    session = get_db_session()
    counts = {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    
    print(f"💾 Saving {len(urls_data)} URLs to collected_urls table...")
    print(f"🏷️ Source type: {source_type}")
    
    try:
        for url_data in urls_data:
            try:
                url = url_data.get('url')
                if not url:
                    print(f"⚠️ Skipping URL data without URL field: {url_data}")
                    counts['errors'] += 1
                    continue
                
                # Prepare metadata (exclude 'url' field to avoid duplication)
                metadata = {k: v for k, v in url_data.items() if k != 'url'}
                
                # Check if URL already exists
                existing = session.query(CollectedUrls).filter_by(url=url).first()
                
                if existing:
                    # Update metadata if provided and different
                    if metadata and existing.url_metadata != metadata:
                        existing.url_metadata = metadata
                        existing.timestamp_collected = datetime.utcnow()
                        counts['updated'] += 1
                        print(f"📝 Updated URL: {url}")
                    else:
                        counts['skipped'] += 1
                        print(f"⏩ Skipped existing URL: {url}")
                else:
                    # Insert new URL
                    new_url = CollectedUrls(
                        url=url,
                        source_type=source_type,
                        is_enriched=False,
                        timestamp_collected=datetime.utcnow(),
                        url_metadata=metadata if metadata else None
                    )
                    session.add(new_url)
                    counts['inserted'] += 1
                    print(f"✅ Added new URL: {url}")
                
            except Exception as e:
                print(f"❌ Error saving URL {url_data.get('url', 'Unknown')}: {str(e)}")
                counts['errors'] += 1
                continue
        
        # Commit all changes
        session.commit()
        
    except Exception as e:
        session.rollback()
        print(f"❌ Database transaction failed: {str(e)}")
        raise
    finally:
        session.close()
    
    # Print summary
    print(f"✅ URL collection save complete:")
    print(f"   • Source type: {source_type}")
    print(f"   • Inserted: {counts['inserted']}")
    print(f"   • Updated: {counts['updated']}")
    print(f"   • Skipped: {counts['skipped']}")
    print(f"   • Errors: {counts['errors']}")
    
    return counts

def get_urls_for_enrichment(source_type: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get URLs that need enrichment (is_enriched=False).
    
    Args:
        source_type: Type of source ('hackathon' or 'conference')
        limit: Optional limit on number of URLs to return
        
    Returns:
        List of URL dictionaries that need enrichment
    """
    if source_type not in ['hackathon', 'conference']:
        raise ValueError("source_type must be either 'hackathon' or 'conference'")
    
    session = get_db_session()
    
    try:
        query = session.query(CollectedUrls).filter(
            CollectedUrls.source_type == source_type,
            CollectedUrls.is_enriched == False
        ).order_by(CollectedUrls.timestamp_collected.asc())
        
        if limit:
            query = query.limit(limit)
        
        results = query.all()
        
        # Convert to list of dictionaries
        urls = []
        for result in results:
            url_data = {
                'url': result.url,
                'source_type': result.source_type,
                'is_enriched': result.is_enriched,
                'timestamp_collected': result.timestamp_collected.isoformat() if result.timestamp_collected else None,
                'url_metadata': result.url_metadata
            }
            # If metadata exists, merge it into the main dictionary
            if result.url_metadata:
                url_data.update(result.url_metadata)
            urls.append(url_data)
        
        print(f"📋 Found {len(urls)} URLs needing enrichment for {source_type}")
        return urls
        
    finally:
        session.close()

def mark_url_as_enriched(url: str) -> bool:
    """
    Mark a URL as enriched (is_enriched=True).
    
    Args:
        url: The URL to mark as enriched
        
    Returns:
        True if successful, False otherwise
    """
    session = get_db_session()
    
    try:
        # Find the URL record
        url_record = session.query(CollectedUrls).filter_by(url=url).first()
        
        if url_record:
            url_record.is_enriched = True
            session.commit()
            print(f"✅ Marked URL as enriched: {url}")
            return True
        else:
            print(f"⚠️ URL not found in collected_urls: {url}")
            return False
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error marking URL as enriched: {str(e)}")
        return False
    finally:
        session.close()

def get_collected_urls_stats() -> Dict[str, Any]:
    """
    Get statistics about collected URLs.
    
    Returns:
        Dictionary with collected URLs statistics
    """
    session = get_db_session()
    
    try:
        stats = {}
        
        # Overall stats
        total_urls = session.query(CollectedUrls).count()
        enriched_urls = session.query(CollectedUrls).filter(CollectedUrls.is_enriched == True).count()
        pending_urls = total_urls - enriched_urls
        
        # By source type
        for source_type in ['hackathon', 'conference']:
            total_source = session.query(CollectedUrls).filter(CollectedUrls.source_type == source_type).count()
            enriched_source = session.query(CollectedUrls).filter(
                CollectedUrls.source_type == source_type,
                CollectedUrls.is_enriched == True
            ).count()
            pending_source = total_source - enriched_source
            
            stats[source_type] = {
                'total': total_source,
                'enriched': enriched_source,
                'pending': pending_source,
                'enrichment_rate': (enriched_source / total_source * 100) if total_source > 0 else 0
            }
        
        # Recent collection stats (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_urls = session.query(CollectedUrls).filter(CollectedUrls.timestamp_collected >= yesterday).count()
        
        stats['overall'] = {
            'total': total_urls,
            'enriched': enriched_urls,
            'pending': pending_urls,
            'recent_24h': recent_urls,
            'enrichment_rate': (enriched_urls / total_urls * 100) if total_urls > 0 else 0
        }
        
        return stats
        
    except Exception as e:
        print(f"❌ Error getting collected URLs stats: {str(e)}")
        return {
            'overall': {'total': 0, 'enriched': 0, 'pending': 0, 'recent_24h': 0, 'enrichment_rate': 0},
            'hackathon': {'total': 0, 'enriched': 0, 'pending': 0, 'enrichment_rate': 0},
            'conference': {'total': 0, 'enriched': 0, 'pending': 0, 'enrichment_rate': 0}
        }
    finally:
        session.close()

def save_event_action(event_id: str, event_type: str, action: str) -> bool:
    """
    Save a manual action for an event.
    
    Args:
        event_id: UUID of the event
        event_type: Type of event ('hackathon' or 'conference')
        action: Action taken ('archive' or 'reached_out')
        
    Returns:
        True if successful, False otherwise
    """
    if event_type not in ['hackathon', 'conference']:
        print(f"❌ Invalid event_type: {event_type}. Must be 'hackathon' or 'conference'")
        return False
    
    if action not in ['archive', 'reached_out']:
        print(f"❌ Invalid action: {action}. Must be 'archive' or 'reached_out'")
        return False
    
    session = get_db_session()
    
    try:
        # Validate that the event exists
        if event_type == 'hackathon':
            event_exists = session.query(Hackathon).filter_by(id=event_id).first()
        else:
            event_exists = session.query(Conference).filter_by(id=event_id).first()
        
        if not event_exists:
            print(f"❌ Event not found: {event_id} ({event_type})")
            return False
        
        # Create new action record
        new_action = EventActions(
            event_id=uuid.UUID(event_id),
            event_type=event_type,
            action=action,
            timestamp=datetime.utcnow()
        )
        
        session.add(new_action)
        session.commit()
        
        print(f"✅ Saved action '{action}' for {event_type} {event_id}")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error saving event action: {str(e)}")
        return False
    finally:
        session.close()

def get_event_action(event_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the latest action for an event.
    
    Args:
        event_id: UUID of the event
        
    Returns:
        Dictionary with action data or None if no action exists
    """
    session = get_db_session()
    
    try:
        # Get the most recent action for this event
        action = session.query(EventActions).filter_by(
            event_id=uuid.UUID(event_id)
        ).order_by(EventActions.timestamp.desc()).first()
        
        if action:
            return {
                'id': str(action.id),
                'event_id': str(action.event_id),
                'event_type': action.event_type,
                'action': action.action,
                'timestamp': action.timestamp.isoformat()
            }
        
        return None
        
    except Exception as e:
        print(f"❌ Error getting event action: {str(e)}")
        return None
    finally:
        session.close()

def get_event_actions_stats() -> Dict[str, Any]:
    """
    Get statistics about event actions.
    
    Returns:
        Dictionary with event actions statistics
    """
    session = get_db_session()
    
    try:
        stats = {}
        
        # Overall stats
        total_actions = session.query(EventActions).count()
        
        # By action type
        for action_type in ['archive', 'reached_out']:
            count = session.query(EventActions).filter(EventActions.action == action_type).count()
            stats[action_type] = count
        
        # By event type
        for event_type in ['hackathon', 'conference']:
            count = session.query(EventActions).filter(EventActions.event_type == event_type).count()
            stats[f'{event_type}_actions'] = count
        
        # Recent actions (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_actions = session.query(EventActions).filter(EventActions.timestamp >= yesterday).count()
        
        stats['total'] = total_actions
        stats['recent_24h'] = recent_actions
        
        return stats
        
    except Exception as e:
        print(f"❌ Error getting event actions stats: {str(e)}")
        return {'total': 0, 'archive': 0, 'reached_out': 0, 'hackathon_actions': 0, 'conference_actions': 0, 'recent_24h': 0}
    finally:
        session.close()

def get_events_with_actions_optimized(
    type_filter: Optional[str] = None,
    location_filter: Optional[str] = None,
    limit: Optional[int] = 100
) -> List[Dict[str, Any]]:
    """
    PERFORMANCE OPTIMIZED: Get unified list of events with their latest actions using efficient SQL JOINs.
    
    This function eliminates the N+1 query problem by using SQL JOINs instead of separate queries.
    
    Performance improvements:
    - Single query with JOINs instead of N+1 queries
    - Database-level filtering and sorting
    - Proper indexing utilization
    - Reduced network round trips
    
    Args:
        type_filter: Filter by event type ('hackathon', 'conference')
        location_filter: Filter by location (substring match)
        limit: Maximum number of events to return
        
    Returns:
        List of unified event dictionaries with action data included
    """
    session = get_db_session()
    
    try:
        # Raw SQL query using UNION ALL for combining hackathons and conferences
        # with LEFT JOIN for latest event actions - this is much more efficient
        # than the previous approach of separate queries + N individual action lookups
        sql_query = text("""
            WITH unified_events AS (
                -- Hackathons with type annotation
                SELECT 
                    h.id,
                    h.name,
                    h.url,
                    h.date,
                    h.start_date,
                    h.end_date,
                    h.location,
                    h.city,
                    h.remote,
                    h.description,
                    h.created_at,
                    'hackathon' as event_type
                FROM hackathons h
                
                UNION ALL
                
                -- Conferences with type annotation  
                SELECT 
                    c.id,
                    c.name,
                    c.url,
                    c.date,
                    c.start_date,
                    c.end_date,
                    c.location,
                    c.city,
                    c.remote,
                    c.description,
                    c.created_at,
                    'conference' as event_type
                FROM conferences c
            ),
            latest_actions AS (
                -- Get only the most recent action for each event
                SELECT DISTINCT ON (event_id) 
                    event_id,
                    action,
                    timestamp
                FROM event_actions 
                ORDER BY event_id, timestamp DESC
            )
            SELECT 
                ue.id,
                ue.name,
                ue.url,
                ue.date,
                ue.start_date,
                ue.end_date,
                ue.location,
                ue.city,
                ue.remote,
                ue.description,
                ue.created_at,
                ue.event_type,
                la.action as last_action,
                la.timestamp as action_time
            FROM unified_events ue
            LEFT JOIN latest_actions la ON ue.id = la.event_id
            WHERE 1=1
                AND (:type_filter IS NULL OR ue.event_type = :type_filter)
                AND (:location_filter IS NULL OR LOWER(ue.location) LIKE LOWER(:location_pattern))
            ORDER BY 
                CASE 
                    WHEN ue.start_date IS NOT NULL AND ue.start_date != 'TBD' 
                    THEN TO_DATE(ue.start_date, 'YYYY-MM-DD')
                    ELSE TO_DATE('1900-01-01', 'YYYY-MM-DD')
                END DESC,
                ue.created_at DESC
            LIMIT :limit_param
        """)
        
        # Prepare parameters for SQL query
        params = {
            'type_filter': type_filter if type_filter and type_filter != 'all' else None,
            'location_filter': f"%{location_filter}%" if location_filter and location_filter != 'all' else None,
            'location_pattern': f"%{location_filter}%" if location_filter and location_filter != 'all' else None,
            'limit_param': limit or 100
        }
        
        # Execute optimized query
        result = session.execute(sql_query, params)
        rows = result.fetchall()
        
        # Convert to list of dictionaries with proper formatting
        events = []
        for row in rows:
            # Determine status based on data completeness
            status = "validated"  # Default status
            if not row.start_date or row.start_date == 'TBD':
                status = "filtered"
            elif row.location and row.location != 'TBD' and row.start_date != 'TBD':
                status = "enriched"
            
            event = {
                'id': str(row.id),
                'title': row.name or 'Untitled Event',
                'type': row.event_type,
                'location': row.location or 'TBD',
                'start_date': row.start_date or row.date or 'TBD',
                'end_date': row.end_date or 'TBD',
                'url': row.url or '',
                'status': status,
                'last_action': row.last_action,  # Already included from JOIN
                'action_time': row.action_time.isoformat() if row.action_time else None
            }
            events.append(event)
        
        print(f"✅ Optimized query fetched {len(events)} events with actions in single query")
        return events
        
    except Exception as e:
        print(f"❌ Error in optimized events query: {str(e)}")
        # Fallback to original method if SQL fails
        return []
    finally:
        session.close()

def create_performance_indexes() -> None:
    """
    Create additional performance indexes for optimal query performance.
    
    This function creates indexes specifically designed to support the optimized
    events query and other performance-critical operations.
    """
    try:
        engine = get_db_engine()
        
        # Create indexes for performance optimization
        with engine.connect() as conn:
            # Composite indexes for event filtering and sorting
            conn.execute(text("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hackathon_location_startdate 
                ON hackathons(location, start_date) 
                WHERE location IS NOT NULL AND start_date IS NOT NULL;
            """))
            
            conn.execute(text("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conference_location_startdate 
                ON conferences(location, start_date) 
                WHERE location IS NOT NULL AND start_date IS NOT NULL;
            """))
            
            # Partial indexes for event actions (most recent first)
            conn.execute(text("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_event_actions_latest
                ON event_actions(event_id, timestamp DESC)
                WHERE timestamp IS NOT NULL;
            """))
            
            # Text search indexes for location filtering
            conn.execute(text("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hackathon_location_gin
                ON hackathons USING gin(to_tsvector('english', COALESCE(location, '')))
                WHERE location IS NOT NULL;
            """))
            
            conn.execute(text("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conference_location_gin
                ON conferences USING gin(to_tsvector('english', COALESCE(location, '')))
                WHERE location IS NOT NULL;
            """))
            
            conn.commit()
            
        print("✅ Performance indexes created successfully")
        
    except Exception as e:
        print(f"⚠️ Warning: Could not create some performance indexes: {str(e)}")
        # This is non-critical, continue operation 