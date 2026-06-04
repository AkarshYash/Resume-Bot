import requests
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, JobPosting
from typing import List

class RemoteOKScraper(BaseScraper):
    def __init__(self):
        self.url = "https://remoteok.com/api"

    def search_jobs(self, keywords: List[str]) -> List[JobPosting]:
        postings = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        try:
            res = requests.get(self.url, headers=headers, timeout=12)
            if res.status_code != 200:
                return postings
                
            jobs_data = res.json()
            # The first item is usually a legal/credits dictionary, skip if it doesn't contain a position
            for item in jobs_data:
                if not isinstance(item, dict) or "position" not in item:
                    continue
                    
                title = item.get("position", "")
                company = item.get("company", "")
                desc_html = item.get("description", "")
                apply_url = item.get("url", "")
                posted_date = item.get("date", "")
                
                # Clean description
                soup = BeautifulSoup(desc_html, "html.parser")
                description = soup.get_text(separator="\n").strip()
                
                match = False
                for kw in keywords:
                    if kw.lower() in title.lower() or kw.lower() in description.lower():
                        match = True
                        break
                        
                if match:
                    postings.append(JobPosting(
                        title=title,
                        company=company,
                        location="Remote",
                        description=description,
                        apply_url=apply_url,
                        platform="RemoteOK",
                        posted_date=posted_date
                    ))
        except Exception as e:
            print(f"Error scraping RemoteOK: {e}")
            
        return postings
