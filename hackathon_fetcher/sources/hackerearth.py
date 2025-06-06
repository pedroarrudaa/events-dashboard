"""
HackerEarth source for fetching hackathon opportunities.
"""
import requests
import time
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from urllib.parse import urljoin, urlparse
import re

class HackerEarthScraper:
    """Enhanced scraper for HackerEarth hackathon listings with DevpostScraper interface."""
    
    def __init__(self):
        """Initialize the scraper."""
        self.base_url = "https://www.hackerearth.com"
        self.hackathon_url = f"{self.base_url}/challenges/hackathon/"
        self.page_metadata = []
    
    def _extract_page_title_from_html(self, html: str) -> str:
        """Extract page title from HTML content for logging."""
        if not html:
            return "No HTML content"
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            title_elem = soup.find('title')
            if title_elem:
                title = title_elem.get_text().strip()
                return title[:100] if title else "Unknown page title"
            return "Unknown page title"
        except Exception as e:
            return f"Title extraction error: {str(e)[:50]}"
    
    def _scrape_with_retry(self, url: str, max_retries: int = 3) -> Dict[str, Any]:
        """Scrape URL with retry logic for rate limits."""
        retries = 0
        backoff_time = 3
        
        while retries < max_retries:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive'
                }
                
                response = requests.get(url, headers=headers, timeout=20)
                response.raise_for_status()
                
                html_content = response.text
                html_size = len(html_content)
                page_title = self._extract_page_title_from_html(html_content)
                
                return {
                    'success': True,
                    'html': html_content,
                    'markdown': BeautifulSoup(html_content, 'html.parser').get_text(),
                    'html_size': html_size,
                    'page_title': page_title
                }
                
            except requests.exceptions.RequestException as e:
                if "429" in str(e) or "rate limit" in str(e).lower():
                    print(f"Rate limit hit for {url}. Waiting {backoff_time}s...")
                    time.sleep(backoff_time)
                    retries += 1
                    backoff_time *= 2
                else:
                    return {
                        'success': False,
                        'error': f"Request failed: {str(e)}",
                        'html': '',
                        'markdown': ''
                    }
        
        return {
            'success': False,
            'error': f"Max retries reached after {max_retries} attempts",
            'html': '',
            'markdown': ''
        }
    
    def get_hackathon_list_urls(self, max_pages: int = 3) -> List[str]:
        """Get URLs for hackathon listing pages."""
        hackathon_urls = []
        
        print(f"🔍 Searching HackerEarth hackathons...")
        
        # Try multiple paths for hackathon discovery
        search_paths = [
            "/challenges/hackathon/",
            "/challenges/competitive/",
            "/challenges/"
        ]
        
        for path in search_paths:
            url = f"{self.base_url}{path}"
            
            result = self._scrape_with_retry(url)
            
            if result['success']:
                page_metadata = {
                    'page_number': 1,
                    'url': url,
                    'path': path,
                    'title': result.get('page_title', 'Unknown'),
                    'html_size': result.get('html_size', 0),
                    'timestamp': time.time()
                }
                self.page_metadata.append(page_metadata)
                
                urls = self._extract_hackathon_urls_from_html(result['html'])
                hackathon_urls.extend(urls)
                
                print(f"   Found {len(urls)} challenges at {path}")
                
                # Small delay between path requests
                time.sleep(2)
            else:
                print(f"   Failed to fetch {path}: {result.get('error')}")
        
        # Remove duplicates
        unique_urls = list(set(hackathon_urls))
        print(f"✅ Found {len(unique_urls)} unique hackathon URLs from HackerEarth")
        return unique_urls
    
    def _extract_hackathon_urls_from_html(self, html: str) -> List[str]:
        """Extract hackathon URLs from HackerEarth HTML."""
        if not html:
            return []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            urls = []
            
            # HackerEarth challenge links
            challenge_selectors = [
                'a[href*="/challenges/hackathon/"]',
                'a[href*="/challenge/"]',
                '.challenge-card a',
                '.hackathon-card a',
                '.challenge-list a'
            ]
            
            for selector in challenge_selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    if href and self._is_hackathon_url(href):
                        if href.startswith('/'):
                            href = urljoin(self.base_url, href)
                        elif not href.startswith('http'):
                            continue
                        
                        # Check if challenge text suggests it's a hackathon
                        challenge_text = link.get_text().strip().lower()
                        hackathon_keywords = [
                            'hackathon', 'hack', 'coding', 'programming', 
                            'contest', 'challenge', 'competition'
                        ]
                        
                        if any(keyword in challenge_text for keyword in hackathon_keywords):
                            urls.append(href)
            
            # Also look for general challenge links and filter by content
            general_links = soup.find_all('a', href=True)
            for link in general_links:
                href = link.get('href')
                text = link.get_text().strip().lower()
                
                if (href and 'challenge' in href and 
                    any(keyword in text for keyword in ['hackathon', 'hack', 'coding', 'programming'])):
                    if href.startswith('/'):
                        href = urljoin(self.base_url, href)
                    if href.startswith('http') and 'hackerearth.com' in href:
                        urls.append(href)
            
            return list(set(urls))  # Remove duplicates
            
        except Exception as e:
            print(f"Error extracting URLs from HackerEarth HTML: {e}")
            return []
    
    def _is_hackathon_url(self, url: str) -> bool:
        """Check if URL is likely a hackathon challenge."""
        if not url:
            return False
        
        # HackerEarth challenge URLs patterns
        hackathon_indicators = [
            '/challenges/hackathon/',
            '/challenge/',
            'hackerearth.com'
        ]
        
        return any(indicator in url for indicator in hackathon_indicators)
    
    def get_hackathon_details(self, url: str) -> Dict[str, Any]:
        """Get detailed information for a specific hackathon."""
        result = self._scrape_with_retry(url)
        
        if not result['success']:
            return {
                'url': url,
                'name': 'Failed to load',
                'source': 'hackerearth',
                'error': result.get('error'),
                'discovery_method': 'hackerearth_search',
                'source_reliability': 0.7,  # Good reliability for HackerEarth
                'data_completeness': 0.1
            }
        
        try:
            soup = BeautifulSoup(result['html'], 'html.parser')
            
            # Extract title
            title = self._extract_title(soup)
            
            # Extract basic details
            details = self._extract_basic_details(soup)
            
            # Calculate quality metrics
            quality_score = self._calculate_content_quality_score(
                result.get('html_size', 0), 
                result['html']
            )
            
            return {
                'url': url,
                'name': title,
                'source': 'hackerearth',
                'discovery_method': 'hackerearth_search',
                'quality_score': quality_score,
                'source_reliability': 0.8,  # High reliability for HackerEarth
                'data_completeness': min(1.0, len([v for v in details.values() if v]) / 8),
                **details
            }
            
        except Exception as e:
            return {
                'url': url,
                'name': 'Parsing failed',
                'source': 'hackerearth',
                'error': str(e),
                'discovery_method': 'hackerearth_search',
                'source_reliability': 0.7,
                'data_completeness': 0.1
            }
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract challenge title from HackerEarth page."""
        title_selectors = [
            'h1.challenge-title',
            '.challenge-header h1',
            '.challenge-name',
            'h1',
            '.page-title',
            'title'
        ]
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text().strip()
                if len(title) > 5 and 'hackerearth' not in title.lower():
                    return title
        
        return "Unknown Challenge"
    
    def _extract_basic_details(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract basic challenge details from HackerEarth page."""
        details = {
            'short_description': None,
            'start_date': None,
            'end_date': None,
            'location': None,
            'organizer': None,
            'prize': None
        }
        
        # Extract description
        desc_selectors = [
            '.challenge-description',
            '.challenge-overview',
            '.problem-statement',
            '.challenge-details'
        ]
        
        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                desc_text = desc_elem.get_text().strip()
                if len(desc_text) > 20:
                    details['short_description'] = desc_text[:300] + "..." if len(desc_text) > 300 else desc_text
                    break
        
        # Extract dates from challenge info
        date_info = soup.select('.challenge-time, .time-left, .challenge-duration')
        for date_elem in date_info:
            date_text = date_elem.get_text().strip()
            if date_text:
                # Try to extract dates with regex
                date_patterns = [
                    r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
                    r'(\d{4}-\d{1,2}-\d{1,2})',
                    r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}'
                ]
                
                for pattern in date_patterns:
                    matches = re.findall(pattern, date_text, re.I)
                    if matches:
                        try:
                            from datetime import datetime
                            date_str = matches[0]
                            # Basic date parsing - could be enhanced
                            if not details['start_date']:
                                details['start_date'] = date_str
                            elif not details['end_date']:
                                details['end_date'] = date_str
                            break
                        except:
                            pass
        
        # Extract organizer info
        organizer_selectors = [
            '.challenge-organizer',
            '.organizer-name',
            '.company-name',
            '.host-name'
        ]
        
        for selector in organizer_selectors:
            org_elem = soup.select_one(selector)
            if org_elem:
                org_text = org_elem.get_text().strip()
                if org_text and len(org_text) > 2:
                    details['organizer'] = org_text
                    break
        
        # Extract prize information
        prize_selectors = [
            '.prize-amount',
            '.reward',
            '.prize-pool',
            '.prize-info'
        ]
        
        for selector in prize_selectors:
            prize_elem = soup.select_one(selector)
            if prize_elem:
                prize_text = prize_elem.get_text().strip()
                if prize_text and ('$' in prize_text or 'prize' in prize_text.lower()):
                    details['prize'] = prize_text
                    break
        
        # Location is typically virtual for HackerEarth
        details['location'] = 'Virtual/Online'
        
        return details
    
    def _calculate_content_quality_score(self, html_size: int, html_content: str) -> float:
        """Calculate quality score based on content richness."""
        score = 0.0
        
        # Size-based scoring
        if html_size > 15000:
            score += 0.4
        elif html_size > 8000:
            score += 0.3
        elif html_size > 3000:
            score += 0.2
        
        # Content-based scoring
        if html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            text = soup.get_text().lower()
            
            # Check for hackathon-specific terms
            hackathon_terms = ['hackathon', 'challenge', 'coding', 'programming', 'contest']
            score += min(0.3, sum(0.1 for term in hackathon_terms if term in text))
            
            # Check for important sections
            important_sections = [
                'problem statement', 'description', 'rules', 'timeline', 
                'prize', 'deadline', 'submission'
            ]
            score += min(0.2, sum(0.05 for section in important_sections if section in text))
            
            # Check for date information
            if any(date_word in text for date_word in ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december', '2024', '2025']):
                score += 0.1
        
        return min(1.0, score)

def get_hackathon_urls(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch hackathon URLs from HackerEarth.
    
    Args:
        limit: Maximum number of hackathons to fetch
        
    Returns:
        List of dictionaries with hackathon information
    """
    print(f"🔍 Fetching {limit} hackathons from HackerEarth...")
    
    scraper = HackerEarthScraper()
    urls = scraper.get_hackathon_list_urls(max_pages=3)
    
    hackathons = []
    for i, url in enumerate(urls[:limit]):
        print(f"📄 Processing hackathon {i+1}/{min(limit, len(urls))}: {url[:80]}...")
        
        details = scraper.get_hackathon_details(url)
        hackathons.append(details)
        
        # Add delay between requests to be respectful
        if i < len(urls) - 1:
            time.sleep(3)
    
    print(f"✅ Successfully processed {len(hackathons)} hackathons from HackerEarth")
    return hackathons 