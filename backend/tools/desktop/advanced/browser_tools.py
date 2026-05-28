import webbrowser
import urllib.parse
import subprocess
import os

def open_url(url: str) -> str:
    """
    Opens a specified URL in the user's default web browser.
    Useful for navigating to specific websites like Gmail, Facebook, or custom URLs.
    """
    if not url.startswith("http"):
        url = "https://" + url
    
    try:
        webbrowser.open(url)
        return f"SUCCESS: Opened {url} in the default browser."
    except Exception as e:
        return f"ERROR: Failed to open {url}. {e}"

def search_youtube(query: str) -> str:
    """
    Searches YouTube for the specified query, finds the first video, and plays it.
    """
    try:
        import urllib.request
        import re
        import ssl
        
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        req = urllib.request.Request(search_url, headers=headers)
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        video_id = None
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=8) as response:
                html = response.read().decode('utf-8')
                
                # Match videoId in JSON or page source
                video_ids = re.findall(r'"videoId":"([^"]+)"', html)
                if video_ids:
                    for vid in video_ids:
                        if len(vid) == 11:
                            video_id = vid
                            break
                            
                if not video_id:
                    # Fallback to simple watch match
                    watch_matches = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html)
                    if watch_matches:
                        video_id = watch_matches[0]
        except Exception:
            pass
            
        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
            open_url(url)
            return f"SUCCESS: Found first video and opened {url} to play it."
        else:
            open_url(search_url)
            return f"SUCCESS: Failed to extract direct video, opened search results page: {search_url}"
            
    except Exception as e:
        return f"ERROR: Failed to play YouTube query '{query}'. {e}"

def search_google(query: str) -> str:
    """
    Searches Google for the specified query and opens the results page.
    """
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={encoded_query}"
    return open_url(url)

def gmail_action(action_type: str, query: str = None, to_recipient: str = None, body: str = None) -> str:
    """
    Perform specific Gmail actions in the default web browser, such as searching or composing messages.
    
    Args:
        action_type (str): The action to perform. Must be 'search' (to search emails), 'compose' (to compose a new draft), or 'inbox' (to open inbox).
        query (str, optional): The search query (e.g., contact name, email address, or keyword) when action_type is 'search'.
        to_recipient (str, optional): The recipient's email address or contact name when action_type is 'compose'.
        body (str, optional): The body content of the email when action_type is 'compose'.
    """
    action_type = action_type.lower().strip()
    if action_type == "inbox":
        url = "https://mail.google.com/mail/u/0/#inbox"
    elif action_type == "search":
        if not query:
            return "ERROR: Query parameter is required for search action."
        encoded_query = urllib.parse.quote(query)
        url = f"https://mail.google.com/mail/u/0/#search/{encoded_query}"
    elif action_type == "compose":
        to_str = urllib.parse.quote(to_recipient or "")
        body_str = urllib.parse.quote(body or "")
        url = f"https://mail.google.com/mail/u/0/?view=cm&fs=1&to={to_str}&body={body_str}"
    else:
        return f"ERROR: Invalid action_type '{action_type}'. Supported types are 'inbox', 'search', 'compose'."
        
    return open_url(url)

def send_background_email(to_recipient: str, subject: str, body: str, attachment_path: str = None, folder_hint: str = "") -> str:
    """
    Sends an email fully in the background using the user's saved Gmail credentials.
    Can optionally attach a file from the PC.

    Args:
        to_recipient (str): Recipient email address.
        subject (str):      Email subject line.
        body (str):         Email body text.
        attachment_path (str, optional):
            Either an absolute file path  (e.g. "C:\\Users\\username\\Downloads\\report.pdf")
            OR just a filename / partial name (e.g. "report.pdf" or "resume").
            When a plain name is given, Maya searches Documents → Downloads → Desktop → all drives
            and uses the first matching document/media file.
        folder_hint (str, optional):
            Folder name to search first (e.g. "RRB", "NTPC"). Speeds up search significantly.
    """
    from backend.database.connection import SessionLocal
    from backend.database.models import UserPreferences
    from backend.database.crypto import crypto_manager
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders

    gmail_user = os.getenv("GMAIL_EMAIL")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        db = SessionLocal()
        try:
            email_pref = db.query(UserPreferences).filter(UserPreferences.key == "GMAIL_EMAIL").first()
            pass_pref = db.query(UserPreferences).filter(UserPreferences.key == "GMAIL_APP_PASSWORD").first()
            if email_pref and pass_pref:
                gmail_user = crypto_manager.decrypt(email_pref.value)
                gmail_password = crypto_manager.decrypt(pass_pref.value)
        except Exception as db_err:
            return f"ERROR: Failed to fetch credentials from DB. {db_err}"
        finally:
            db.close()

    if not gmail_user or not gmail_password:
        return (
            "ERROR: Gmail credentials not configured. "
            "Please tell Maya to save your Gmail address and App Password."
        )

    # ── File resolution ───────────────────────────────────────────────────────
    # Use the shared _find_file_in_search_dirs from system_tools which:
    #   - Excludes the Maya project directory (prevents returning .py script files)
    #   - Prioritises PDF/DOC/images over scripts
    #   - Supports folder_hint for faster targeted search
    # ─────────────────────────────────────────────────────────────────────────
    resolved_path: str | None = None
    if attachment_path:
        if os.path.isabs(attachment_path) and os.path.isfile(attachment_path):
            resolved_path = attachment_path
        else:
            from backend.tools.desktop.advanced.system_tools import _find_file_in_search_dirs
            resolved_path = _find_file_in_search_dirs(attachment_path, folder_hint=folder_hint)
            if not resolved_path:
                return (
                    f"ERROR: Could not find a file matching '{attachment_path}' in "
                    f"Documents, Downloads, Desktop, or any drive. Please provide the full file path."
                )

    try:
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        if resolved_path:
            with open(resolved_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(resolved_path)}",
            )
            msg.attach(part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, to_recipient, msg.as_string())

        attachment_note = f" with '{os.path.basename(resolved_path)}' attached" if resolved_path else ""
        return f"SUCCESS: Email sent to {to_recipient}{attachment_note}."
    except Exception as e:
        return f"ERROR: Failed to send email: {e}"
