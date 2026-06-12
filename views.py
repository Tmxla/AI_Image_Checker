from html import escape
from urllib.parse import urlencode


def render_page(
    title: str,
    body: str,
    message: str = "",
    message_type: str = "info",
    home_link: str = "/",
    admin_authenticated: bool = False,
) -> str:
    alert = ""
    if message:
        alert = f'<div class="alert {escape(message_type)}">{escape(message)}</div>'
    admin_link = '<a class="admin-link" href="/admin/logout">Logout</a>' if admin_authenticated else '<a class="admin-link" href="/admin">Administrator</a>'
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} | TrueLens</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="app">
    <header class="header">
      <a class="brand-block" href="{escape(home_link, quote=True)}">
        <h1>TrueLens</h1>
        <p>AI 기반 이미지 진위 판별 보조 시스템</p>
      </a>
      {admin_link}
    </header>

    {alert}
    {body}
  </div>
  <script src="/static/script.js"></script>
</body>
</html>"""


def render_index(message: str = "", message_type: str = "info") -> str:
    body = """
<section class="screen active">
  <div class="hero-card">
    <span class="badge">AI Image Checker</span>
    <h2>AI 생성 이미지 여부를 확인해보세요.</h2>
    <p>이미지 파일을 업로드하거나 이미지 URL을 입력하면 TrueLens가 AI 생성 가능성을 분석합니다.</p>

    <form id="analysisForm" action="/analyze" method="post" enctype="multipart/form-data">
      <div class="upload-grid">
        <div class="upload-box" id="dropZone" data-drop-zone>
          <div class="upload-icon">UP</div>
          <h3>이미지 파일 업로드</h3>
          <p>JPG 또는 PNG 파일을 드래그 앤 드롭하거나 선택하세요.</p>
          <label class="file-label">
            파일 선택
            <input type="file" id="fileInput" name="image_file" accept="image/png, image/jpeg">
          </label>
          <p id="fileName" class="file-name">선택된 파일 없음</p>
        </div>

        <div class="url-box">
          <h3>이미지 URL 입력</h3>
          <p>웹상 이미지 주소를 입력하여 분석할 수 있습니다.</p>
          <input type="text" id="urlInput" name="image_url" placeholder="https://example.com/image.jpg">
          <p class="hint">파일 업로드 또는 URL 입력 중 하나만 사용하세요.</p>
        </div>
      </div>

      <div class="button-row">
        <button class="primary-btn" type="submit">분석</button>
        <button class="secondary-btn" type="button" data-reset-input>초기화</button>
      </div>
    </form>
  </div>
</section>
"""
    return render_page("이미지 분석", body, message, message_type)


def render_admin_login(message: str = "", message_type: str = "info") -> str:
    body = """
<section class="screen active">
  <div class="content-card narrow">
    <div class="section-title">
      <span class="badge">Administrator</span>
      <h2>관리자 로그인</h2>
    </div>

    <p class="login-copy">관리자 대시보드는 관리자 인증 후 접근할 수 있습니다.</p>

    <form action="/admin/login" method="post">
      <label class="form-label">관리자 비밀번호</label>
      <input type="password" name="password" placeholder="관리자 비밀번호를 입력하세요" autocomplete="current-password">
      <p class="hint">관리자에게 발급된 비밀번호를 입력해야 대시보드에 접근할 수 있습니다.</p>

      <div class="button-row left">
        <button class="primary-btn" type="submit">로그인</button>
        <a class="ghost-btn" href="/">메인으로 돌아가기</a>
      </div>
    </form>
  </div>
</section>
"""
    return render_page("관리자 로그인", body, message, message_type)


def render_progress(result_id: str) -> str:
    result_id = escape(result_id, quote=True)
    body = f"""
<section class="screen active">
  <div class="center-card">
    <div class="spinner"></div>
    <h2>이미지를 분석하는 중입니다.</h2>
    <p>AI 분석 엔진이 생성 가능성과 보조 시각 근거를 계산하고 있습니다.</p>

    <div class="status-card">
      <div>
        <span>요청 상태</span>
        <strong>분석 완료</strong>
      </div>
      <div>
        <span>결과 화면</span>
        <strong>자동 이동</strong>
      </div>
    </div>

    <a class="primary-btn" href="/result?id={result_id}">결과 화면으로 이동</a>
  </div>
</section>
<script>
  window.setTimeout(function () {{
    window.location.href = "/result?id={result_id}";
  }}, 900);
</script>
"""
    return render_page("분석 진행", body)


def render_result(row, message: str = "", message_type: str = "info") -> str:
    percent = int(row["ai_probability"] * 100)
    result_id = escape(row["result_id"])
    elapsed = round((row["processing_time_ms"] or 0) / 1000, 1)
    body = f"""
