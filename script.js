const screens = document.querySelectorAll(".screen");
const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const urlInput = document.getElementById("urlInput");

function showScreen(screenId) {
  screens.forEach((screen) => {
    screen.classList.remove("active");
  });

  const target = document.getElementById(screenId);
  if (target) {
    target.classList.add("active");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

if (fileInput) {
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      fileName.textContent = fileInput.files[0].name;
    } else {
      fileName.textContent = "선택된 파일 없음";
    }
  });
}

function startAnalysis() {
  const hasFile = fileInput.files.length > 0;
  const hasUrl = urlInput.value.trim().length > 0;

  if (!hasFile && !hasUrl) {
    alert("이미지 파일을 업로드하거나 URL을 입력해 주세요.");
    return;
  }

  if (hasFile && hasUrl) {
    alert("파일과 URL이 모두 입력되었습니다. 하나의 입력 방식만 선택해 주세요.");
    return;
  }

  showScreen("progress");
}

function resetInput() {
  fileInput.value = "";
  urlInput.value = "";
  fileName.textContent = "선택된 파일 없음";
}

function submitFeedback() {
  const selected = document.querySelector("input[name='feedbackType']:checked");
  const message = document.getElementById("feedbackMessage");

  if (!selected) {
    alert("피드백 유형을 선택해 주세요.");
    return;
  }

  message.classList.remove("hidden");

  setTimeout(() => {
    message.classList.add("hidden");
    showScreen("result");
  }, 1200);
}

function saveReview() {
  const message = document.getElementById("reviewMessage");
  message.classList.remove("hidden");

  setTimeout(() => {
    message.classList.add("hidden");
    showScreen("admin");
  }, 1200);
}