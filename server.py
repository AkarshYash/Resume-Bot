import os
import json
import time
import threading
from datetime import datetime, date
from flask import Flask, jsonify, request, render_template, send_from_directory, after_this_request
from core.resume_processor import tailor_resume, load_master_resume
from core.doc_generator import generate_pdf, generate_docx
from core.google_helper import get_google_credentials, create_drive_document, log_to_google_sheets, update_google_sheet_status
from core.llm_client import LLMClient
from scrapers.job_aggregator import JobAggregator
import config

app = Flask(__name__, static_folder="static", template_folder="templates")

# Log file or messages
logs = []

def add_log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logs.insert(0, f"[{timestamp}] {msg}")
    if len(logs) > 100:
        logs.pop()

# Queue file path
QUEUE_FILE = "job_queue.json"

def load_queue():
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_queue(queue):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=4)


def build_job_context(limit: int = 6) -> str:
    queue = load_queue()
    pending = [j for j in queue if j.get("status") != "rejected"][:limit]
    if not pending:
        return "There are currently no saved jobs in the queue."

    lines = []
    for job in pending:
        lines.append(
            f"- {job.get('title', 'Role')} at {job.get('company', 'Company')} | "
            f"ATS {job.get('ats_score', 0)}/100 | "
            f"Status: {job.get('status', 'pending')} | "
            f"Drive: {job.get('drive_link') or 'Not uploaded yet'}"
        )
    return "\n".join(lines)


def generate_and_upload_resume(job_dict: dict, creds=None) -> str:
    """Create a local tailored resume PDF, upload it to Drive, and return the shareable URL."""
    import os
    from core.doc_generator import generate_pdf
    from core.google_helper import upload_pdf_to_drive

    save_dir = os.path.join(os.path.dirname(__file__), "Generated_Resumes")
    os.makedirs(save_dir, exist_ok=True)

    safe_company = "".join(c for c in job_dict.get('company', 'Unknown') if c.isalnum() or c in " -_").strip()
    safe_role = "".join(c for c in job_dict.get('job_role', job_dict.get('title', 'Role')) if c.isalnum() or c in " -_").strip()
    filename = f"{safe_company}_{safe_role}_Resume.pdf".replace(" ", "_")
    local_path = os.path.abspath(os.path.join(save_dir, filename))

    generate_pdf(job_dict.get("tailored_resume_text", ""), local_path)

    if not creds:
        add_log(f"No Google credentials — resume saved locally: {filename}")
        return f"Saved Locally: {local_path}"

    folder_id = config.RESUME_DRIVE_FOLDER
    try:
        drive_link = upload_pdf_to_drive(creds, local_path, folder_id, filename)
        add_log(f"Resume uploaded to Drive: {drive_link[:80]}")
        return drive_link
    except Exception as upload_e:
        add_log(f"ERROR: Drive upload failed for {filename}: {upload_e}")
        return f"Saved Locally: {local_path}"


def is_valid_drive_link(link: str) -> bool:
    """Check if a drive_link is a real Google Drive URL (not a local fallback)."""
    if not link:
        return False
    return link.startswith("https://drive.google.com") or link.startswith("https://docs.google.com")

# ─────────────────────────────────────────────────────────────────────────────
#  BACKGROUND AUTO-SCAN THREAD
# ─────────────────────────────────────────────────────────────────────────────
scheduler_running = False
# Track when the last successful scan completed (ISO timestamp)
last_scan_time = None

def auto_scan_loop():
    global scheduler_running, last_scan_time
    while scheduler_running:
        try:
            perform_scan()
            # Update the last successful scan time
            last_scan_time = datetime.utcnow().isoformat() + 'Z'
        except Exception as e:
            add_log(f"Auto-scan failed: {e}")
        # Sleep 1 hour
        for _ in range(3600):
            if not scheduler_running:
                break
            time.sleep(1)