<section class="screen active">
  <div class="content-card">
    <div class="section-title">
      <span class="badge danger">Result</span>
      <h2>분석 결과 상세</h2>
    </div>

    <div class="result-layout">
      <div class="image-preview">
        {real_image(row, "Sample Image")}
      </div>

      <div class="result-panel">
        <p class="label">AI 생성 확률</p>
        <div class="score">{percent}%</div>
        <h3>{escape(row["result_label"])}</h3>
        <p>{escape(row["result_summary"])}</p>

        <div class="summary-box">
          <div>
            <span>판별 결과</span>
            <strong>{escape(_short_result(row["ai_probability"]))}</strong>
          </div>
          <div>
            <span>분석 시간</span>
            <strong>{elapsed}초</strong>
          </div>
          <div>
            <span>모델 버전</span>
            <strong>{escape(row["model_version"])}</strong>
          </div>
        </div>

        <div class="button-row left">
          <a class="primary-btn" href="/heatmap?id={result_id}">시각 근거 보기</a>
          <a class="secondary-btn" href="/feedback?id={result_id}">오판별 피드백</a>
          <a class="ghost-btn" href="/">새 이미지 분석</a>
        </div>
      </div>
    </div>
  </div>
</section>
"""
    return render_page("분석 결과", body, message, message_type)


def render_heatmap(row, message: str = "", message_type: str = "info") -> str:
    result_id = escape(row["result_id"])
    probability = float(row["ai_probability"])
    x = int(row["heatmap_x"])
    y = int(row["heatmap_y"])
    size = int(row["heatmap_size"])
    has_heatmap_signal = probability >= 0.20 and size > 0
    heatmap_class = "fake-image heatmap-img has-signal" if has_heatmap_signal else "fake-image heatmap-img clean"
    heatmap_overlay = '<div class="heatmap-layer" aria-hidden="true"></div>' if has_heatmap_signal else '<div class="clean-layer">검출된 의심 영역 없음</div>'
    heatmap_label = "Visual Evidence" if has_heatmap_signal else "No Suspicious Region"
    body = f"""
<section class="screen active">
  <div class="content-card">
    <div class="section-title">
      <span class="badge">Visual Evidence</span>
      <h2>보조 시각 근거 확인</h2>
    </div>

    <p class="notice">{escape(row["heatmap_description"])}</p>

    <div class="heatmap-grid">
      <div>
        <h3>원본 이미지</h3>
        <div class="fake-image original">
          {real_image(row, "Original Image")}
        </div>
      </div>
      <div>
        <h3>보조 시각화</h3>
        <div class="{heatmap_class}" style="--heat-x: {x}%; --heat-y: {y}%; --heat-size: {size}%;">
          {real_image(row, heatmap_label)}
          {heatmap_overlay}
        </div>
      </div>
    </div>

    <div class="button-row">
      <a class="primary-btn" href="/result?id={result_id}">결과 화면으로 돌아가기</a>
      <a class="secondary-btn" href="/feedback?id={result_id}">오판별 피드백</a>
    </div>
  </div>
</section>
"""
    return render_page("시각 근거", body, message, message_type)


def render_feedback(row, message: str = "", message_type: str = "info") -> str:
    result_id = escape(row["result_id"])
    percent = int(row["ai_probability"] * 100)
    body = f"""
<section class="screen active">
  <div class="content-card narrow">
    <div class="section-title">
      <span class="badge">Feedback</span>
      <h2>오판별 피드백 제출</h2>
    </div>

    <div class="mini-result">
      <p>현재 시스템 판별 결과</p>
      <strong>{escape(row["result_label"])} · {percent}%</strong>
    </div>

    <form action="/feedback" method="post">
      <input type="hidden" name="result_id" value="{result_id}">
      <label class="form-label">피드백 유형</label>
      <div class="radio-group">
        <label><input type="radio" name="feedback_type" value="real_photo"> 실제 사진입니다</label>
        <label><input type="radio" name="feedback_type" value="ai_generated"> AI 생성 이미지입니다</label>
        <label><input type="radio" name="feedback_type" value="uncertain"> 판별 결과가 애매합니다</label>
      </div>

      <label class="form-label">추가 의견</label>
      <textarea name="comment" placeholder="판별 결과에 대한 의견을 입력해 주세요."></textarea>

      <div class="button-row">
        <button class="primary-btn" type="submit">전송</button>
        <a class="ghost-btn" href="/result?id={result_id}">취소</a>
      </div>
    </form>
  </div>
