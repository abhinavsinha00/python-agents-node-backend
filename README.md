# AI DevFlow

AI DevFlow is a Python application that demonstrates staged Web and Mobile software development with CrewAI agents and a deterministic local demo mode.

## What It Does

The project decomposes a user requirement into planned work, implementation, and validation stages. Web and Mobile roles are defined separately, while a central orchestrator owns deterministic demo execution and Web recovery decisions.

## Architecture

- `agents/` contains the Web and Mobile role factories.
- `workflows/` constructs CrewAI tasks for each platform.
- `orchestrator.py` coordinates deterministic stage execution and bounded Web recovery.
- `schemas/` defines structured stage results.
- `state/` holds serializable project workflow state.
- `providers/llm_config.py` configures the default OpenAI-compatible LLM client.
- `tools/` contains constrained file and command tools.
- `app.py` is the local deterministic Flask dashboard.

## Agents

Web roles are Requirement, Architecture, Developer, QA/Test, Code Review, Bug Fix, and Deployment/Documentation. Mobile roles are Mobile Requirement, Mobile Architecture, Mobile Developer, and Mobile QA/Build. Mobile app-store deployment is not implemented.

## Web Workflow

Requirement -> Architecture -> Developer -> QA -> Code Review -> Fix if needed -> QA retest -> final documentation.

The real Web task crew is an opt-in entry point. The current CrewAI crew executes Requirement, Architecture, Developer, QA, and Code Review sequentially. Deterministic orchestrator demos remain separate and do not call an LLM.

## Mobile Workflow

Mobile Requirement -> Mobile Architecture -> Mobile Developer -> Mobile QA/Build -> final.

The included generated example is an Expo/React Native Todo project. Local validation is recorded in its report; native Expo prebuild requires its dependencies to be installed.

## Technology

Python, CrewAI, LiteLLM, Pydantic, Flask, React Native, Expo, and AsyncStorage.

## Configure the LLM

The default provider uses `TARGET_URL` and `TARGET_MODEL`, configured in `.env` or the process environment. Defaults target the instructor's OpenAI-compatible endpoint with model `ethos-6`. Copy `.env.example` to `.env` and adjust values only as needed. Never commit local credentials.

## Run the Dashboard

```powershell
cd "C:\Users\prath\Downloads\ai_dev_agents (2)"
.\.venv\Scripts\Activate.ps1
python app.py
```

Open `http://127.0.0.1:5000/`. The dashboard executes deterministic Web or Mobile demo stages and makes no provider calls.

## Run Demo Mode

```powershell
python demo_mode.py
```

## Run the Interactive CLI

```powershell
python run.py
```

The CLI asks for `web` or `mobile`, then a requirement. It creates a new project directory beneath `output/`. Use `python run.py --demo` to exercise only deterministic stages.

Opt-in single-request connectivity and Code Review diagnostics are under `tests/`; only run the endpoint tests when you intend to contact the configured service.

## Generated Applications

Generated projects are stored under `output/`. For a generated Flask application, change to its project directory and run `python -m flask --app app run --host 127.0.0.1 --port 5001` (choose an unused local port as needed). Static projects can be opened using their `index.html`.

## Limitations

- Real CrewAI workflows require access to the configured compatible endpoint and may be affected by endpoint-specific model capabilities.
- The workspace has no Git metadata, so tracked-file status cannot be verified here.
- The QA-passing static Counter demo is retained at `output/web-build-a-simple-counter-website/`; an alternate static variation is in `examples/alternate-counter/`.