// Uses html5-qrcode (loaded via CDN in scan.html)

const html5QrcodeScanner = new Html5QrcodeScanner(
  "reader",
  { fps: 10, qrbox: { width: 200, height: 200 } }, // smaller box
  false
);


let scannedStudent = null;
let scannedBook = null;

function setStatus(id, msg) {
  const el = document.getElementById(id);
  if (el) el.textContent = msg;
}

function parsePayload(text) {
  if (text.startsWith("STUDENT:")) return { type: "student", id: text.split(":")[1] };
  if (text.startsWith("BOOK:")) return { type: "book", id: text.split(":")[1] };
  if (text.startsWith("STU")) return { type: "student", id: text };
  if (text.startsWith("BK")) return { type: "book", id: text };
  return { type: "unknown", id: text };
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
      setStatus(
        "bookStatus",
        `Book: ${scannedBook.title} (${scannedBook.bid}) — ${scannedBook.available ? "Available" : "Borrowed"}`
      );
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
  if (borrowBtn) borrowBtn.disabled = !(scannedStudent && scannedBook && scannedBook.available);
  if (returnBtn) returnBtn.disabled = !(scannedBook && !scannedBook.available);
}

async function borrowNow() {
  if (!scannedStudent || !scannedBook) return alert("Scan student and book first!");
  const days = Number(document.getElementById("days").value || 14);
  const body = JSON.stringify({ sid: scannedStudent.sid, bid: scannedBook.bid, days });
  const res = await fetchJson("/api/borrow", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body
  });
  if (res.ok && res.data.ok) {
    alert(`Borrowed. Due: ${new Date(res.data.due_dt).toLocaleString()}`);
    const r = await fetchJson(`/api/book/${encodeURIComponent(scannedBook.bid)}`);
    if (r.ok && r.data.ok) scannedBook = r.data.book;
  } else {
    alert(res.data.error || "Borrow failed");
  }
  refreshActions();
}

async function returnNow() {
  if (!scannedBook) return alert("Scan a book first!");
  const body = JSON.stringify({ bid: scannedBook.bid });
  const res = await fetchJson("/api/return", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body
  });
  if (res.ok && res.data.ok) {
    alert(`Returned at: ${new Date(res.data.return_dt).toLocaleString()}`);
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
    () => {}
  );
}

document.addEventListener("DOMContentLoaded", () => {
  startScanner();
  const borrowBtn = document.getElementById("borrowBtn");
  const returnBtn = document.getElementById("returnBtn");
  if (borrowBtn) borrowBtn.addEventListener("click", borrowNow);
  if (returnBtn) returnBtn.addEventListener("click", returnNow);
});
