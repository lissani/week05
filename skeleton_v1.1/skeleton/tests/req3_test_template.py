"""
requirement_3.md 최종 검증 및 Report 생성 스크립트 (TE용)

로컬 실행
---------
    # skeleton 프로젝트 루트에서
    python tests/req3_test_template.py

작성자 이름을 Report에 넣으려면 `--author "홍길동"`을 추가하세요.

GitHub Actions와 Render까지 포함한 최종 검증
--------------------------------------------
    python tests/req3_test_template.py \
        --author "홍길동" \
        --ci-run-url "https://github.com/OWNER/REPO/actions/runs/RUN_ID" \
        --render-url "https://SERVICE.onrender.com"

비공개 GitHub 저장소의 Actions 실행을 확인할 때는 API 접근 권한이 있는 토큰을
`GITHUB_TOKEN` 환경 변수로 전달할 수 있습니다.

결과
----
    tests/reports/req3_report_template.md

검증 범위
---------
  * 요구사항 #1~#2 핵심 API 회귀 테스트
  * requirement_3의 상태 Badge 9개 TE 시나리오
  * GitHub Actions 워크플로우 정적 검사 및 CI와 같은 로컬 API 검사
  * 공개 GitHub Actions 실행 결과와 Render 배포 URL 검사(옵션)

주의
----
외부 URL을 주지 않은 항목은 성공으로 간주하지 않고 NOT RUN으로 기록합니다.
Badge 함수의 실제 반환값 검증에는 Node.js가 필요합니다. 별도 Python 패키지는
사용하지 않습니다.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)


def find_repository_root(start_path):
    """현재 앱이 하위 폴더에 있어도 실제 Git 저장소 루트를 찾는다."""
    current = os.path.abspath(start_path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return start_path
        current = parent


REPOSITORY_ROOT = find_repository_root(PROJECT_ROOT)
REPORT_DIR = os.path.join(THIS_DIR, "reports")
REPORT_PATH = os.path.join(REPORT_DIR, "req3_report_template.md")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "app.js")
STYLE_CSS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "style.css")
CI_PATH = os.path.join(REPOSITORY_ROOT, ".github", "workflows", "ci.yml")
DEFAULT_RENDER_URL = "https://week05-6i8g.onrender.com/"

LOCAL_BASE_URL = None
results = []

BADGE_EXPECTATIONS = {
    "Active": "badge status-active",
    "Online": "badge status-active",
    "Normal": "badge status-active",
    "Paused": "badge status-paused",
    "Standby": "badge status-paused",
    "Expired": "badge status-expired",
    "Error": "badge status-expired",
    "Warning": "badge status-expired",
    "Offline": "badge status-offline",
    "On": "badge status-on",
    "Cleaning": "badge status-on",
    "Off": "badge status-off",
    "Unknown": "badge",
    "": "badge",
    None: "badge",
}

CSS_COLORS = {
    "status-active": ("#dcfce7", "#166534", "초록"),
    "status-paused": ("#e0e7ff", "#3730a3", "파랑"),
    "status-expired": ("#fee2e2", "#991b1b", "빨강"),
    "status-offline": ("#e5e7eb", "#374151", "회색"),
    "status-on": ("#fef3c7", "#92400e", "노랑"),
    "status-off": ("#f3f4f6", "#4b5563", "연회색"),
}


def parse_args():
    parser = argparse.ArgumentParser(description="requirement_3 최종 검증 Report 생성")
    parser.add_argument("--author", default=os.getenv("REPORT_AUTHOR", "(이름 미입력)"))
    parser.add_argument("--ci-run-url", default=os.getenv("CI_RUN_URL", ""))
    parser.add_argument(
        "--render-url", default=os.getenv("RENDER_URL", DEFAULT_RENDER_URL)
    )
    return parser.parse_args()


def check(tc_id, requirement, scenario, expected, actual, status):
    """PASS, FAIL, NOT RUN 중 하나로 검증 결과를 기록한다."""
    if isinstance(status, bool):
        status = "PASS" if status else "FAIL"
    if status not in {"PASS", "FAIL", "NOT RUN"}:
        raise ValueError(f"지원하지 않는 판정: {status}")
    results.append((tc_id, requirement, scenario, expected, actual, status))
    print(f"  [{status}] {tc_id}  {scenario}")


def read_text(path):
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except OSError:
        return ""


def extract_js_function(source, function_name):
    """문자열 안의 중괄호를 제외하며 JavaScript 함수 하나를 추출한다."""
    match = re.search(rf"\bfunction\s+{re.escape(function_name)}\s*\(", source)
    if not match:
        return ""
    opening = source.find("{", match.end())
    if opening < 0:
        return ""

    depth = 0
    quote = None
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():index + 1]
    return ""


def evaluate_badge_function(function_source):
    """app.js의 badgeClass를 Node.js에서 실행해 상태별 실제 반환값을 얻는다."""
    node = shutil.which("node")
    if not node:
        return None, "Node.js를 찾을 수 없음"
    if not function_source:
        return None, "badgeClass 함수를 찾을 수 없음"

    values = list(BADGE_EXPECTATIONS)
    script = (
        '"use strict";\n'
        + function_source
        + "\nconst values = "
        + json.dumps(values, ensure_ascii=False)
        + ";\nprocess.stdout.write(JSON.stringify(values.map(v => badgeClass(v))));"
    )
    try:
        completed = subprocess.run(
            [node, "-e", script],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip().replace("\n", " ")
            return None, f"Node 실행 실패: {detail[:200]}"
        outputs = json.loads(completed.stdout)
        return dict(zip(values, outputs)), f"Node {subprocess_node_version(node)}로 실행"
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return None, f"badgeClass 실행 예외: {error}"


def subprocess_node_version(node):
    try:
        result = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=3, check=False
        )
        return result.stdout.strip() or "version unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "version unknown"


def css_rule_matches(css_source, class_name):
    """요구된 클래스 규칙에 배경색과 글자색이 모두 있는지 확인한다."""
    background, foreground, color_name = CSS_COLORS[class_name]
    blocks = re.findall(r"([^{}]+)\{([^{}]*)\}", css_source)
    for selectors, declarations in blocks:
        selector_list = [item.strip() for item in selectors.split(",")]
        if f".{class_name}" not in selector_list:
            continue
        compact = re.sub(r"\s+", "", declarations).lower()
        passed = (
            f"background:{background}" in compact
            and f"color:{foreground}" in compact
        )
        return passed, f"{color_name}({background}/{foreground})"
    return False, f".{class_name} 규칙 없음"


def find_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def start_server(port):
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for _ in range(40):
        if process.poll() is not None:
            return process, False
        status, body = http_get(f"http://127.0.0.1:{port}", "/health", timeout=1)
        if status == 200 and body == {"status": "ok"}:
            return process, True
        time.sleep(0.5)
    return process, False


def stop_server(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def http_get(base_url, path, timeout=10, expect_json=True):
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url, headers={"User-Agent": "req3-test-template"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not expect_json:
                return response.status, raw
            try:
                return response.status, json.loads(raw)
            except json.JSONDecodeError:
                return response.status, None
    except urllib.error.HTTPError as error:
        return error.code, None
    except Exception:
        return None, None


def run_static_and_badge_tests():
    app_js = read_text(APP_JS_PATH)
    css = read_text(STYLE_CSS_PATH)
    badge_function = extract_js_function(app_js, "badgeClass")
    badge_results, runner_detail = evaluate_badge_function(badge_function)

    all_mapping_ok = badge_results is not None and all(
        badge_results.get(value) == expected
        for value, expected in BADGE_EXPECTATIONS.items()
    )
    actual = runner_detail
    if badge_results is not None:
        wrong = {
            str(value): badge_results.get(value)
            for value, expected in BADGE_EXPECTATIONS.items()
            if badge_results.get(value) != expected
        }
        actual = f"{runner_detail}; " + (f"불일치={wrong}" if wrong else "15개 입력 일치")
    check(
        "DEV-01", "#3", "badgeClass 전체 매핑 및 기본값 실행",
        "12개 상태와 대소문자/빈 값/미정의 값 매핑", actual, all_mapping_ok,
    )

    css_checks = {name: css_rule_matches(css, name) for name in CSS_COLORS}
    css_ok = all(passed for passed, _ in css_checks.values())
    css_actual = ", ".join(
        f"{name}={'OK' if passed else detail}"
        for name, (passed, detail) in css_checks.items()
    )
    check(
        "DEV-02", "#3", "Badge CSS 색상 규칙",
        "초록/파랑/빨강/회색/노랑/연회색 정의", css_actual, css_ok,
    )

    render_subscribers = extract_js_function(app_js, "renderSubscribers")
    render_devices = extract_js_function(app_js, "renderDevices")
    select_device = extract_js_function(app_js, "selectDevice")
    integration = {
        "구독 상태": "badgeClass(s.status)" in render_subscribers,
        "가전 상태": "badgeClass(d.status)" in render_devices,
        "전원/건강 상태": "badgeClass(value)" in select_device,
    }
    check(
        "DEV-03", "#3", "화면 렌더링에서 badgeClass 적용",
        "구독/가전/전원·건강 상태에 적용", str(integration), all(integration.values()),
    )

    scenarios = [
        ("TE-01", "Active 상태 구독자", "Active", "초록 badge"),
        ("TE-02", "Paused 상태 구독자", "Paused", "파랑 badge"),
        ("TE-03", "Expired 상태 구독자", "Expired", "빨강 badge"),
        ("TE-04", "Online 상태 가전", "Online", "초록 badge"),
        ("TE-05", "Offline 상태 가전", "Offline", "회색 badge"),
        ("TE-06", "Error 상태 가전", "Error", "빨강 badge"),
        ("TE-07", "Power On 상태", "On", "노랑 badge"),
        ("TE-08", "Health Normal 상태", "Normal", "초록 badge"),
        ("TE-09", "Health Warning 상태", "Warning", "빨강 badge"),
    ]
    for tc_id, scenario, value, expected_text in scenarios:
        expected_class = BADGE_EXPECTATIONS[value]
        actual_class = badge_results.get(value) if badge_results is not None else runner_detail
        class_name = expected_class.split()[-1]
        css_passed, css_detail = css_checks[class_name]
        passed = badge_results is not None and actual_class == expected_class and css_passed
        check(
            tc_id, "#3 4.7", scenario, expected_text,
            f"class={actual_class}, CSS={css_detail}", passed,
        )


def run_ci_config_tests():
    source = read_text(CI_PATH)
    compact = source.replace("\r", "")
    contracts = {
        "workflow 파일": bool(source),
        "push main": bool(re.search(r"(?ms)^\s*push\s*:.*?branches\s*:\s*\[?\s*main", compact)),
        "pull_request main": bool(
            re.search(r"(?ms)^\s*pull_request\s*:.*?branches\s*:\s*\[?\s*main", compact)
        ),
        "Python 설정": "actions/setup-python@" in source,
        "의존성 설치": "pip install -r requirements.txt" in source,
        "main.py 문법 검사": "python -m py_compile app/main.py" in source,
        "subscribers.py 문법 검사": "python -m py_compile app/api/subscribers.py" in source,
        "devices.py 문법 검사": "python -m py_compile app/api/devices.py" in source,
        "서버 기동": "uvicorn app.main:app" in source,
        "health 검사": "curl -f http://localhost:8000/health" in source,
        "subscribers API": "curl -f http://localhost:8000/api/subscribers" in source,
        "devices API": "curl -f http://localhost:8000/api/subscribers/U001/devices" in source,
        "usage API": "curl -f http://localhost:8000/api/devices/D001/usage" in source,
    }
    check(
        "CI-CONFIG", "#3 4.8", ".github/workflows/ci.yml 구성",
        "main Push/PR, 설치, 서버 기동, health 및 API 3종 검사",
        str(contracts), all(contracts.values()),
    )


def run_local_api_tests(server_started):
    if not server_started:
        for tc_id, requirement, scenario, expected in (
            ("REG-01", "#1", "GET /api/subscribers 회귀 검사", "200, 구독자 5명"),
            ("REG-02", "#2", "GET /api/subscribers/U001/devices 회귀 검사", "200, D001/D002"),
            ("REG-03", "#2", "GET /api/devices/D001/usage 회귀 검사", "200, 7일 사용량"),
            ("TE-11", "#3 4.8", "CI health 체크 재현", "200, status=ok"),
            ("TE-12", "#3 4.8", "CI API 테스트 재현", "API 3개 모두 통과"),
        ):
            check(tc_id, requirement, scenario, expected, "로컬 서버 기동 실패", False)
        return

    sub_status, subscribers = http_get(LOCAL_BASE_URL, "/api/subscribers")
    dev_status, devices = http_get(LOCAL_BASE_URL, "/api/subscribers/U001/devices")
    use_status, usage = http_get(LOCAL_BASE_URL, "/api/devices/D001/usage")
    health_status, health = http_get(LOCAL_BASE_URL, "/health")

    subscribers_ok = sub_status == 200 and isinstance(subscribers, list) and len(subscribers) == 5
    device_ids = [item.get("deviceId") for item in devices] if isinstance(devices, list) else []
    devices_ok = dev_status == 200 and device_ids == ["D001", "D002"]
    trend = usage.get("weeklyUsageTrend", []) if isinstance(usage, dict) else []
    usage_ok = use_status == 200 and usage.get("deviceId") == "D001" and len(trend) == 7
    health_ok = health_status == 200 and health == {"status": "ok"}

    check("REG-01", "#1", "GET /api/subscribers 회귀 검사", "200, 구독자 5명",
          f"status={sub_status}, count={len(subscribers) if isinstance(subscribers, list) else 0}", subscribers_ok)
    check("REG-02", "#2", "GET /api/subscribers/U001/devices 회귀 검사", "200, D001/D002",
          f"status={dev_status}, devices={device_ids}", devices_ok)
    check("REG-03", "#2", "GET /api/devices/D001/usage 회귀 검사", "200, 7일 사용량",
          f"status={use_status}, trend={trend}", usage_ok)
    check("TE-11", "#3 4.8", "CI health 체크 재현", "200, status=ok",
          f"status={health_status}, body={health}", health_ok)
    check("TE-12", "#3 4.8", "CI API 테스트 재현", "API 3개 모두 통과",
          f"subscribers/devices/usage={subscribers_ok}/{devices_ok}/{usage_ok}",
          subscribers_ok and devices_ok and usage_ok)


def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "req3-test-template",
    }
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def github_repository_from_origin():
    try:
        completed = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        origin = completed.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None

    patterns = (
        r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$",
        r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, origin)
        if match:
            return match.group(1), match.group(2)
    return None


def discover_latest_ci_run():
    """origin 저장소의 main 브랜치에서 가장 최근 완료된 CI 실행을 찾는다."""
    repository = github_repository_from_origin()
    if not repository:
        return "", "GitHub origin 저장소를 확인할 수 없음"
    owner, name = repository
    api_url = (
        f"https://api.github.com/repos/{owner}/{name}/actions/runs"
        "?branch=main&status=completed&per_page=20"
    )
    request = urllib.request.Request(api_url, headers=github_headers())
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        runs = data.get("workflow_runs", [])
        ci_runs = [
            run for run in runs
            if run.get("name") == "CI" or str(run.get("path", "")).endswith("ci.yml")
        ]
        if not ci_runs:
            return "", "main 브랜치의 완료된 CI 실행을 찾을 수 없음"
        return ci_runs[0].get("html_url", ""), "origin에서 최신 CI 실행 자동 조회"
    except Exception as error:
        return "", f"최신 CI 자동 조회 실패: {error}"


def github_run_result(run_url):
    pattern = re.compile(
        r"^https://github\.com/([^/]+)/([^/]+)/actions/runs/(\d+)(?:/.*)?$"
    )
    match = pattern.match(run_url.strip().rstrip("/"))
    if not match:
        return False, "GitHub Actions run URL 형식이 아님"
    owner, repository, run_id = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repository}/actions/runs/{run_id}"
    request = urllib.request.Request(
        api_url,
        headers=github_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        event = data.get("event")
        correct_branch = event == "pull_request" or data.get("head_branch") == "main"
        passed = (
            data.get("status") == "completed"
            and data.get("conclusion") == "success"
            and event in {"push", "pull_request"}
            and correct_branch
        )
        actual = (
            f"event={data.get('event')}, branch={data.get('head_branch')}, "
            f"status={data.get('status')}, conclusion={data.get('conclusion')}"
        )
        return passed, actual
    except Exception as error:
        return False, f"GitHub API 확인 실패: {error}"


def run_external_tests(ci_run_url, render_url, ci_discovery_detail=""):
    if ci_run_url:
        passed, actual = github_run_result(ci_run_url)
        check("TE-10", "#3 4.8", "main Push/PR 시 CI 자동 실행",
              "Actions 실행 완료 및 success", actual, passed)
    else:
        check("TE-10", "#3 4.8", "main Push/PR 시 CI 자동 실행",
              "Actions 실행 완료 및 success",
              ci_discovery_detail or "실제 Actions 실행 증빙 필요", "NOT RUN")

    if not render_url:
        check("TE-13", "#3 CD", "CI 통과 후 Render 배포 확인",
              "배포 URL에서 화면·health·API·Badge 정상",
              "--render-url 미입력: 실제 배포 URL 필요", "NOT RUN")
        return

    root_status, root_body = http_get(render_url, "/", timeout=30, expect_json=False)
    health_status, health = http_get(render_url, "/health", timeout=30)
    js_status, deployed_js = http_get(
        render_url, "/static/app.js", timeout=30, expect_json=False
    )
    css_status, deployed_css = http_get(
        render_url, "/static/style.css", timeout=30, expect_json=False
    )
    endpoints = (
        "/api/subscribers",
        "/api/subscribers/U001/devices",
        "/api/devices/D001/usage",
    )
    api_statuses = [http_get(render_url, path, timeout=30)[0] for path in endpoints]
    root_ok = root_status == 200 and isinstance(root_body, str) and "<html" in root_body.lower()
    health_ok = health_status == 200 and health == {"status": "ok"}
    deployed_badges, badge_detail = evaluate_badge_function(
        extract_js_function(deployed_js if isinstance(deployed_js, str) else "", "badgeClass")
    )
    badge_ok = deployed_badges is not None and all(
        deployed_badges.get(value) == expected
        for value, expected in BADGE_EXPECTATIONS.items()
    )
    deployed_css = deployed_css if isinstance(deployed_css, str) else ""
    css_ok = css_status == 200 and all(
        css_rule_matches(deployed_css, class_name)[0]
        for class_name in CSS_COLORS
    )
    passed = (
        root_ok
        and health_ok
        and api_statuses == [200, 200, 200]
        and js_status == 200
        and badge_ok
        and css_ok
    )
    actual = (
        f"root={root_status}, health={health_status}/{health}, "
        f"API statuses={api_statuses}, badge={badge_ok}({badge_detail}), CSS={css_ok}"
    )
    check("TE-13", "#3 CD", "CI 통과 후 Render 배포 확인",
          "배포 URL에서 화면·health·API·Badge 정상", actual, passed)


def markdown_escape(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_report(args):
    counts = {name: sum(1 for *_, status in results if status == name)
              for name in ("PASS", "FAIL", "NOT RUN")}
    executed = counts["PASS"] + counts["FAIL"]
    rate = counts["PASS"] / executed * 100 if executed else 0.0
    overall = "PASS" if counts["FAIL"] == 0 and counts["NOT RUN"] == 0 else "INCOMPLETE"
    if counts["FAIL"]:
        overall = "FAIL"

    marks = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "NOT RUN": "⚪ NOT RUN"}
    lines = [
        "# 요구사항 #1~#3 최종 검증 Report",
        "",
        "| 항목 | 내용 |",
        "|------|------|",
        "| **프로젝트** | webOS Subscription Management Dashboard |",
        "| **검증 대상** | requirement_1.md ~ requirement_3.md |",
        f"| **검증 일시** | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |",
        f"| **작성자** | {markdown_escape(args.author)} |",
        f"| **GitHub Actions 증빙** | {markdown_escape(args.ci_run_url or '미입력')} |",
        f"| **Render 배포 URL** | {markdown_escape(args.render_url or '미입력')} |",
        f"| **종합 판정** | **{overall}** |",
        "",
        (
            f"**총 {len(results)}건: PASS {counts['PASS']} / FAIL {counts['FAIL']} / "
            f"NOT RUN {counts['NOT RUN']} — 실행 항목 Pass Rate {rate:.1f}%**"
        ),
        "",
        "| TC ID | 요구사항 | 테스트 시나리오 | 기대 결과 | 실제 결과 | 판정 |",
        "|:-----:|:--------:|----------------|-----------|-----------|:----:|",
    ]
    for tc_id, requirement, scenario, expected, actual, status in results:
        lines.append(
            f"| {tc_id} | {requirement} | {markdown_escape(scenario)} | "
            f"{markdown_escape(expected)} | {markdown_escape(actual)} | {marks[status]} |"
        )

    lines.extend([
        "",
        "## 판정 기준 및 남은 조치",
        "",
        "- `FAIL`: 구현 또는 설정을 수정한 뒤 스크립트를 다시 실행해야 합니다.",
        "- `NOT RUN`: 외부 증빙이 없어 판정하지 않은 항목입니다. 성공으로 계산하지 않습니다.",
        "- 최종 `PASS`를 받으려면 성공한 공개 Actions run URL과 Render URL을 옵션으로 전달하세요.",
        "",
        "> 본 Report는 `tests/req3_test_template.py`로 생성되었습니다.",
    ])

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    return counts, rate, overall


def main():
    global LOCAL_BASE_URL
    args = parse_args()
    os.chdir(PROJECT_ROOT)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    print("=" * 72)
    print(" requirement_3 및 요구사항 #1~#3 최종 검증")
    print("=" * 72)

    run_static_and_badge_tests()
    run_ci_config_tests()

    port = find_free_port()
    print(f"[로컬 서버 기동] 127.0.0.1:{port} ...")
    process, started = start_server(port)
    if started:
        LOCAL_BASE_URL = f"http://127.0.0.1:{port}"
        print("[로컬 서버 기동] 성공")
    else:
        print("[로컬 서버 기동] 실패")
    try:
        run_local_api_tests(started)
    finally:
        stop_server(process)

    ci_discovery_detail = ""
    if not args.ci_run_url:
        args.ci_run_url, ci_discovery_detail = discover_latest_ci_run()
    run_external_tests(args.ci_run_url, args.render_url, ci_discovery_detail)
    counts, rate, overall = render_report(args)

    print("\n" + "=" * 72)
    print(
        f" 결과: PASS {counts['PASS']} / FAIL {counts['FAIL']} / "
        f"NOT RUN {counts['NOT RUN']} - 실행 항목 {rate:.1f}% ({overall})"
    )
    print(f" Report 저장: {os.path.relpath(REPORT_PATH, PROJECT_ROOT)}")
    print("=" * 72)
    if counts["FAIL"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
