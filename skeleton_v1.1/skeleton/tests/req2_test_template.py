"""
requirement_2.md 검증 템플릿 스크립트 (TE용)

실행 방법
--------
    # skeleton 프로젝트 루트에서
    python tests/req2_test_template.py

결과
----
    tests/reports/req2_report_template.md

별도의 브라우저 자동화 패키지 없이 다음 세 가지를 함께 검증합니다.
  1) 개발자 테스트: API 함수를 직접 호출해 반환 데이터 확인
  2) API 테스트: 실제 uvicorn 서버를 기동해 HTTP 응답 확인
  3) TE 시나리오: 검색/필터 결과와 app.js의 화면 동작 계약 확인
"""

import json
import os
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
REPORT_DIR = os.path.join(THIS_DIR, "reports")
REPORT_PATH = os.path.join(REPORT_DIR, "req2_report_template.md")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "app", "static", "app.js")

os.chdir(PROJECT_ROOT)
BASE_URL = None
results = []


def check(tc_id, scenario, expected, actual, passed):
    """검증 결과 한 건을 기록한다."""
    results.append((tc_id, scenario, expected, actual, bool(passed)))
    tag = "PASS" if passed else "FAIL"
    print(f"  [{tag}] {tc_id}  {scenario}")


def http_get(path, timeout=5):
    """GET 요청 결과를 (상태 코드, JSON 본문)으로 반환한다."""
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            try:
                return response.status, json.loads(body)
            except json.JSONDecodeError:
                return response.status, None
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = None
        return error.code, body
    except Exception:
        return None, None


def filter_devices(devices, search="", status=""):
    """app.js의 renderDevices와 같은 검색/상태 필터 규칙을 재현한다."""
    keyword = (search or "").strip().lower()
    selected_status = (status or "").strip().lower()
    output = []

    for device in devices:
        if not isinstance(device, dict):
            continue
        searchable = (
            device.get("type"),
            device.get("model"),
            device.get("status"),
            device.get("deviceId"),
            device.get("location"),
        )
        matches_search = not keyword or any(
            keyword in str(value or "").lower() for value in searchable
        )
        matches_status = (
            not selected_status
            or selected_status == "all"
            or str(device.get("status", "")).lower() == selected_status
        )
        if matches_search and matches_status:
            output.append(device)

    return output


def read_app_js():
    try:
        with open(APP_JS_PATH, encoding="utf-8") as file:
            return file.read()
    except OSError:
        return ""


def extract_js_function(source, function_name):
    """중괄호 깊이를 따라 지정한 JavaScript 함수 본문을 추출한다."""
    marker = f"function {function_name}("
    start = source.find(marker)
    if start < 0:
        return ""
    opening = source.find("{", start)
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
                return source[start:index + 1]
    return ""


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
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=1
            ) as response:
                if response.status == 200:
                    return process, True
        except Exception:
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


def run_developer_tests():
    try:
        from app.api.subscribers import get_devices_by_user

        devices = get_devices_by_user("U001")
        ids = [device.get("deviceId") for device in devices]
        passed = ids == ["D001", "D002"]
        actual = f"{len(devices)}개: {ids}"
    except Exception as error:
        passed, actual = False, f"예외: {error}"
    check(
        "DEV-01",
        "get_devices_by_user('U001') 직접 호출",
        "D001, D002 반환",
        actual,
        passed,
    )

    try:
        from app.api.devices import get_device_usage

        usage = get_device_usage("D001")
        passed = (
            isinstance(usage, dict)
            and usage.get("deviceId") == "D001"
            and len(usage.get("weeklyUsageTrend", [])) == 7
        )
        actual = (
            f"deviceId={usage.get('deviceId')}, "
            f"trend={usage.get('weeklyUsageTrend')}"
        )
    except Exception as error:
        passed, actual = False, f"예외: {error}"
    check(
        "DEV-02",
        "get_device_usage('D001') 직접 호출",
        "D001 사용 현황과 7일 데이터 반환",
        actual,
        passed,
    )


