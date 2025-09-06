let labMode = "TOGGLE";
let lastScanTimes = {}; // store last scan per student for cooldown
let currentSid = null;
let faceVerified = false;

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

async function logLabFinal(sid) {
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
    logLabFinal(currentSid); // mark attendance after both checks
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
    logLabFinal(currentSid); // mark attendance after QR only
  } else {
    alert(res.data.error || "Wrong password");
  }
}



function manualLog() {
  const v = document.getElementById("manual").value;
  const sid = parseStudent(v);
  logLabFinal(sid);
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
