# Standalone utility — reads env vars directly (does not require full app config)
"""Check Google Drive storage quota for the service account."""

import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')

credentials = Credentials.from_service_account_info(
    json.loads(creds_json),
    scopes=['https://www.googleapis.com/auth/drive']
)
service = build('drive', 'v3', credentials=credentials)

about = service.about().get(fields='storageQuota,user').execute()
quota = about.get('storageQuota', {})
user = about.get('user', {})

print(f"Service Account: {user.get('emailAddress', 'Unknown')}")
print(f"Usage: {int(quota.get('usage', 0)) / (1024**3):.2f} GB")
print(f"Limit: {int(quota.get('limit', 0)) / (1024**3):.2f} GB")
print(f"Usage in Drive: {int(quota.get('usageInDrive', 0)) / (1024**3):.2f} GB")
print(f"Usage in Trash: {int(quota.get('usageInDriveTrash', 0)) / (1024**3):.2f} GB")

# Check if limit is 0 (shared drive or no personal quota)
if quota.get('limit') == '0' or not quota.get('limit'):
    print("\nNote: Limit=0 may indicate files are being created in the service account's own Drive,")
    print("not in a Shared Drive. Service accounts have very limited or no personal storage.")