def perform_scan():
    add_log("Starting job discovery scan (AI + scrapers)...")
    aggregator = JobAggregator()
    found_jobs = aggregator.aggregate(config.DEFAULT_KEYWORDS)
    add_log(f"Discovered {len(found_jobs)} matching job listings.")
    
    queue = load_queue()
    existing_urls = {job.get("apply_url") for job in queue}
    
    new_count = 0
    newly_added_jobs = []
    
    for job in found_jobs:
        if job.apply_url and job.apply_url not in existing_urls:
            new_job_dict = {
                "title": job.title,
                "company": job.company,
                "apply_url": job.apply_url,
                "platform": job.platform,
                "posted_date": job.posted_date,
                "jd_text": job.description,
                "ats_score": 0,
                "tech_stack": "",
                "summary_looking_for": "",
                "job_role": job.title,
                "keywords": "",
                "tailored_resume_text": "",
                "status": "pending",
                "drive_link": "",
                "date_added": datetime.now().strftime("%Y-%m-%d")
            }
            queue.append(new_job_dict)
            newly_added_jobs.append(new_job_dict)
            new_count += 1
                
    if new_count > 0:
        save_queue(queue)
        add_log(f"Added {new_count} new jobs. Starting background auto-tailoring...")
        
        # Auto-tailor each newly added job
        from core.resume_processor import tailor_resume
        from core.google_helper import log_to_google_sheets, get_google_credentials
        from core.doc_generator import generate_pdf
        import os
        
        try:
            creds = get_google_credentials()
        except Exception as e:
            add_log(f"Warning: Failed to load Google Credentials: {e}")
            creds = None
            
        save_dir = os.path.join(os.path.dirname(__file__), "Generated_Resumes")
        os.makedirs(save_dir, exist_ok=True)
        
        for job_dict in newly_added_jobs:
            add_log(f"Auto-tailoring resume for {job_dict['title']} at {job_dict['company']}...")
            try:
                ai_data = tailor_resume(
                    master_resume_path=config.MASTER_RESUME_FILE,
                    jd_text=job_dict.get("jd_text", ""),
                    provider=config.DEFAULT_LLM_PROVIDER
                )
                
                job_dict["ats_score"] = ai_data.get("ats_score", 0)
                job_dict["tech_stack"] = ai_data.get("tech_stack", "")
                job_dict["summary_looking_for"] = ai_data.get("summary_looking_for", "")
                job_dict["job_role"] = ai_data.get("job_role", job_dict["title"])
                job_dict["keywords"] = ai_data.get("keywords", "")
                job_dict["tailored_resume_text"] = ai_data.get("tailored_resume_text", "")
                
                drive_link = generate_and_upload_resume(job_dict, creds)
                job_dict["drive_link"] = drive_link

                if is_valid_drive_link(drive_link):
                    add_log(f"Drive link ready for {job_dict['company']}: {drive_link[:60]}...")
                else:
                    add_log(f"WARNING: No Drive link for {job_dict['company']} — saved locally only")

                if creds:
                    add_log(f"Logging {job_dict['company']} to Google Sheets as 'Due'...")
                    from core.google_helper import ensure_google_sheet_entry
                    ensure_google_sheet_entry(creds, job_dict, config.DEFAULT_SHEET_TAB, status="Due")
                
                save_queue(queue)
                # Sleep to avoid strict Groq/LLM TPM rate limits during batch processing
                # Groq free tier = 12k TPM, each call uses ~7-8k tokens → need ~60s+ between calls
                import time
                time.sleep(65)
            except Exception as e:
                add_log(f"Warning: Auto-tailoring failed for {job_dict['title']}: {e}")
                
        add_log("Background auto-tailoring complete!")
    else:
        add_log("Scan complete. No new unique jobs found.")

