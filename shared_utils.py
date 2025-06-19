import os
import json
import requests
import re
import time
import csv
import asyncio
import logging
from datetime import datetime
from dataclasses import dataclass, field, fields
from typing import List, Dict, Any, Optional, Callable, Union
from functools import lru_cache, wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, asynccontextmanager
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import aiohttp
from openai import OpenAI
from firecrawl import FirecrawlApp
from dotenv import load_dotenv
from config import *

# Load environment
load_dotenv()

# Add import for crawl4ai integration at the top
try:
    from crawl4ai_integration import crawl4ai_scrape_url, crawl4ai_check_availability
    CRAWL4AI_AVAILABLE = crawl4ai_check_availability()
except ImportError:
    CRAWL4AI_AVAILABLE = False

# Unified Logger with context
class Logger:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger("EventsDashboard")
    
    def log(self, level: str, msg: str, **ctx):
        context = " | ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else ""
        message = f"{msg} | {context}" if context else msg
        getattr(self.logger, level.lower())(message)

# Global instances
logger = Logger()

# Performance monitoring decorator
def performance_monitor(func):
    """Simple performance monitoring decorator."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            duration = (datetime.now() - start_time).total_seconds()
            print(f"    {func.__name__} completed in {duration:.2f}s")
            return result
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            print(f"   {func.__name__} failed after {duration:.2f}s: {e}")
            raise
    return wrapper

# Enhanced Singleton metaclass
class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

# Unified HTTP Client with sync/async capabilities
class HTTPClient(metaclass=Singleton):
    def __init__(self):
        self.session = self._create_session()
        self.connector = None
    
    def _create_session(self):
        session = requests.Session()
        retry = Retry(total=HTTP_MAX_RETRIES, backoff_factor=HTTP_BACKOFF_FACTOR, 
                     status_forcelist=[429, 500, 502, 503, 504])
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update({'User-Agent': ENHANCED_USER_AGENT})
        return session
    
    def get(self, url: str, **kwargs) -> requests.Response:
        return self.session.get(url, timeout=kwargs.get('timeout', HTTP_TIMEOUT_STANDARD), **kwargs)
    
    @asynccontextmanager
    async def async_session(self):
        if not self.connector:
            self.connector = aiohttp.TCPConnector(limit=50, limit_per_host=20)
        async with aiohttp.ClientSession(connector=self.connector, headers={'User-Agent': ENHANCED_USER_AGENT}) as session:
            yield session

# External service clients
class ServiceClients(metaclass=Singleton):
    def __init__(self):
        self.openai = self._init_openai()
        self.firecrawl = self._init_firecrawl()
    
    def _init_openai(self):
        try:
            return OpenAI(api_key=os.getenv('OPENAI_API_KEY')) if os.getenv('OPENAI_API_KEY') else None
        except Exception as e:
            logger.log("error", "OpenAI init failed", error=str(e))
            return None
    
    def _init_firecrawl(self):
        try:
            return FirecrawlApp(api_key=os.getenv('FIRECRAWL_API_KEY')) if os.getenv('FIRECRAWL_API_KEY') else None
        except Exception as e:
            logger.log("error", "Firecrawl init failed", error=str(e))
            return None

# Data processing utilities with method chaining
@dataclass
class Event:
    """Unified event data structure with flexible field handling."""
    url: str = ""
    name: str = "TBD"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    remote: bool = False
    description: Optional[str] = None
    speakers: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    ticket_price: Optional[str] = None
    is_paid: bool = False
    source: str = ""
    quality_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Additional fields for compatibility
    discovery_method: Optional[str] = None
    source_reliability: float = 0.0
    data_completeness: float = 0.0
    enrichment_status: Optional[str] = None
    enrichment_error: Optional[str] = None
    source_page_quality: float = 0.0
    
    def __post_init__(self):
        """Handle any unexpected fields by storing them in metadata."""
        pass
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Create Event from dictionary, handling unexpected fields gracefully."""
        # Get all field names from the dataclass
        field_names = {f.name for f in fields(cls)}
        
        # Separate known fields from unknown ones
        known_fields = {k: v for k, v in data.items() if k in field_names}
        unknown_fields = {k: v for k, v in data.items() if k not in field_names}
        
        # Create event with known fields
        event = cls(**known_fields)
        
        # Store unknown fields in metadata
        if unknown_fields:
            if not event.metadata:
                event.metadata = {}
            event.metadata.update(unknown_fields)
        
        return event

