import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, JobPosting
from typing import List

class WeWorkRemotelyScraper(BaseScraper):
    def __init__(self):
        self.feed_urls = [
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss"
        ]

    def search_jobs(self, keywords: List[str]) -> List[JobPosting]:
        postings = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
        for url in self.feed_urls:
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code != 200:
                    continue
                    
                root = ET.fromstring(res.content)
                for item in root.findall(".//item"):
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    desc_html = item.find("description").text if item.find("description") is not None else ""
                    
                    # Clean HTML description
                    soup = BeautifulSoup(desc_html, "html.parser")
                    description = soup.get_text(separator="\n").strip()
                    
                    # Check keywords match in title or description
                    match = False
                    for kw in keywords:
                        if kw.lower() in title.lower() or kw.lower() in description.lower():
                            match = True
                            break
                            
                    if match:
                        company = "Unknown Company"
                        if " at " in title:
                            # e.g., "Full Stack Developer at Acme Corp"
                            parts = title.split(" at ")
                            title_clean = parts[0].strip()
                            company = parts[1].strip()
                        else:
                            title_clean = title
                            
                        postings.append(JobPosting(
                            title=title_clean,
                            company=company,
                            location="Remote",
                            description=description,
                            apply_url=link,
                            platform="We Work Remotely",
                            posted_date=pub_date
                        ))
            except Exception as e:
                print(f"Error scraping We Work Remotely: {e}")
                
        return postings