# ─────────────────────────────────────────────────────────────────────────────
#  API ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/stats", methods=["GET"])
def get_stats():
    queue = load_queue()
    today_str = date.today().strftime("%Y-%m-%d")

    pending = sum(1 for j in queue if j.get("status") == "pending")
    # Support both old "applied" and new "approved" status
    approved = sum(1 for j in queue if j.get("status") in ("applied", "approved"))
    # Include timestamp of last auto-scan (may be null if never run)
    last_scan = last_scan_time
    rejected = sum(1 for j in queue if j.get("status") == "rejected")
    total_jobs = len(queue)
    new_today = sum(1 for j in queue if j.get("date_added", "") == today_str)
    resumes_generated = sum(1 for j in queue if j.get("tailored_resume_text"))
    drive_uploads = sum(1 for j in queue if j.get("drive_link") and not j["drive_link"].startswith("Saved Locally") and not j["drive_link"].startswith("Error"))
    scored = [j for j in queue if j.get("ats_score", 0) > 0]
    avg_ats = int(sum(j["ats_score"] for j in scored) / len(scored)) if scored else 0
    
    return jsonify({
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "avg_ats": avg_ats,
        "total_jobs": total_jobs,
        "new_today": new_today,
        "resumes_generated": resumes_generated,
        "drive_uploads": drive_uploads,
        "scheduler_running": scheduler_running,
        "last_scan_time": last_scan,
        "logs": logs
    })

@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    queue = load_queue()
    return jsonify(queue)

@app.route("/api/scan", methods=["POST"])
def trigger_scan():
    threading.Thread(target=perform_scan, daemon=True).start()
    return jsonify({"status": "success", "message": "Scan started. New jobs will be added and tailored in the background."})


@app.route("/api/chatbot", methods=["POST"])
def chatbot_assistant():
    data = request.json or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"status": "error", "message": "Please type a question first."}), 400

    try:
        context = build_job_context()
        system_prompt = (
            "You are Resume Bot AI, a knowledgeable career assistant. "
            "You help with:\n"
            "1. **Job Analysis** — Explain job descriptions, required skills, and company culture\n"
            "2. **Resume Optimization** — Suggest resume improvements, keyword optimization, and ATS strategies\n"
            "3. **Interview Preparation** — Provide common interview questions, STAR method tips, and technical prep advice\n"
            "4. **Career Guidance** — Career path recommendations, skill gap analysis, salary negotiation tips\n"
            "5. **Job Fit Analysis** — Compare candidate profile against job requirements\n"
            "6. **Project Info** — This app is a Flask dashboard that discovers remote jobs, scores them with ATS logic, "
            "tailors resumes with AI, uploads PDFs to Google Drive, and logs progress to Google Sheets. "
            "It uses Python, Flask, Google APIs, job scrapers, and LLM providers (Gemini/Groq/OpenRouter).\n\n"
            "Answer concisely in well-formatted markdown with bullets. Be practical and actionable."
        )
        user_prompt = f"Question: {question}\n\nCurrent job context:\n{context}"
        answer = LLMClient.call_llm(system_prompt, user_prompt, provider=config.DEFAULT_LLM_PROVIDER)
        return jsonify({"status": "success", "answer": answer})
    except Exception as exc:
        add_log(f"Chatbot assistant error: {exc}")
        fallback = (
            "I'm currently unable to reach the AI model, but the dashboard is still tracking your jobs. "
            "Try reloading the page or updating the API keys in Settings."
        )
        return jsonify({"status": "success", "answer": fallback})

@app.route("/api/scheduler/toggle", methods=["POST"])
def toggle_scheduler():
    global scheduler_running
    scheduler_running = not scheduler_running
    if scheduler_running:
        threading.Thread(target=auto_scan_loop, daemon=True).start()
        add_log("Auto-scan scheduler turned ON.")
    else:
        add_log("Auto-scan scheduler turned OFF.")
    return jsonify({"status": "success", "scheduler_running": scheduler_running})