def run_te_tests():
    app_js = read_app_js()
    select_subscriber_js = extract_js_function(app_js, "selectSubscriber")
    render_devices_js = extract_js_function(app_js, "renderDevices")
    select_device_js = extract_js_function(app_js, "selectDevice")
    render_chart_js = extract_js_function(app_js, "renderUsageChart")

    # 1. U001의 가전 목록 API
    status, u001_devices = http_get("/api/subscribers/U001/devices")
    u001_devices = u001_devices if isinstance(u001_devices, list) else []
    u001_ids = [device.get("deviceId") for device in u001_devices]
    check(
        "TE-01",
        "GET /api/subscribers/U001/devices",
        "200, D001/D002 두 개 반환",
        f"status={status}, devices={u001_ids}",
        status == 200 and u001_ids == ["D001", "D002"],
    )

    # 2. 가전이 없는 사용자
    status, body = http_get("/api/subscribers/U005/devices")
    check(
        "TE-02",
        "GET /api/subscribers/U005/devices",
        "200, 빈 배열 반환",
        f"status={status}, body={body}",
        status == 200 and body == [],
    )

    # 3. 존재하지 않는 사용자
    status, body = http_get("/api/subscribers/U999/devices")
    check(
        "TE-03",
        "GET /api/subscribers/U999/devices",
        "404 반환",
        f"status={status}, body={body}",
        status == 404,
    )

    # 4. 사용자 선택 시 목록 조회/렌더링
    subscriber_ui_contract = all(
        token in select_subscriber_js
        for token in (
            "selectedUserId = userId",
            "selectedDeviceId = null",
            "/api/subscribers/${encodeURIComponent(userId)}/devices",
            "currentDevices =",
            "renderDevices()",
        )
    )
    row_click_contract = "selectDevice(d.deviceId)" in render_devices_js
    check(
        "TE-04",
        "U001 클릭 시 가전 Table 표시",
        "D001, D002 렌더링",
        (
            f"API={u001_ids}, selectSubscriber 구현={subscriber_ui_contract}, "
            f"행 클릭 구현={row_click_contract}"
        ),
        u001_ids == ["D001", "D002"]
        and subscriber_ui_contract
        and row_click_contract,
    )

    # 5. 빈 목록 안내 문구
    empty_message_exists = '"No registered devices"' in render_devices_js
    check(
        "TE-05",
        "U005 클릭 시 안내 메시지",
        "No registered devices 표시",
        f"빈 목록=[], 안내 문구 구현={empty_message_exists}",
        empty_message_exists,
    )

    # 6. 5개 검색 필드와 이벤트 연결
    search_cases = {
        "type=TV": ("TV", ["D001"]),
        "model=WashTower": ("WashTower", ["D002"]),
        "status=Offline": ("Offline", ["D002"]),
        "deviceId=D001": ("D001", ["D001"]),
        "location=Dormitory": ("Dormitory", ["D001"]),
    }
    search_results = {
        label: [item.get("deviceId") for item in filter_devices(u001_devices, query)]
        for label, (query, _) in search_cases.items()
    }
    search_passed = all(
        search_results[label] == expected
        for label, (_, expected) in search_cases.items()
    )
    search_fields_in_js = all(
        f"d.{field}" in render_devices_js
        for field in ("type", "model", "status", "deviceId", "location")
    )
    search_event_bound = (
        'getElementById("device-search").addEventListener("input", renderDevices)'
        in app_js
    )
    check(
        "TE-06",
        "모델명/타입/상태/ID/위치 검색",
        "각 검색어에 맞는 가전만 표시",
        f"results={search_results}, JS 필드/이벤트={search_fields_in_js}/{search_event_bound}",
        search_passed and search_fields_in_js and search_event_bound,
    )

    # 7. 문서가 요구하는 네 가지 상태 필터
    all_devices = []
    for user_id in ("U001", "U002", "U003", "U004", "U005"):
        _, devices = http_get(f"/api/subscribers/{user_id}/devices")
        if isinstance(devices, list):
            all_devices.extend(devices)
    expected_by_status = {
        "Online": ["D001", "D003", "D004", "D005", "D007"],
        "Offline": ["D002"],
        "Standby": ["D008"],
        "Error": ["D006"],
    }
    actual_by_status = {
        state: [item.get("deviceId") for item in filter_devices(all_devices, status=state)]
        for state in expected_by_status
    }
    status_event_bound = (
        'getElementById("device-status-filter").addEventListener("change", renderDevices)'
        in app_js
    )
    check(
        "TE-07",
        "Online/Offline/Standby/Error 상태 필터",
        "선택한 상태의 가전만 표시",
        f"results={actual_by_status}, 이벤트={status_event_bound}",
        actual_by_status == expected_by_status and status_event_bound,
    )

    # 8. 사용 현황 API 정상 응답
    status, usage = http_get("/api/devices/D001/usage")
    usage = usage if isinstance(usage, dict) else {}
    required_usage_fields = {
        "deviceId",
        "deviceName",
        "powerStatus",
        "lastUsedAt",
        "totalUsageHours",
        "weeklyUsageCount",
        "healthStatus",
        "remark",
        "weeklyUsageTrend",
    }
    usage_shape_ok = required_usage_fields.issubset(usage)
    check(
        "TE-08",
        "GET /api/devices/D001/usage",
        "사용 현황 JSON 반환",
        f"status={status}, fields={sorted(usage)}",
        status == 200 and usage_shape_ok,
    )

    # 9. 존재하지 않는 가전
    status, body = http_get("/api/devices/D999/usage")
    check(
        "TE-09",
        "GET /api/devices/D999/usage",
        "404 반환",
        f"status={status}, body={body}",
        status == 404,
    )

    # 10. 가전 선택 시 상세 필드 표시
    detail_fields = (
        "deviceId",
        "deviceName",
        "powerStatus",
        "lastUsedAt",
        "totalUsageHours",
        "weeklyUsageCount",
        "healthStatus",
        "remark",
    )
    detail_contract = all(f"data.{field}" in select_device_js for field in detail_fields)
    visibility_contract = all(
        token in select_device_js
        for token in ("setVisible(emptyEl, false)", "setVisible(detailEl, true)")
    )
    check(
        "TE-10",
        "D001 클릭 시 사용 현황 표시",
        "전원 상태, 누적 시간 등 상세 정보 표시",
        f"8개 필드 구현={detail_contract}, 상세 영역 전환={visibility_contract}",
        usage_shape_ok and detail_contract and visibility_contract,
    )

    # 11. 요일별 Bar Chart
    chart_contract = all(
        token in render_chart_js
        for token in (
            'type: "bar"',
            'labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]',
            "data: trend",
            "beginAtZero: true",
        )
    )
    chart_called = "renderUsageChart(data.weeklyUsageTrend" in select_device_js
    trend = usage.get("weeklyUsageTrend", [])
    check(
        "TE-11",
        "D001 클릭 시 주간 사용량 Bar Chart 표시",
        "Mon~Sun 7개 막대 표시",
        f"trend={trend}, 차트 구현/호출={chart_contract}/{chart_called}",
        len(trend) == 7 and chart_contract and chart_called,
    )

    # 12. 다른 가전 선택 시 기존 차트 제거 후 새 차트 생성
    destroy_index = render_chart_js.find("usageChart.destroy()")
    create_index = render_chart_js.find("new Chart(")
    refresh_contract = (
        destroy_index >= 0 and create_index >= 0 and destroy_index < create_index
    )
    second_status, second_usage = http_get("/api/devices/D002/usage")
    second_trend = (
        second_usage.get("weeklyUsageTrend", [])
        if isinstance(second_usage, dict)
        else []
    )
    check(
        "TE-12",
        "다른 가전 클릭 시 차트 갱신",
        "기존 차트 제거 후 새 데이터 표시",
        (
            f"D002 status={second_status}, trend={second_trend}, "
            f"destroy→new Chart={refresh_contract}"
        ),
        second_status == 200 and len(second_trend) == 7 and refresh_contract,
    )


