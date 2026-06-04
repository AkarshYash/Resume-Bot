import os
import json
from docx import Document as DocxDocument
from core.llm_client import LLMClient
import config

SYSTEM_PROMPT = """
You are an expert ATS resume optimization specialist and technical recruiter.
I will provide:
1. A detailed master profile / resume
2. The target company's job description (JD)

Your task is to deeply analyze both inputs and create a highly optimized ATS-friendly resume specifically tailored for the target role and company.

CRITICAL OBJECTIVE:
Strategically position the candidate as an extremely strong and highly relevant fit for THIS SPECIFIC ROLE by identifying exactly what the company wants, selecting the most relevant information from the master background, removing irrelevant content, and restructuring projects and experience for maximum ATS and recruiter impact.

VERY IMPORTANT RULES:
DO NOT: invent fake companies, internships, achievements, leadership roles, unrealistic expertise, fake years of experience, or add technologies the candidate does not know.
YOU MAY: optimize wording, improve technical presentation, reorganize sections strategically, combine related responsibilities, and deprioritize/remove weak/irrelevant sections. Everything must remain authentic and grounded in actual experience.

RESUME FORMAT RULES (Plain text, visually clean):
[Name]
[Target Job Title]
[Contact Info]

SUMMARY
[Rewrite the summary specifically for THIS company and role. Emphasize most relevant technologies and ownership. Concise but impactful.]

TECHNICAL SKILLS
[Create a CLEAN ATS-FRIENDLY SKILLS section grouped by categories relevant to JD:]
Programming Languages: [skills]
Frontend Technologies: [skills]
Backend Technologies: [skills]
Cloud/DevOps: [skills]
...etc. Only include technologies that strengthen candidacy for THIS role.

PROFESSIONAL EXPERIENCE
[Company Name] | [Role] | ([Dates])
- [6 to 8 strong bullet points per role]
- [Distribution: 70% technical depth focusing on architecture, scalable systems, cloud, CI/CD, performance. 30% ownership, collaboration, mentoring, business impact.]

PROJECTS (If relevant)
[Project Name]
- [Explain architecture, technologies used, integrations, and business impact]

EDUCATION
[Degree and Institution]

ROLE-BASED OPTIMIZATION LOGIC:
- If Software Engineering: Prioritize scalable systems, APIs, cloud, CI/CD, testing, microservices.
- If AI/ML: Prioritize ML pipelines, model deployment, NLP/CV, vector databases, MLOps.
- If Cybersecurity: Prioritize IAM, SOC, pentesting, cloud security, compliance.

OUTPUT FORMAT:
You MUST return ONLY a valid JSON object. No markdown fences, no extra text.
{
  "tailored_resume_text": "<The complete rewritten resume in plain text. Use standard text, avoid special decorative symbols, use '-' for bullets.>",
  "tech_stack": "<Primary tech stack summary, e.g. 'Python, AWS, Node.js'>",
  "summary_looking_for": "<Brief bullet points of what the employer is looking for>",
  "job_role": "<Job title from JD>",
  "keywords": "<Comma-separated list of 10-20 critical ATS keywords extracted from JD>",
  "ats_score": <Integer 1-100 reflecting match quality after optimization>,
  "analysis": {
    "missing_keywords": "<List of JD keywords missing from profile>",
    "removed_skills": "<List of skills removed because they were irrelevant>",
    "recruiter_tips": "<Suggestions for improvement>"
  }
}
"""

def load_master_resume(filepath: str) -> str:
    """Reads the master resume from a .docx Word file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Master resume not found at: {filepath}")
        
    doc = DocxDocument(filepath)
    paragraphs = [para.text for para in doc.paragraphs]
    content = "\n".join(paragraphs).strip()
    if not content:
        raise ValueError("master_resume.docx appears to be empty.")
    return content

def tailor_resume(master_resume_path: str, jd_text: str, provider: str = None) -> dict:
    """Uses the specified LLM client to optimize and score the resume for the JD."""
    master_resume = load_master_resume(master_resume_path)
    master_resume = LLMClient.sanitize_text(master_resume)
    jd_text = LLMClient.sanitize_text(jd_text)

    user_prompt = (
        f"MASTER PROFILE / RESUME:\n{master_resume}\n\n"
        f"JOB DESCRIPTION:\n{jd_text}"
    )
    
    raw_response = LLMClient.call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        provider=provider
    )
    
    parsed = LLMClient.clean_json_response(raw_response)
    
    required_keys = {
        "tailored_resume_text", "tech_stack", "summary_looking_for",
        "job_role", "keywords", "ats_score",
    }
    missing = required_keys - parsed.keys()
    if missing:
        raise ValueError(f"LLM response missing keys: {missing}")
        
    return parsed
