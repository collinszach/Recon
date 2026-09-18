const TEXT_FIELDS = [
  "phone", "email", "address_line1", "city", "state", "zip_code", "country",
  "linkedin_url", "portfolio_url", "github_url",
  "desired_salary", "earliest_start_date", "notice_period", "how_heard",
  "pronouns", "veteran_status", "disability_status", "gender", "race_ethnicity",
];
const BOOL_FIELDS = ["work_authorized", "requires_sponsorship", "willing_to_relocate"];

async function load() {
  const { apiBase } = await chrome.storage.local.get("apiBase");
  document.getElementById("apiBase").value = apiBase || "";

  const resp = await chrome.runtime.sendMessage({ type: "GET_PROFILE" });
  if (!resp?.ok) return;
  const profile = resp.profile || {};
  for (const f of TEXT_FIELDS) {
    const el = document.getElementById(f);
    if (el && profile[f] != null) el.value = profile[f];
  }
  for (const f of BOOL_FIELDS) {
    const el = document.getElementById(f);
    if (el) el.checked = !!profile[f];
  }
}

document.getElementById("save").addEventListener("click", async () => {
  const status = document.getElementById("saveStatus");
  status.textContent = "Saving…";

  await chrome.storage.local.set({ apiBase: document.getElementById("apiBase").value.trim() });

  const fields = {};
  for (const f of TEXT_FIELDS) {
    const v = document.getElementById(f).value.trim();
    if (v) fields[f] = v;
  }
  for (const f of BOOL_FIELDS) {
    fields[f] = document.getElementById(f).checked;
  }

  const resp = await chrome.runtime.sendMessage({ type: "UPDATE_PROFILE", fields });
  status.textContent = resp?.ok ? "Saved." : `Error: ${resp?.error || "unknown"}`;
  setTimeout(() => { status.textContent = ""; }, 3000);
});

load();