def render_report():
    total = len(results)
    passed = sum(1 for *_, result in results if result)
    failed = total - passed
    rate = passed / total * 100 if total else 0.0

    lines = [
        "# requirement_2 검증 Report (TE 실습)",
        "",
        "| 항목 | 내용 |",
        "|------|------|",
        "| **프로젝트** | webOS Subscription Management Dashboard |",
        "| **검증 대상** | requirement_2.md |",
        f"| **검증 일시** | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |",
        "| **작성자** | (여기에 이름을 적으세요) |",
        "",
        f"**총 {total}건 중 PASS {passed} / FAIL {failed} — Pass Rate {rate:.1f}%**",
        "",
        "| TC ID | 테스트 시나리오 | 기대 결과 | 실제 결과 | 판정 |",
        "|:-----:|----------------|-----------|-----------|:----:|",
    ]
    for tc_id, scenario, expected, actual, passed_ in results:
        safe_actual = str(actual).replace("|", "\\|").replace("\n", " ")
        mark = "✅ PASS" if passed_ else "❌ FAIL"
        lines.append(
            f"| {tc_id} | {scenario} | {expected} | {safe_actual} | {mark} |"
        )
    lines.extend(
        [
            "",
            "> 본 Report는 `tests/req2_test_template.py`로 생성되었습니다.",
        ]
    )

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    return passed, failed, total, rate


def main():
    global BASE_URL
    print("=" * 64)
    print(" requirement_2 검증 (TE 템플릿)")
    print("=" * 64)

    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    run_developer_tests()

    port = find_free_port()
    print(f"[서버 기동] 127.0.0.1:{port} ...")
    process, started = start_server(port)
    if not started:
        print("[오류] 서버 기동 실패. requirements 설치 및 app/main.py를 확인하세요.")
        stop_server(process)
        sys.exit(1)

    BASE_URL = f"http://127.0.0.1:{port}"
    print("[서버 기동] 성공\n")
    try:
        run_te_tests()
    finally:
        stop_server(process)

    passed, failed, total, rate = render_report()
    print("\n" + "=" * 64)
    print(f" 결과: PASS {passed} / FAIL {failed} (총 {total}) - {rate:.1f}%")
    print(f" Report 저장: {os.path.relpath(REPORT_PATH, PROJECT_ROOT)}")
    print("=" * 64)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
