const statusEl = document.getElementById("status");
const fillBtn = document.getElementById("fill");
const companyEl = document.getElementById("company");
const titleEl = document.getElementById("title");

async function ping() {
  const resp = await chrome.runtime.sendMessage({ type: "PING" });
  if (resp?.ok) {
    statusEl.textContent = `Connected — ${resp.base}`;
    statusEl.className = "ok";
    fillBtn.disabled = false;
  } else {
    statusEl.textContent = `Not connected: ${resp?.error || "unreachable"}. Check Settings.`;
    statusEl.className = "err";
    fillBtn.disabled = true;
  }
}

document.getElementById("opts").addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

fillBtn.addEventListener("click", async () => {
  fillBtn.disabled = true;
  fillBtn.textContent = "Filling…";
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const override = { company: companyEl.value.trim(), title: titleEl.value.trim() };

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (o) => { window.__reconRoleOverride = o; },
    args: [override],
  });
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: [
      "field-matcher.js",
      "adapters/greenhouse.js",
      "adapters/lever.js",
      "adapters/workday.js",
      "adapters/ashby-icims.js",
      "adapters/generic.js",
      "content.js",
    ],
  });
  window.close();
});

ping();
