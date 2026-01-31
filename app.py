"""
Discord Archiver - Streamlit Web Application

A web-based tool to archive Discord channels to PDFs and upload to Google Drive.
"""

import base64
import logging
import os
import pickle
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set

import streamlit as st
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from playwright.sync_api import sync_playwright

from config import Config, sanitize_filename
from discord_client import DiscordClient
from html_builder import DiscordRenderer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from shared module
TEMP_DIR = Config.TEMP_DIR
SCOPES = Config.SCOPES

st.set_page_config(page_title="Discord Archiver", page_icon="📂", layout="wide")

# --- AUTH HELPERS ---
# --- AUTH HELPERS ---
# ensure_exporter removed - no longer needed



def get_drive_service() -> Optional[Any]:
    """
    Get authenticated Google Drive service.
    
    Tries credentials in order:
    1. Environment variable (cloud)
    2. Local token.pickle file
    3. Interactive OAuth flow (local only)
    
    Returns:
        Google Drive service object or None if authentication fails.
    """
    creds = None
    
    # 1. Try Environment Variable (Cloud friendly)
    if Config.GOOGLE_DRIVE_TOKEN_BASE64:
        try:
            token_bytes = base64.b64decode(Config.GOOGLE_DRIVE_TOKEN_BASE64)
            creds = pickle.loads(token_bytes)
            logger.info("Loaded credentials from environment variable")
        except Exception as e:
            logger.error(f"Failed to load token from environment: {e}")
            st.error(f"Failed to load token from environment: {e}")
    
    # 2. Try Local File
    if not creds and os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
        logger.info("Loaded credentials from token.pickle")
    
    # 3. Refresh or Create (Only locally)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            logger.info("Refreshed expired credentials")
        else:
            # We cannot do interactive login in the cloud
            if Config.is_cloud_environment():
                logger.error("Authentication expired in cloud environment")
                st.error("Authentication expired or missing in Cloud Environment. Please update GOOGLE_DRIVE_TOKEN_BASE64 variable.")
                return None
                 
            if not os.path.exists('credentials.json'):
                logger.error("Missing credentials.json")
                st.error("Missing credentials.json")
                st.stop()
            
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            success_msg = """
            <html>
                <head><meta http-equiv="refresh" content="0; url=http://localhost:8501" /></head>
                <body>
                    <h1>Authentication Successful!</h1>
                    <p>Redirecting you back to the app...</p>
                    <script>window.location.href = "http://localhost:8501";</script>
                </body>
            </html>
            """
            creds = flow.run_local_server(port=0, success_message=success_msg)
            logger.info("Completed OAuth flow")
            
        # Save locally if possible
        try:
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        except Exception:
            pass

    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, folder_name, parent_id=None):
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    if files: return files[0]['id']
    else:
        file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id: file_metadata['parents'] = [parent_id]
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder['id']

def upload_file(service, file_path, file_name, folder_id):
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype='application/pdf')
    
    query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id)").execute()
    if results.get('files'):
        return False # Skipped
    
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return True # Uploaded

def get_stored_creds():
    """
    Checks for valid credentials in Env Var or Local File without triggering a login flow.
    """
    creds = None
    # 1. Cloud Env Var
    if 'GOOGLE_DRIVE_TOKEN_BASE64' in os.environ:
        try:
            token_bytes = base64.b64decode(os.environ['GOOGLE_DRIVE_TOKEN_BASE64'])
            creds = pickle.loads(token_bytes)
            return creds
        except:
             pass
             
    # 2. Local File
    if os.path.exists('token.pickle'):
        try:
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                if creds and creds.valid:
                    return creds
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    # Check if we can write back
                    try:
                        with open('token.pickle', 'wb') as t:
                             pickle.dump(creds, t)
                    except: pass
                    return creds
        except Exception:
            return None
    return None

