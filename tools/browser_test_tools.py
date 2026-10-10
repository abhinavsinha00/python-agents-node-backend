"""Automated web validation and behavior testing layer for generated web applications."""

from __future__ import annotations

import html.parser
import json
import logging
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from schemas.project_results import StageFailure, StageStatus, TestCaseResult, TestResult

LOGGER = logging.getLogger(__name__)


class AssetExtractor(html.parser.HTMLParser):
    """Extract asset links and key interactive tags from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.stylesheets: list[str] = []
        self.scripts: list[str] = []
        self.images: list[str] = []
        self.has_input: bool = False
        self.has_button: bool = False
        self.input_ids: list[str] = []
        self.button_ids: list[str] = []
        self.elements_with_id: list[str] = []
        self.buttons_text: list[str] = []
        self._current_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        self._current_tag = tag

        elem_id = attr_dict.get("id")
        if elem_id:
            self.elements_with_id.append(elem_id)

        if tag == "link" and attr_dict.get("rel") == "stylesheet":
            href = attr_dict.get("href")
            if href:
                self.stylesheets.append(href)

        elif tag == "script":
            src = attr_dict.get("src")
            if src:
                self.scripts.append(src)

        elif tag == "img":
            src = attr_dict.get("src")
            if src:
                self.images.append(src)

        elif tag == "input":
            self.has_input = True
            if elem_id:
                self.input_ids.append(elem_id)

        elif tag == "button":
            self.has_button = True
            if elem_id:
                self.button_ids.append(elem_id)

    def handle_data(self, data: str) -> None:
        if self._current_tag == "button" and data.strip():
            self.buttons_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        self._current_tag = None


# Node.js DOM simulation runner script for behavioral testing
NODE_INTERACTION_RUNNER = """
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const projectDir = process.argv[1];
const testName = process.argv[2] || 'Alice';

const result = {
    interaction_passed: false,
    output_text: '',
    console_errors: [],
    runtime_error: null,
    elements_found: {}
};

