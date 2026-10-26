(function () {
  const form = document.getElementById("plot-form");
  const fileInput = document.getElementById("file");
  const drop = document.getElementById("drop");
  const acceptHint = document.getElementById("accept-hint");
  const statusEl = document.getElementById("status");
  const btn = document.getElementById("btn");
  const result = document.getElementById("result");
  const preview = document.getElementById("preview");
  const downloads = document.getElementById("downloads");
  const resultMeta = document.getElementById("result-meta");
  const colorPicker = document.getElementById("color_picker");
  const colorText = document.getElementById("color");
  const fitPicker = document.getElementById("fit_color_picker");
  const fitText = document.getElementById("fit_color");

  const HINTS = {
    eis: "EIS：CSV / TXT / Excel（Frequency + Zre/Zim 或 |Z|+相位；支持仪器制表符 TXT）",
    sem: "SEM：PNG / TIFF / JPG 灰度图",
    polar: "极化：CSV / TXT / Excel（电位 E + 电流密度 i/j）",
    ocp: "OCP：CSV/TXT（Potential；可无时间列，将用点序号；也可带 time/t）",
    pull: "拉拔：CSV / Excel（group + strength，或已汇总 mean/sd/n）",
  };

  function currentType() {
    const el = form.querySelector('input[name="plot_type"]:checked');
    return el ? el.value : "eis";
  }

  function syncTypeUI() {
    const t = currentType();
    acceptHint.textContent = HINTS[t] || "";
    document.querySelectorAll(".type-opts").forEach((fs) => fs.classList.add("hidden"));
    const map = { eis: "opts-eis", sem: "opts-sem", polar: "opts-polar" };
    if (map[t]) document.getElementById(map[t]).classList.remove("hidden");
    if (t === "sem") {
      fileInput.accept = ".png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,image/*";
    } else {
      fileInput.accept = ".csv,.txt,.tsv,.xlsx,.xls,text/csv,text/plain,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    }
  }

  form.querySelectorAll('input[name="plot_type"]').forEach((r) => {
    r.addEventListener("change", syncTypeUI);
  });
  syncTypeUI();

  colorPicker.addEventListener("input", () => {
    colorText.value = colorPicker.value;
  });
  fitPicker.addEventListener("input", () => {
    fitText.value = fitPicker.value;
  });

  ["dragenter", "dragover"].forEach((ev) => {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.remove("drag");
    });
  });
  drop.addEventListener("drop", (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      fileInput.files = e.dataTransfer.files;
      document.getElementById("drop-hint").textContent = "已选择：" + e.dataTransfer.files[0].name;
    }
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
      document.getElementById("drop-hint").textContent = "已选择：" + fileInput.files[0].name;
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!fileInput.files || !fileInput.files[0]) {
      statusEl.textContent = "请先选择文件";
      statusEl.className = "status err";
      return;
    }
    statusEl.textContent = "正在出图…";
    statusEl.className = "status";
    btn.disabled = true;
    result.classList.add("hidden");

    const fd = new FormData(form);
    // stretch checkbox: if unchecked, send 0
    if (currentType() === "sem" && !form.querySelector('input[name="stretch"]').checked) {
      fd.set("stretch", "0");
    }
    // auto_tafel checkbox
    const at = form.querySelector('input[name="auto_tafel"]');
    if (currentType() === "polar") {
      fd.set("auto_tafel", at && at.checked ? "1" : "0");
    }
    // color: prefer text field; if empty leave empty to use palette
    if (!colorText.value.trim()) {
      fd.delete("color");
    } else {
      fd.set("color", colorText.value.trim());
    }
    fd.delete("color_picker");
    if (!fitText.value.trim()) {
      fd.delete("fit_color");
    }
    // always use JSON endpoint for preview + multi download
    try {
      const resp = await fetch("/api/plot/json", { method: "POST", body: fd });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        let msg = data.message || ("HTTP " + resp.status);
        if (typeof data.detail === "string") msg = data.detail;
        else if (Array.isArray(data.detail)) msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
        else if (data.detail) msg = JSON.stringify(data.detail);
        throw new Error(msg);
      }
      statusEl.textContent = "完成";
      statusEl.className = "status ok";
      result.classList.remove("hidden");
      resultMeta.textContent = "任务 " + data.job_id + " · " + (data.note || "");
      if (data.preview_url) {
        preview.src = data.preview_url + "?t=" + Date.now();
        preview.style.display = "";
      } else {
        preview.removeAttribute("src");
        preview.style.display = "none";
      }
      downloads.innerHTML = "";
      (data.files || []).forEach((f) => {
        const a = document.createElement("a");
        a.href = f.url;
        a.download = f.name;
        a.textContent = "下载 " + f.name;
        downloads.appendChild(a);
      });
    } catch (err) {
      statusEl.textContent = String(err.message || err);
      statusEl.className = "status err";
    } finally {
      btn.disabled = false;
    }
  });
})();
