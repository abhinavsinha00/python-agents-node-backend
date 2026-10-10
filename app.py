"""Local Flask dashboard for the deterministic AI development platform demo."""

from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template_string, request

from orchestrator import WorkflowOutcome, run_demo_mobile, run_demo_web
from state.project_state import ProjectState

app = Flask(__name__)
LOGGER = logging.getLogger(__name__)

def _serialize_state(state: ProjectState) -> dict:
    qa = state.qa_result
    review = state.review_result
    return {
        "project_type": state.project_type,
        "requirement": state.user_requirement,
        "current_agent": state.current_agent,
        "completed_agents": state.completed_agents,
        "final_status": state.final_status,
        "iteration": state.iteration,
        "qa_result": qa.model_dump() if qa else None,
        "review_result": review.model_dump() if review else None,
        "logs": state.logs,
        "deployment_ready": state.deployment_ready,
        "artifacts": state.artifacts,
    }


def _run_demo(requirement: str, platform: str) -> WorkflowOutcome:
    if platform == "mobile":
        outcome = run_demo_mobile()
    else:
        outcome = run_demo_web()
    outcome.state.user_requirement = requirement
    return outcome


def _display_stages(result: dict | None, platform: str = "web") -> list[str]:
    if platform == "mobile":
        return [
            "Mobile Requirement Agent",
            "Mobile Architecture Agent",
            "Mobile Developer Agent",
            "Mobile QA/Build Agent",
        ]
    stages = [
        "Requirement Agent",
        "Architecture Agent",
        "Developer Agent",
        "QA/Test Agent",
        "Code Review Agent",
    ]
    if result and result["review_result"] and result["review_result"].get("verdict") == "FAIL":
        stages.extend(["Bug Fix Agent", "QA/Test Agent"])
    stages.append("Deployment/Documentation Agent")
    return stages


@app.get("/")
def index():
    return render_template_string(
        TEMPLATE,
        platform="web",
        requirement="",
        result=None,
        stages=_display_stages(None),
        error=None,
    )


@app.post("/demo")
def demo():
    requirement = request.form.get("requirement", "").strip()
    platform = request.form.get("platform", "web").strip().lower()
    if platform not in {"web", "mobile"}:
        platform = "web"
    if not requirement:
        return render_template_string(
            TEMPLATE,
            platform=platform,
            requirement=requirement,
            result=None,
            stages=_display_stages(None, platform),
            error="Enter a project requirement before starting the demo.",
        ), 400

    try:
        outcome = _run_demo(requirement, platform)
        serialized = _serialize_state(outcome.state)
        return render_template_string(
            TEMPLATE,
            platform=platform,
            requirement=requirement,
            result=serialized,
            stages=_display_stages(serialized, platform),
            error=None,
        )
    except Exception:
        LOGGER.exception("Deterministic dashboard demo failed")
        return render_template_string(
            TEMPLATE,
            platform=platform,
            requirement=requirement,
            result=None,
            stages=_display_stages(None, platform),
            error="Demo execution failed. Check the local application log for details.",
        ), 500


