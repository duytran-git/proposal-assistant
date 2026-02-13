# Standalone utility — reads env vars directly (does not require full app config)
"""Check folder permissions and type."""

import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
folder_id = os.environ.get('GOOGLE_DRIVE_ROOT_FOLDER_ID')

credentials = Credentials.from_service_account_info(
    json.loads(creds_json),
    scopes=['https://www.googleapis.com/auth/drive']
)
service = build('drive', 'v3', credentials=credentials)

print(f"Checking folder: {folder_id}\n")

try:
    # Get folder info
    folder = service.files().get(
        fileId=folder_id,
        fields='id,name,owners,driveId,capabilities',
        supportsAllDrives=True
    ).execute()
    
    print(f"Folder name: {folder.get('name')}")
    print(f"Drive ID: {folder.get('driveId', 'None (Personal Drive)')}")
    
    owners = folder.get('owners', [])
    if owners:
        print(f"Owner: {owners[0].get('emailAddress')}")
    else:
        print("Owner: None (Shared Drive)")
    
    caps = folder.get('capabilities', {})
    print(f"Can add children: {caps.get('canAddChildren', 'Unknown')}")
    print(f"Can create files: {caps.get('canEdit', 'Unknown')}")
    
    if folder.get('driveId'):
        print("\n✅ This is a Shared Drive folder - should work!")
    else:
        print("\n⚠️ This is a Personal Drive folder")
        print("Files created here will count against the owner's quota,")
        print("but the owner needs to transfer ownership to use their quota.")
        
except Exception as e:
    print(f"Error: {e}")
