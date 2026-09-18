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

  const adapter = pickAdapter();
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