def get_existing_archives(service, guild_name):
    """
    Returns a set of channel names (sanitized) that already exist as PDFs in the guild folder.
    """
    archives = set()
    root_id = get_or_create_folder(service, "Discord Archive")
    
    # 1. Find Guild Folder
    g_safe = "".join(c for c in guild_name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
    query = f"mimeType='application/vnd.google-apps.folder' and name='{g_safe}' and '{root_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id)").execute()
    g_files = results.get('files', [])
    if not g_files:
        return archives
    
    g_folder_id = g_files[0]['id']
    
    # 2. List all Category Folders
    # We could do this recursively, but since depth is fixed (Guild -> Category -> Channel.pdf), we can double loop.
    q_cats = f"mimeType='application/vnd.google-apps.folder' and '{g_folder_id}' in parents and trashed=false"
    cats = service.files().list(q=q_cats, fields="files(id, name)").execute().get('files', [])
    
    for cat in cats:
        cat_id = cat['id']
        # 3. List PDFs in Category
        q_pdfs = f"mimeType='application/pdf' and '{cat_id}' in parents and trashed=false"
        pdfs = service.files().list(q=q_pdfs, fields="files(name)").execute().get('files', [])
        for pdf in pdfs:
            # name is typically "channel-name.pdf"
            # We store just the stem for matching
            name = pdf['name']
            if name.endswith('.pdf'):
                archives.add(name[:-4]) # Remove .pdf
                
    return archives

# --- DISCORD HELPERS ---
def run_command(cmd):
    try:
        # Avoid printing to stdout/stderr to keep streamlit clean
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result
    except Exception as e:
        return None

def get_guilds(token):
    client = DiscordClient(token)
    guilds = client.get_guilds()
    # Explicitly add Direct Messages handled by client or manual?
    # For now, client.get_guilds() returns REST objects.
    # We map them to simple dicts
    # Note: client.get_guilds() is already returning dicts from JSON
    
    # Needs explicit DM adding if API doesn't return them (User API does, Bot API typically doesn't see DMs same way)
    # But for now let's stick to Server archiving
    return guilds

# ... [Lines 162-373 unchanged] ...
def get_channels(token, guild_id):
    if guild_id == "0":
        return [] # TODO: DM handling later
        
    client = DiscordClient(token)
    return client.get_channels(guild_id)

def sanitize(name):
    return "".join(c for c in name if c.isalnum() or c in (' ', '.', '_', '-')).strip()

