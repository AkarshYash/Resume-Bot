"""
AI-Powered Job Finder using Gemini.
Uses Gemini to generate structured job listings for US-based fully remote
software development positions, similar to asking Gemini directly.
"""
import json
import re
import google.generativeai as genai
from scrapers.base_scraper import BaseScraper, JobPosting
from typing import List
import config


class AIJobFinder(BaseScraper):
    """Uses Gemini AI to discover and generate structured remote job listings."""

    SYSTEM_PROMPT = """You are a job search assistant specializing in US-based fully remote
software development positions. You have extensive knowledge of current job openings across
major job portals like LinkedIn, Indeed, Glassdoor, We Work Remotely, RemoteOK, AngelList,
Dice, ZipRecruiter, and company career pages.

When asked, you will generate a JSON array of realistic, current job listings.
Each job must be a JSON object with these exact keys:
{
  "title": "exact job title",
  "company": "company name",
  "location": "Remote - US",
  "description": "2-3 sentence description of the role, key requirements, and tech stack",
  "apply_url": "realistic apply URL from a job portal",
  "platform": "which job portal (LinkedIn, Indeed, etc.)",
  "posted_date": "approximate posting date in format like Jun 2, 2026"
}

RULES:
- ALL jobs must be US-based and fully remote
- Focus on software development, engineering, cloud, AI/ML, data, DevOps roles
- Include a mix of junior, mid-level, and senior positions
- Include a mix of different tech stacks (Python, React, Node.js, Java, Go, etc.)
- Use realistic company names and job portals
- Return ONLY the raw JSON array, no markdown fences, no extra text
- Each job description should mention 3-5 specific technologies
"""

    def search_jobs(self, keywords: List[str]) -> List[JobPosting]:
        """Use the configured LLM provider to find/generate job listings matching keywords."""
        from core.llm_client import LLMClient

        keywords_str = ", ".join(keywords)
        import random
        random_modifier = random.choice([
            "Focus on startups and mid-size companies.",
            "Focus on enterprise companies.",
            "Focus on remote-first companies.",
            "Include some interesting niche tech roles.",
            "Focus on high-growth product companies.",
            "Include both recent postings (last 24 hours) and slightly older ones."
        ])

        user_prompt = (
            f"Find 30 current US-based fully remote job openings in these categories: {keywords_str}.\n"
            f"Include jobs from multiple job portals (LinkedIn, Indeed, Glassdoor, We Work Remotely, etc.).\n"
            f"Focus on software development, cloud engineering, full stack, frontend, backend, "
            f"DevOps, AI/ML, and data engineering roles.\n"
            f"{random_modifier}\n"
            f"Ensure these are unique compared to typical generic examples. "
            f"Return the results as a JSON array."
        )

        try:
            # Route through LLMClient so it can use Groq/Gemini/OpenRouter as configured
            raw_text = LLMClient.call_llm(self.SYSTEM_PROMPT, user_prompt, provider=config.DEFAULT_LLM_PROVIDER)
            raw_text = raw_text.strip()

            # Strip markdown fences if present
            raw_text = re.sub(r"^```(?:json)?", "", raw_text, flags=re.MULTILINE).strip()
            raw_text = re.sub(r"```$", "", raw_text, flags=re.MULTILINE).strip()

            # Try to find JSON array
            match = re.search(r"\[.*\]", raw_text, re.DOTALL)
            if match:
                raw_text = match.group(0)

            jobs_data = json.loads(raw_text)

            postings = []
            import urllib.parse
            for item in jobs_data:
                if not isinstance(item, dict):
                    continue
                    
                apply_url = item.get("apply_url", "").strip()
                title = item.get("title", "Unknown Role")
                company = item.get("company", "Unknown Company")
                
                # The AI always hallucinates fake URLs (like /viewjob?jk=...). 
                # So we must discard whatever it gives us and use a safe Google search link.
                query = urllib.parse.quote(f"{title} {company} careers")
                apply_url = f"https://www.google.com/search?q={query}"
                        
                postings.append(JobPosting(
                    title=title,
                    company=company,
                    location=item.get("location", "Remote - US"),
                    description=item.get("description", ""),
                    apply_url=apply_url,
                    platform=item.get("platform", "AI Discovery"),
                    posted_date=item.get("posted_date", ""),
                    is_remote=True,
                ))

            return postings

        except json.JSONDecodeError as e:
            print(f"AI Job Finder JSON parse error: {e}")
            return []
        except Exception as e:
            print(f"AI Job Finder error: {e}")
            return []
