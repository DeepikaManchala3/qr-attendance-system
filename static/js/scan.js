// Uses html5-qrcode (loaded via CDN in scan.html)

let scannedStudent = null;
let scannedBook = null;

function setStatus(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
}

function parsePayload(text) {
  // expecting "STUDENT:<sid>" or "BOOK:<bid>"
  if (text.startsWith("STUDENT:")) return {type: "student", id: text.split(":")[1]};
  if (text.startsWith("BOOK:"))    return {type: "book", id: text.split(":")[1]};
  // Fallback: try raw IDs (user pasted)
  if (text.startsWith("STU")) return {type: "student", id: text};
  if (text.startsWith("BK"))  return {type: "book", id: text};
  return {type: "unknown", id: text};
}

async function fetchJson(url, opts) {
  const r = await fetch(url, opts);
  return { ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) };
}

async function handleScan(decodedText) {
  const p = parsePayload(decodedText.trim());
  if (p.type === "student") {
    const res = await fetchJson(`/api/student/${encodeURIComponent(p.id)}`);
    if (res.ok && res.data.ok) {
      scannedStudent = res.data.student;
      setStatus("studentStatus", `Student: ${scannedStudent.name} (${scannedStudent.sid})`);
    } else {
      setStatus("studentStatus", `Student not found (${p.id})`);
    }
  } else if (p.type === "book") {
    const res = await fetchJson(`/api/book/${encodeURIComponent(p.id)}`);
    if (res.ok && res.data.ok) {
      scannedBook = res.data.book;
      setStatus("bookStatus", `Book: ${scannedBook.title} (${scannedBook.bid}) — ${scannedBook.available ? "Available" : "Borrowed"}`);
    } else {
      setStatus("bookStatus", `Book not found (${p.id})`);
    }
  } else {
    alert("Unknown QR payload. Expect STUDENT:<sid> or BOOK:<bid>.");
  }
  refreshActions();
}

function refreshActions() {
  const borrowBtn = document.getElementById("borrowBtn");
  const returnBtn = document.getElementById("returnBtn");
  borrowBtn.disabled = !(scannedStudent && scannedBook && scannedBook.available);
  returnBtn.disabled = !(scannedBook && !scannedBook.available);
}

async function borrowNow() {
  const days = Number(document.getElementById("days").value || 14);
  const body = JSON.stringify({ sid: scannedStudent.sid, bid: scannedBook.bid, days });
  const res = await fetchJson("/api/borrow", { method: "POST", headers: { "Content-Type": "application/json" }, body });
  if (res.ok && res.data.ok) {
    alert(`Borrowed. Due: ${new Date(res.data.due_dt).toLocaleString()}`);
    // refresh book state
    const r = await fetchJson(`/api/book/${encodeURIComponent(scannedBook.bid)}`);
    if (r.ok && r.data.ok) scannedBook = r.data.book;
  } else {
    alert(res.data.error || "Borrow failed");
  }
  refreshActions();
}

async function returnNow() {
  const body = JSON.stringify({ bid: scannedBook.bid });
  const res = await fetchJson("/api/return", { method: "POST", headers: { "Content-Type": "application/json" }, body });
  if (res.ok && res.data.ok) {
    alert(`Returned at: ${new Date(res.data.return_dt).toLocaleString()}`);
    // refresh book state
    const r = await fetchJson(`/api/book/${encodeURIComponent(scannedBook.bid)}`);
    if (r.ok && r.data.ok) scannedBook = r.data.book;
  } else {
    alert(res.data.error || "Return failed");
  }
  refreshActions();
}

async function startScanner() {
  const html5QrcodeScanner = new Html5QrcodeScanner(
    "reader",
    { fps: 10, qrbox: 250, rememberLastUsedCamera: true },
    false
  );
  html5QrcodeScanner.render(
    (text) => handleScan(text),
    (err) => {}
  );
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

async function startFaceVerification() {
  const video = document.getElementById("faceCam");
  video.style.display = "block";

  // Request camera
  const stream = await navigator.mediaDevices.getUserMedia({ video: true });
  video.srcObject = stream;

  // Capture after 3 seconds
  setTimeout(async () => {
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);

    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg"));
    const formData = new FormData();
    formData.append("face", blob, "face.jpg");
    formData.append("sid", scannedStudent?.sid || "");

    const res = await fetch("/api/face/verify", { method: "POST", body: formData });
    const data = await res.json();

    if (data.ok) {
      alert("✅ Face verified successfully!");
      markAttendance();
    } else {
      alert("❌ Face verification failed: " + (data.error || ""));
    }

    // stop camera
    stream.getTracks().forEach(track => track.stop());
    video.style.display = "none";
  }, 3000);
}

async function markAttendance() {
  const fingerprint = document.getElementById("fingerprint").value;
  if (!scannedStudent) return alert("Scan student QR first!");
  if (!fingerprint) return alert("Enter fingerprint!");

  const res = await fetch("/api/attendance/mark", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sid: scannedStudent.sid, fingerprint })
  });
  const data = await res.json();
  alert(data.msg || data.error);
}


document.addEventListener("DOMContentLoaded", () => {
  startScanner();
  document.getElementById("borrowBtn").addEventListener("click", borrowNow);
  document.getElementById("returnBtn").addEventListener("click", returnNow);
});