@app.route("/api/tailor", methods=["POST"])
def tailor_job():
    """Tailor resume for a single job on-demand (saves API quota)."""
    data = request.json
    apply_url = data.get("apply_url")
    
    queue = load_queue()
    target_job = None
    for job in queue:
        if job["apply_url"] == apply_url:
            target_job = job
            break
            
    if not target_job:
        return jsonify({"status": "error", "message": "Job not found."}), 404
    
    if target_job.get("ats_score", 0) > 0 and target_job.get("tailored_resume_text"):
        return jsonify({"status": "success", "message": "Already tailored."})
    
    try:
        add_log(f"Tailoring resume for: {target_job['title']}...")
        ai_data = tailor_resume(
            master_resume_path=config.MASTER_RESUME_FILE,
            jd_text=target_job.get("jd_text", ""),
            provider=config.DEFAULT_LLM_PROVIDER
        )
        
        target_job["ats_score"] = ai_data["ats_score"]
        target_job["tech_stack"] = ai_data["tech_stack"]
        target_job["summary_looking_for"] = ai_data["summary_looking_for"]
        target_job["job_role"] = ai_data["job_role"]
        target_job["keywords"] = ai_data["keywords"]
        target_job["tailored_resume_text"] = ai_data["tailored_resume_text"]

        try:
            creds = get_google_credentials()
        except Exception:
            creds = None

        target_job["drive_link"] = generate_and_upload_resume(target_job, creds)
        save_queue(queue)

        if creds:
            from core.google_helper import ensure_google_sheet_entry
            ensure_google_sheet_entry(creds, target_job, config.DEFAULT_SHEET_TAB, status="Due")
        
        add_log(f"Tailored! ATS: {ai_data['ats_score']}/100 for {target_job['title']}")
        return jsonify({"status": "success", "ats_score": ai_data["ats_score"]})
    except Exception as e:
        add_log(f"Tailoring failed for '{target_job['title']}': {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/approve", methods=["POST"])
def approve_job():
    """Approve a job: generate resume, upload to Drive, log to Google Sheets. Does NOT apply."""
    data = request.json
    apply_url = data.get("apply_url")
    
    queue = load_queue()
    target_job = None
    for job in queue:
        if job["apply_url"] == apply_url:
            target_job = job
            break
            
    if not target_job:
        return jsonify({"status": "error", "message": "Job not found."}), 404
    
    try:
        # If not yet tailored, tailor first
        if not target_job.get("tailored_resume_text"):
            add_log(f"Tailoring resume before approval for: {target_job['title']}...")
            ai_data = tailor_resume(
                master_resume_path=config.MASTER_RESUME_FILE,
                jd_text=target_job.get("jd_text", ""),
                provider=config.DEFAULT_LLM_PROVIDER
            )
            target_job["ats_score"] = ai_data["ats_score"]
            target_job["tech_stack"] = ai_data["tech_stack"]
            target_job["summary_looking_for"] = ai_data["summary_looking_for"]
            target_job["job_role"] = ai_data["job_role"]
            target_job["keywords"] = ai_data["keywords"]
            target_job["tailored_resume_text"] = ai_data["tailored_resume_text"]
        
        # Generate PDF and upload to Drive
        # Always re-upload: ensures we get a real Drive link even if prior attempt failed
        add_log(f"Generating PDF and uploading to Drive for {target_job['title']}...")
        try:
            creds = get_google_credentials()
        except Exception as cred_e:
            add_log(f"ERROR: Cannot load Google credentials: {cred_e}")
            creds = None

        drive_link = generate_and_upload_resume(target_job, creds)

        if not is_valid_drive_link(drive_link):
            add_log(f"WARNING: Could not upload to Drive. Resume saved locally.")
        else:
            add_log(f"Resume Drive link: {drive_link[:80]}")

        # Log to Google Sheets with status "Approved" (NOT "Applied")
        if creds:
            try:
                add_log(f"Saving to Google Sheet with status 'Approved'...")
                from core.google_helper import ensure_google_sheet_entry
                ensure_google_sheet_entry(
                    creds,
                    {**target_job, "drive_link": drive_link},
                    config.DEFAULT_SHEET_TAB,
                    status="Approved"
                )
                add_log(f"Google Sheet updated successfully for {target_job['title']}")
            except Exception as sheet_e:
                add_log(f"Warning: Google Sheet update failed: {sheet_e}")
        else:
            add_log("Skipping Google Sheet update — no credentials available.")

        # Update local queue — status is "approved" (NOT "applied")
        target_job["status"] = "approved"
        target_job["drive_link"] = drive_link
        save_queue(queue)
        
        add_log(f"Approved & logged: {target_job['title']} at {target_job['company']}")
        return jsonify({"status": "success", "drive_link": drive_link})
    except Exception as e:
        add_log(f"Approval error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/reject", methods=["POST"])
