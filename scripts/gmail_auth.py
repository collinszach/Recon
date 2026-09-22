#!/usr/bin/env python3
"""Mint the Gmail refresh token Recon uses. Run this once, on your Mac.

Why here and not on the NUC: Google allows a plain-http OAuth redirect only to
localhost, so the consent flow has to finish on the machine with the browser.
Doing it here means the API never hosts a callback and never has to be publicly
reachable — it just exchanges the refresh token for short-lived access tokens.

Usage (either form):

     pip install google-auth-oauthlib
     python3 scripts/gmail_auth.py <CLIENT_ID> <CLIENT_SECRET>
     python3 scripts/gmail_auth.py ~/Downloads/client_secret_XXX.json

Getting a client, once: console.cloud.google.com -> new project -> enable the
Gmail API -> OAuth consent screen (External, add yourself as a test user) ->
Credentials -> Create credentials -> OAuth client ID -> **Desktop app**.

Run this in your own terminal rather than through an assistant session: it
prints a refresh token, which is a credential and does not belong in a
transcript.

It prints the three values to put in the NUC's ~/recon/.env. The scope is
gmail.readonly: Recon can read mail, and cannot send, label, or delete it.
"""
import json
import sys

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Missing dependency. Run:  pip install google-auth-oauthlib")
        return 1

    # Either the downloaded client JSON, or the id/secret straight from the
    # Cloud console — no reason to require the file if you already have both.
    if len(args) == 2 and not args[0].endswith(".json"):
        client_id, client_secret = args
        config = {"installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }}
        flow = InstalledAppFlow.from_client_config(config, SCOPES)
    else:
        path = args[0]
        flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
        with open(path) as fh:
            config = json.load(fh)

    creds = flow.run_local_server(port=0, prompt="consent")
    installed = config["installed"]

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
