import os
import sys
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
import config

def get_google_credentials():
    if not os.path.exists(config.CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"'{config.CREDENTIALS_FILE}' not found. "
            "Please ensure credentials.json is in the project directory."
        )
    return service_account.Credentials.from_service_account_file(
        config.CREDENTIALS_FILE, scopes=config.SCOPES
    )

import io
from googleapiclient.http import MediaIoBaseUpload

def create_drive_document(credentials, tailored_resume: str, job_role: str) -> str:
    """
    Creates a Google Doc with the tailored resume using Drive API, 
    sets it to public view, and returns the web-view URL.
    """
    today = datetime.now()
    date_str = today.strftime("%d %B %Y")
    doc_title = f"{date_str} - Tailored Resume - {job_role}"

    drive_service = build("drive", "v3", credentials=credentials)

    # Use Drive API to upload text and convert it to a Google Doc directly
    file_metadata = {
        'name': doc_title,
        'mimeType': 'application/vnd.google-apps.document'
    }
    
    # If a resume folder is configured, put the doc there (service accounts need this)
    if hasattr(config, 'RESUME_DRIVE_FOLDER') and config.RESUME_DRIVE_FOLDER:
        file_metadata['parents'] = [config.RESUME_DRIVE_FOLDER]
    
    # Encode string to bytes so MediaIoBaseUpload can process it
    media = MediaIoBaseUpload(io.BytesIO(tailored_resume.encode('utf-8')), mimetype='text/plain', resumable=True)
    
    doc = drive_service.files().create(
        body=file_metadata, 
        media_body=media, 
        fields='id',
        supportsAllDrives=True
    ).execute()
    
    doc_id = doc.get('id')

    # Set sharing: anyone with the link can view
    drive_service.permissions().create(
        fileId=doc_id,
        body={"type": "anyone", "role": "reader"},
        fields="id",
        supportsAllDrives=True
    ).execute()

    # Get the shareable URL
    meta = drive_service.files().get(
        fileId=doc_id, fields="webViewLink", supportsAllDrives=True
    ).execute()
    return meta.get("webViewLink", "")

def upload_pdf_to_drive(credentials, pdf_path: str, folder_id: str, title: str) -> str:
    """
    Uploads a local PDF file to Google Drive, sets it to public view,
    and returns the web-view URL.
    
    Service accounts have no personal storage — they MUST upload into a folder
    shared with them (or a Shared Drive). We pass supportsAllDrives=True so
    both regular shared folders and Shared Drives work.
    """
    drive_service = build("drive", "v3", credentials=credentials)
    pdf_bytes = open(pdf_path, 'rb').read()
    
    file_id = None

    if not folder_id:
        raise Exception(
            "No Drive folder ID configured. Service accounts cannot upload to root. "
            "Set RESUME_DRIVE_FOLDER in config to a folder ID shared with your service account."
        )

    # Upload to the specified shared folder
    try:
        file_metadata = {'name': title, 'parents': [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype='application/pdf', resumable=True)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        file_id = file.get('id')
    except Exception as upload_err:
        raise Exception(
            f"Drive upload failed for folder '{folder_id}': {upload_err}. "
            "Make sure the folder is shared with the service account email (Editor access)."
        )

    # Set sharing: anyone with the link can view
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            fields="id",
            supportsAllDrives=True
        ).execute()
    except Exception as perm_err:
        print(f"Warning: Could not set sharing permissions: {perm_err}")
    
    # Get the shareable URL
    meta = drive_service.files().get(
        fileId=file_id, fields="webViewLink", supportsAllDrives=True
    ).execute()
    return meta.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

def log_to_google_sheets(
    credentials,
    apply_link: str,
    drive_url: str,
    ai_data: dict,
    sheet_tab: str,
    status: str = "Due"
) -> int:
    """
    Finds the next empty row in the specified sheet tab and writes columns A–J.
    """
    sheets_service = build("sheets", "v4", credentials=credentials)
    drive_service  = build("drive",  "v3", credentials=credentials)

    # Locate spreadsheet
    spreadsheet_id = getattr(config, "GOOGLE_SPREADSHEET_ID", None)
    if not spreadsheet_id:
        results = drive_service.files().list(
            q=(
                f"name='{config.GOOGLE_SHEET_TITLE}' "
                "and mimeType='application/vnd.google-apps.spreadsheet' "
                "and trashed=false"
            ),
            fields="files(id, name)",
        ).execute()

        files = results.get("files", [])
        if not files:
            raise FileNotFoundError(f"Google Sheet titled '{config.GOOGLE_SHEET_TITLE}' not found.")

        spreadsheet_id = files[0]["id"]

    # Read column A to find the next empty row
    col_a_range = f"'{sheet_tab}'!A:A"
    try:
        col_a = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=col_a_range,
        ).execute()
    except HttpError as e:
        raise HttpError(f"Could not read sheet tab '{sheet_tab}': {e}")

    existing_values = col_a.get("values", [])
    next_row = len(existing_values) + 1

    last_sno = 0
    for row in reversed(existing_values):
        if row:
            cell = str(row[0]).strip().rstrip(".")
            if cell.isdigit():
                last_sno = int(cell)
                break
    new_sno = last_sno + 1

    today = datetime.now()
    date_formatted = today.strftime("%d / %B")
    ats_formatted  = f"ATS Score: {ai_data['ats_score']}/100"

    def _to_str(val):
        if isinstance(val, list):
            return "\n".join(str(v) for v in val)
        if isinstance(val, dict):
            return str(val)
        return val

    row_values = [
        new_sno,
        _to_str(ai_data.get("tech_stack", "")),
        _to_str(ai_data.get("summary_looking_for", "")),
        _to_str(ai_data.get("job_role", "")),
        _to_str(apply_link),
        _to_str(drive_url),
        _to_str(ai_data.get("keywords", "")),
        _to_str(ats_formatted),
        _to_str(date_formatted),
        status,
    ]

    write_range = f"'{sheet_tab}'!A{next_row}:J{next_row}"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=write_range,
        valueInputOption="USER_ENTERED",
        body={"values": [row_values]},
    ).execute()

    return new_sno