def reject_job():
    data = request.json
    apply_url = data.get("apply_url")
    
    queue = load_queue()
    for job in queue:
        if job["apply_url"] == apply_url:
            job["status"] = "rejected"
            save_queue(queue)
            add_log(f"Rejected job: {job['title']} at {job['company']}")
            return jsonify({"status": "success"})
            
    return jsonify({"status": "error", "message": "Job not found."}), 404

@app.route("/api/download/pdf", methods=["GET"])
def download_pdf():
    apply_url = request.args.get("apply_url")
    queue = load_queue()
    target_job = None
    for job in queue:
        if job["apply_url"] == apply_url:
            target_job = job
            break
            
    if not target_job:
        return "Job not found", 404
        
    filename = f"tailored_resume_{int(time.time())}.pdf"
    path = os.path.join(app.root_path, filename)
    generate_pdf(target_job["tailored_resume_text"], path)
    
    @after_this_request
    def remove_file(response):
        try:
            os.remove(path)
        except Exception:
            pass
        return response
        
    return send_from_directory(app.root_path, filename, as_attachment=True, download_name="tailored_resume.pdf")

@app.route("/api/settings", methods=["GET", "POST"])
def manage_settings():
    if request.method == "POST":
        data = request.json
        config.DEFAULT_LLM_PROVIDER = data.get("llm_provider", config.DEFAULT_LLM_PROVIDER).lower()
        config.GROQ_API_KEY = data.get("groq_key", config.GROQ_API_KEY)
        config.OPENROUTER_API_KEY = data.get("openrouter_key", config.OPENROUTER_API_KEY)
        config.GEMINI_API_KEY = data.get("gemini_key", config.GEMINI_API_KEY)
        config.GOOGLE_SHEET_TITLE = data.get("sheet_title", config.GOOGLE_SHEET_TITLE)
        config.GOOGLE_SPREADSHEET_ID = data.get("sheet_id", getattr(config, "GOOGLE_SPREADSHEET_ID", ""))
        config.DEFAULT_SHEET_TAB = data.get("sheet_tab", config.DEFAULT_SHEET_TAB)
        
        keywords = data.get("keywords", "")
        if keywords:
            config.DEFAULT_KEYWORDS = [k.strip() for k in keywords.split(",") if k.strip()]
            
        add_log("System settings updated successfully.")
        return jsonify({"status": "success"})
        
    return jsonify({
        "llm_provider": config.DEFAULT_LLM_PROVIDER,
        "groq_key": config.GROQ_API_KEY,
        "openrouter_key": config.OPENROUTER_API_KEY,
        "gemini_key": config.GEMINI_API_KEY,
        "sheet_title": config.GOOGLE_SHEET_TITLE,
        "sheet_id": getattr(config, "GOOGLE_SPREADSHEET_ID", ""),
        "sheet_tab": config.DEFAULT_SHEET_TAB,
        "keywords": ", ".join(config.DEFAULT_KEYWORDS)
    })

