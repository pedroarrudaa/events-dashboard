"""
Crawl4AI Integration for Events Dashboard
Provides enhanced web scraping capabilities for hackathons and conferences
"""

import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    from crawl4ai.extraction_strategy import JsonCssExtractionStrategy, LLMExtractionStrategy
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    from crawl4ai.content_filter_strategy import PruningContentFilter
    CRAWL4AI_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Crawl4AI not available: {e}")
    print("💡 Run: pip install crawl4ai && crawl4ai-setup")
    CRAWL4AI_AVAILABLE = False


class Crawl4AIEventScraper:
    """
    Enhanced event scraper using Crawl4AI for better content extraction.
    Provides LLM-friendly markdown and structured data extraction.
    """
    
    def __init__(self, headless: bool = True, enable_stealth: bool = True):
        """
        Initialize Crawl4AI scraper with optimal settings for event websites.
        
        Args:
            headless: Run browser in headless mode
            enable_stealth: Enable stealth mode to avoid bot detection
        """
        if not CRAWL4AI_AVAILABLE:
            raise ImportError("Crawl4AI is not installed. Run: pip install crawl4ai && crawl4ai-setup")
        
        self.browser_config = BrowserConfig(
            headless=headless,
            verbose=False,  # Set to True for debugging
            # Enable stealth mode for better bot detection avoidance
            # java_script_enabled=True,
            # Custom user agent for better compatibility
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Schema for extracting hackathon/conference data
        self.event_extraction_schema = {
            "name": "Event Information Extraction",
            "baseSelector": "body",  # Extract from entire page
            "fields": [
                {
                    "name": "title",
                    "selector": "h1, .title, .event-title, .hackathon-title, .conference-title, title",
                    "type": "text"
                },
                {
                    "name": "description", 
                    "selector": ".description, .about, .overview, .summary, .event-description, p",
                    "type": "text"
                },
                {
                    "name": "date_info",
                    "selector": ".date, .when, .schedule, .time, .event-date, .dates",
                    "type": "text"
                },
                {
                    "name": "location",
                    "selector": ".location, .where, .venue, .address, .place, .city",
                    "type": "text"
                },
                {
                    "name": "registration_links",
                    "selector": "a[href*='register'], a[href*='signup'], a[href*='apply'], .register-btn, .apply-btn",
                    "type": "list",
                    "fields": [
                        {"name": "text", "selector": "a", "type": "text"},
                        {"name": "href", "selector": "a", "type": "attribute", "attribute": "href"}
                    ]
                },
                {
                    "name": "prizes",
                    "selector": ".prize, .reward, .awards, .winning",
                    "type": "text"
                },
                {
                    "name": "sponsors",
                    "selector": ".sponsor, .partner, .supporter",
                    "type": "text"
                },
                {
                    "name": "contact_info",
                    "selector": ".contact, .email, .social, .organizer",
                    "type": "text"
                }
            ]
        }
    
    async def scrape_event_page(self, url: str, extract_structured_data: bool = True) -> Dict[str, Any]:
        """
        Scrape a single event page using Crawl4AI.
        
        Args:
            url: URL to scrape
            extract_structured_data: Whether to extract structured data using CSS selectors
            
        Returns:
            Dictionary containing scraped data
        """
        print(f"🔍 Scraping event page with Crawl4AI: {url}")
        
        try:
            # Configure extraction strategy
            extraction_strategy = None
            if extract_structured_data:
                extraction_strategy = JsonCssExtractionStrategy(
                    schema=self.event_extraction_schema,
                    verbose=False
                )
            
            # Configure crawler run
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.ENABLED,  # Use cache for better performance
                extraction_strategy=extraction_strategy,
                markdown_generator=DefaultMarkdownGenerator(
                    content_filter=PruningContentFilter(
                        threshold=0.5,  # Remove low-quality content blocks
                        threshold_type="fixed",
                        min_word_threshold=10
                    )
                ),
                wait_for_timeout=3000,  # Wait 3 seconds for dynamic content
                output_formats=['markdown', 'extracted_content', 'links', 'media'],
                # Take screenshot for debugging if needed
                # screenshot=True,
            )
            
            async with AsyncWebCrawler(config=self.browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)
                
                if not result.success:
                    print(f"❌ Failed to scrape {url}: {result.error_message}")
                    return {
                        'success': False,
                        'error': result.error_message,
                        'url': url
                    }
                
                # Parse extracted content if available
                extracted_data = {}
                if result.extracted_content:
                    try:
                        extracted_data = json.loads(result.extracted_content)
                        if isinstance(extracted_data, list) and len(extracted_data) > 0:
                            extracted_data = extracted_data[0]  # Take first result
                    except json.JSONDecodeError:
                        print(f"⚠️  Could not parse extracted JSON for {url}")
                
                # Compile comprehensive result
                return {
                    'success': True,
                    'url': url,
                    'title': extracted_data.get('title', '').strip(),
                    'description': extracted_data.get('description', '').strip(),
                    'date_info': extracted_data.get('date_info', '').strip(),
                    'location': extracted_data.get('location', '').strip(),
                    'registration_links': extracted_data.get('registration_links', []),
                    'prizes': extracted_data.get('prizes', '').strip(),
                    'sponsors': extracted_data.get('sponsors', '').strip(),
                    'contact_info': extracted_data.get('contact_info', '').strip(),
                    'markdown': result.markdown.fit_markdown,
                    'raw_markdown': result.markdown.raw_markdown,
                    'links': result.links,
                    'media': result.media,
                    'word_count': result.markdown.word_count,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            print(f"❌ Error scraping {url} with Crawl4AI: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'url': url
            }
    
    async def scrape_multiple_events(self, urls: List[str], max_concurrent: int = 3) -> List[Dict[str, Any]]:
        """
        Scrape multiple event pages concurrently using Crawl4AI.
        
        Args:
            urls: List of URLs to scrape
            max_concurrent: Maximum number of concurrent requests
            
        Returns:
            List of scraped event data
        """
        print(f"🚀 Scraping {len(urls)} event pages concurrently...")
        
        results = []
        
        # Process URLs in batches to avoid overwhelming the server
        for i in range(0, len(urls), max_concurrent):
            batch = urls[i:i + max_concurrent]
            print(f"📦 Processing batch {i//max_concurrent + 1}: {len(batch)} URLs")
            
            # Create tasks for concurrent execution
            tasks = [self.scrape_event_page(url) for url in batch]
            
            # Execute batch concurrently
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle results and exceptions
            for result in batch_results:
                if isinstance(result, Exception):
                    print(f"❌ Batch processing error: {result}")
                    results.append({
                        'success': False,
                        'error': str(result),
                        'url': 'unknown'
                    })
                else:
                    results.append(result)
            
            # Rate limiting between batches
            if i + max_concurrent < len(urls):
                print("⏳ Waiting between batches...")
                await asyncio.sleep(2)
        
        successful = sum(1 for r in results if r.get('success', False))
        print(f"✅ Completed scraping: {successful}/{len(urls)} successful")
        
        return results
    
    async def discover_events_from_listing_page(self, listing_url: str, 
                                              max_events: int = 20) -> List[Dict[str, Any]]:
        """
        Discover event URLs from a listing page and scrape them.
        
        Args:
            listing_url: URL of the listing page
            max_events: Maximum number of events to scrape
            
        Returns:
            List of discovered and scraped events
        """
        print(f"🔎 Discovering events from listing page: {listing_url}")
        
        try:
            # First, scrape the listing page to get event URLs
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.ENABLED,
                output_formats=['links'],
                wait_for_timeout=5000,  # Wait longer for listing pages to load
            )
            
            async with AsyncWebCrawler(config=self.browser_config) as crawler:
                result = await crawler.arun(url=listing_url, config=run_config)
                
                if not result.success:
                    print(f"❌ Failed to scrape listing page: {result.error_message}")
                    return []
                
                # Extract internal links that might be event pages
                internal_links = result.links.get('internal', [])
                
                # Filter links that likely point to individual events
                event_urls = []
                event_keywords = [
                    'hackathon', 'conference', 'event', 'summit', 'meetup', 
                    'workshop', 'seminar', 'symposium', '/e/', '/events/',
                    '/hackathons/', '/conferences/'
                ]
                
                base_domain = urlparse(listing_url).netloc
                
                for link in internal_links:
                    # Convert relative URLs to absolute
                    if link.startswith('/'):
                        link = urljoin(listing_url, link)
                    
                    # Check if link is from same domain and contains event keywords
                    if (urlparse(link).netloc == base_domain and
                        any(keyword in link.lower() for keyword in event_keywords)):
                        event_urls.append(link)
                
                # Remove duplicates and limit
                event_urls = list(set(event_urls))[:max_events]
                print(f"🎯 Found {len(event_urls)} potential event URLs")
                
                # Scrape individual event pages
                if event_urls:
                    return await self.scrape_multiple_events(event_urls)
                else:
                    print("⚠️  No event URLs found on listing page")
                    return []
                
        except Exception as e:
            print(f"❌ Error discovering events from {listing_url}: {str(e)}")
            return []


