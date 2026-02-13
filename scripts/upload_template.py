# Standalone utility — reads env vars directly (does not require full app config)
"""Upload and convert the PPTX template to Google Slides in the Shared Drive."""

import os
import json
from pathlib import Path
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

load_dotenv()
creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
root_folder_id = os.environ.get('GOOGLE_DRIVE_ROOT_FOLDER_ID')

credentials = Credentials.from_service_account_info(
    json.loads(creds_json),
    scopes=['https://www.googleapis.com/auth/drive']
)
service = build('drive', 'v3', credentials=credentials)

# Path to the template
template_path = Path("template/Renessai basic template 10_2025.pptx")

print(f"Uploading template: {template_path}")
print(f"To Shared Drive folder: {root_folder_id}")

# Upload and convert to Google Slides
file_metadata = {
    'name': 'Renessai Proposal Template',
    'parents': [root_folder_id],
    'mimeType': 'application/vnd.google-apps.presentation',  # Convert to Google Slides
}

media = MediaFileUpload(
    str(template_path),
    mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
    resumable=True
)

file = service.files().create(
    body=file_metadata,
    media_body=media,
    fields='id,webViewLink',
    supportsAllDrives=True,
).execute()

print(f"\n✅ Template uploaded and converted!")
print(f"   ID: {file['id']}")
print(f"   Link: {file['webViewLink']}")
print(f"\n📝 Update your .env file:")
print(f'   PROPOSAL_TEMPLATE_SLIDE_ID="{file["id"]}"')
