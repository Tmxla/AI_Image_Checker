from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import hashlib
import hmac
import mimetypes
import os

from controllers import AdminController, AnalysisController, FeedbackController
from detection_engine import DetectionEngine
from storage import SQLiteStorage
from views import (
    redirect_url,
    render_admin,
    render_admin_login,
    render_feedback,
    render_feedback_review,
    render_heatmap,
    render_index,
    render_not_found,
    render_progress,
    render_result,
)


storage = SQLiteStorage()
analysis_controller = AnalysisController(storage, DetectionEngine())
feedback_controller = FeedbackController(storage)
admin_controller = AdminController(storage)
ADMIN_PASSWORD = os.environ.get("TRUELENS_ADMIN_PASSWORD", "admin1234")
ADMIN_SECRET = os.environ.get("TRUELENS_ADMIN_SECRET", "truelens-local-admin-secret")
ADMIN_COOKIE_NAME = "truelens_admin"


class TrueLensHandler(BaseHTTPRequestHandler):
    server_version = "TrueLensHTTP/1.0"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/static/"):
            self.serve_static(parsed.path, head_only=True)
            return
        if parsed.path in {"/", "/progress", "/result", "/heatmap", "/feedback", "/admin", "/admin/login", "/admin/logout", "/admin/feedback"}:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            return
        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path.startswith("/static/"):
            self.serve_static(path)
            return
        if path == "/":
            self.send_html(render_index())
            return
        if path == "/result":
            self.show_result(query)
            return
        if path == "/progress":
            self.show_progress(query)
            return
        if path == "/heatmap":
            self.show_heatmap(query)
            return
        if path == "/feedback":
            self.show_feedback(query)
            return
        if path == "/admin":
            self.show_admin(query)
            return
        if path == "/admin/login":
            self.show_admin_login(query)
            return
        if path == "/admin/logout":
            self.handle_admin_logout()
            return
        if path == "/admin/feedback":
            self.show_feedback_review(query)
            return
        self.send_html(render_not_found(), HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/analyze":
            self.handle_analyze()
            return
        if parsed.path == "/feedback":
            self.handle_feedback()
            return
        if parsed.path == "/admin/login":
            self.handle_admin_login()
            return
        if parsed.path == "/admin/review":
            self.handle_review()
            return
        self.send_html(render_not_found(), HTTPStatus.NOT_FOUND)

    def show_result(self, query: dict[str, list[str]]) -> None:
        result_id = first(query, "id")
        row = storage.get_result_detail(result_id)
        if not row:
            self.send_html(render_not_found("분석 결과를 찾을 수 없습니다."), HTTPStatus.NOT_FOUND)
            return
        self.send_html(render_result(row, first(query, "message"), first(query, "type") or "info"))

    def show_progress(self, query: dict[str, list[str]]) -> None:
        result_id = first(query, "id")
        if not storage.get_result_detail(result_id):
            self.send_html(render_not_found("분석 진행 정보를 찾을 수 없습니다."), HTTPStatus.NOT_FOUND)
            return
        self.send_html(render_progress(result_id))

    def show_heatmap(self, query: dict[str, list[str]]) -> None:
        result_id = first(query, "id")
        row = storage.get_result_detail(result_id)
        if not row:
            self.send_html(render_not_found("히트맵 정보를 찾을 수 없습니다."), HTTPStatus.NOT_FOUND)
            return
        self.send_html(render_heatmap(row))

    def show_feedback(self, query: dict[str, list[str]]) -> None:
        result_id = first(query, "id")
        row = feedback_controller.open_feedback_interface(result_id)
        if not row:
            self.send_html(render_not_found("피드백을 남길 분석 결과를 찾을 수 없습니다."), HTTPStatus.NOT_FOUND)
            return
        self.send_html(render_feedback(row, first(query, "message"), first(query, "type") or "info"))

    def show_admin(self, query: dict[str, list[str]]) -> None:
        if not self.is_admin_authenticated():
            self.redirect(redirect_url("/admin/login", {"message": "관리자 인증 후 접근할 수 있습니다.", "type": "error"}))
            return
        status = admin_controller.load_system_status()
        feedbacks = admin_controller.load_feedback_list()
        self.send_html(render_admin(status, feedbacks, first(query, "message"), first(query, "type") or "info"))

    def show_admin_login(self, query: dict[str, list[str]]) -> None:
        if self.is_admin_authenticated():
            self.redirect("/admin")
            return
        self.send_html(render_admin_login(first(query, "message"), first(query, "type") or "info"))

    def show_feedback_review(self, query: dict[str, list[str]]) -> None:
        if not self.is_admin_authenticated():
            self.redirect(redirect_url("/admin/login", {"message": "관리자 인증 후 접근할 수 있습니다.", "type": "error"}))
            return
        feedback_id = first(query, "id")
        row = admin_controller.load_feedback_detail(feedback_id)
        if not row:
            self.send_html(render_not_found("선택한 피드백 상세 정보를 찾을 수 없습니다."), HTTPStatus.NOT_FOUND)
            return
        self.send_html(render_feedback_review(row, first(query, "message"), first(query, "type") or "info"))

    def handle_analyze(self) -> None:
        fields, files = self.parse_form()
        image_input, error = analysis_controller.receive_image_input(files.get("image_file"), fields.get("image_url", ""))
        if error:
            self.send_html(render_index(error, "error"), HTTPStatus.BAD_REQUEST)
            return
        success, message, result_id = analysis_controller.start_detection(image_input)
        if not success or not result_id:
            self.send_html(render_index(message, "error"), HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.redirect(redirect_url("/progress", {"id": result_id}))

    def handle_feedback(self) -> None:
        fields, _files = self.parse_form()
        result_id = fields.get("result_id", "")
        success, message = feedback_controller.submit_feedback(
            result_id=result_id,
            feedback_type=fields.get("feedback_type", ""),
            comment=fields.get("comment", ""),
        )
        if not success:
            self.redirect(redirect_url("/feedback", {"id": result_id, "message": message, "type": "error"}))
            return
        self.redirect(redirect_url("/result", {"id": result_id, "message": message, "type": "success"}))

    def handle_admin_login(self) -> None:
        fields, _files = self.parse_form()
        password = fields.get("password", "")
        if not hmac.compare_digest(password, ADMIN_PASSWORD):
            self.send_html(render_admin_login("관리자 비밀번호가 올바르지 않습니다.", "error"), HTTPStatus.UNAUTHORIZED)
            return
        cookie = f"{ADMIN_COOKIE_NAME}={self.admin_cookie_value()}; HttpOnly; SameSite=Lax; Path=/admin"
        self.redirect("/admin", headers={"Set-Cookie": cookie})

    def handle_admin_logout(self) -> None:
        cookie = f"{ADMIN_COOKIE_NAME}=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/admin"
        self.redirect("/", headers={"Set-Cookie": cookie})

    def handle_review(self) -> None:
        if not self.is_admin_authenticated():
            self.redirect(redirect_url("/admin/login", {"message": "관리자 인증 후 접근할 수 있습니다.", "type": "error"}))
            return
        fields, _files = self.parse_form()
        feedback_id = fields.get("feedback_id", "")
        success, message = admin_controller.save_feedback_review(
            feedback_id=feedback_id,
            review_result=fields.get("review_result", ""),
            admin_comment=fields.get("admin_comment", ""),
        )
        target = "/admin/feedback" if not success else "/admin"
        params = {"message": message, "type": "success" if success else "error"}
        if not success:
            params["id"] = feedback_id
        self.redirect(redirect_url(target, params))

    def parse_form(self) -> tuple[dict[str, str], dict[str, dict]]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(content_length)
        content_type = self.headers.get("Content-Type", "")
        fields: dict[str, str] = {}
        files: dict[str, dict] = {}
        if content_type.startswith("multipart/form-data"):
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
            )
            for part in message.iter_parts():
                disposition = part.get("Content-Disposition", "")
                name = part.get_param("name", header="content-disposition")
                if not name or "form-data" not in disposition:
                    continue
                filename = part.get_filename()
                content = part.get_payload(decode=True) or b""
                if filename:
                    files[name] = {
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "content": content,
                    }
                else:
                    fields[name] = content.decode(part.get_content_charset() or "utf-8", errors="replace")
        else:
            parsed = parse_qs(body.decode("utf-8", errors="replace"))
            fields = {key: values[0] if values else "" for key, values in parsed.items()}
        return fields, files

    def serve_static(self, path: str, head_only: bool = False) -> None:
        root = Path.cwd()
        requested = root / unquote(path.lstrip("/"))
        try:
            resolved = requested.resolve()
            static_root = (root / "static").resolve()
            if static_root not in resolved.parents and resolved != static_root:
                raise FileNotFoundError
            if not resolved.is_file():
                raise FileNotFoundError
        except FileNotFoundError:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(resolved.stat().st_size))
        self.end_headers()
        if not head_only:
            self.wfile.write(resolved.read_bytes())

    def send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def is_admin_authenticated(self) -> bool:
        cookies = self.headers.get("Cookie", "")
        expected = self.admin_cookie_value()
        for chunk in cookies.split(";"):
            if "=" not in chunk:
                continue
            name, value = chunk.strip().split("=", 1)
            if name == ADMIN_COOKIE_NAME:
                return hmac.compare_digest(value, expected)
        return False

    def admin_cookie_value(self) -> str:
        digest = hmac.new(ADMIN_SECRET.encode("utf-8"), b"admin", hashlib.sha256).hexdigest()
        return f"admin.{digest}"

    def log_message(self, format: str, *args) -> None:
        print(f"[TrueLens] {self.address_string()} - {format % args}")


def first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, [""])
    return values[0] if values else ""


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), TrueLensHandler)
    print(f"TrueLens server running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    run()
