from scrapers.weworkremotely import WeWorkRemotelyScraper
from scrapers.remoteok import RemoteOKScraper
from scrapers.ai_job_finder import AIJobFinder
from typing import List, Dict
from scrapers.base_scraper import JobPosting

class JobAggregator:
    def __init__(self):
        self.scrapers = [
            AIJobFinder(),           # AI-powered Gemini job discovery (primary)
            WeWorkRemotelyScraper(), # RSS feed scraper
            RemoteOKScraper()       # API scraper
        ]

    def aggregate(self, keywords: List[str]) -> List[JobPosting]:
        all_postings = []
        for scraper in self.scrapers:
            try:
                results = scraper.search_jobs(keywords)
                all_postings.extend(results)
            except Exception as e:
                print(f"Scraper error ({scraper.__class__.__name__}): {e}")
                
        # Deduplication based on title & company name
        seen = set()
        deduped = []
        for post in all_postings:
            key = (post.title.lower().strip(), post.company.lower().strip())
            if key not in seen:
                seen.add(key)
                deduped.append(post)
                
        return deduped