class EventProcessor:
    """Streamlined event processing with method chaining."""
    
    def __init__(self, event_type: str):
        self.event_type = event_type
        self.keywords = {
            'hackathon': ['hackathon', 'hack', 'coding', 'programming', 'developer'],
            'conference': ['conference', 'summit', 'symposium', 'workshop', 'seminar']
        }.get(event_type, [])
        self.remote_indicators = ['virtual', 'remote', 'online', 'webinar']
    
    def validate_url(self, url: str, text: str = "") -> bool:
        if not url or any(skip in url.lower() for skip in ['/about', '/contact', '.css', '.js']):
            return False
        return any(keyword in (url + " " + text).lower() for keyword in self.keywords)
    
    def extract_dates(self, text: str) -> tuple:
        patterns = [
            r'(\w+)\s+(\d+)(?:st|nd|rd|th)?\s*[-–]\s*(\d+)(?:st|nd|rd|th)?,?\s*(\d{4})',
            r'(\d{4})-(\d{1,2})-(\d{1,2})\s*to\s*(\d{4})-(\d{1,2})-(\d{1,2})'
        ]
        for pattern in patterns:
            if match := re.search(pattern, text, re.IGNORECASE):
                try:
                    groups = match.groups()
                    if len(groups) >= 4:
                        if groups[0].isdigit():  # YYYY-MM-DD format
                            return f"{groups[0]}-{groups[1]:0>2}-{groups[2]:0>2}", f"{groups[3]}-{groups[4]:0>2}-{groups[5]:0>2}"
                        else:  # Month name format
                            start = datetime.strptime(f"{groups[0]} {groups[1]} {groups[3]}", "%B %d %Y").strftime("%Y-%m-%d")
                            end = datetime.strptime(f"{groups[0]} {groups[2]} {groups[3]}", "%B %d %Y").strftime("%Y-%m-%d")
                            return start, end
                except: continue
        return None, None
    
    def extract_location(self, text: str) -> tuple:
        # Simple location extraction - can be enhanced
        location_pattern = r'(?:in|at|@)\s+([A-Z][a-z\s,]+(?:(?:USA?|NY|CA|)[,\s]*)?)'
        if match := re.search(location_pattern, text):
            location = match.group(1).strip()
            city = location.split(',')[0].strip()
            return location, city
        return None, None
    
    def is_remote(self, text: str) -> bool:
        return any(indicator in text.lower() for indicator in self.remote_indicators)
    
    def normalize(self, raw_event: Dict[str, Any]) -> Event:
        """Convert raw event data to normalized Event object."""
        text = f"{raw_event.get('name', '')} {raw_event.get('description', '')}"
        start_date, end_date = self.extract_dates(text)
        location, city = self.extract_location(text)
        
        event = Event(
            url=raw_event.get('url', ''),
            name=raw_event.get('name', 'TBD'),
            start_date=start_date or raw_event.get('start_date'),
            end_date=end_date or raw_event.get('end_date'),
            location=location or raw_event.get('location'),
            city=city or raw_event.get('city'),
            remote=self.is_remote(text) or bool(raw_event.get('remote')),
            description=raw_event.get('description'),
            speakers=raw_event.get('speakers', []),
            themes=raw_event.get('themes', []),
            source=raw_event.get('source', self.event_type),
            metadata=raw_event
        )
        
        # Calculate quality score
        weights = {'name': 0.25, 'start_date': 0.2, 'location': 0.2, 'description': 0.15, 'speakers': 0.1, 'themes': 0.1}
        event.quality_score = sum(weight for field, weight in weights.items() 
                                 if getattr(event, field) and str(getattr(event, field)).strip() != 'TBD')
        
        return event

