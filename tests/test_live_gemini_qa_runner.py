"""Run deterministic behavioral checks against the local Flask Todo app."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
APP_PATH = PROJECT_DIR / "app.py"


@contextmanager
def database_connection(path: Path):
    connection = sqlite3.connect(path)
    try:
        yield connection
    finally:
        connection.close()


def run_checks(run_id: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("run id must be a 32-character hexadecimal UUID")

    database_path = PROJECT_DIR / f".qa-{run_id}.sqlite3"
    result_path = PROJECT_DIR / f".qa-result-{run_id}.json"
    details: list[dict[str, str]] = []
    cleanup_warnings: list[str] = []

    def record(name: str, passed: bool, evidence: str) -> None:
        details.append(
            {"name": name, "status": "PASS" if passed else "FAIL", "evidence": evidence}
        )

    try:
        sys.path.insert(0, str(PROJECT_DIR))
        import app as module

        module.DB_NAME = str(database_path)
        module.app.config.update(TESTING=True)
        module.init_db()
        client = module.app.test_client()

        homepage = client.get("/")
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"', homepage.data
        )
        csrf_token = token_match.group(1).decode("ascii") if token_match else ""
        record(
            "Homepage loads",
            homepage.status_code == 200 and bool(csrf_token),
            f"GET / returned HTTP {homepage.status_code}; CSRF form token present={bool(csrf_token)}",
        )

        add_response = client.post(
            "/add",
            data={"title": "QA task", "csrf_token": csrf_token},
            follow_redirects=True,
        )
        with database_connection(database_path) as connection:
            task_row = connection.execute(
                "SELECT id, completed FROM tasks WHERE title = ?", ("QA task",)
            ).fetchone()
        record(
            "Add task",
            add_response.status_code == 200
            and b"QA task" in add_response.data
            and task_row is not None,
            f"POST /add returned HTTP {add_response.status_code}; task persisted={task_row is not None}",
        )

        task_id = task_row[0] if task_row else -1
        complete_response = client.post(
            f"/toggle/{task_id}", data={"csrf_token": csrf_token}, follow_redirects=True
        )
        with database_connection(database_path) as connection:
            completed_row = connection.execute(
                "SELECT completed FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        record(
            "Mark task complete",
            complete_response.status_code == 200
            and completed_row is not None
            and completed_row[0] == 1,
            f"POST /toggle/{task_id} returned HTTP {complete_response.status_code}; completed={completed_row[0] if completed_row else None}",
        )

        delete_response = client.post(
            f"/delete/{task_id}", data={"csrf_token": csrf_token}, follow_redirects=True
        )
        with database_connection(database_path) as connection:
            deleted_row = connection.execute(
                "SELECT id FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        record(
            "Delete task",
            delete_response.status_code == 200 and deleted_row is None,
            f"POST /delete/{task_id} returned HTTP {delete_response.status_code}; task absent={deleted_row is None}",
        )

        client.post(
            "/add",
            data={"title": "Persistent task", "csrf_token": csrf_token},
            follow_redirects=True,
        )
        fresh_client_response = module.app.test_client().get("/")
        with database_connection(database_path) as connection:
            persistent_row = connection.execute(
                "SELECT id FROM tasks WHERE title = ?", ("Persistent task",)
            ).fetchone()
        record(
            "SQLite persistence",
            persistent_row is not None
            and fresh_client_response.status_code == 200
            and b"Persistent task" in fresh_client_response.data,
            f"task survived separate requests and was visible in a fresh client={persistent_row is not None and b'Persistent task' in fresh_client_response.data}",
        )

        invalid_csrf = client.post("/add", data={"title": "Rejected", "csrf_token": "bad"})
        blank_title = client.post(
            "/add", data={"title": "   ", "csrf_token": csrf_token}
        )
        get_mutation = client.get(f"/delete/{persistent_row[0] if persistent_row else 1}")
        with database_connection(database_path) as connection:
            rejected_count = connection.execute(
                "SELECT COUNT(*) FROM tasks WHERE title = 'Rejected' OR title = ''"
            ).fetchone()[0]
        record(
            "Basic error handling",
            invalid_csrf.status_code == 400
            and blank_title.status_code == 302
            and get_mutation.status_code == 405
            and rejected_count == 0,
            f"invalid CSRF={invalid_csrf.status_code}, blank title={blank_title.status_code}, GET mutation={get_mutation.status_code}, rejected rows={rejected_count}",
        )
    except Exception as exc:
        record("QA runner setup", False, f"{type(exc).__name__}: {exc}")
    finally:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(database_path) + suffix)
            try:
                candidate.unlink(missing_ok=True)
            except OSError as exc:
                cleanup_warnings.append(f"Could not remove {candidate.name}: {exc}")

    failed = sum(item["status"] == "FAIL" for item in details)
    result = {
        "status": "pass" if len(details) == 6 and failed == 0 else "fail",
        "tests_passed": len(details) - failed,
        "tests_failed": failed,
        "test_details": details,
        "defects": [item["evidence"] for item in details if item["status"] == "FAIL"],
        "recommendations": [],
        "cleanup_warnings": cleanup_warnings,
    }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: qa_runner.py <32-character-run-id>")
    run_checks(sys.argv[1])