const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const urlInput = document.getElementById("urlInput");
const resetButton = document.querySelector("[data-reset-input]");
const dropZone = document.querySelector("[data-drop-zone]");

if (fileInput && fileName) {
  fileInput.addEventListener("change", () => {
    updateSelectedFileName();
  });
}

if (resetButton) {
  resetButton.addEventListener("click", () => {
    if (fileInput) {
      fileInput.value = "";
    }
    if (urlInput) {
      urlInput.value = "";
    }
    if (fileName) {
      fileName.textContent = "선택된 파일 없음";
    }
  });
}

if (dropZone && fileInput) {
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropZone.classList.add("drag-over");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropZone.classList.remove("drag-over");
    });
  });

  dropZone.addEventListener("drop", (event) => {
    const files = event.dataTransfer && event.dataTransfer.files;
    if (!files || files.length === 0) {
      return;
    }
    fileInput.files = files;
    updateSelectedFileName();
  });
}

["dragover", "drop"].forEach((eventName) => {
  document.addEventListener(eventName, (event) => {
    const hasFiles = event.dataTransfer && Array.from(event.dataTransfer.types || []).includes("Files");
    if (hasFiles) {
      event.preventDefault();
    }
  });
});

function updateSelectedFileName() {
  if (!fileInput || !fileName) {
    return;
  }
  if (fileInput.files.length > 0) {
    fileName.textContent = fileInput.files[0].name;
  } else {
    fileName.textContent = "선택된 파일 없음";
  }
}