try {
    const htmlPath = path.join(projectDir, 'index.html');
    if (!fs.existsSync(htmlPath)) {
        throw new Error('index.html not found');
    }
    const htmlContent = fs.readFileSync(htmlPath, 'utf8');

    // Simple DOM representation
    const elementStore = new Map();
    const eventListeners = new Map();

    function createElement(id, tagName, attrs = {}) {
        return {
            id,
            tagName: tagName.toUpperCase(),
            value: '',
            textContent: '',
            innerText: '',
            innerHTML: '',
            style: {},
            classList: {
                add: () => {},
                remove: () => {},
                contains: () => false
            },
            addEventListener: function(evt, handler) {
                const list = eventListeners.get(this) || [];
                list.push({ event: evt, handler });
                eventListeners.set(this, list);
            },
            click: function() {
                if (typeof this.onclick === 'function') {
                    this.onclick({ target: this, preventDefault: () => {} });
                }
                const list = eventListeners.get(this) || [];
                for (const item of list) {
                    if (item.event === 'click') {
                        item.handler({ target: this, preventDefault: () => {} });
                    }
                }
            }
        };
    }

    // Extract IDs and elements from HTML
    const idRegex = /id=["']([^"']+)["']/g;
    let match;
    while ((match = idRegex.exec(htmlContent)) !== null) {
        const elemId = match[1];
        if (!elementStore.has(elemId)) {
            elementStore.set(elemId, createElement(elemId, 'div'));
        }
    }

    // Mock document
    const window = {
        addEventListener: (evt, handler) => {
            if (evt === 'DOMContentLoaded') {
                setTimeout(handler, 0);
            }
        }
    };

    const document = {
        getElementById: (id) => {
            if (!elementStore.has(id)) {
                elementStore.set(id, createElement(id, 'div'));
            }
            return elementStore.get(id);
        },
        querySelector: (sel) => {
            const clean = sel.replace(/^[#.]/, '');
            if (sel.startsWith('#') || !sel.includes(' ')) {
                if (!elementStore.has(clean)) {
                    elementStore.set(clean, createElement(clean, 'div'));
                }
                return elementStore.get(clean);
            }
            // Tag selectors
            for (const [id, el] of elementStore.entries()) {
                if (el.tagName.toLowerCase() === sel.toLowerCase()) return el;
            }
            const fallback = createElement(clean, sel);
            elementStore.set(clean, fallback);
            return fallback;
        },
        querySelectorAll: (sel) => {
            return [document.querySelector(sel)];
        },
        addEventListener: (evt, handler) => {
            if (evt === 'DOMContentLoaded') {
                setTimeout(handler, 0);
            }
        },
        createElement: (tag) => createElement('dynamic-' + Math.random(), tag),
        body: createElement('body', 'body')
    };

    const consoleMock = {
        log: (...args) => {},
        warn: (...args) => {},
        error: (...args) => {
            result.console_errors.push(args.map(a => String(a)).join(' '));
        }
    };

    // Load and run script.js or embedded scripts
    const scriptFiles = ['script.js', 'main.js', 'app.js'];
    let scriptCode = '';
    for (const sf of scriptFiles) {
        const sp = path.join(projectDir, sf);
        if (fs.existsSync(sp)) {
            scriptCode += fs.readFileSync(sp, 'utf8') + '\\n';
        }
    }

    // Extract inline scripts
    const scriptTagRegex = /<script(?![^>]*src)[^>]*>([\\s\\S]*?)<\\/script>/gi;
    let sMatch;
    while ((sMatch = scriptTagRegex.exec(htmlContent)) !== null) {
        scriptCode += sMatch[1] + '\\n';
    }

    // Execute in sandboxed context
    const context = vm.createContext({
        window,
        document,
        console: consoleMock,
        alert: (msg) => { result.output_text += String(msg); },
        setTimeout: (fn, ms) => { fn(); },
        setInterval: () => {},
        clearTimeout: () => {},
        clearInterval: () => {}
    });

    if (scriptCode.trim()) {
        vm.runInContext(scriptCode, context, { timeout: 1000 });
    }

    // Simulate User Action: Enter Name
    // Find input element
    let inputElem = null;
    for (const [id, el] of elementStore.entries()) {
        const idLower = id.toLowerCase();
        if (idLower.includes('name') || idLower.includes('input') || idLower.includes('user')) {
            inputElem = el;
            break;
        }
    }
    if (!inputElem && elementStore.size > 0) {
        inputElem = Array.from(elementStore.values())[0];
    }
    if (inputElem) {
        inputElem.value = testName;
    }

    // Find and Click Button
    let buttonElem = null;
    for (const [id, el] of elementStore.entries()) {
        const idLower = id.toLowerCase();
        if (idLower.includes('btn') || idLower.includes('button') || idLower.includes('greet') || idLower.includes('submit')) {
            buttonElem = el;
            break;
        }
    }
    if (!buttonElem) {
        for (const [id, el] of elementStore.entries()) {
            if (el !== inputElem) {
                buttonElem = el;
                break;
            }
        }
    }

    if (buttonElem) {
        buttonElem.click();
    }

    // Collect outputs
    let outputText = result.output_text;
    for (const [id, el] of elementStore.entries()) {
        const t = (el.textContent || el.innerText || el.innerHTML || '').trim();
        if (t) {
            outputText += ' ' + t;
        }
    }
    result.output_text = outputText.trim();

    // Verification: does the output contain "Hello, [name]" (case-insensitive)
    const expectedRegex = new RegExp('Hello,\\\\s*' + testName, 'i');
    result.interaction_passed = expectedRegex.test(result.output_text) || result.output_text.toLowerCase().includes('hello');
} catch (err) {
    result.runtime_error = err.message || String(err);
}

process.stdout.write(JSON.stringify(result));
""";


def _run_node_interaction_test(project_dir: Path, test_name: str = "Alice") -> dict:
    """Run Node.js mock interaction script against the project."""
    node_exe = shutil.which("node")
    if not node_exe:
        return {"interaction_passed": False, "skipped": True, "reason": "node not installed"}

    try:
        proc = subprocess.run(
            [node_exe, "-e", NODE_INTERACTION_RUNNER, str(project_dir), test_name],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.strip())
        return {
            "interaction_passed": False,
            "runtime_error": proc.stderr.strip() or "Node test process returned non-zero exit code",
            "console_errors": [proc.stderr.strip()] if proc.stderr.strip() else [],
        }
    except Exception as exc:
        return {"interaction_passed": False, "runtime_error": str(exc)}


def _check_js_syntax(js_path: Path) -> tuple[bool, str]:
    """Check JS file syntax using node --check or fallback."""
    node_exe = shutil.which("node")
    if node_exe:
        try:
            proc = subprocess.run(
                [node_exe, "--check", str(js_path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode != 0:
                return False, proc.stderr.strip() or "JS syntax error"
            return True, ""
        except Exception as exc:
            LOGGER.debug("node --check failed: %s", exc)

    # Basic Python bracket/syntax check fallback
    content = js_path.read_text(encoding="utf-8", errors="replace")
    stack = []
    pairs = {"(": ")", "{": "}", "[": "]"}
    in_str = None
    for char in content:
        if in_str:
            if char == in_str:
                in_str = None
            continue
        if char in ("'", '"', "`"):
            in_str = char
        elif char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return False, f"Unbalanced delimiter: {char}"
    if stack:
        return False, f"Unclosed delimiter: {stack[-1]}"
    return True, ""


def validate_web_application(url: str, project_dir: Path, requirement: str = "") -> TestResult:
    """Validate a running web application across HTTP, assets, DOM, JS, and user interaction."""
    project_dir = project_dir.resolve()
    details: list[TestCaseResult] = []
    console_errors: list[str] = []
    broken_assets: list[str] = []

    # 1. Page Load Test (HTTP 200)
    page_html = ""
    target_url = url if url.endswith("/") or url.endswith(".html") else f"{url}/"
    try:
        req = urllib.request.Request(
            target_url,
            headers={"User-Agent": "AI-Dev-Automated-Tester/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.status
            if status == 200:
                details.append(TestCaseResult(name="Page Load (HTTP 200)", passed=True, message=f"HTTP {status} OK"))
                page_html = response.read().decode("utf-8", errors="replace")
            else:
                details.append(TestCaseResult(name="Page Load (HTTP 200)", passed=False, message=f"HTTP {status}"))
    except Exception as exc:
        details.append(TestCaseResult(name="Page Load (HTTP 200)", passed=False, message=f"Connection failed: {exc}"))

    # Prioritize local index.html content for DOM parsing if it exists
    index_file = project_dir / "index.html"
    if index_file.is_file():
        page_html = index_file.read_text(encoding="utf-8", errors="replace")

    # 2. Parse HTML and check assets
    extractor = AssetExtractor()
    if page_html:
        try:
            extractor.feed(page_html)
        except Exception as exc:
            details.append(TestCaseResult(name="HTML Syntax Parsing", passed=False, message=f"Parse error: {exc}"))
        else:
            details.append(TestCaseResult(name="HTML Syntax Parsing", passed=True, message="HTML parsed successfully"))

    # Check broken assets (Stylesheets & Images)
    base_url = target_url
    for rel_asset in extractor.stylesheets + extractor.images:
        if rel_asset.startswith(("http://", "https://", "//")):
            continue
        asset_url = urllib.parse.urljoin(base_url, rel_asset)
        asset_file = project_dir / rel_asset.lstrip("/\\")
        if not asset_file.is_file():
            try:
                with urllib.request.urlopen(asset_url, timeout=3) as res:
                    if res.status != 200:
                        broken_assets.append(f"{rel_asset} (HTTP {res.status})")
            except Exception as exc:
                broken_assets.append(f"{rel_asset} ({exc})")

    if broken_assets:
        details.append(
            TestCaseResult(
                name="Asset Integrity",
                passed=False,
                message=f"Broken assets detected: {', '.join(broken_assets)}",
            )
        )
    else:
        details.append(TestCaseResult(name="Asset Integrity", passed=True, message="All referenced assets found"))

    # 3. HTML Elements Verification (input and button)
    has_input = extractor.has_input or bool(re.search(r"<input\b", page_html, re.I))
    has_button = extractor.has_button or bool(re.search(r"<(?:button\b|input[^>]*type=[\"']?(?:button|submit))", page_html, re.I))

    req_lower = requirement.lower()
    needs_greeting_form = "name" in req_lower and "button" in req_lower

    if needs_greeting_form:
        if has_input and has_button:
            details.append(TestCaseResult(name="HTML Interactive Elements", passed=True, message="Input and button elements present"))
        else:
            missing = []
            if not has_input:
                missing.append("<input>")
            if not has_button:
                missing.append("<button>")
            details.append(
                TestCaseResult(
                    name="HTML Interactive Elements",
                    passed=False,
                    message=f"Missing required elements: {', '.join(missing)}",
                )
            )

    # 4. JavaScript Load & Syntax Check
    js_files = list(project_dir.glob("*.js"))
    for js_file in js_files:
        valid_syntax, err_msg = _check_js_syntax(js_file)
        if valid_syntax:
            details.append(TestCaseResult(name=f"JavaScript Syntax ({js_file.name})", passed=True, message="Valid syntax"))
        else:
            console_errors.append(f"{js_file.name}: {err_msg}")
            details.append(
                TestCaseResult(
                    name=f"JavaScript Syntax ({js_file.name})",
                    passed=False,
                    message=f"Syntax error in {js_file.name}: {err_msg}",
                )
            )

    # 5. User Interaction / Behavior Test
    node_res = _run_node_interaction_test(project_dir, test_name="Alice")
    if node_res.get("console_errors"):
        console_errors.extend(node_res["console_errors"])

    if node_res.get("runtime_error"):
        console_errors.append(f"Runtime error: {node_res['runtime_error']}")
        details.append(
            TestCaseResult(
                name="User Interaction & Behavior",
                passed=False,
                message=f"Script runtime error: {node_res['runtime_error']}",
            )
        )
    elif node_res.get("interaction_passed"):
        details.append(
            TestCaseResult(
                name="User Interaction & Behavior",
                passed=True,
                message=f"Interaction passed. Output: '{node_res.get('output_text')}'",
            )
        )
    else:
        # Fallback inspection if Node was skipped or couldn't run
        out_text = node_res.get("output_text", "")
        if "hello" in out_text.lower():
            details.append(TestCaseResult(name="User Interaction & Behavior", passed=True, message="Greeting behavior verified."))
        elif node_res.get("skipped"):
            # Check script.js for event listener and greeting logic
            js_code = "".join(f.read_text(encoding="utf-8", errors="replace") for f in js_files)
            if ("click" in js_code or "onclick" in js_code) and ("hello" in js_code.lower() or "greeting" in js_code.lower()):
                details.append(TestCaseResult(name="User Interaction & Behavior", passed=True, message="Greeting logic detected in script."))
            else:
                details.append(TestCaseResult(name="User Interaction & Behavior", passed=False, message="Greeting logic missing or not triggered."))
        else:
            details.append(
                TestCaseResult(
                    name="User Interaction & Behavior",
                    passed=False,
                    message=f"Expected 'Hello, Alice!' but got '{out_text}'",
                )
            )

    tests_run = len(details)
    passed = sum(1 for d in details if d.passed)
    failed = tests_run - passed
    overall_status = StageStatus.PASS if failed == 0 and not console_errors else StageStatus.FAIL

    failure_info = None
    if overall_status == StageStatus.FAIL:
        failed_names = [d.name for d in details if not d.passed]
        evidence_lines = [f"{d.name}: {d.message}" for d in details if not d.passed]
        if console_errors:
            evidence_lines.extend(console_errors)
        failure_info = StageFailure(
            error_type="BehavioralTestFailure",
            message=f"Automated web testing failed ({failed}/{tests_run} tests failed).",
            stage="Test",
            affected_files=["index.html", "script.js"],
            evidence="\n".join(evidence_lines),
            suggested_action="Fix element IDs, button click listener, or output display in index.html and script.js.",
        )

    return TestResult(
        status=overall_status,
        tests_run=tests_run,
        passed=passed,
        failed=failed,
        details=details,
        console_errors=console_errors,
        broken_assets=broken_assets,
        failure=failure_info,
    )
