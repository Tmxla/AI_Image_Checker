import sqlite3
from pathlib import Path
from typing import Any, Optional

from models import (
    FeedbackReview,
    MisclassificationFeedback,
    SystemStatus,
    utc_now_iso,
)


class SQLiteStorage:
    def __init__(self, database_path: str = "data/truelens.db"):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_requests (
                    request_id TEXT PRIMARY KEY,
                    input_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    image_path TEXT,
                    image_url TEXT,
                    request_status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_message TEXT,
                    processing_time_ms INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS analysis_results (
                    result_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    ai_probability REAL NOT NULL,
                    result_label TEXT NOT NULL,
                    result_summary TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    heatmap_id TEXT NOT NULL,
                    heatmap_x INTEGER NOT NULL,
                    heatmap_y INTEGER NOT NULL,
                    heatmap_size INTEGER NOT NULL,
                    heatmap_description TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES analysis_requests(request_id)
                );

                CREATE TABLE IF NOT EXISTS misclassification_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    comment TEXT,
                    submitted_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY(result_id) REFERENCES analysis_results(result_id)
                );

                CREATE TABLE IF NOT EXISTS feedback_reviews (
                    review_id TEXT PRIMARY KEY,
                    feedback_id TEXT NOT NULL,
                    review_result TEXT NOT NULL,
                    admin_comment TEXT,
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY(feedback_id) REFERENCES misclassification_feedback(feedback_id)
                );
                """
            )

    def create_analysis_request(self, request: Any, source_name: str, image_path: Optional[str], image_url: Optional[str]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_requests (
                    request_id, input_type, source_name, image_path, image_url,
                    request_status, requested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.request_id,
                    request.image_input.input_type,
                    source_name,
                    image_path,
                    image_url,
                    request.request_status,
                    request.requested_at,
                ),
            )

    def save_analysis_result(self, result: Any, processing_time_ms: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_results (
                    result_id, request_id, ai_probability, result_label, result_summary,
                    completed_at, heatmap_id, heatmap_x, heatmap_y, heatmap_size,
                    heatmap_description, model_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    result.request_id,
                    result.ai_probability,
                    result.result_label,
                    result.result_summary,
                    result.completed_at,
                    result.heatmap.heatmap_id,
                    result.heatmap.heatmap_x,
                    result.heatmap.heatmap_y,
                    result.heatmap.heatmap_size,
                    result.heatmap.description,
                    result.model_version,
                ),
            )
            connection.execute(
                """
                UPDATE analysis_requests
                SET request_status = ?, completed_at = ?, processing_time_ms = ?
                WHERE request_id = ?
                """,
                ("completed", result.completed_at, processing_time_ms, result.request_id),
            )

    def mark_request_failed(self, request_id: str, message: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE analysis_requests
                SET request_status = ?, completed_at = ?, error_message = ?
                WHERE request_id = ?
                """,
                ("failed", utc_now_iso(), message, request_id),
            )

    def get_result_detail(self, result_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT
                    ar.*, res.*
                FROM analysis_results res
                JOIN analysis_requests ar ON ar.request_id = res.request_id
                WHERE res.result_id = ?
                """,
                (result_id,),
            ).fetchone()

    def save_feedback(self, feedback: MisclassificationFeedback) -> None:
        feedback.register_feedback()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO misclassification_feedback (
                    feedback_id, result_id, feedback_type, comment, submitted_at, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.feedback_id,
                    feedback.result_id,
                    feedback.feedback_type,
                    feedback.comment,
                    feedback.submitted_at,
                    feedback.status,
                ),
            )

    def list_feedbacks(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT
                    mf.*,
                    res.ai_probability,
                    res.result_label,
                    ar.source_name,
                    ar.image_path,
                    ar.image_url
                FROM misclassification_feedback mf
                JOIN analysis_results res ON res.result_id = mf.result_id
                JOIN analysis_requests ar ON ar.request_id = res.request_id
                ORDER BY mf.submitted_at DESC
                """
            ).fetchall()

    def get_feedback_detail(self, feedback_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT
                    mf.*,
                    res.ai_probability,
                    res.result_label,
                    res.result_summary,
                    ar.source_name,
                    ar.image_path,
                    ar.image_url,
                    fr.review_result,
                    fr.admin_comment,
                    fr.reviewed_at
                FROM misclassification_feedback mf
                JOIN analysis_results res ON res.result_id = mf.result_id
                JOIN analysis_requests ar ON ar.request_id = res.request_id
                LEFT JOIN feedback_reviews fr ON fr.feedback_id = mf.feedback_id
                WHERE mf.feedback_id = ?
                ORDER BY fr.reviewed_at DESC
                """,
                (feedback_id,),
            ).fetchone()

    def save_review(self, review: FeedbackReview) -> None:
        review.save_review()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback_reviews (
                    review_id, feedback_id, review_result, admin_comment, reviewed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.feedback_id,
                    review.review_result,
                    review.admin_comment,
                    review.reviewed_at,
                ),
            )
            connection.execute(
                """
                UPDATE misclassification_feedback
                SET status = ?
                WHERE feedback_id = ?
                """,
                ("검토 완료", review.feedback_id),
            )

    def get_system_status(self) -> SystemStatus:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    COALESCE(AVG(NULLIF(processing_time_ms, 0)), 0) AS average_processing_time,
                    SUM(CASE WHEN request_status = 'completed' THEN 1 ELSE 0 END) AS success_count,
                    SUM(CASE WHEN request_status = 'failed' THEN 1 ELSE 0 END) AS failure_count,
                    SUM(CASE WHEN request_status IN ('waiting', 'analyzing') THEN 1 ELSE 0 END) AS processing_count
                FROM analysis_requests
                WHERE date(requested_at) = date('now')
                """
            ).fetchone()
        processing_count = int(row["processing_count"] or 0)
        system_state = "정상 운영" if processing_count < 5 else "처리량 증가"
        return SystemStatus(
            daily_request_count=int(row["total_count"] or 0),
            average_processing_time=round((row["average_processing_time"] or 0) / 1000, 2),
            success_count=int(row["success_count"] or 0),
            failure_count=int(row["failure_count"] or 0),
            processing_count=processing_count,
            system_state=system_state,
        )
