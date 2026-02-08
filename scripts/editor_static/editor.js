(function () {
  "use strict";

  // --- State ---
  let characters = [];
  // Page order: 0=Fox Right, 1=Fox Left, 2..27=all right (alpha), 28..53=all left (alpha)
  let pageIndex = 0;
  let currentValues = { scale: 1.0, offset_x: 0, raise: 0 };
  let dirty = false;
  let loading = false;
  let flipped = false;
  let useOther = false;

  // --- DOM refs ---
  const preview = document.getElementById("preview");
  const previewContainer = document.getElementById("preview-container");
  const pageTitle = document.getElementById("page-title");
  const pageIndexEl = document.getElementById("page-index");
  const dirtyIndicator = document.getElementById("dirty-indicator");
  const loadingOverlay = document.getElementById("loading-overlay");
  const valScale = document.getElementById("val-scale");
  const valOffsetX = document.getElementById("val-offset-x");
  const valRaise = document.getElementById("val-raise");
  const btnSave = document.getElementById("btn-save");
  const btnReset = document.getElementById("btn-reset");
  const chkFlip = document.getElementById("chk-flip");
  const chkUseOther = document.getElementById("chk-use-other");

  // --- Helpers ---
  // First 2 pages are Fox Right, Fox Left. Then all right (alpha), then all left (alpha).
  let foxIndex = -1; // set after characters load

  function pageCharacter() {
    if (pageIndex === 0 || pageIndex === 1) return "Fox";
    var offset = pageIndex - 2;
    return characters[offset % characters.length];
  }

  function pageSide() {
    if (pageIndex === 0) return "right";
    if (pageIndex === 1) return "left";
    var offset = pageIndex - 2;
    return offset < characters.length ? "right" : "left";
  }

  function totalPages() {
    return 2 + characters.length * 2;
  }

  function updateUI() {
    const char = pageCharacter();
    const side = pageSide();
    pageTitle.textContent = char + " \u2014 " + side.charAt(0).toUpperCase() + side.slice(1);
    pageIndexEl.textContent = "(" + (pageIndex + 1) + "/" + totalPages() + ")";
    dirtyIndicator.classList.toggle("hidden", !dirty);
    valScale.textContent = currentValues.scale.toFixed(2);
    valOffsetX.textContent = String(currentValues.offset_x);
    valRaise.textContent = String(currentValues.raise);
  }

  function renderUrl() {
    const char = encodeURIComponent(pageCharacter());
    const side = pageSide();
    const s = currentValues.scale;
    const ox = currentValues.offset_x;
    const r = currentValues.raise;
    return "/api/render?character=" + char + "&side=" + side +
      "&scale=" + s + "&offset_x=" + ox + "&raise=" + r +
      "&flip=" + (flipped ? "1" : "0") + "&use_other=" + (useOther ? "1" : "0");
  }

  // Throttled image refresh
  let renderTimer = null;
  let renderPending = false;

  function requestRender() {
    if (renderTimer) {
      renderPending = true;
      return;
    }
    doRender();
    renderTimer = setTimeout(function () {
      renderTimer = null;
      if (renderPending) {
        renderPending = false;
        doRender();
      }
    }, 40); // ~25fps max
  }

  function doRender() {
    loadingOverlay.classList.remove("hidden");
    const url = renderUrl();
    const img = new window.Image();
    img.onload = function () {
      preview.src = img.src;
      loadingOverlay.classList.add("hidden");
    };
    img.onerror = function () {
      loadingOverlay.classList.add("hidden");
    };
    img.src = url;
  }

  // --- API calls ---
  async function fetchCharacters() {
    const res = await fetch("/api/characters");
    characters = await res.json();
  }

  async function fetchPage() {
    const char = pageCharacter();
    const side = pageSide();
    const res = await fetch("/api/page?character=" + encodeURIComponent(char) + "&side=" + side);
    const data = await res.json();
    currentValues.scale = data.scale;
    currentValues.offset_x = data.offset_x;
    currentValues.raise = data["raise"];
    dirty = data.dirty;
    flipped = data.mirror || false;
    useOther = data.use_other_side || false;
    chkFlip.checked = flipped;
    chkUseOther.checked = useOther;
    updateUI();
    requestRender();
  }

  async function commitCurrent() {
    if (!dirty) return;
    await fetch("/api/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        character: pageCharacter(),
        side: pageSide(),
        scale: currentValues.scale,
        offset_x: currentValues.offset_x,
        raise: currentValues.raise,
        mirror: flipped,
        use_other_side: useOther,
      }),
    });
  }

  async function navigateTo(newIndex) {
    // Commit current page if dirty before navigating
    await commitCurrent();
    pageIndex = newIndex;
    await fetchPage();
  }

  // --- Display scale factor (image pixels to screen pixels) ---
  function displayScale() {
    if (!preview.naturalWidth) return 1;
    return preview.clientWidth / preview.naturalWidth;
  }

  // Scale factors from set_thumbnail.py (1920x1080 base)
  // These are passed implicitly — we need to compute them from the actual image.
  // The server renders at the base image's native resolution.
  // scale_x = actual_width / 1920, scale_y = actual_height / 1080
  // We don't know the actual size, but we can estimate from the image dimensions.
  // Actually, we know the thumbnail is the base image size. We can read naturalWidth/Height.
  function configScaleX() {
    if (!preview.naturalWidth) return 1;
    return preview.naturalWidth / 1920;
  }

  function configScaleY() {
    if (!preview.naturalHeight) return 1;
    return preview.naturalHeight / 1080;
  }

  // --- Drag handling ---
  let dragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragStartOffsetX = 0;
  let dragStartRaise = 0;

  previewContainer.addEventListener("mousedown", function (e) {
    if (e.button !== 0) return;
    e.preventDefault();
    dragging = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    dragStartOffsetX = currentValues.offset_x;
    dragStartRaise = currentValues.raise;
  });

  window.addEventListener("mousemove", function (e) {
    if (!dragging) return;
    e.preventDefault();
    const ds = displayScale();
    const sx = configScaleX();
    const sy = configScaleY();
    const dx = e.clientX - dragStartX;
    const dy = e.clientY - dragStartY;

    // Convert pixel delta to config units
    currentValues.offset_x = dragStartOffsetX + Math.round(dx / ds / sx);
    currentValues.raise = dragStartRaise + Math.round(-dy / ds / sy);

    dirty = true;
    updateUI();
    requestRender();
  });

  window.addEventListener("mouseup", function (e) {
    if (!dragging) return;
    dragging = false;
    if (dirty) scheduleAutosave();
  });

  // --- Scroll to resize ---
  previewContainer.addEventListener("wheel", function (e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.02 : 0.02;
    currentValues.scale = Math.round(Math.max(0.3, Math.min(2.0, currentValues.scale + delta)) * 100) / 100;
    dirty = true;
    updateUI();
    requestRender();
    scheduleAutosave();
  }, { passive: false });

  // --- Keyboard navigation ---
  window.addEventListener("keydown", function (e) {
    if (e.target.tagName === "TEXTAREA") return;

    if (e.key === "z" || e.key === "Z") {
      e.preventDefault();
      const newIndex = (pageIndex - 1 + totalPages()) % totalPages();
      navigateTo(newIndex);
      return;
    }

    if (e.key === "x" || e.key === "X") {
      e.preventDefault();
      const newIndex = (pageIndex + 1) % totalPages();
      navigateTo(newIndex);
      return;
    }

    if (e.key === "c" || e.key === "C") {
      e.preventDefault();
      currentValues.scale = Math.round(Math.max(0.3, currentValues.scale - 0.01) * 100) / 100;
      dirty = true;
      updateUI();
      requestRender();
      scheduleAutosave();
      return;
    }

    if (e.key === "v" || e.key === "V") {
      e.preventDefault();
      currentValues.scale = Math.round(Math.min(2.0, currentValues.scale + 0.01) * 100) / 100;
      dirty = true;
      updateUI();
      requestRender();
      scheduleAutosave();
      return;
    }

    if (e.key === "s" || e.key === "S" || ((e.ctrlKey || e.metaKey) && e.key === "s")) {
      e.preventDefault();
      doSave();
      return;
    }

    if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      doReset();
      return;
    }
  });

  // --- Autosave (debounced) ---
  let autosaveTimer = null;

  function scheduleAutosave() {
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(function () {
      autosaveTimer = null;
      doSave();
    }, 1000);
  }

  // --- Save / Reset ---
  async function doSave() {
    if (autosaveTimer) { clearTimeout(autosaveTimer); autosaveTimer = null; }
    await commitCurrent();
    const res = await fetch("/api/save", { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      dirty = false;
      updateUI();
      btnSave.textContent = "Saved!";
      setTimeout(function () { btnSave.textContent = "Save"; }, 1500);
    }
  }

  async function doReset() {
    await fetch("/api/reset", { method: "POST" });
    dirty = false;
    await fetchPage();
  }

  btnSave.addEventListener("click", doSave);
  btnReset.addEventListener("click", doReset);

  // --- Sidebar toggles ---
  chkFlip.addEventListener("change", function () {
    flipped = chkFlip.checked;
    chkFlip.blur();
    dirty = true;
    updateUI();
    requestRender();
    scheduleAutosave();
  });

  chkUseOther.addEventListener("change", function () {
    useOther = chkUseOther.checked;
    chkUseOther.blur();
    dirty = true;
    updateUI();
    requestRender();
    scheduleAutosave();
  });

  // --- Init ---
  async function init() {
    await fetchCharacters();
    await fetchPage();
  }

  init();
})();
