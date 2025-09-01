let labMode = "TOGGLE";

function setMode(m) {
  labMode = m;
  document.getElementById("mode").textContent = `Mode: ${labMode}`;
}

function parseStudent(text) {
  const t = text.trim();
  if (t.startsWith("STUDENT:")) return t.split(":")[1];
  if (t.startsWith("STU")) return t;
  return t;
}

async function fetchJson(url, opts) {
  const r = await fetch(url, opts);
  try { return { ok: r.ok, status: r.status, data: await r.json() }; }
  catch { return { ok: r.ok, status: r.status, data: {} }; }
}

async function logLab(sid) {
  const lab_id = Number(document.getElementById("lab_id").value);
  const res = await fetchJson("/api/labs/log", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ lab_id, sid, action: labMode })
  });
  const el = document.getElementById("labMsg");
  if (res.ok && res.data.ok) {
    el.textContent = `${sid} -> ${res.data.action} at ${new Date(res.data.ts).toLocaleTimeString()}`;
    refreshInside();
  } else {
    el.textContent = res.data.error || "Failed";
  }
}

function manualLog() {
  const v = document.getElementById("manual").value;
  logLab(parseStudent(v));
}

function ensureScanner() {
  if (window._scanner) return;
  const scanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: 250 }, false);
  scanner.render((text) => {
    const t = text.trim();
    if (t.startsWith("STUDENT:") || t.startsWith("STU")) {
      logLab(parseStudent(t));
    }
  }, (err) => {});
  window._scanner = scanner;
}

async function refreshInside() {
  const lab_id = Number(document.getElementById("lab_id").value);
  const r = await fetchJson(`/api/labs/stats/${lab_id}`);
  if (r.ok && r.data.ok) {
    document.getElementById("inside").textContent = `Inside now: ${r.data.inside}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setMode("TOGGLE");
  ensureScanner();
  refreshInside();
});

fetch("/api/labs/log", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ lab_id: labId, sid: sid, fingerprint: fingerprint, action: "TOGGLE" })
})

async function verifyFace() {
  if (!sessionId) { alert("Start a session first"); return; }

  const sid = document.getElementById("sid") ? document.getElementById("sid").value : null;
  const fingerprint = document.getElementById("fingerprint").value;
  const faceInput = document.getElementById("face");
  if (!sid || !fingerprint || faceInput.files.length === 0) {
    alert("Missing student ID, fingerprint, or face image");
    return;
  }

  const formData = new FormData();
  formData.append("sid", sid);
  formData.append("fingerprint", fingerprint);
  formData.append("face", faceInput.files[0]);

  const res = await fetch("/api/face/verify", {
    method: "POST",
    body: formData
  });
  const data = await res.json();

  const m = document.getElementById("faceStatus");
  if (data.ok) {
    m.textContent = data.msg || "Face verified ✔️, marking attendance...";
    // Call markPresent only if face verified
    markPresent(sid);
  } else {
    m.textContent = data.error || "Face verification failed ❌";
  }
}
