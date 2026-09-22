// All network calls to the Recon API happen here (MV3 service worker), not in
// content scripts — keeps them clear of any page CSP and centralizes the API base URL.

const DEFAULT_API_BASE = "http://100.91.198.28:8010";

async function getApiBase() {
  const { apiBase } = await chrome.storage.local.get("apiBase");
  return apiBase || DEFAULT_API_BASE;
}

async function callApi(path, options = {}) {
  const base = await getApiBase();
  const res = await fetch(base + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case "PING": {
          const base = await getApiBase();
          const res = await fetch(base + "/health");
          sendResponse({ ok: res.ok, base });
          break;
        }
        case "GET_PROFILE": {
          const profile = await callApi("/api/autofill/profile");
          sendResponse({ ok: true, profile });
          break;
        }
        case "UPDATE_PROFILE": {
          await callApi("/api/autofill/profile", {
            method: "PUT",
            body: JSON.stringify(msg.fields),
          });
          sendResponse({ ok: true });
          break;
        }
        case "GET_RESUME": {
          // Fetched here, not in the content script: the page's CSP would block
          // it, and the API host permission lives with the service worker.
          const base = await getApiBase();
          const res = await fetch(base + "/api/resume/file");
          if (!res.ok) { sendResponse({ ok: false, error: `${res.status} — no résumé stored?` }); break; }
          const buf = await res.arrayBuffer();
          const name = (res.headers.get("Content-Disposition") || "")
            .match(/filename="?([^"]+)"?/)?.[1] || "resume.pdf";
          // Structured clone can't carry a File across the message boundary, so
          // send bytes and rebuild it on the other side.
          sendResponse({ ok: true, name, type: res.headers.get("Content-Type") || "application/pdf",
                         bytes: Array.from(new Uint8Array(buf)) });
          break;
        }
        case "ANSWER_QUESTIONS": {
          const data = await callApi("/api/autofill/answer", {
            method: "POST",
            body: JSON.stringify({ questions: msg.questions, role_ctx: msg.role_ctx || {} }),
          });
          sendResponse({ ok: true, ...data });
          break;
        }
        default:
          sendResponse({ ok: false, error: `unknown message type: ${msg.type}` });
      }
    } catch (err) {
      sendResponse({ ok: false, error: String(err && err.message || err) });
    }
  })();
  return true; // keep the message channel open for the async response
});
