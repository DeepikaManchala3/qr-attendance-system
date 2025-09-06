let sessionId = null;
let currentSid = null; // student being processed
let faceStream = null;

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

function ensureScanner() {
  if (window._scanner) return;
  const scanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: 250 }, false);
  scanner.render((text) => {
    const sid = parseStudent(text);
    if (!sid) return;
    currentSid = sid;
    document.getElementById("qrStatus").textContent = "QR ✅";
    openFaceModal();
  }, (err) => {});
  window._scanner = scanner;
}

function openFaceModal() {
  document.getElementById("faceModal").classList.remove("hidden");
  navigator.mediaDevices.getUserMedia({ video: true }).then(stream => {
    faceStream = stream;
    document.getElementById("faceCamera").srcObject = stream;
  });
}

function closeFaceModal() {
  if (faceStream) {
    faceStream.getTracks().forEach(t => t.stop());
    faceStream = null;
  }
  document.getElementById("faceCamera").srcObject = null;
  document.getElementById("faceModal").classList.add("hidden");
}

async function startFaceVerify() {
  const video = document.getElementById("faceCamera");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0);
  const imgData = canvas.toDataURL("image/png");

  const res = await fetchJson("/api/face/verify", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ sid: currentSid, image: imgData })
  });

  const msg = document.getElementById("faceVerifyMsg");
  if (res.ok && res.data.ok) {
    document.getElementById("faceStatus").textContent = "Face ✅";
    msg.textContent = "Face verified!";
    closeFaceModal();
    markPresent(currentSid); // mark attendance after both checks
  } else {
    msg.textContent = res.data.error || "Face verification failed";
  }
}

async function stopFaceWithPassword() {
  const pwd = prompt("Enter operator password to stop face verification:");
  if (!pwd) return;

  const res = await fetchJson("/api/face/stop", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ sid: currentSid, password: pwd })
  });

  if (res.ok && res.data.ok) {
    document.getElementById("faceStatus").textContent = "Face ⏭ (skipped)";
    closeFaceModal();
    markPresent(currentSid); // mark attendance after QR only
  } else {
    alert(res.data.error || "Wrong password");
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

async function refreshList() {
  if (!sessionId) return;
  const r = await fetchJson(`/api/attendance/session/${sessionId}`);
  if (r.ok && r.data.ok) {
    const list = r.data.session.records.map(x => `${x.sid} @ ${new Date(x.ts).toLocaleTimeString()}`);
    document.getElementById("presentList").textContent = list.length ? list.join(", ") : "—";
  }
}