@app.get("/api/status")
def api_status():
    return jsonify({"mode": "demo", "external_api": False})


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI DevFlow — Local Agent Demo</title>
  <style>
    :root { color-scheme: light; --ink:#172033; --muted:#617087; --line:#dce3ee; --accent:#5b5fe9; --success:#16896a; --warn:#a96c00; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Inter,system-ui,sans-serif; color:var(--ink); background:#f5f7fb; }
    header { background:#172033; color:white; padding:28px 5vw; }
    header h1 { margin:0 0 8px; font-size:clamp(1.7rem,4vw,2.7rem); }
    header p { margin:0; color:#c7d0e0; }
    main { max-width:1150px; margin:0 auto; padding:32px 5vw 56px; }
    .grid { display:grid; grid-template-columns:1fr 1.1fr; gap:24px; }
    .card { background:white; border:1px solid var(--line); border-radius:16px; padding:22px; box-shadow:0 12px 32px rgba(24,36,64,.06); }
    h2 { margin:0 0 18px; font-size:1.15rem; }
    label { display:block; font-weight:700; margin-bottom:8px; }
    textarea, select { width:100%; border:1px solid #b9c4d5; border-radius:10px; padding:12px; font:inherit; background:white; }
    textarea { min-height:110px; resize:vertical; }
    .radio { display:flex; gap:12px; margin:14px 0 20px; }
    .radio label { margin:0; }
    .radio input { accent-color:var(--accent); }
    button { border:0; border-radius:10px; background:var(--accent); color:white; font-weight:700; padding:12px 18px; cursor:pointer; }
    button:hover { filter:brightness(1.08); }
    .status { display:inline-flex; align-items:center; gap:8px; padding:7px 11px; border-radius:999px; background:#eef1ff; color:#4b4fd1; font-weight:700; text-transform:capitalize; }
    .status.failed { background:#fff0ed; color:#b43b2d; }
    .stage-list { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin:0; padding:0; list-style:none; }
    .stage { border:1px solid var(--line); border-radius:10px; padding:12px; background:#fafbfe; }
    .stage.done { border-color:#9fd8c7; background:#f0fbf7; }
    .stage.active { border-color:#8589ef; background:#f2f3ff; box-shadow:inset 4px 0 var(--accent); }
    .stage small { color:var(--muted); display:block; margin-top:4px; }
    .result-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; margin:16px 0; }
    .metric { border:1px solid var(--line); border-radius:10px; padding:13px; }
    .metric strong { display:block; margin-top:5px; }
    .log { margin:0; background:#11182a; color:#dce7fb; border-radius:10px; padding:14px; overflow:auto; max-height:300px; font:13px/1.5 ui-monospace,monospace; }
    .error { color:#b43b2d; font-weight:700; }
    .notice { color:var(--muted); font-size:.92rem; line-height:1.5; }
    @media (max-width:760px) { .grid { grid-template-columns:1fr; } .stage-list { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>AI DevFlow</h1>
    <p>Deterministic local platform for web and mobile development workflows.</p>
  </header>
  <main>
    <div class="grid">
      <section class="card">
        <h2>Start a Demo</h2>
        <form method="post" action="/demo">
          <label for="requirement">Project requirement</label>
          <textarea id="requirement" name="requirement" placeholder="For example: Build a task manager for a small team">{{ requirement }}</textarea>
          <label>Platform</label>
          <div class="radio">
            <label><input type="radio" name="platform" value="web" {% if platform == "web" %}checked{% endif %}> Web</label>
            <label><input type="radio" name="platform" value="mobile" {% if platform == "mobile" %}checked{% endif %}> Mobile</label>
          </div>
          <button type="submit">Run deterministic demo</button>
        </form>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <p class="notice">No LLM or external API calls. Web uses the existing workflow; Mobile uses React Native/Expo architecture and local validation only.</p>
      </section>

      <section class="card">
        <h2>Workflow status</h2>
        {% if result %}
          <span class="status {{ result.final_status }}">{{ result.final_status }}</span>
          <div class="result-grid">
            <div class="metric">Current agent<strong>{{ result.current_agent or "None" }}</strong></div>
            <div class="metric">Iteration<strong>{{ result.iteration }}</strong></div>
            <div class="metric">QA result<strong>{{ result.qa_result.status if result.qa_result else "Not run" }}</strong></div>
            <div class="metric">Review result<strong>{{ result.review_result.verdict if result.review_result else "Not run" }}</strong></div>
          </div>
          <ul class="stage-list">
            {% for stage in stages %}
              <li class="stage {{ 'done' if stage in result.completed_agents else '' }} {{ 'active' if stage == result.current_agent else '' }}">
                {{ stage }}{% if stage in result.completed_agents %}<small>Completed</small>{% elif stage == result.current_agent %}<small>Running</small>{% endif %}
              </li>
            {% endfor %}
          </ul>
        {% else %}
          <p class="notice">Submit a requirement to view the workflow state and structured results.</p>
        {% endif %}
      </section>
    </div>

    {% if result %}
      <section class="card" style="margin-top:24px">
        <h2>Agent execution log</h2>
        <pre class="log">{% for line in result.logs %}- {{ line }}
{% endfor %}</pre>
      </section>
    {% endif %}
  </main>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
