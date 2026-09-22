#!/usr/bin/env python3
"""Mint the Gmail refresh token Recon uses. Run this once, on your Mac.

Why here and not on the NUC: Google allows a plain-http OAuth redirect only to
localhost, so the consent flow has to finish on the machine with the browser.
Doing it here means the API never hosts a callback and never has to be publicly
reachable — it just exchanges the refresh token for short-lived access tokens.

Setup, once:
  1. console.cloud.google.com -> new project -> APIs & Services
  2. Enable the Gmail API
  3. OAuth consent screen -> External -> add yourself as a test user
  4. Credentials -> Create credentials -> OAuth client ID -> Desktop app
  5. Download the JSON, then:

     pip install google-auth-oauthlib
     python3 scripts/gmail_auth.py ~/Downloads/client_secret_XXX.json

It prints the three values to put in the NUC's ~/recon/.env. The scope is
gmail.readonly: Recon can read mail, and cannot send, label, or delete it.
"""
import json
import sys

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Missing dependency. Run:  pip install google-auth-oauthlib")
        return 1

    path = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    with open(path) as fh:
        installed = json.load(fh)["installed"]

    print("\nAdd these to ~/recon/.env on the NUC, then restart the api+worker:\n")
    print("MAIL_ENABLED=true")
    print(f"GMAIL_CLIENT_ID={installed['client_id']}")
    print(f"GMAIL_CLIENT_SECRET={installed['client_secret']}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("\nThe refresh token is a credential: treat it like a password, and "
          "revoke it any time at myaccount.google.com/permissions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