# --- WORKER FUNCTION ---
def archive_channel_task(channel, guild_name, token, drive_creds, temp_base_dir):
    """
    Worker function to process a single channel.
    Runs in a separate process. Must be top-level to be picklable.
    """
    try:
        cid = channel['id']
        c_name = channel['name']
        c_cat = channel['category']
        
        # 1. Setup Drive Service (New instance per process)
        service = build('drive', 'v3', credentials=drive_creds)
        
        # 2. Setup Playwright (New instance per process)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            
            g_safe = "".join(c for c in guild_name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
            c_safe = "".join(c for c in c_cat if c.isalnum() or c in (' ', '.', '_', '-')).strip()
            n_safe = "".join(c for c in c_name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
            
            # Helper to create folders
            def _get_create(srv, name, pid=None):
                q = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
                if pid: q += f" and '{pid}' in parents"
                res = srv.files().list(q=q, fields="files(id)").execute()
                files = res.get('files', [])
                if files: return files[0]['id']
                
                meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
                if pid: meta['parents'] = [pid]
                try:
                    return srv.files().create(body=meta, fields='id').execute()['id']
                except:
                    # Retry once for race conditions
                    time.sleep(1)
                    res = srv.files().list(q=q, fields="files(id)").execute()
                    if res.get('files'): return res['files'][0]['id']
                    return srv.files().create(body=meta, fields='id').execute()['id']

            root_id = _get_create(service, "Discord Archive")
            g_folder = _get_create(service, g_safe, root_id)
            c_folder = _get_create(service, c_safe, g_folder)
            
            # Check if exists
            final_pdf_name = f"{n_safe}.pdf"
            q = f"name='{final_pdf_name}' and '{c_folder}' in parents and trashed=false"
            res = service.files().list(q=q, fields="files(id)").execute()
            if res.get('files'):
                return {"cid": cid, "status": "Exists", "msg": "Already archived"}
            
            # Download & Generate HTML
            temp_path = os.path.join(temp_base_dir, f"{cid}")
            if os.path.exists(temp_path): shutil.rmtree(temp_path)
            os.makedirs(temp_path, exist_ok=True)

            try:
                # Fetch messages
                client = DiscordClient(token)
                all_messages = []
                
                # Fetch all messages (no limit)
                for batch in client.get_messages(cid, limit=None):
                     all_messages.extend(batch)
                
                if not all_messages:
                     shutil.rmtree(temp_path, ignore_errors=True)
                     return {"cid": cid, "status": "Empty", "msg": "No messages found"}

                # Generate HTML
                html_content = DiscordRenderer.render(c_name, all_messages)
                html_path = os.path.join(temp_path, f"{cid}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                
            except Exception as e:
                return {"cid": cid, "status": "Error", "msg": f"Fetch/Render Error: {str(e)}"}

            # Convert to PDF
            try:
                page = browser.new_page()
                page.goto(f"file://{os.path.abspath(html_path)}", wait_until="networkidle") # networkidle for correct rendering
                # Small wait to ensure fonts/images render
                time.sleep(2) 
                pdf_path = os.path.join(temp_path, final_pdf_name)
                page.pdf(path=pdf_path, format="A4", print_background=True, margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"})
                page.close()
            except Exception as e:
                # If playwright fails or times out
                return {"cid": cid, "status": "Error", "msg": f"PDF Gen Failed: {str(e)}"}
            
            # Upload with retry logic
            upload_success = False
            last_upload_error = None
            max_retries = 3
            
            for attempt in range(1, max_retries + 1):
                try:
                    media = MediaFileUpload(pdf_path, mimetype='application/pdf', resumable=True)
                    file_meta = {'name': final_pdf_name, 'parents': [c_folder]}
                    service.files().create(body=file_meta, media_body=media, fields='id').execute()
                    upload_success = True
                    break
                except (BrokenPipeError, ConnectionError, ConnectionResetError, OSError) as e:
                    last_upload_error = e
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)  # Exponential backoff: 2, 4, 8 seconds
                except Exception as e:
                    error_str = str(e).lower()
                    if 'broken pipe' in error_str or 'connection' in error_str or 'timeout' in error_str:
                        last_upload_error = e
                        if attempt < max_retries:
                            time.sleep(2 ** attempt)
                    else:
                        last_upload_error = e
                        break  # Non-retryable error
            
            if not upload_success:
                # Save locally as fallback
                LOCAL_BACKUP_DIR = "Local_Backup_PDFs"
                local_backup_path = os.path.join(LOCAL_BACKUP_DIR, g_safe, c_safe)
                os.makedirs(local_backup_path, exist_ok=True)
                local_pdf_path = os.path.join(local_backup_path, final_pdf_name)
                shutil.copy2(pdf_path, local_pdf_path)
                return {"cid": cid, "status": "Error", "msg": f"Upload Failed, saved locally: {local_pdf_path}"}

            # Cleanup
            shutil.rmtree(temp_path, ignore_errors=True)
            
            return {"cid": cid, "status": "Success", "msg": "Done"}

    except Exception as e:
        return {"cid": channel['id'], "status": "Error", "msg": str(e)}

# --- UI ---
st.markdown("""
    <style>
        /* Main app background */
        .stApp {
            background-color: #1e1f22 !important;
            color: #dcddde;
        }
        
        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: #2b2d31 !important;
        }
        section[data-testid="stSidebar"] .stMarkdown {
            color: #b5bac1;
        }
        
        /* Headers */
        h1, h2, h3, h4, h5, h6 {
            color: #ffffff !important;
        }
        
        /* All text */
        .stMarkdown, p, span, label {
            color: #dcddde !important;
        }
        
        /* Buttons */
        .stButton > button {
            background-color: #5865f2 !important;
            color: white !important;
            border: none !important;
            border-radius: 4px !important;
        }
        .stButton > button:hover {
            background-color: #4752c4 !important;
        }
        
        /* Form submit button */
        .stFormSubmitButton > button {
            background-color: #5865f2 !important;
            color: white !important;
            border: none !important;
        }
        .stFormSubmitButton > button:hover {
            background-color: #4752c4 !important;
        }
        
        /* Checkboxes */
        .stCheckbox label {
            color: #dcddde !important;
        }
        
        /* Radio buttons */
        .stRadio label {
            color: #dcddde !important;
        }
        div[data-testid="stRadio"] > div {
            background-color: transparent !important;
        }
        
        /* Form container */
        .stForm {
            background-color: #2b2d31 !important;
            border: 1px solid #3f4147 !important;
            border-radius: 8px !important;
            padding: 20px !important;
        }
        
        /* Spinner */
        .stSpinner > div {
            color: #dcddde !important;
        }
        
        /* Status bars - Discord style */
        /* Success - green bar for Done/Uploaded */
        div[data-testid="stAlert"][data-baseweb="notification"]:has(div[role="alert"]:contains("✅")),
        .stSuccess, div.stSuccess,
        div[data-testid="stNotification"] div[role="alert"] {
            background-color: #2d4f3c !important;
            border: none !important;
            border-radius: 4px !important;
        }
        div.element-container:has(.stSuccess) {
            background-color: transparent !important;
        }
        .stSuccess > div, .stSuccess p {
            color: #3ba55c !important;
            font-weight: 500 !important;
        }
        
        /* Error - red bar for failures */
        .stError, div.stError {
            background-color: #4f2d2d !important;
            border: none !important;
            border-radius: 4px !important;
        }
        .stError > div, .stError p {
            color: #ed4245 !important;
            font-weight: 500 !important;
        }
        
        /* Warning - amber bar */
        .stWarning, div.stWarning {
            background-color: #4f3d2d !important;
            border: none !important;
            border-radius: 4px !important;
        }
        .stWarning > div, .stWarning p {
            color: #faa61a !important;
            font-weight: 500 !important;
        }
        
        /* Info - dark blue bar for Queued */
        .stInfo, div.stInfo {
            background-color: #1e3a5f !important;
            border: none !important;
            border-radius: 4px !important;
        }
        .stInfo > div, .stInfo p {
            color: #5865f2 !important;
            font-weight: 500 !important;
        }
        
        /* General alert styling */
        .stAlert {
            background-color: #2b2d31 !important;
            color: #dcddde !important;
            border-radius: 4px !important;
            border: none !important;
        }
        
        /* Style the alert containers to be full width */
        div[data-testid="stAlert"] {
            padding: 8px 12px !important;
            border-radius: 4px !important;
            min-height: 36px !important;
        }
        
        /* Progress bar */
        .stProgress > div > div {
            background-color: #5865f2 !important;
        }
        
        /* Category header */
        .category-header {
            text-transform: uppercase;
            font-size: 12px;
            font-weight: bold;
            color: #949ba4 !important;
            margin-top: 20px;
            margin-bottom: 5px;
        }
        
        /* Channel row */
        .channel-row {
            display: flex;
            align-items: center;
            padding: 5px 0;
            border-radius: 4px;
        }
        
        /* Login container */
        .login-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 50px;
            border: 1px solid #3f4147;
            border-radius: 8px;
            background-color: #2b2d31;
        }
        .login-container h3, .login-container p {
            color: #dcddde !important;
        }
        
        /* Dividers */
        hr {
            border-color: #3f4147 !important;
        }
        
        /* Remove default white backgrounds */
        .element-container, .stMarkdown, div[data-testid="column"] {
            background-color: transparent !important;
        }
        
        /* Expander */
        .streamlit-expanderHeader {
            background-color: #2b2d31 !important;
            color: #dcddde !important;
        }
        
        /* Success/Warning/Error messages */
        div[data-testid="stNotification"] {
            background-color: #2b2d31 !important;
        }
        
        /* File change notification bar - dark style */
        div[data-testid="stStatusWidget"],
        .stStatusWidget,
        div[data-testid="stAppDeployButton"],
        div[data-testid="stToolbar"] {
            background-color: #1e1f22 !important;
            color: #dcddde !important;
        }
        
        /* Header and main area */
        header[data-testid="stHeader"],
        .stDeployButton,
        div[data-testid="stDecoration"],
        div[data-testid="stToolbar"] button,
        .stToolbar {
            background-color: #1e1f22 !important;
            color: #dcddde !important;
        }
        
        /* Main content blocks */
        .main .block-container {
            background-color: transparent !important;
        }
        
        /* Any remaining white backgrounds */
        .css-1d391kg, .css-12oz5g7, .css-1adrfps,
        .css-18e3th9, .css-1629p8f, .css-k1vhr4,
        .stMainBlockContainer, div[data-testid="stMainBlockContainer"] {
            background-color: #1e1f22 !important;
        }
        
        /* Toast messages */
        div[data-testid="stToast"] {
            background-color: #2b2d31 !important;
            color: #dcddde !important;
        }
        
        /* Bottom container / footer area */
        div[data-testid="stBottomBlockContainer"],
        footer, .stBottom {
            background-color: #1e1f22 !important;
        }
        
        /* Any iframe or embedded elements */
        iframe {
            background-color: #1e1f22 !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- OAUTH AUTH ---
if Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET:
    if 'user_info' not in st.session_state:
        
        # Check for Code
        if 'code' in st.query_params:
            try:
                code = st.query_params['code']
                
                # Create Flow
                flow = Flow.from_client_config(
                    {
                        "web": {
                            "client_id": Config.GOOGLE_CLIENT_ID,
                            "client_secret": Config.GOOGLE_CLIENT_SECRET,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                        }
                    },
                    scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email'],
                    redirect_uri=Config.REDIRECT_URI
                )
                
                flow.fetch_token(code=code)
                credentials = flow.credentials
                
                # Fetch User Info
                user_info_service = build('oauth2', 'v2', credentials=credentials)
                user_info = user_info_service.userinfo().get().execute()
                
                st.session_state.user_info = user_info
                st.query_params.clear() # Clear code from URL
                st.rerun()
                
            except Exception as e:
                st.error(f"Login Failed: {str(e)}")
                if st.button("Try Again"):
                    st.query_params.clear()
                    st.rerun()
                st.stop()
        
        else:
            # Show Login Button
            st.title("🔒 Login Required")
            
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": Config.GOOGLE_CLIENT_ID,
                        "client_secret": Config.GOOGLE_CLIENT_SECRET,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email'],
                redirect_uri=Config.REDIRECT_URI
            )
            
            auth_url, _ = flow.authorization_url(prompt='consent')
            
            st.markdown(f'<a href="{auth_url}" target="_self"><button style="background-color:#4285F4; color:white; padding:10px 20px; border:none; border-radius:4px; font-size:16px;">Sign in with Google</button></a>', unsafe_allow_html=True)
            st.stop()

# --- AUTH GATE ---
creds = get_stored_creds()
if not creds:
    st.title("📂 Discord Archiver")
    
    st.markdown("""
    <div class="login-container">
        <h3>Authentication Required</h3>
        <p>Please login to continue.</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if st.button("🔐 Login with Google", type="primary", use_container_width=True):
            get_drive_service() # Trigger flow
            st.rerun()
            
    st.stop()

# --- APP START ---
# Store creds for workers
st.session_state.drive_creds = creds

# Top Bar Layout
col_title, col_logout = st.columns([6, 1])
with col_title:
    st.title("📂 Discord Archiver")
with col_logout:
    st.write("") # Spacer
    if st.button("Logout"):
        if os.path.exists("token.pickle"):
            os.remove("token.pickle")
        st.session_state.pop('drive_creds', None)
        st.session_state.pop('user_info', None)
        st.rerun()

# Get Discord token from environment (secure)
DISCORD_TOKEN = Config.get_discord_token()
if not DISCORD_TOKEN:
    st.error("⚠️ Missing DISCORD_BOT_TOKEN environment variable. Please set it in your .env file.")
    st.stop()
st.session_state.token = DISCORD_TOKEN

if 'guilds' not in st.session_state:
    st.session_state.guilds = []
    if st.session_state.token:
        with st.spinner("Authenticated. Loading servers..."):
            st.session_state.guilds = get_guilds(st.session_state.token)

if 'channels' not in st.session_state:
    st.session_state.channels = {}

# Sidebar (Simplified)
with st.sidebar:
    st.header("Server List")
    
    # Drive Link in Sidebar
    try:
        if 'drive_folder_url' not in st.session_state:
            service = build('drive', 'v3', credentials=creds)
            folder_id = get_or_create_folder(service, "Discord Archive")
            st.session_state.drive_folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
        
        st.markdown(f"**[📂 Open Drive Folder]({st.session_state.drive_folder_url})**")
    except Exception:
        pass
        
    st.markdown("---")
    
    if st.button("🔄 Refresh Guilds"):
        if st.session_state.token:
            with st.spinner("Refreshing..."):
                st.session_state.guilds = get_guilds(st.session_state.token)
                
    st.markdown("---")
    
    if not st.session_state.guilds:
        st.info("Loading servers...")
    else:
        guild_options = {g['name']: g['id'] for g in st.session_state.guilds}
        selected_guild_name = st.radio("Servers", list(guild_options.keys()))

# Main Content
if st.session_state.guilds and selected_guild_name:
    # ... [Rest of logic remains same] ...
    gid = guild_options[selected_guild_name]
    
    # Load Channels
    if gid not in st.session_state.channels:
        with st.spinner(f"Loading channels for {selected_guild_name}..."):
            st.session_state.channels[gid] = get_channels(st.session_state.token, gid)
    
    channels = st.session_state.channels[gid]
    
    # Group by Category
    grouped_channels = {}
    for c in channels:
        cat = c['category']
        if cat not in grouped_channels:
            grouped_channels[cat] = []
        grouped_channels[cat].append(c)
    
    # Selection Form
    with st.form("archive_form"):
        st.header(f"#{selected_guild_name}")
        
        # Cache existing checks
        archive_cache_key = f"archives_{gid}"
        if archive_cache_key not in st.session_state:
             # Use the global creds
             try:
                service = build('drive', 'v3', credentials=st.session_state.drive_creds)
                with st.spinner("Checking Google Drive for existing archives..."):
                    st.session_state[archive_cache_key] = get_existing_archives(service, selected_guild_name)
             except Exception as e:
                 st.warning(f"Could not check Drive status: {e}")
                 st.session_state[archive_cache_key] = set()
        
        existing_archives = st.session_state[archive_cache_key]
        
        selected_ids = []
        progress_placeholders = {}
        
        col_header, col_btn = st.columns([4, 1])
        with col_btn:
            submitted = st.form_submit_button("Start Archiving", type="primary")

        # Render Channels
        sorted_categories = sorted(grouped_channels.keys())
        
        for cat in sorted_categories:
            st.markdown(f"<div class='category-header'>⌄ {cat}</div>", unsafe_allow_html=True)
            
            for channel in grouped_channels[cat]:
                c2, c3 = st.columns([3, 4])
                with c2:
                    # Auto selected
                    is_selected = st.checkbox(f"**# {channel['name']}**", value=False, key=channel['id'])
                    if is_selected:
                        selected_ids.append(channel)
                with c3:
                    progress_placeholders[channel['id']] = st.empty()
                    
                    # Check status
                    c_safe = sanitize(channel['name'])
                    if c_safe in existing_archives:
                        progress_placeholders[channel['id']].success("✅ Uploaded")
                    else:
                        progress_placeholders[channel['id']].progress(0, text="0%")
    
    if submitted:
        if not selected_ids:
            st.error("Please select at least one channel.")
        else:
            MAX_WORKERS = 4 
            st.info(f"Starting {len(selected_ids)} downloads with {MAX_WORKERS} parallel workers...")
            
            for ch in selected_ids:
                 progress_placeholders[ch['id']].info("Queued...")

            with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_channel = {
                    executor.submit(
                        archive_channel_task, 
                        ch, 
                        selected_guild_name, 
                        st.session_state.token, 
                        st.session_state.drive_creds, # Pass the ready creds
                        TEMP_DIR
                    ): ch 
                    for ch in selected_ids
                }
                
                for future in as_completed(future_to_channel):
                    ch = future_to_channel[future]
                    cid = ch['id']
                    try:
                        result = future.result()
                        status = result['status']
                        msg = result['msg']
                        
                        if status == "Success":
                            progress_placeholders[cid].success(f"✅ {msg}")
                        elif status == "Exists":
                            progress_placeholders[cid].success(f"⏩ {msg}")
                        elif status == "Empty":
                            progress_placeholders[cid].warning(f"⚠️ {msg}")
                        else:
                            progress_placeholders[cid].error(f"❌ {msg}")
                            
                    except Exception as exc:
                         progress_placeholders[cid].error(f"Worker Error: {exc}")
            
            st.success("All tasks completed!")
            
            if archive_cache_key in st.session_state:
                del st.session_state[archive_cache_key]