class WebScraper:
    """Unified web scraping with retry logic and multiple backends."""
    
    def __init__(self):
        self.http = HTTPClient()
        self.clients = ServiceClients()
        self.crawl4ai_available = CRAWL4AI_AVAILABLE
    
    async def scrape_async(self, url: str, use_crawl4ai: bool = True, use_firecrawl: bool = False, max_retries: int = 3) -> Dict[str, Any]:
        """Async scraping with Crawl4AI support and automatic fallback."""
        for attempt in range(max_retries):
            try:
                # Try Crawl4AI first if available and enabled
                if use_crawl4ai and self.crawl4ai_available:
                    result = await crawl4ai_scrape_url(url, extract_structured=True)
                    if result.get('success'):
                        return {
                            'success': True, 
                            'content': result.get('markdown', result.get('content', '')),
                            'structured_data': result,
                            'method': 'crawl4ai'
                        }
                
                # Try FireCrawl if available and enabled
                if use_firecrawl and self.clients.firecrawl:
                    result = self.clients.firecrawl.scrape_url(url, params={'formats': ['html'], 'onlyMainContent': True})
                    if result.get('success'):
                        return {'success': True, 'content': result.get('html', ''), 'method': 'firecrawl'}
                
                # Fallback to HTTP
                response = self.http.get(url)
                response.raise_for_status()
                return {'success': True, 'content': response.text, 'method': 'http'}
                
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.log("error", "Scraping failed", url=url, error=str(e))
                    return {'success': False, 'error': str(e)}
                time.sleep(2 ** attempt)
        
        return {'success': False, 'error': 'Max retries exceeded'}
    
    def scrape(self, url: str, use_crawl4ai: bool = True, use_firecrawl: bool = False, max_retries: int = 3) -> Dict[str, Any]:
        """Unified scraping with automatic fallback (sync version)."""
        # For backward compatibility, provide sync version that runs async internally
        try:
            import asyncio
            # Try to get existing event loop
            try:
                loop = asyncio.get_running_loop()
                # If there's already a loop running, we can't use asyncio.run()
                # So we fall back to sync methods only
                logger.log("warning", "Event loop already running, using sync fallback only")
                return self._scrape_sync_only(url, use_firecrawl, max_retries)
            except RuntimeError:
                # No event loop running, we can create one
                return asyncio.run(self.scrape_async(url, use_crawl4ai, use_firecrawl, max_retries))
        except Exception as e:
            logger.log("error", "Async scraping failed, falling back to sync", error=str(e))
            return self._scrape_sync_only(url, use_firecrawl, max_retries)
    
    def _scrape_sync_only(self, url: str, use_firecrawl: bool = False, max_retries: int = 3) -> Dict[str, Any]:
        """Synchronous-only scraping for when async is not available."""
        for attempt in range(max_retries):
            try:
                if use_firecrawl and self.clients.firecrawl:
                    result = self.clients.firecrawl.scrape_url(url, params={'formats': ['html'], 'onlyMainContent': True})
                    if result.get('success'):
                        return {'success': True, 'content': result.get('html', ''), 'method': 'firecrawl'}
                
                # Fallback to HTTP
                response = self.http.get(url)
                response.raise_for_status()
                return {'success': True, 'content': response.text, 'method': 'http'}
                
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.log("error", "Sync scraping failed", url=url, error=str(e))
                    return {'success': False, 'error': str(e)}
                time.sleep(2 ** attempt)
        
        return {'success': False, 'error': 'Max retries exceeded'}

class ContentEnricher:
    """Streamlined content enrichment using GPT."""
    
    def __init__(self, event_type: str):
        self.event_type = event_type
        self.clients = ServiceClients()
        self.scraper = WebScraper()
        self.processor = EventProcessor(event_type)
    
    def enrich(self, url: str, content: str = None) -> Event:
        """Enrich event data using GPT extraction."""
        try:
            if not content:
                scrape_result = self.scraper.scrape(url)
                if not scrape_result['success']:
                    return Event(url=url, name='Extraction failed', metadata={'error': scrape_result['error']})
                content = scrape_result['content'][:MAX_CONTENT_FOR_PARSING]
            
            if not self.clients.openai:
                return Event(url=url, name='OpenAI unavailable')
            
            prompt = f"""Extract {self.event_type} details as JSON:
{{"name": "event name", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "location": "location", 
"city": "city", "remote": true/false, "description": "brief description", "speakers": [], 
"ticket_price": "price", "is_paid": true/false, "themes": []}}"""
            
            response = self.clients.openai.chat.completions.create(
                model=GPT_MODEL_STANDARD,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": content}],
                max_tokens=GPT_MAX_TOKENS_STANDARD,
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content.strip())
            result['url'] = url
            result['source'] = f'{self.event_type}_gpt'
            
            return self.processor.normalize(result)
            
        except Exception as e:
            logger.log("error", "Enrichment failed", url=url, error=str(e))
            return Event(url=url, name='Enrichment failed', metadata={'error': str(e)})