# Utility functions for integration with existing codebase
async def crawl4ai_scrape_url(url: str, extract_structured: bool = True) -> Dict[str, Any]:
    """
    Convenience function to scrape a single URL with Crawl4AI.
    Can be used as a drop-in replacement for FireCrawl.
    """
    if not CRAWL4AI_AVAILABLE:
        return {
            'success': False,
            'error': 'Crawl4AI not available',
            'content': ''
        }
    
    scraper = Crawl4AIEventScraper()
    return await scraper.scrape_event_page(url, extract_structured)


async def crawl4ai_discover_events(listing_url: str, max_events: int = 20) -> List[Dict[str, Any]]:
    """
    Convenience function to discover and scrape events from a listing page.
    """
    if not CRAWL4AI_AVAILABLE:
        return []
    
    scraper = Crawl4AIEventScraper()
    return await scraper.discover_events_from_listing_page(listing_url, max_events)


def crawl4ai_check_availability() -> bool:
    """Check if Crawl4AI is properly installed and available."""
    return CRAWL4AI_AVAILABLE


# Example usage and testing
async def test_crawl4ai_integration():
    """Test the Crawl4AI integration with sample URLs."""
    print("🧪 Testing Crawl4AI Integration...")
    
    if not CRAWL4AI_AVAILABLE:
        print("❌ Crawl4AI not available for testing")
        return
    
    # Test URLs (replace with actual event URLs)
    test_urls = [
        "https://devpost.com/software/built-on-replit",  # Sample hackathon
        "https://mlh.io/seasons/2025/events",  # MLH events listing
    ]
    
    scraper = Crawl4AIEventScraper()
    
    # Test single URL scraping
    print("\n📄 Testing single URL scraping...")
    for url in test_urls[:1]:  # Test first URL only
        result = await scraper.scrape_event_page(url)
        print(f"Result for {url}: {result.get('success', False)}")
        if result.get('success'):
            print(f"Title: {result.get('title', 'N/A')}")
            print(f"Word count: {result.get('word_count', 0)}")
    
    # Test listing page discovery
    print("\n🔍 Testing listing page discovery...")
    listing_url = "https://mlh.io/seasons/2025/events"
    events = await scraper.discover_events_from_listing_page(listing_url, max_events=5)
    print(f"Discovered {len(events)} events from listing page")
    
    print("✅ Crawl4AI integration test completed")


if __name__ == "__main__":
    # Run tests if script is executed directly
    asyncio.run(test_crawl4ai_integration()) 