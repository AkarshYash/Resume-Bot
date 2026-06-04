from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class JobPosting:
    title: str
    company: str
    location: str
    description: str
    apply_url: str
    platform: str
    posted_date: str
    is_remote: bool = True

class BaseScraper(ABC):
    @abstractmethod
    def search_jobs(self, keywords: List[str]) -> List[JobPosting]:
        """Search and return job postings matching the keywords."""
        pass
