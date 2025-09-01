let hMode = "TOGGLE";

function setHostelMode(m) {
  hMode = m;
  document.getElementById("hMode").textContent = `Mode: ${hMode}`;
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

async function logHostel(sid) {
  const gate = document.getElementById("gate").value || "Main Gate";
  const res = await fetchJson("/api/hostel/log", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ sid, action: hMode, gate })
  });
  const el = document.getElementById("hostelMsg");
  if (res.ok && res.data.ok) {
    el.textContent = `${sid} -> ${res.data.action} (${res.data.gate}) at ${new Date(res.data.ts).toLocaleTimeString()}`;
  } else {
    el.textContent = res.data.error || "Failed";
  }
}

function manualHostel() {
  const v = document.getElementById("manual").value;
  logHostel(parseStudent(v));
}

function ensureScanner() {
  if (window._hscanner) return;
  const scanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: 250 }, false);
  scanner.render((text) => {
    const t = text.trim();
    if (t.startsWith("STUDENT:") || t.startsWith("STU")) {
      logHostel(parseStudent(t));
    }
  }, (err) => {});
  window._hscanner = scanner;
}

document.addEventListener("DOMContentLoaded", () => {
  setHostelMode("TOGGLE");
  ensureScanner();
});

fetch("/api/hostel/log", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ sid: sid, fingerprint: fingerprint, action: "TOGGLE", gate: "Main Gate" })
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
