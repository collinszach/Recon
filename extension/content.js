// Injected on demand (from popup.js, via chrome.scripting.executeScript) after
// field-matcher.js and adapters/*.js. Runs the whole fill pass once and reports a
// summary via a floating toast. Never touches a submit button.
(async function () {
  const ns = window.ReconAutofill;
  if (!ns || !ns.adapters || !ns.adapters.length) {
    console.error("Recon Autofill: matcher/adapters not loaded");
    return;
  }

  function showToast(text, isError) {
    const id = "recon-autofill-toast";
    document.getElementById(id)?.remove();
    const el = document.createElement("div");
    el.id = id;
    el.textContent = text;
    Object.assign(el.style, {
      position: "fixed", bottom: "16px", right: "16px", zIndex: 2147483647,
      background: isError ? "#c0392b" : "#2d2d3a", color: "#fff",
      padding: "10px 14px", borderRadius: "8px", font: "13px/1.4 -apple-system,sans-serif",
      boxShadow: "0 4px 16px rgba(0,0,0,.3)", maxWidth: "320px",
    });
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 8000);
  }

  function extractRoleCtx() {
    const override = window.__reconRoleOverride;
    if (override && (override.company || override.title)) {
      return { company: override.company || "", title: override.title || "",
        url: location.href, description: "" };
    }
    // Try JobPosting JSON-LD, common on Greenhouse/Lever/Ashby postings.
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const data = JSON.parse(script.textContent);
        const jp = Array.isArray(data) ? data.find((d) => d["@type"] === "JobPosting") : data;
        if (jp && jp["@type"] === "JobPosting") {
          return {
            company: jp.hiringOrganization?.name || "",
            title: jp.title || document.title,
            url: location.href,
            description: (jp.description || "").replace(/<[^>]+>/g, " ").slice(0, 2000),
          };
        }
      } catch { /* not JSON-LD we care about */ }
    }
    return { company: "", title: document.title, url: location.href, description: "" };
  }

  function pickAdapter() {
    const specific = ns.adapters.find((a) => a.name !== "generic" && a.detect());
    return specific || ns.adapters.find((a) => a.name === "generic");
  }

  function showReport(step, rows, adapterName) {
    const id = "recon-autofill-report";
    document.getElementById(id)?.remove();
    const panel = document.createElement("div");
    panel.id = id;
    Object.assign(panel.style, {
      position: "fixed", bottom: "16px", right: "16px", zIndex: 2147483647,
      background: "#fffdf8", color: "#22201c", border: "1px solid #e4ddd0",
      borderRadius: "12px", font: "13px/1.45 -apple-system,sans-serif",
      boxShadow: "0 8px 32px rgba(0,0,0,.18)", maxWidth: "360px",
      maxHeight: "70vh", overflow: "auto", padding: "12px 14px",
    });
    const filled = rows.filter((r) => r.status === "filled").length;
    const attention = rows.filter((r) => r.status === "attention").length;
    const head = document.createElement("div");
    head.innerHTML =
      `<div style="font-weight:600;margin-bottom:2px">Recon · ${step}</div>` +
      `<div style="color:#6b6458;margin-bottom:8px">${filled} filled` +
      (attention ? ` · <b style="color:#c0522d">${attention} need you</b>` : "") +
      ` · nothing submitted</div>`;
    panel.appendChild(head);
    for (const r of rows) {
      const line = document.createElement("div");
      const color = r.status === "filled" ? "#3f7d3f" : r.status === "skipped" ? "#6b6458" : "#c0522d";
      const mark = r.status === "filled" ? "✓" : r.status === "skipped" ? "–" : "!";
      line.style.cssText = "display:flex;gap:6px;padding:2px 0";
      line.innerHTML = `<span style="color:${color};font-weight:700">${mark}</span>` +
        `<span style="flex:1"><b>${r.label}</b>` +
        (r.detail ? ` <span style="color:#6b6458">— ${r.detail}</span>` : "") + `</span>`;
      panel.appendChild(line);
    }
    const close = document.createElement("button");
    close.textContent = "Close";
    close.style.cssText = "margin-top:10px;padding:6px 10px;border:1px solid #e4ddd0;" +
      "background:#fff;border-radius:8px;cursor:pointer;font:inherit";
    close.onclick = () => panel.remove();
    panel.appendChild(close);
    document.body.appendChild(panel);
  }

  async function getResume() {
    const resp = await chrome.runtime.sendMessage({ type: "GET_RESUME" });
    if (!resp?.ok) return null;
    const blob = new Blob([new Uint8Array(resp.bytes)], { type: resp.type });
    return new File([blob], resp.name, { type: resp.type });
  }

  const adapter = pickAdapter();

  // Adapters that own their fill pass (Workday) get called directly: its fields
  // are mostly not inputs, so handing elements to the generic filler writes
  // values React immediately discards.
  if (typeof adapter.fill === "function") {
    const profileResp0 = await chrome.runtime.sendMessage({ type: "GET_PROFILE" });
    if (!profileResp0?.ok) {
      showToast(`Recon Autofill: couldn't reach Recon API — ${profileResp0?.error || "unknown error"}`, true);
      return;
    }
    const { step, report } = await adapter.fill({ profile: profileResp0.profile, getResume });
    showReport(step, report, adapter.name);
    return;
  }

  const fields = adapter.extractFields();
  if (!fields.length) {
    showToast("Recon Autofill: no fillable fields found on this page.", true);
    return;
  }

  const structured = fields.filter((f) => f.kind === "structured" && f.profileKey);
  const essay = fields.filter((f) => f.kind === "essay");

  const profileResp = await chrome.runtime.sendMessage({ type: "GET_PROFILE" });
  if (!profileResp?.ok) {
    showToast(`Recon Autofill: couldn't reach Recon API — ${profileResp?.error || "unknown error"}`, true);
    return;
  }
  const profile = profileResp.profile;

  let structuredFilled = 0;
  for (const f of structured) {
    const value = profile[f.profileKey];
    if (value === undefined || value === null || value === "") continue;
    if (ns.fillField(f.el, value)) {
      ns.highlightField(f.el);
      structuredFilled++;
    }
  }

  let essayFilled = 0;
  let essayError = null;
  if (essay.length) {
    const questions = essay.map((f, i) => ({ id: String(i), label: f.label }));
    const roleCtx = extractRoleCtx();
    const answerResp = await chrome.runtime.sendMessage({
      type: "ANSWER_QUESTIONS", questions, role_ctx: roleCtx,
    });
    if (answerResp?.ok && !answerResp.error) {
      const byId = new Map((answerResp.answers || []).map((a) => [a.id, a.answer]));
      essay.forEach((f, i) => {
        const answer = byId.get(String(i));
        if (answer && ns.fillField(f.el, answer)) {
          ns.highlightField(f.el);
          essayFilled++;
        }
      });
    } else {
      essayError = answerResp?.error || "LLM answers unavailable";
    }
  }

  let msg = `Recon Autofill (${adapter.name}): filled ${structuredFilled}/${structured.length} fields`;
  if (essay.length) msg += `, ${essayFilled}/${essay.length} drafted answers`;
  msg += ". Review before submitting — nothing was submitted.";
  if (essayError) msg += ` (essay answers skipped: ${essayError})`;
  showToast(msg, false);
})();