@app.route("/api/system-info", methods=["GET"])
def system_info():
    """Returns system architecture documentation."""
    return jsonify({
        "project_name": "Resume Bot — AI Job Automator",
        "version": "2.0",
        "description": "An automated job discovery and resume tailoring platform that finds remote software jobs, generates ATS-optimized resumes, uploads them to Google Drive, and tracks everything in Google Sheets.",
        "architecture": {
            "frontend": {
                "title": "Frontend Layer",
                "tech": ["HTML5", "CSS3 (Vanilla)", "JavaScript (ES6+)"],
                "description": "Single-page dashboard served by Flask with tab-based navigation, floating AI chatbot, real-time stats, and job management interface."
            },
            "backend": {
                "title": "Backend Layer",
                "tech": ["Python 3.10+", "Flask 3.0", "Threading"],
                "description": "RESTful API server handling job queue management, background auto-scanning, resume tailoring orchestration, and Google API integration.",
                "endpoints": [
                    {"method": "GET", "path": "/api/stats", "desc": "Dashboard statistics"},
                    {"method": "GET", "path": "/api/jobs", "desc": "All jobs in queue"},
                    {"method": "POST", "path": "/api/scan", "desc": "Trigger job discovery scan"},
                    {"method": "POST", "path": "/api/tailor", "desc": "Tailor resume for a specific job"},
                    {"method": "POST", "path": "/api/approve", "desc": "Approve job → save to Google Sheet"},
                    {"method": "POST", "path": "/api/reject", "desc": "Reject a job"},
                    {"method": "POST", "path": "/api/chatbot", "desc": "AI assistant Q&A"},
                    {"method": "POST", "path": "/api/scheduler/toggle", "desc": "Toggle hourly auto-scanner"},
                    {"method": "GET/POST", "path": "/api/settings", "desc": "Read/write system settings"},
                    {"method": "GET", "path": "/api/system-info", "desc": "System architecture docs"}
                ]
            },
            "ai_layer": {
                "title": "AI & LLM Layer",
                "tech": ["Google Gemini 1.5 Flash", "Groq (Llama 3.3 70B)", "OpenRouter"],
                "description": "Multi-provider LLM routing for resume tailoring, ATS scoring, job discovery, and AI chatbot. Supports Gemini (recommended), Groq (free), and OpenRouter.",
                "capabilities": [
                    "ATS-optimized resume generation from master resume",
                    "Job description analysis and keyword extraction",
                    "ATS score calculation (1-100)",
                    "AI-powered job discovery via Gemini",
                    "Career guidance chatbot"
                ]
            },
            "automation_layer": {
                "title": "Job Discovery & Automation",
                "tech": ["BeautifulSoup4", "RSS/XML Parsing", "Gemini AI Search"],
                "description": "Three-source job aggregation pipeline that discovers remote software development jobs.",
                "sources": [
                    {"name": "AI Job Finder", "type": "Gemini AI", "desc": "Uses Gemini to discover jobs from LinkedIn, Indeed, Glassdoor, and other portals"},
                    {"name": "We Work Remotely", "type": "RSS Feed", "desc": "Parses RSS feeds for remote programming jobs"},
                    {"name": "RemoteOK", "type": "REST API", "desc": "Queries RemoteOK API for remote dev positions"}
                ]
            },
            "google_services": {
                "title": "Google Services Integration",
                "tech": ["Google Drive API v3", "Google Sheets API v4", "Service Account Auth"],
                "description": "Automated Google Workspace integration for resume storage and job tracking.",
                "features": [
                    "Upload tailored PDF resumes to Google Drive",
                    "Set public view sharing on uploaded files",
                    "Log job data to Google Sheets (10 columns)",
                    "Update existing sheet entries on status change",
                    "Find-or-create sheet row logic"
                ]
            }
        },
        "workflow": [
            "Job Discovery — Scan 3 sources for matching jobs",
            "Data Extraction — Parse job title, company, description, URL",
            "Resume Tailoring — AI analyzes JD vs master resume, generates optimized version",
            "PDF Generation — Create formatted PDF from tailored text",
            "Drive Upload — Upload PDF to Google Drive, get shareable link",
            "Sheet Logging — Save all job data + resume link to Google Sheets",
            "User Review — Browse pending jobs on dashboard",
            "Approve/Reject — Approve saves to sheet; Reject discards",
            "Manual Apply — User opens resume link from sheet and applies manually"
        ]
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=(os.environ.get("FLASK_ENV") != "production"))
