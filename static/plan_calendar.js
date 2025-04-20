/* ------------------------------------------------------------
   plan_calendar.js
   — render the study‑plan JSON into a calendar grid, show
     details on click, and expose a “Regenerate Plan” button
     that dispatches  plan:regenerate.
------------------------------------------------------------ */

(() => {
    const root = document.getElementById("calendar-root");
    if (!root) return console.error("plan_calendar.js ➜ #calendar-root not found");
  
    /* ───────────────────────── helpers ───────────────────────── */
  
    const dayNames   = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const monthNames = [
      "January","February","March","April","May","June",
      "July","August","September","October","November","December"
    ];
  
    const safeParse = (txt) => { try { return JSON.parse(txt); } catch { return null; } };
  
    /* convert “5:30pm-7:30pm” → {start:"17:30", end:"19:30"} */
    function splitTimeRange(range) {
      if (!range) return null;
      const [rawStart, rawEnd] = range.split("-").map(s => s.trim());
      if (!rawStart || !rawEnd) return null;
  
      const to24h = (str) => {
        const m = str.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/i);
        if (!m) return null;
        let [, h, mm = "00", ap = ""] = m;
        h  = parseInt(h, 10);
        ap = ap.toLowerCase();
        if (ap === "pm" && h !== 12) h += 12;
        if (ap === "am" && h === 12) h  = 0;
        return `${String(h).padStart(2,"0")}:${mm}`;
      };
  
      const start = to24h(rawStart);
      const end   = to24h(rawEnd);
      return start && end ? { start, end } : null;
    }
  
    /**
     * Try‑hard extractor: returns an **array** of session objects
     * from many possible shapes the backend / LLM might return.
     */
    function extractSessions(plan) {
      if (!plan || typeof plan !== "object") return null;
  
      for (const k of ["sessions","study_plan","days","items"])
        if (Array.isArray(plan[k])) return plan[k];
  
      /* markdown‑wrapped string under plan.raw */
      if (typeof plan.raw === "string") {
        let txt = plan.raw.trim();
        if (txt.startsWith("```")) {
          txt = txt.replace(/^```json\s*/i, "").replace(/```$/i, "").trim();
        }
        const inner = safeParse(txt);
        if (inner) return extractSessions(inner);         // recurse once
      }
      return null;
    }
  
    /* ───────────────────── calendar renderer ─────────────────── */
  
    function renderCalendar(plan) {
      const sessionsIn = extractSessions(plan);
  
      if (!sessionsIn) {
        root.innerHTML = `
          <div style="border:1px solid #e74c3c;padding:16px;border-radius:8px;background:#fdecea;color:#c0392b;">
            <p><strong>Oops!</strong> I couldn’t understand the study‑plan format returned by the server.</p>
            <button class="btn-secondary" id="regen-btn">Regenerate Plan</button>
          </div>`;
        root.querySelector("#regen-btn").onclick =
          () => document.dispatchEvent(new Event("plan:regenerate"));
        return;
      }
  
      /* cache for page refreshes */
      try { localStorage.setItem("latestStudyPlan", JSON.stringify(plan)); } catch { /* ignore quota */ }
  
      /* normalise every item to a common shape */
      const sessions = sessionsIn.map(item => {
        const t = splitTimeRange(item.time || item.timeslot || item.period || "");
        return {
          date:   item.date,
          start:  t?.start || item.start || "?",
          end:    t?.end   || item.end   || "?",
          subject: item.subject || item.content || "",
          label:  item.label || "",
          instructions: item.instructions || item.focus || item.note || "",
          type:   item.type || (item.label ? "test" : "study")
        };
      });
  
      /* group by ISO date */
      const byDate = {};
      sessions.forEach(s => {
        if (s.date) (byDate[s.date] = byDate[s.date] || []).push(s);
      });
  
      /* decide which month to show:
         – earliest session’s month, else current month            */
      let baseDate = new Date();
      const allDates = Object.keys(byDate);
      if (allDates.length) {
        allDates.sort();                              // lexicographic → chronological for ISO
        baseDate = new Date(allDates[0] + "T00:00:00");
      }
  
      const month     = baseDate.getMonth();
      const year      = baseDate.getFullYear();
      const firstDay  = new Date(year, month, 1).getDay();
      const daysInMon = new Date(year, month + 1, 0).getDate();
  
      /* header & grid scaffold */
      root.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h2>${monthNames[month]} ${year}</h2>
          <button class="btn-secondary" id="regen-btn">Regenerate Plan</button>
        </div>
        <div class="calendar-grid" style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px;"></div>
        <div id="detail-box" style="margin-top:20px;"></div>
      `;
  
      const grid = root.querySelector(".calendar-grid");
      dayNames.forEach(d => {
        const hd = document.createElement("div");
        hd.textContent = d;
        hd.style = "font-weight:bold;text-align:center;";
        grid.appendChild(hd);
      });
  
      for (let i = 0; i < firstDay; i++) grid.appendChild(emptyCell());
  
      for (let d = 1; d <= daysInMon; d++) {
        const iso  = new Date(year, month, d).toISOString().split("T")[0];
        const cell = document.createElement("div");
        cell.className = "day-cell";
        cell.style = "border:1px solid #e0e0e0;min-height:90px;padding:4px;border-radius:6px;cursor:pointer;";
  
        const header = document.createElement("div");
        header.textContent = d;
        header.style = "font-weight:bold;margin-bottom:4px;";
        cell.appendChild(header);
  
        (byDate[iso] || []).forEach(s => {
          const block = document.createElement("div");
          const kind  = s.type === "test" ? "test" : "session";
          block.className = `${kind}-block`;
          block.textContent =
            kind === "test"
              ? (s.label || "Test")
              : `${s.subject || "Study"} • ${s.start}-${s.end}`;
          block.style = `
            font-size:11px;padding:2px 4px;margin-bottom:2px;border-radius:3px;color:#fff;
            background:${kind === "test" ? "#2ecc71" : "#3498db"};
          `;
          cell.appendChild(block);
        });
  
        cell.addEventListener("click", () => showDetails(iso, byDate[iso] || []));
        grid.appendChild(cell);
      }
  
      root.querySelector("#regen-btn").onclick =
        () => document.dispatchEvent(new Event("plan:regenerate"));
    }
  
    const emptyCell = () => {
      const d = document.createElement("div");
      d.style = "min-height:90px;";
      return d;
    };
  
    /* ──────────────────── accordion details ─────────────────── */
  
    function showDetails(dateISO, sessions) {
      const box = document.getElementById("detail-box");
      if (!sessions.length) {
        box.innerHTML = `<p>No sessions on ${dateISO}</p>`;
        return;
      }
      box.innerHTML = `
        <h3>📅 ${dateISO}</h3>
        <ul style="list-style:disc inside;margin-left:16px;">
          ${sessions.map(s => `
            <li style="margin:6px 0;">
              <strong>${s.start}-${s.end}</strong> — ${s.subject || s.label || "Study"}<br>
              <em>${s.instructions || "No details provided."}</em>
            </li>`).join("")}
        </ul>`;
      box.scrollIntoView({ behavior:"smooth" });
    }
  
    /* ─────────────────────── bootstrap ─────────────────────── */
  
    const cached = localStorage.getItem("latestStudyPlan");
    if (cached) {
      try { renderCalendar(JSON.parse(cached)); }
      catch (e) { console.warn("cached plan unreadable", e); }
    }
  
    document.addEventListener("plan:ready", e => renderCalendar(e.detail));
  })();
  