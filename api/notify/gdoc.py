"""Publish the daily brief to a Google Doc via a service account.

This is the heaviest, most optional channel. All imports happen lazily
inside publish_gdoc() so that a missing google-api-python-client /
google-auth install (or missing credentials) never crashes the scan —
it just logs a warning and no-ops.
"""
import logging
from config import settings

log = logging.getLogger("recon.notify.gdoc")


def publish_gdoc(title: str, markdown_body: str) -> None:
    """Create or update a Google Doc titled `title` containing
    `markdown_body`, in `settings.gdoc_folder_id`.

    No-ops (with a warning) if gdoc delivery is disabled, credentials
    are missing, or the required libraries are not installed.
    """
    if not settings.notify_gdoc_enabled:
        log.warning("gdoc: notify_gdoc_enabled is False — skipping")
        return
    if not settings.gdoc_credentials_json:
        log.warning("gdoc: gdoc_credentials_json not configured — skipping")
        return

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        log.warning("gdoc: google-api-python-client / google-auth not installed — skipping")
        return

    try:
        scopes = [
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = service_account.Credentials.from_service_account_file(
            settings.gdoc_credentials_json, scopes=scopes
        )
        docs = build("docs", "v1", credentials=creds)
        drive = build("drive", "v3", credentials=creds)

        # find an existing doc with this title (in the target folder, if set)
        existing_id = None
        q = f"name = '{title}' and mimeType = 'application/vnd.google-apps.document' and trashed = false"
        if settings.gdoc_folder_id:
            q += f" and '{settings.gdoc_folder_id}' in parents"
        results = drive.files().list(q=q, fields="files(id, name)").execute()
        files = results.get("files", [])
        if files:
            existing_id = files[0]["id"]

        if existing_id:
            doc_id = existing_id
            # clear existing body content before re-inserting
            doc = docs.documents().get(documentId=doc_id).execute()
            end_index = doc["body"]["content"][-1]["endIndex"]
            if end_index > 1:
                docs.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": [{
                        "deleteContentRange": {
                            "range": {"startIndex": 1, "endIndex": end_index - 1}
                        }
                    }]},
                ).execute()
        else:
            create_body = {"title": title}
            doc = docs.documents().create(body=create_body).execute()
            doc_id = doc["documentId"]
            if settings.gdoc_folder_id:
                drive.files().update(
                    fileId=doc_id,
                    addParents=settings.gdoc_folder_id,
                    fields="id, parents",
                ).execute()

        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{
                "insertText": {
                    "location": {"index": 1},
                    "text": markdown_body,
                }
            }]},
        ).execute()

        log.info("gdoc: published brief to doc %s", doc_id)
    except Exception as e:
        log.warning("gdoc: failed to publish: %s: %s", type(e).__name__, e)
