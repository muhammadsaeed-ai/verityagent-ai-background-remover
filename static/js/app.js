(() => {
  "use strict";

  const MAX_FILE_BYTES = 12 * 1024 * 1024;
  const SUPPORTED_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"]);
  const els = {
    uploadZone: document.getElementById("uploadZone"),
    sourceInput: document.getElementById("sourceInput"),
    loadedSource: document.getElementById("loadedSource"),
    sourceImage: document.getElementById("sourceImage"),
    sourceName: document.getElementById("sourceName"),
    sourceDetails: document.getElementById("sourceDetails"),
    removeSource: document.getElementById("removeSource"),
    replaceSource: document.getElementById("replaceSource"),
    modeOptions: [...document.querySelectorAll("[data-mode]")],
    colorFields: document.getElementById("colorFields"),
    imageFields: document.getElementById("imageFields"),
    backgroundColor: document.getElementById("backgroundColor"),
    colorHex: document.getElementById("colorHex"),
    resetColor: document.getElementById("resetColor"),
    colorPresets: [...document.querySelectorAll("[data-color]")],
    backgroundDrop: document.getElementById("backgroundDrop"),
    backgroundInput: document.getElementById("backgroundInput"),
    backgroundFileName: document.getElementById("backgroundFileName"),
    backgroundFileDetails: document.getElementById("backgroundFileDetails"),
    processButton: document.getElementById("processButton"),
    processLabel: document.getElementById("processLabel"),
    processIcon: document.getElementById("processIcon"),
    downloadButton: document.getElementById("downloadButton"),
    emptyResult: document.getElementById("emptyResult"),
    outputImage: document.getElementById("outputImage"),
    resultSubtitle: document.getElementById("resultSubtitle"),
    resultStatus: document.getElementById("resultStatus"),
    resultStatusRing: document.getElementById("resultStatusRing"),
    resultMeta: document.getElementById("resultMeta"),
    stageDimensions: document.getElementById("stageDimensions"),
    compareChip: document.getElementById("compareChip"),
    compareLabel: document.getElementById("compareLabel"),
    viewToggle: document.getElementById("viewToggle"),
    liveMessage: document.getElementById("liveMessage")
  };
  const state = {
    sourceFile: null, sourceUrl: null, backgroundFile: null,
    resultBlob: null, resultUrl: null, mode: "transparent",
    busy: false, showingOriginal: false, messageTimer: null
  };
  const sparkIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1"/><circle cx="12" cy="12" r="4"/></svg>';

  function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }
  function normalizeHex(value) {
    const candidate = String(value || "").trim();
    const prefixed = candidate.startsWith("#") ? candidate : "#" + candidate;
    return /^#[0-9a-fA-F]{6}$/.test(prefixed) ? prefixed.toUpperCase() : null;
  }
  function showMessage(message, kind = "info") {
    window.clearTimeout(state.messageTimer);
    els.liveMessage.textContent = message;
    els.liveMessage.className = "live-message " + kind;
    els.liveMessage.hidden = false;
    if (kind !== "error") state.messageTimer = window.setTimeout(() => { els.liveMessage.hidden = true; }, 6200);
  }
  function clearMessage() {
    window.clearTimeout(state.messageTimer);
    els.liveMessage.hidden = true;
    els.liveMessage.textContent = "";
    els.liveMessage.className = "live-message";
  }
  function updateProcessButton() {
    const missingBackground = state.mode === "image" && !state.backgroundFile;
    els.processButton.disabled = !state.sourceFile || state.busy || missingBackground;
    els.processLabel.textContent = state.resultBlob ? "Reprocess image" : "Remove background";
    els.downloadButton.disabled = !state.resultBlob || state.busy;
  }
  function setStatus(text, kind = "idle") {
    els.resultStatus.textContent = text;
    els.resultStatusRing.className = "status-ring";
    if (kind === "ready") els.resultStatusRing.classList.add("ready");
    if (kind === "busy") els.resultStatusRing.classList.add("busy");
    if (kind === "error") els.resultStatusRing.classList.add("error");
  }
  function releaseResult() {
    if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
    state.resultUrl = null;
    state.resultBlob = null;
    state.showingOriginal = false;
    els.outputImage.removeAttribute("src");
    els.outputImage.hidden = true;
    els.emptyResult.hidden = false;
    els.stageDimensions.hidden = true;
    els.compareChip.hidden = true;
    els.viewToggle.disabled = true;
    els.resultSubtitle.textContent = "Your cleaned-up image will appear here";
    els.resultMeta.textContent = "OUTPUT · PNG";
    setStatus(state.sourceFile ? "Ready to process" : "Waiting for your first image");
    updateProcessButton();
  }
  function clearSource() {
    if (state.sourceUrl) URL.revokeObjectURL(state.sourceUrl);
    state.sourceUrl = null;
    state.sourceFile = null;
    els.sourceInput.value = "";
    els.sourceImage.removeAttribute("src");
    els.uploadZone.hidden = false;
    els.loadedSource.hidden = true;
    els.sourceName.textContent = "image.png";
    els.sourceDetails.textContent = "Ready to process";
    releaseResult();
    clearMessage();
    updateProcessButton();
  }
  function validateFile(file, label = "image") {
    if (!file) return false;
    const extension = file.name.split(".").pop().toLowerCase();
    const allowedExtensions = new Set(["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"]);
    if (!(SUPPORTED_TYPES.has(file.type) || allowedExtensions.has(extension))) {
      showMessage("Choose a PNG, JPG, WEBP, BMP, or TIFF " + label + ".", "error");
      return false;
    }
    if (file.size > MAX_FILE_BYTES) {
      showMessage("The " + label + " must be 12 MB or smaller.", "error");
      return false;
    }
    if (file.size === 0) {
      showMessage("The selected " + label + " is empty.", "error");
      return false;
    }
    return true;
  }
  function setSource(file) {
    if (!validateFile(file, "source image")) return;
    if (state.sourceUrl) URL.revokeObjectURL(state.sourceUrl);
    state.sourceFile = file;
    state.sourceUrl = URL.createObjectURL(file);
    els.sourceName.textContent = file.name;
    els.sourceDetails.textContent = formatBytes(file.size) + " · Loading preview…";
    els.uploadZone.hidden = true;
    els.loadedSource.hidden = false;
    releaseResult();
    clearMessage();
    els.sourceImage.onload = () => {
      const width = els.sourceImage.naturalWidth;
      const height = els.sourceImage.naturalHeight;
      els.sourceDetails.textContent = width.toLocaleString() + " × " + height.toLocaleString() + " px · " + formatBytes(file.size);
      updateProcessButton();
    };
    els.sourceImage.onerror = () => {
      clearSource();
      showMessage("This image format cannot be previewed by your browser. Try PNG, JPG, or WEBP.", "error");
    };
    els.sourceImage.src = state.sourceUrl;
    updateProcessButton();
    if (state.mode === "image" && !state.backgroundFile) {
      showMessage("Source loaded. Add a background image to enable processing.", "info");
    } else {
      showMessage("Image loaded and ready. Choose your finish, then remove the background.", "success");
    }
  }
  function setMode(mode) {
    if (!["transparent", "color", "image"].includes(mode) || state.busy) return;
    state.mode = mode;
    els.modeOptions.forEach((button) => {
      const selected = button.dataset.mode === mode;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    els.colorFields.hidden = mode !== "color";
    els.imageFields.hidden = mode !== "image";
    releaseResult();
    updateProcessButton();
  }
  function updateColor(hex, invalidate = false) {
    const normalized = normalizeHex(hex);
    if (!normalized) {
      els.colorHex.setAttribute("aria-invalid", "true");
      return false;
    }
    els.colorHex.removeAttribute("aria-invalid");
    els.colorHex.value = normalized;
    els.backgroundColor.value = normalized;
    els.colorPresets.forEach((button) => {
      button.classList.toggle("preset-active", button.dataset.color.toUpperCase() === normalized);
    });
    if (invalidate) {
      releaseResult();
      clearMessage();
    }
    return true;
  }
  async function processImage() {
    if (!state.sourceFile || state.busy) return;
    if (state.mode === "image" && !state.backgroundFile) {
      showMessage("Upload a background image before processing.", "error");
      return;
    }
    const chosenColor = normalizeHex(els.colorHex.value);
    if (state.mode === "color" && !chosenColor) {
      showMessage("Enter a valid six-digit HEX color first.", "error");
      els.colorHex.focus();
      return;
    }
    state.busy = true;
    state.showingOriginal = false;
    els.processButton.classList.add("loading");
    els.processButton.disabled = true;
    els.downloadButton.disabled = true;
    els.processIcon.innerHTML = '<span class="button-spinner" aria-hidden="true"></span>';
    els.processLabel.textContent = "Separating subject…";
    els.emptyResult.hidden = true;
    els.outputImage.hidden = true;
    els.compareChip.hidden = true;
    els.stageDimensions.hidden = true;
    els.resultSubtitle.textContent = "The model is building your foreground mask";
    setStatus("Processing locally — first run may take longer", "busy");
    clearMessage();

    const formData = new FormData();
    formData.append("image", state.sourceFile, state.sourceFile.name);
    formData.append("mode", state.mode);
    if (state.mode === "color") formData.append("color", chosenColor);
    if (state.mode === "image" && state.backgroundFile) {
      formData.append("background", state.backgroundFile, state.backgroundFile.name);
    }

    try {
      const response = await fetch("/api/remove-background", {
        method: "POST",
        body: formData,
        headers: { "Accept": "image/png, application/json" },
        cache: "no-store"
      });
      if (!response.ok) {
        let message = "Processing failed (" + response.status + ").";
        try {
          const body = await response.json();
          if (body && typeof body.error === "string") message = body.error;
        } catch (_ignored) {}
        throw new Error(message);
      }
      const blob = await response.blob();
      if (!blob.type.includes("image/")) throw new Error("The server returned an unexpected output. Please retry.");
      const nextUrl = URL.createObjectURL(blob);
      if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
      state.resultUrl = nextUrl;
      state.resultBlob = blob;
      state.showingOriginal = false;
      els.outputImage.src = state.resultUrl;
      els.outputImage.alt = state.mode === "transparent"
        ? "Image with its background removed and transparent pixels preserved"
        : "Image with its background removed and a replacement background applied";
      els.outputImage.hidden = false;
      els.emptyResult.hidden = true;
      els.compareChip.hidden = false;
      els.compareLabel.textContent = state.mode === "transparent" ? "TRANSPARENT CUTOUT" : "FINAL COMPOSITE";
      els.stageDimensions.hidden = false;
      const width = response.headers.get("X-Output-Width");
      const height = response.headers.get("X-Output-Height");
      els.stageDimensions.textContent = width && height
        ? Number(width).toLocaleString() + " × " + Number(height).toLocaleString() + " PX"
        : "PNG · LOSSLESS";
      els.resultSubtitle.textContent = state.mode === "transparent"
        ? "Foreground isolated · transparency preserved"
        : state.mode === "color"
          ? "Foreground isolated · " + chosenColor
          : "Foreground isolated · custom background applied";
      els.resultMeta.textContent = state.mode === "transparent" ? "ALPHA · PRESERVED" : "COMPOSITE · PNG";
      setStatus("Cutout complete — ready to export", "ready");
      els.viewToggle.disabled = false;
      updateProcessButton();
      showMessage("Your cutout is ready. Preview it, then export the full-resolution PNG.", "success");
    } catch (error) {
      setStatus("Could not complete this cutout", "error");
      els.resultSubtitle.textContent = "The last output could not be generated";
      showMessage(error instanceof Error ? error.message : "An unexpected processing error occurred.", "error");
    } finally {
      state.busy = false;
      els.processButton.classList.remove("loading");
      els.processIcon.innerHTML = sparkIcon;
      updateProcessButton();
    }
  }
  function togglePreview() {
    if (!state.resultBlob || !state.resultUrl || !state.sourceUrl || state.busy) return;
    state.showingOriginal = !state.showingOriginal;
    els.outputImage.src = state.showingOriginal ? state.sourceUrl : state.resultUrl;
    els.outputImage.alt = state.showingOriginal ? "Original source image preview" : "Processed background removal result";
    els.compareLabel.textContent = state.showingOriginal
      ? "ORIGINAL IMAGE"
      : (state.mode === "transparent" ? "TRANSPARENT CUTOUT" : "FINAL COMPOSITE");
    els.resultSubtitle.textContent = state.showingOriginal
      ? "Original source · comparison view"
      : state.mode === "transparent"
        ? "Foreground isolated · transparency preserved"
        : "Foreground isolated · replacement background applied";
    els.resultMeta.textContent = state.showingOriginal
      ? "SOURCE · PREVIEW"
      : (state.mode === "transparent" ? "ALPHA · PRESERVED" : "COMPOSITE · PNG");
  }
  function downloadResult() {
    if (!state.resultBlob || state.busy) return;
    const baseName = (state.sourceFile?.name || "image")
      .replace(/\.[^.]+$/, "")
      .replace(/[^a-zA-Z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 70) || "image";
    const link = document.createElement("a");
    link.href = state.resultUrl;
    link.download = baseName + "-cutout.png";
    document.body.appendChild(link);
    link.click();
    link.remove();
    showMessage("PNG export started.", "success");
  }

  els.uploadZone.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    els.sourceInput.click();
  });
  els.uploadZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      els.sourceInput.click();
    }
  });
  els.sourceInput.addEventListener("change", () => {
    const file = els.sourceInput.files && els.sourceInput.files[0];
    if (file) setSource(file);
  });
  els.uploadZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    els.uploadZone.classList.add("drag-over");
  });
  els.uploadZone.addEventListener("dragleave", () => els.uploadZone.classList.remove("drag-over"));
  els.uploadZone.addEventListener("drop", (event) => {
    event.preventDefault();
    els.uploadZone.classList.remove("drag-over");
    const file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) setSource(file);
  });
  els.replaceSource.addEventListener("click", () => els.sourceInput.click());
  els.removeSource.addEventListener("click", clearSource);
  els.modeOptions.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
  els.backgroundColor.addEventListener("input", () => updateColor(els.backgroundColor.value, true));
  els.colorHex.addEventListener("input", () => updateColor(els.colorHex.value, true));
  els.colorHex.addEventListener("blur", () => {
    if (!updateColor(els.colorHex.value, false)) {
      els.colorHex.value = els.backgroundColor.value.toUpperCase();
      els.colorHex.removeAttribute("aria-invalid");
    }
  });
  els.resetColor.addEventListener("click", () => {
    updateColor("#F4F1EB", true);
    showMessage("Background color reset to warm ivory.", "info");
  });
  els.colorPresets.forEach((button) => {
    button.addEventListener("click", () => {
      updateColor(button.dataset.color, true);
      showMessage("Background color set to " + button.dataset.color.toUpperCase() + ".", "info");
    });
  });
  els.backgroundDrop.addEventListener("click", () => els.backgroundInput.click());
  els.backgroundInput.addEventListener("change", () => {
    const file = els.backgroundInput.files && els.backgroundInput.files[0];
    if (!file) return;
    if (!validateFile(file, "background image")) {
      els.backgroundInput.value = "";
      return;
    }
    state.backgroundFile = file;
    els.backgroundFileName.textContent = file.name;
    els.backgroundFileDetails.textContent = formatBytes(file.size) + " · ready to place";
    els.backgroundDrop.setAttribute("aria-label", "Replace background image " + file.name);
    releaseResult();
    updateProcessButton();
    showMessage("New background selected. The subject will be composited over it.", "success");
  });
  els.processButton.addEventListener("click", processImage);
  els.downloadButton.addEventListener("click", downloadResult);
  els.viewToggle.addEventListener("click", togglePreview);

  updateColor("#F4F1EB", false);
  updateProcessButton();
  setStatus("Waiting for your first image");
})();
