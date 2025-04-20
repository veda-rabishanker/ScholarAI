console.log("__VERSION 6  ::  video_recs.js loaded");

// ────────────────────────────────────────────────────────────
// Mounts on <div id="video-recs-root"> and handles:
//  • POST → /recommend_videos with diagnostic_summary + learning_style
//  • Skeleton loader while waiting
//  • Responsive gallery of video cards (thumbnail + title + channel)
//  • In‑page playback with Back button
//  • "Refresh Videos" button pulls the latest diagnostic summary first
// ────────────────────────────────────────────────────────────
(() => {
  /* ────────── bootstrap ────────── */
  const mount = document.getElementById("video-recs-root");
  if (!mount) return;                         // not on Results page

  const state = {
    videos: [],
    lastPayload: {
      diagnostic_summary: mount.dataset.diagnosticSummary || "",
      learning_style    : mount.dataset.learningStyle     || ""
    }
  };

  renderIntro();

  /* ────────── UI helpers ────────── */

  function renderIntro() {
    mount.innerHTML = "";
    if (!state.lastPayload.diagnostic_summary.trim()) {
      mount.innerHTML =
        `<p>Complete a diagnostic test to unlock personalised video recommendations.</p>`;
      return;
    }
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.textContent = "Load Recommended Videos";
    btn.onclick    = loadVideos;
    mount.appendChild(btn);
  }

  function renderSkeleton() {
    mount.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "video-container";
    for (let i = 0; i < 6; i++) {
      const card = document.createElement("div");
      card.className = "video-card";
      card.style =
        "background:#ececec;height:180px;border:none;animation:pulse 1.5s ease-in-out infinite;";
      wrap.appendChild(card);
    }
    mount.appendChild(wrap);

    if (!document.getElementById("pulse-anim")) {
      const style = document.createElement("style");
      style.id = "pulse-anim";
      style.textContent =
        "@keyframes pulse{0%{opacity:.7;}50%{opacity:.4;}100%{opacity:.7;}}";
      document.head.appendChild(style);
    }
  }

  function renderGrid() {
    mount.innerHTML = "";

    // Refresh button
    const refresh = document.createElement("button");
    refresh.className = "btn";
    refresh.textContent = "Refresh Videos";
    refresh.onclick    = loadVideos;      // loadVideos already updates summary
    mount.appendChild(refresh);

    if (!state.videos.length) {
      mount.insertAdjacentHTML(
        "beforeend",
        `<p id="no-videos-message">No videos found for your diagnostic profile.</p>`
      );
      return;
    }

    const grid = document.createElement("div");
    grid.className = "video-container";
    state.videos.forEach(v => {
      const card = document.createElement("div");
      card.className = "video-card";
      card.innerHTML = `
        <div class="video-thumbnail">
          <img src="${v.thumbnail}" alt="${v.title}">
        </div>
        <div class="video-info">
          <h4>${v.title}</h4>
          <p>Channel: ${v.channel}</p>
        </div>`;
      card.querySelector(".video-thumbnail").onclick = () => renderEmbed(v);
      grid.appendChild(card);
    });
    mount.appendChild(grid);
  }

  function renderEmbed(video) {
    mount.innerHTML = "";

    const back = document.createElement("button");
    back.className = "btn";
    back.textContent = "Back to Videos";
    back.onclick     = renderGrid;
    mount.appendChild(back);

    const iframe = document.createElement("iframe");
    iframe.className      = "embedded-video";
    iframe.src            = `https://www.youtube.com/embed/${video.video_id}?autoplay=1`;
    iframe.allow          = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
    iframe.allowFullscreen = true;
    iframe.frameBorder    = "0";
    mount.appendChild(iframe);

    mount.scrollIntoView({ behavior: "smooth" });
  }

  /* ────────── data helpers ────────── */

  // ALWAYS adopt whatever the server returns (even an empty string)
  async function updateDiagnosticSummary() {
    try {
      const profile = await fetch("/get_user_profile").then(r => r.json());
      state.lastPayload.diagnostic_summary = profile.diagnostic_summary ?? "";
      console.log("🔄 diagnostic_summary now:",
                  state.lastPayload.diagnostic_summary.slice(0, 60) || "(empty)");
    } catch (e) {
      console.warn("Could not refresh diagnostic summary:", e);
    }
  }

  /* ────────── main fetch routine ────────── */

  async function loadVideos () {
    await updateDiagnosticSummary();           // always latest
    console.log("📦 Final payload:", state.lastPayload);

    renderSkeleton();
    fetch(`/recommend_videos?ts=${Date.now()}`, {   // cache‑bust
      method : "POST",
      headers: { "Content-Type": "application/json" },
      body   : JSON.stringify(state.lastPayload)
    })
    .then(r => r.ok ? r.json() : Promise.reject(r))
    .then(data => {
      console.log("◀ /recommend_videos →", data.videos?.map(v => v.title));
      state.videos = Array.isArray(data.videos) ? data.videos : [];
      renderGrid();
    })
    .catch(err => {
      console.error("/recommend_videos error:", err);
      mount.innerHTML =
        `<p style="color:#c0392b;">Failed to load videos. Please try again later.</p>`;
    });
  }
})();