def _get_spreadsheet_id(drive_service):
    spreadsheet_id = getattr(config, "GOOGLE_SPREADSHEET_ID", None)
    if spreadsheet_id:
        return spreadsheet_id

    results = drive_service.files().list(
        q=(
            f"name='{config.GOOGLE_SHEET_TITLE}' "
            "and mimeType='application/vnd.google-apps.spreadsheet' "
            "and trashed=false"
        ),
        fields="files(id, name)",
    ).execute()

    files = results.get("files", [])
    if not files:
        raise FileNotFoundError(f"Google Sheet titled '{config.GOOGLE_SHEET_TITLE}' not found.")

    return files[0]["id"]


def find_sheet_row_index(sheets_service, spreadsheet_id: str, sheet_tab: str, apply_link: str) -> int:
    """Return 1-based row index for the matching apply link in Column E, or -1 if not found."""
    col_e_range = f"'{sheet_tab}'!E:E"
    col_e = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=col_e_range,
    ).execute()

    values = col_e.get("values", [])
    for i, row in enumerate(values):
        if row and str(row[0]).strip() == apply_link.strip():
            return i + 1
    return -1


def update_google_sheet_job_entry(credentials, job_dict: dict, sheet_tab: str, status: str = "Due") -> bool:
    """Update an existing sheet row with the latest job + resume data."""
    sheets_service = build("sheets", "v4", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    spreadsheet_id = _get_spreadsheet_id(drive_service)
    row_index = find_sheet_row_index(sheets_service, spreadsheet_id, sheet_tab, job_dict.get("apply_url", ""))
    if row_index == -1:
        return False

    today = datetime.now().strftime("%d / %B")
    ats_formatted = f"ATS Score: {job_dict.get('ats_score', 0)}/100"

    def _to_str(val):
        if isinstance(val, list):
            return "\n".join(str(v) for v in val)
        if isinstance(val, dict):
            return str(val)
        return val

    row_values = [
        row_index,
        _to_str(job_dict.get("tech_stack", "")),
        _to_str(job_dict.get("summary_looking_for", "")),
        _to_str(job_dict.get("job_role", job_dict.get("title", ""))),
        _to_str(job_dict.get("apply_url", "")),
        _to_str(job_dict.get("drive_link", "")),
        _to_str(job_dict.get("keywords", "")),
        _to_str(ats_formatted),
        _to_str(today),
        status,
    ]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_tab}'!A{row_index}:J{row_index}",
        valueInputOption="USER_ENTERED",
        body={"values": [row_values]},
    ).execute()
    return True


def ensure_google_sheet_entry(credentials, job_dict: dict, sheet_tab: str, status: str = "Due") -> bool:
    """Create a row if missing, otherwise refresh the existing row with the latest resume data."""
    sheets_service = build("sheets", "v4", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)
    spreadsheet_id = _get_spreadsheet_id(drive_service)

    row_index = find_sheet_row_index(sheets_service, spreadsheet_id, sheet_tab, job_dict.get("apply_url", ""))
    if row_index != -1:
        return update_google_sheet_job_entry(credentials, job_dict, sheet_tab, status=status)

    log_to_google_sheets(credentials, job_dict.get("apply_url", ""), job_dict.get("drive_link", ""), job_dict, sheet_tab, status=status)
    return True


def update_google_sheet_status(credentials, apply_link: str, sheet_tab: str, new_status: str = "Applied") -> bool:
    """
    Searches the sheet for the row matching the apply_link (Column E),
    and updates its status (Column J) to new_status.
    """
    sheets_service = build("sheets", "v4", credentials=credentials)
    drive_service  = build("drive",  "v3", credentials=credentials)

    spreadsheet_id = getattr(config, "GOOGLE_SPREADSHEET_ID", None)
    if not spreadsheet_id:
        return False
        
    try:
        # Read Column E (Apply Links)
        col_e_range = f"'{sheet_tab}'!E:E"
        col_e = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=col_e_range,
        ).execute()
        
        values = col_e.get("values", [])
        row_index = -1
        
        for i, row in enumerate(values):
            if row and len(row) > 0 and str(row[0]).strip() == apply_link.strip():
                row_index = i + 1 # 1-indexed
                break
                
        if row_index != -1:
            # Update Column J (Status)
            update_range = f"'{sheet_tab}'!J{row_index}"
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=update_range,
                valueInputOption="USER_ENTERED",
                body={"values": [[new_status]]},
            ).execute()
            return True
    except HttpError:
        pass
    return False
