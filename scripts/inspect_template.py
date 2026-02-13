# Standalone utility — reads env vars directly (does not require full app config)
"""Inspect the structure of the Google Slides template."""

import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
template_id = os.environ.get('PROPOSAL_TEMPLATE_SLIDE_ID')

credentials = Credentials.from_service_account_info(
    json.loads(creds_json),
    scopes=['https://www.googleapis.com/auth/presentations.readonly']
)
service = build('slides', 'v1', credentials=credentials)

print(f"Inspecting template: {template_id}\n")

presentation = service.presentations().get(
    presentationId=template_id,
    fields="slides(objectId,pageElements(objectId,shape(placeholder(type,index),shapeType,text)))"
).execute()

slides = presentation.get('slides', [])
print(f"Total slides: {len(slides)}\n")

for i, slide in enumerate(slides, 1):
    print(f"=== Slide {i} (ID: {slide['objectId']}) ===")
    for element in slide.get('pageElements', []):
        shape = element.get('shape', {})
        placeholder = shape.get('placeholder', {})
        shape_type = shape.get('shapeType', 'unknown')
        
        # Get first 50 chars of text content
        text_content = ""
        text_elements = shape.get('text', {}).get('textElements', [])
        for te in text_elements:
            if 'textRun' in te:
                text_content += te['textRun'].get('content', '')
        text_preview = text_content[:50].replace('\n', ' ').strip()
        
        if placeholder:
            print(f"  [{element['objectId']}] Placeholder: {placeholder.get('type')} idx={placeholder.get('index', 0)}")
            if text_preview:
                print(f"      Text: \"{text_preview}...\"")
        elif shape_type == 'TEXT_BOX':
            print(f"  [{element['objectId']}] TextBox: \"{text_preview[:30]}...\"")
    print()
