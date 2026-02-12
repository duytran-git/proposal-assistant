"""Health check module for Proposal Assistant."""

import json
import os
import time
from pathlib import Path

import httpx


def check_claude_api() -> dict:
    """Check if Claude API is reachable."""
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        resp = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=10,
        )
        if resp.status_code == 200:
            return {"status": "healthy", "provider": "anthropic"}
        return {"status": "degraded", "status_code": resp.status_code}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def check_google_drive() -> dict:
    """Check if Google Drive API is accessible and root folder is reachable."""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        from proposal_assistant.config import get_config

        config = get_config()
        root_id = config.google_drive_root_folder_id

        credentials = Credentials.from_service_account_info(
            json.loads(config.google_service_account_json),
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        service = build("drive", "v3", credentials=credentials)
        result = (
            service.files()
            .get(fileId=root_id, fields="id,name", supportsAllDrives=True)
            .execute()
        )
        return {
            "status": "healthy",
            "root_folder": root_id,
            "root_folder_name": result.get("name"),
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def check_state_storage() -> dict:
    """Check if state storage directory is writable."""
    try:
        data_dir = Path("data/threads")
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / "_health_check.json"
        test_file.write_text(json.dumps({"ts": time.time()}))
        test_file.unlink()
        return {"status": "healthy", "path": str(data_dir)}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def check() -> dict:
    """Run all health checks. Used by Docker HEALTHCHECK."""
    results = {
        "claude_api": check_claude_api(),
        "google_drive": check_google_drive(),
        "state_storage": check_state_storage(),
        "timestamp": time.time(),
    }
    all_healthy = all(
        r["status"] == "healthy" for r in results.values() if isinstance(r, dict) and "status" in r
    )
    if not all_healthy:
        raise SystemExit(1)
    return results
