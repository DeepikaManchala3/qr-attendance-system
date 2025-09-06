let hMode = "TOGGLE";
let lastScanTime = {};   // cooldown tracking
let currentSid = null;   // student in progress
let qrVerified = false;  // QR step status
let faceVerified = false; // Face step status

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

// ✅ Final log after QR + Face or Stop override
async function logHostelFinal(sid) {
  const gate = document.getElementById("gate").value || "Main Gate";
  const res = await fetchJson("/api/hostel/log", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ sid, action: hMode, gate })
  });
  const el = document.getElementById("hostelMsg");
  if (res.ok && res.data.ok) {
    el.textContent = `✅ ${sid} -> ${res.data.action} (${res.data.gate}) at ${new Date(res.data.ts).toLocaleTimeString()}`;
  } else {
    el.textContent = res.data.error || "Failed";
  }
}

// 🔹 Step 1: QR Verified
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
    logHostelFinal(currentSid); // mark attendance after both checks
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
    logHostelFinal(currentSid); // mark attendance after QR only
  } else {
    alert(res.data.error || "Wrong password");
  }
}



function manualHostel() {
  const v = document.getElementById("manual").value;
  logHostelFinal(parseStudent(v));
}



document.addEventListener("DOMContentLoaded", () => {
  setHostelMode("TOGGLE");
  ensureScanner();
});
