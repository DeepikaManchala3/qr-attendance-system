let sessionId = null;

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

async function startSession() {
  const class_id = Number(document.getElementById("class_id").value);
  const res = await fetchJson("/api/attendance/start", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ class_id })
  });
  if (res.ok && res.data.ok) {
    sessionId = res.data.session_id;
    document.getElementById("sessionInfo").textContent = `Session #${sessionId} — scan Student QR to mark present.`;
    document.getElementById("stopBtn").disabled = false;
    ensureScanner();
    refreshList();
  } else {
    alert(res.data.error || "Unable to start session");
  }
}

async function stopSession() {
  if (!sessionId) return;
  const res = await fetchJson("/api/attendance/stop", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ session_id: sessionId })
  });
  if (res.ok && res.data.ok) {
    document.getElementById("sessionInfo").textContent = `Session #${sessionId} closed.`;
    document.getElementById("stopBtn").disabled = true;
  } else {
    alert(res.data.error || "Unable to stop");
  }
}

async function markPresent(sid) {
  if (!sessionId) { alert("Start a session first"); return; }
  const res = await fetchJson("/api/attendance/mark", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ session_id: sessionId, sid })
  });
  const m = document.getElementById("markStatus");
  if (res.ok && res.data.ok) {
    m.textContent = res.data.msg || "Marked";
    refreshList();
  } else {
    m.textContent = res.data.error || "Failed";
  }
}

function manualMark() {
  const v = document.getElementById("manual").value;
  const sid = parseStudent(v);
  markPresent(sid);
}

function ensureScanner() {
  if (window._scanner) return;
  const scanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: 250 }, false);
  scanner.render((text) => {
    const t = text.trim();
    if (t.startsWith("STUDENT:") || t.startsWith("STU")) {
      markPresent(parseStudent(t));
    }
  }, (err) => {});
  window._scanner = scanner;
}

async function refreshList() {
  if (!sessionId) return;
  const r = await fetchJson(`/api/attendance/session/${sessionId}`);
  if (r.ok && r.data.ok) {
    const list = r.data.session.records.map(x => `${x.sid} @ ${new Date(x.ts).toLocaleTimeString()}`);
    document.getElementById("presentList").textContent = list.length ? list.join(", ") : "—";
  }
}

const sid = document.getElementById("sid").value;
const fingerprint = document.getElementById("fingerprint").value;

fetch("/api/attendance/mark", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ session_id: sessionId, sid: sid, fingerprint: fingerprint })
})
.then(res => res.json())
.then(data => alert(data.msg || data.error));

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