</section>
"""
    return render_page("오판별 피드백", body, message, message_type)


def render_admin(status, feedbacks, message: str = "", message_type: str = "info") -> str:
    items = []
    for item in feedbacks:
        feedback_id = escape(item["feedback_id"])
        items.append(
            f"""
            <a class="feedback-item" href="/admin/feedback?id={feedback_id}">
              <div class="thumb"></div>
              <div>
                <strong>{escape(item["result_label"])}</strong>
                <p>사용자 피드백: {escape(item["feedback_type"])}</p>
              </div>
              <span>{escape(item["submitted_at"])}</span>
              <em>{escape(item["status"])}</em>
            </a>
            """
        )
    feedback_list = "".join(items) or '<div class="empty-list">접수된 오판별 피드백이 없습니다.</div>'
    body = f"""
<section class="screen active">
  <div class="content-card">
    <div class="section-title">
      <span class="badge">Administrator</span>
      <h2>관리자 대시보드</h2>
    </div>

    <h3>시스템 상태 관리</h3>
    <div class="dashboard-grid">
      <div class="metric-card">
        <span>일일 분석 요청 수</span>
        <strong>{status.daily_request_count}</strong>
      </div>
      <div class="metric-card">
        <span>평균 분석 처리 시간</span>
        <strong>{status.average_processing_time}초</strong>
      </div>
      <div class="metric-card">
        <span>분석 성공 건수</span>
        <strong>{status.success_count}</strong>
      </div>
      <div class="metric-card">
        <span>분석 실패 건수</span>
        <strong>{status.failure_count}</strong>
      </div>
      <div class="metric-card">
        <span>현재 처리 중인 요청 수</span>
        <strong>{status.processing_count}</strong>
      </div>
      <div class="metric-card success">
        <span>시스템 상태</span>
        <strong>{escape(status.system_state)}</strong>
      </div>
    </div>

    <h3 class="mt">피드백 관리</h3>
    <div class="feedback-list">{feedback_list}</div>

    <a class="ghost-btn mt" href="/">메인 화면으로</a>
  </div>
</section>
"""
    return render_page("관리자", body, message, message_type, admin_authenticated=True)


def render_feedback_review(row, message: str = "", message_type: str = "info") -> str:
    feedback_id = escape(row["feedback_id"])
    percent = int(row["ai_probability"] * 100)
    body = f"""
<section class="screen active">
  <div class="content-card">
    <div class="section-title">
      <span class="badge">Review</span>
      <h2>피드백 상세 검토</h2>
    </div>

    <div class="review-layout">
      <div class="fake-image review-img">
        {real_image(row, "Original Image")}
      </div>

      <form class="review-panel" action="/admin/review" method="post">
        <input type="hidden" name="feedback_id" value="{feedback_id}">
        <h3>시스템 판별 결과</h3>
        <p><strong>AI 생성 확률:</strong> {percent}%</p>
        <p><strong>판별 문구:</strong> {escape(row["result_label"])}</p>

        <h3>사용자 피드백</h3>
        <p><strong>피드백 유형:</strong> {escape(row["feedback_type"])}</p>
        <p><strong>추가 의견:</strong> {escape(row["comment"] or "작성된 추가 의견이 없습니다.")}</p>

        <label class="form-label">검토 결과 선택</label>
        <select name="review_result">
          <option>모델 개선 후보</option>
          <option>단순 참고</option>
          <option>검토 제외</option>
        </select>

        <label class="form-label">관리자 의견</label>
        <textarea name="admin_comment" placeholder="검토 의견을 입력해 주세요."></textarea>

        <div class="button-row left">
          <button class="primary-btn" type="submit">저장</button>
          <a class="ghost-btn" href="/admin">목록으로 돌아가기</a>
        </div>
      </form>
    </div>
  </div>
</section>
"""
    return render_page("피드백 상세 검토", body, message, message_type, admin_authenticated=True)


def render_not_found(message: str = "요청한 페이지를 찾을 수 없습니다.") -> str:
    body = f"""
<section class="screen active">
  <div class="center-card">
    <span class="badge danger">Not Found</span>
    <h2>{escape(message)}</h2>
    <p>이전 화면으로 돌아가 다시 시도해 주세요.</p>
    <a class="primary-btn" href="/">메인으로 이동</a>
  </div>
</section>
"""
    return render_page("페이지 없음", body)


def redirect_url(path: str, params: dict[str, str]) -> str:
    return f"{path}?{urlencode(params)}"


def image_src(row) -> str:
    if row["image_url"]:
        return row["image_url"]
    path = (row["image_path"] or "").replace("\\", "/")
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def real_image(row, fallback_text: str) -> str:
    src = escape(image_src(row), quote=True)
    alt = escape(row["source_name"] or "분석 이미지")
    return f'<img src="{src}" alt="{alt}" onerror="this.remove()"><span>{escape(fallback_text)}</span>'


def _short_result(probability: float) -> str:
    if probability >= 0.72:
        return "AI Generated"
    if probability >= 0.45:
        return "Uncertain"
    return "Likely Real"
