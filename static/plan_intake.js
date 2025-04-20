/* 
  wizard that gathers:
      • study goals / subjects
      • deadlines (label + date list)
      • weekly availability  → busy & free blocks
    Merges learner profile (window.LEARNER_PROFILE) and POSTs to
    /generate_study_plan.  Emits  plan:ready  with the LLM‑crafted
    plan JSON so plan_calendar.js can render it.

    The wizard also listens for  plan:regenerate  (e.g. user clicks
    “Regenerate” on the calendar) and resends the last payload.      */

(() => {
    /* ‑‑‑ quick DOM helpers ‑‑‑ */
    const $  = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
    const root = document.getElementById("intake-root");
    if (!root) return console.error("plan_intake.js ➜ #intake-root not found");
  
    /* ‑‑‑ learner profile (diagnostic summary / learning style) ‑‑‑ */
    window.LEARNER_PROFILE = {};            // make globally visible
    let diagnosticSummary = "";             // cached string for wizard display
  
    /* ‑‑‑ wizard state ‑‑‑ */
    const state = {
      goals: "",
      deadlines: [],                        // {label,date}
      busy : {0: [],1: [],2: [],3: [],4: [],5: [],6: []},
      free : {0: [],1: [],2: [],3: [],4: [],5: [],6: []}
    };
    let currentStep = 0;
    let lastPayload = null;                 // for regenerate shortcut
  
    /* ‑‑‑ UI templates for each step ‑‑‑ */
    const stepTemplates = [
      /* STEP 1: goals */
      () => `
        <h2>1 · Study goals / subjects</h2>
        ${diagnosticSummary
          ? `<div class="diag-summary" style="background:#f0f4ff;border-left:4px solid #4677ff;padding:8px 12px;margin-bottom:12px;">
               <strong>Diagnostic summary:</strong><br>${diagnosticSummary}
             </div>`
          : ""
        }
        <textarea id="goals-input" rows="5"
          placeholder="e.g. Algebra II chapters 5‑7, score ≥ 85 % on 15 May test"
          style="width:100%;"></textarea>
      `,
  
      /* STEP 2: deadlines */
      () => `
        <h2>2 · Deadlines & tests</h2>
        <p>Add important dates (exam, quiz, assignment, etc.).</p>
        <div id="deadline-list"></div>
        <button class="btn-secondary" id="add-deadline">+ Add deadline</button>
      `,
  
      /* STEP 3: availability */
      () => {
        const dayNames = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
        return `
          <h2>3 · Weekly availability</h2>
          <p>Enter time ranges in 24‑hour format “HH:MM‑HH:MM”. Use commas for multiple blocks.</p>
          <table style="width:100%;border-collapse:collapse;">
            <thead>
              <tr><th></th><th>Busy</th><th>Usually Free (optional)</th></tr>
            </thead>
            <tbody>
              ${dayNames.map((d,i)=>`
                <tr>
                  <td style="padding-right:4px;">${d}</td>
                  <td><input data-day="${i}" data-type="busy" style="width:100%;" placeholder="e.g. 09:00‑17:00"></td>
                  <td><input data-day="${i}" data-type="free" style="width:100%;" placeholder="e.g. 18:00‑20:00"></td>
                </tr>`).join("")}
            </tbody>
          </table>
        `;
      },
  
      /* REVIEW + submit */
      () => `
        <h2>4 · Review & generate</h2>
        <p>Click <strong>Generate Plan</strong> to create your personalised calendar.</p>
        <ul>
          <li><strong>Goals:</strong> ${state.goals || "<em>none</em>"}</li>
          <li><strong>Deadlines:</strong> ${
            state.deadlines.length
              ? state.deadlines.map(d=>`${d.label} (${d.date})`).join(", ")
              : "<em>none</em>"
          }</li>
        </ul>
        <button class="btn-primary" id="generate-plan">Generate Plan</button>
      `
    ];
  
    /* ‑‑‑ render helper ‑‑‑ */
    function renderStep() {
      root.innerHTML = `
        <div class="wizard-box">
          ${stepTemplates[currentStep]()}
          <div style="margin-top:20px;display:flex;justify-content:${currentStep ? "space-between" : "flex-end"}">
            ${currentStep ? '<button class="btn-secondary" id="prev">Back</button>' : ""}
            ${currentStep < stepTemplates.length-1 ? '<button class="btn-primary" id="next">Next</button>' : ""}
          </div>
        </div>
      `;
      attachHandlers();
    }
  
    /* ‑‑‑ attach event handlers for current step ‑‑‑ */
    function attachHandlers() {
      $("#next")?.addEventListener("click", () => { if (saveStep()) { currentStep++; renderStep(); }});
      $("#prev")?.addEventListener("click", () => { currentStep--; renderStep(); });
  
      /* step‑specific hooks */
      if (currentStep === 0) {
        $("#goals-input").value = state.goals;
      }
      if (currentStep === 1) {
        const list = $("#deadline-list");
        state.deadlines.forEach(addRow);
        $("#add-deadline").addEventListener("click", () => addRow());
        function addRow(d = { label:"", date:"" }) {
          const row = document.createElement("div");
          row.style = "display:flex;gap:6px;margin:6px 0";
          row.innerHTML = `
            <input placeholder="Label" style="flex:2" value="${d.label}">
            <input type="date"        style="flex:1" value="${d.date}">
            <button class="btn-secondary" title="remove">✕</button>`;
          row.querySelector("button").onclick = () => row.remove();
          list.appendChild(row);
        }
      }
      if (currentStep === 2) {
        $$("input[data-day]").forEach(inp => {
          const day = inp.dataset.day, typ = inp.dataset.type;
          inp.value = (state[typ][day] || []).join(", ");
        });
      }
      /* final step */
      $("#generate-plan")?.addEventListener("click", submitWizard);
    }
  
    /* ‑‑‑ save inputs of current step into state ‑‑‑ */
    function saveStep() {
      if (currentStep === 0) {
        state.goals = $("#goals-input").value.trim();
        return true;
      }
      if (currentStep === 1) {
        const rows = [...$("#deadline-list").children];
        state.deadlines = rows.map(r => {
          const [label, date] = r.querySelectorAll("input");
          return { label: label.value.trim(), date: date.value };
        }).filter(d => d.label && d.date);
        return true;
      }
      if (currentStep === 2) {
        $$("input[data-day]").forEach(inp => {
          const { day, type } = inp.dataset;
          const ranges = inp.value.split(",").map(s => s.trim()).filter(Boolean);
          state[type][day] = ranges;
        });
        return true;
      }
      return true;
    }
  
    /* ‑‑‑ build payload & POST to backend ‑‑‑ */
    function submitWizard() {
      if (!saveStep()) return;
  
      const payload = {
        diagnostic_summary : window.LEARNER_PROFILE?.diagnostic_summary || "",
        learning_style     : window.LEARNER_PROFILE?.learning_style     || "",
        study_goals        : state.goals,
        deadlines_json     : state.deadlines,
        busy_json          : state.busy,
        free_json          : state.free
      };
      lastPayload = payload;                 // cache for regenerate
  
      root.innerHTML = "<p>⏳ Generating your plan…</p>";
  
      fetch("/generate_study_plan", {
        method  : "POST",
        headers : { "Content-Type": "application/json" },
        body    : JSON.stringify(payload)
      })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(data => {
        if (!data.study_plan) throw new Error("No study_plan in response");
        document.dispatchEvent(new CustomEvent("plan:ready", { detail: data.study_plan }));
        root.innerHTML = "";                 // hide wizard
      })
      .catch(err => {
        console.error("Plan generation failed", err);
        root.innerHTML = "<p style='color:red'>Failed to generate plan. Please try again.</p>";
      });
    }
  
    /* ‑‑‑ public “regenerate” listener ‑‑‑ */
    document.addEventListener("plan:regenerate", () => {
      if (lastPayload) {
        fetch("/generate_study_plan", {
          method  : "POST",
          headers : { "Content-Type": "application/json" },
          body    : JSON.stringify(lastPayload)
        })
        .then(r => r.ok ? r.json() : Promise.reject(r))
        .then(data => {
          if (data.study_plan) {
            document.dispatchEvent(new CustomEvent("plan:ready", { detail: data.study_plan }));
          }
        })
        .catch(() => alert("Couldn’t regenerate plan – server error."));
      } else {
        currentStep = 0; renderStep();
      }
    });
  
    /* ‑‑‑ initialise: fetch learner profile then start wizard ‑‑‑ */
    root.innerHTML = "<p>Loading learner profile…</p>";
    fetch("/get_user_profile")
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(data => {
        window.LEARNER_PROFILE  = data || {};
        diagnosticSummary       = data.diagnostic_summary || "";
      })
      .catch(err => {
        console.warn("Could not fetch learner profile:", err);
      })
      .finally(() => {
        renderStep();
      });
  })();
  