class EventGPTExtractor:
    """
    Unified GPT extractor for all event types (hackathons, conferences).
    
    This class consolidates the common GPT extraction logic to eliminate
    code duplication between event-specific extractors.
    """
    
    def __init__(self, event_type: str):
        """
        Initialize extractor for specific event type.
        
        Args:
            event_type: Type of events to extract ('hackathon' or 'conference')
        """
        self.event_type = event_type
        self.enricher = ContentEnricher(event_type)
    
    def extract_details(self, url: str, content: str = None) -> Dict[str, Any]:
        """
        Extract event details from URL.
        
        Args:
            url: Event URL to process
            content: Optional pre-fetched content
            
        Returns:
            Dictionary containing extracted event details
        """
        try:
            event_obj = self.enricher.enrich(url, content)
            if event_obj and hasattr(event_obj, '__dict__'):
                return event_obj.__dict__
            return {}
        except Exception as e:
            logger.log("error", f"Failed to extract {self.event_type} details", url=url, error=str(e))
            return {'enrichment_error': str(e)}
    
    @performance_monitor
    def process_batch(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a batch of events for enrichment.
        
        Args:
            events: List of event dictionaries to enrich
            
        Returns:
            List of enriched event dictionaries
        """
        if not events:
            return []
        
        enriched_events = []
        
        for event in events:
            try:
                url = event.get('url')
                if not url:
                    logger.log("warning", f"Skipping {self.event_type} without URL", event=event.get('name', 'Unknown'))
                    event['enrichment_status'] = 'skipped_no_url'
                    enriched_events.append(event)
                    continue
                
                # Extract details and merge with original data
                details = self.extract_details(url)
                enriched_event = {**event, **details}
                enriched_event['enrichment_status'] = 'success' if not details.get('enrichment_error') else 'error'
                
                enriched_events.append(enriched_event)
                
            except Exception as e:
                logger.log("error", f"Failed to process {self.event_type}", event=event.get('name', 'Unknown'), error=str(e))
                event['enrichment_error'] = str(e)
                event['enrichment_status'] = 'error'
                enriched_events.append(event)
        
        return enriched_events
    
    @performance_monitor
    def enrich_data(self, raw_events: List[Dict[str, Any]], 
                   force_reenrich: bool = False) -> List[Dict[str, Any]]:
        """
        Main function to enrich event data with statistics.
        
        Args:
            raw_events: List of raw event data
            force_reenrich: Whether to force re-enrichment (currently unused)
            
        Returns:
            List of enriched event data with processing statistics
        """
        if not raw_events:
            logger.log("info", f"No {self.event_type}s to enrich")
            return []
        
        logger.log("info", f"Starting enrichment of {len(raw_events)} {self.event_type}s")
        
        enriched_events = self.process_batch(raw_events)
        
        # Log statistics
        total = len(enriched_events)
        successful = sum(1 for e in enriched_events if e.get('enrichment_status') == 'success')
        errors = sum(1 for e in enriched_events if e.get('enrichment_status') == 'error')
        skipped = total - successful - errors
        
        logger.log("info", f"{self.event_type.title()} enrichment completed", 
                  successful=successful, errors=errors, skipped=skipped)
        
        return enriched_events

class FileManager:
    """Streamlined file operations - database-only storage."""
    
    @staticmethod
    def save_events(events: List[Event], event_type: str, base_filename: str = None) -> Dict[str, str]:
        """Events are stored in database only. File generation removed for efficiency."""
        if not events:
            return {}
        
        logger.log("info", f"Processed {len(events)} {event_type}s - stored in database only")
        return {'status': 'database_only', 'count': len(events)}

class ParallelProcessor:
    """Simplified parallel processing with automatic batching."""
    
    @staticmethod
    def process(items: List[Any], processor: Callable, max_workers: int = 10, batch_size: int = 50) -> List[Any]:
        """Process items in parallel with automatic error handling."""
        if not items:
            return []
        
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Process in batches
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                future_to_item = {executor.submit(processor, item): item for item in batch}
                
                for future in as_completed(future_to_item):
                    try:
                        if result := future.result():
                            results.append(result)
                    except Exception as e:
                        logger.log("error", "Parallel processing error", error=str(e))
        
        return results

# Search query generator with concise implementation
class QueryGenerator:
    """Compact search query generator."""
    
    def __init__(self):
        self.cities = ["San Francisco", "New York"]
        self.remote_terms = ["virtual", "remote", "online"]
        
    def generate(self, event_type: str, year: int = 2025) -> List[str]:
        """Generate search queries for event type."""
        keywords = {
            'conference': ["AI conference", "tech conference", "data science conference", "ML conference"],
            'hackathon': ["hackathon", "coding competition", "tech challenge", "developer contest"]
        }.get(event_type, [])
        
        queries = []
        for keyword in keywords:
            queries.extend([f"{keyword} {city} {year}" for city in self.cities])
            queries.extend([f"{keyword} {remote} {year}" for remote in self.remote_terms])
            queries.append(f'"{keyword}" {year}')
        
        return queries

# Utility functions
def validate_date(date_str: str) -> Optional[str]:
    """Validate and normalize date string."""
    if not date_str:
        return None
    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

def deduplicate_by_url(events: List[Event]) -> List[Event]:
    """Remove duplicate events by URL."""
    seen = set()
    unique = []
    for event in events:
        url_key = event.url.lower().strip().rstrip('/')
        if url_key not in seen:
            seen.add(url_key)
            unique.append(event)
    return unique

def is_valid_event_url(url: str) -> bool:
    """Check if URL is valid for events (not generic/administrative pages)."""
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower()
    
    # Invalid keywords that indicate non-event pages
    invalid_keywords = [
        "login", "privacy", "terms", "about", "help", "contact", "careers", 
        "support", "settings", "register", "signup", "logout", "account",
        "linkedin.com", "twitter.com", "facebook.com", "instagram.com",
        "youtube.com", "github.com", "/api/", "/static/", "redirect?",
        "community-guidelines", "california-consumer-privacy", "legal/"
    ]
    
    # Check for invalid keywords
    if any(keyword in url_lower for keyword in invalid_keywords):
        return False
    
    # Valid event-related keywords (at least one should be present)
    valid_keywords = [
        "hackathon", "event", "challenge", "competition", "contest", 
        "summit", "conference", "workshop", "coding", "programming",
        "hack", "tech", "innovation", "startup", "dev", "developer"
    ]
    
    # URL should contain at least one valid keyword
    return any(keyword in url_lower for keyword in valid_keywords)

def generate_summary(events: List[Event], event_type: str) -> Dict[str, Any]:
    """Generate event summary statistics."""
    if not events:
        return {}
    
    return {
        'total_count': len(events),
        'remote_count': sum(1 for e in events if e.remote),
        'with_dates': sum(1 for e in events if e.start_date),
        'avg_quality': sum(e.quality_score for e in events) / len(events),
        'sources': {src: count for src, count in 
                   {e.source: sum(1 for ev in events if ev.source == e.source) for e in events}.items()},
        'top_cities': {city: count for city, count in 
                      {e.city: sum(1 for ev in events if ev.city == e.city) for e in events if e.city}.items()},
        'event_type': event_type
    }

# Legacy compatibility
def clean_event_data(events: List[Dict[str, Any]], event_type: str = "events") -> List[Dict[str, Any]]:
    """Legacy wrapper for event cleaning."""
    processor = EventProcessor(event_type.rstrip('s'))
    return [processor.normalize(event).__dict__ for event in events] 