// =============================================================================
// 전역 변수
// =============================================================================
let subscribers = [];
let currentDevices = [];
let selectedUserId = null;
let selectedDeviceId = null;
let usageChart = null;


// =============================================================================
// [요구사항 #3] 상태 기반 Badge 스타일
// =============================================================================
// TODO [요구사항 #3]: 상태 값(value)에 따라 적절한 CSS 클래스를 반환하세요.
//
function badgeClass(value) {
    const v = (value || "").toLowerCase();

    // 매핑 규칙:
    // Active, Online, Normal   → "badge status-active"   (초록)
    // Paused, Standby          → "badge status-paused"   (파랑)
    // Expired, Error, Warning  → "badge status-expired"  (빨강)
    // Offline                  → "badge status-offline"  (회색)
    // On, Cleaning             → "badge status-on"       (노랑)
    // Off                      → "badge status-off"      (연회색)
    // 그 외                     → "badge"
    return "badge";
}


// =============================================================================
// [요구사항 #1] 구독 사용자 조회 + 검색/필터
// =============================================================================

// TODO [요구사항 #1-A]: GET /api/subscribers 를 호출하여
//   subscribers 변수에 저장하고 renderSubscribers()를 호출하세요.
//
async function fetchSubscribers() {
    // 1. GET /api/subscribers 호출
    // 2. 응답을 subscribers 변수에 저장
    // 3. renderSubscribers() 호출
    try {
        // 1. GET /api/subscribers 호출
        const res = await fetch("/api/subscribers");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // 2. 응답을 subscribers 변수에 저장 (배열 / {subscribers: [...]} 둘 다 대응)
        subscribers = Array.isArray(data) ? data : (data.subscribers ?? []);

        // 3. renderSubscribers() 호출
        renderSubscribers();
    } catch (err) {
        console.error("구독자 조회 실패:", err);
        const tbody = document.getElementById("subscriber-body");
        if (tbody) tbody.innerHTML = `<tr><td colspan="5">데이터를 불러오지 못했습니다.</td></tr>`;
    }
}

// TODO [요구사항 #1-B]: subscribers 배열을 테이블에 렌더링하세요.
//
function renderSubscribers() {
    // 1. 검색어와 상태 필터 값 가져오기
    // 2. subscribers 배열 필터링
    //    - 검색: name, plan, status, userId에 대해 부분 문자열 매칭
    //    - 필터: status가 선택된 값과 일치
    // 3. <tbody>에 <tr> 렌더링
    //    - 표시 컬럼: userId, name, plan, status, deviceCount
    //    - 각 행 클릭 시 selectSubscriber(userId) 호출
    //    - 선택된 행(selectedUserId)에 "selected" 클래스 추가

    const tbody = document.getElementById("subscriber-body");
    const search = document.getElementById("subscriber-search").value.trim().toLowerCase();
    const statusFilter = document.getElementById("subscriber-status-filter").value.toLowerCase();
    const isAll = statusFilter === "" || statusFilter === "all";

    const filtered = subscribers.filter((s) => {
        const matchesKeyword = !search ||
            [s.name, s.plan, s.status, s.userId]
                .some((v) => String(v ?? "").toLowerCase().includes(search));
        const matchesStatus = isAll || String(s.status).toLowerCase() === statusFilter;
        return matchesKeyword && matchesStatus;
    });

    tbody.innerHTML = "";

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5">검색 결과가 없습니다.</td></tr>`;
        return;
    }

    filtered.forEach((s) => {
        const tr = document.createElement("tr");
        if (s.userId === selectedUserId) tr.classList.add("selected");

        [s.userId, s.name, s.plan, s.status, s.deviceCount].forEach((v) => {
            const td = document.createElement("td");
            td.textContent = v ?? "-";
            tr.appendChild(td);
        });

        tr.addEventListener("click", () => selectSubscriber(s.userId));
        tbody.appendChild(tr);
    });
}


// =============================================================================
// [요구사항 #2] 사용자별 가전 목록 + 사용 현황 + 차트
// =============================================================================

// TODO [요구사항 #2-A]: 사용자 클릭 시 해당 사용자의 가전 목록을 조회하세요.

// 요소 표시/숨김 헬퍼
function setVisible(el, visible, display = "block") {
    if (el) el.style.display = visible ? display : "none";
}

async function selectSubscriber(userId) {
    // 1. 선택 상태 갱신
    selectedUserId = userId;
    selectedDeviceId = null;

    // 2. 구독자 테이블 하이라이트 반영
    renderSubscribers();

    // 3. 이전 사용 현황 초기화
    document.getElementById("device-search").value = "";        
    document.getElementById("device-status-filter").selectedIndex = 0; 
    setVisible(document.getElementById("usage-empty"), true);
    setVisible(document.getElementById("usage-detail"), false);
    document.getElementById("usage-info").innerHTML = "";
    if (usageChart) {
        usageChart.destroy();
        usageChart = null;
    }

    // 4~6. 가전 조회 → 저장 → 렌더링
    try {
        const res = await fetch(`/api/subscribers/${encodeURIComponent(userId)}/devices`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // 응답 대기 중 다른 사용자를 클릭했으면 무시
        if (selectedUserId !== userId) return;

        currentDevices = Array.isArray(data) ? data : (data.devices ?? []);
    } catch (err) {
        console.error("가전 조회 실패:", err);
        currentDevices = [];
    }
    renderDevices();
}

// TODO [요구사항 #2-B]: currentDevices 배열을 테이블에 렌더링하세요.
//
function renderDevices() {
    const emptyEl = document.getElementById("device-empty");
    const tableEl = document.getElementById("device-table");
    const tbody = document.getElementById("device-body");
    const search = document.getElementById("device-search").value.trim().toLowerCase();
    const statusFilter = document.getElementById("device-status-filter").value.toLowerCase();
    const isAll = statusFilter === "" || statusFilter === "all";

    // 필터링 (검색 AND 상태)
    const filtered = currentDevices.filter((d) => {
        const matchesKeyword = !search ||
            [d.type, d.model, d.status, d.deviceId, d.location]
                .some((v) => String(v ?? "").toLowerCase().includes(search));
        const matchesStatus = isAll || String(d.status).toLowerCase() === statusFilter;
        return matchesKeyword && matchesStatus;
    });

    tbody.innerHTML = "";

    // 가전 없음 / 필터 결과 없음
    if (currentDevices.length === 0 || filtered.length === 0) {
        emptyEl.textContent = currentDevices.length === 0
            ? "No registered devices"
            : "No devices matched";
        setVisible(emptyEl, true);
        setVisible(tableEl, false);
        return;
    }

    setVisible(emptyEl, false);
    setVisible(tableEl, true, "table");

    filtered.forEach((d) => {
        const tr = document.createElement("tr");
        if (d.deviceId === selectedDeviceId) tr.classList.add("selected");

        [d.deviceId, d.type, d.model, d.location].forEach((v) => {
            const td = document.createElement("td");
            td.textContent = v ?? "-";
            tr.appendChild(td);
        });

        // status는 badge로 표시
        const statusTd = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = badgeClass(d.status);
        badge.textContent = d.status ?? "-";
        statusTd.appendChild(badge);
        tr.appendChild(statusTd);

        tr.addEventListener("click", () => selectDevice(d.deviceId));
        tbody.appendChild(tr);
    });
}

// TODO [요구사항 #2-C]: 가전 클릭 시 상세 사용 현황을 조회하세요.
//
async function selectDevice(deviceId) {
    // 여기에 구현하세요
    // 1. selectedDeviceId 업데이트
    // 2. renderDevices() 호출 (선택 상태 반영)
    // 3. GET /api/devices/{deviceId}/usage 호출
    // 4. usage-empty 숨기기, usage-detail 표시
    // 5. usage-info에 상세 정보 렌더링:
    //    - Device ID, Device Name
    //    - Power Status (badge 스타일 적용)
    //    - Last Used, Total Usage Hours, Weekly Usage Count
    //    - Health Status (badge 스타일 적용)
    //    - Remark
    // 6. renderUsageChart(data.weeklyUsageTrend) 호출

    // 1~2. 선택 상태 갱신 + 하이라이트
    selectedDeviceId = deviceId;
    renderDevices();

    const emptyEl = document.getElementById("usage-empty");
    const detailEl = document.getElementById("usage-detail");
    const infoEl = document.getElementById("usage-info");

    try {
        // 3. 사용 현황 조회
        const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/usage`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (selectedDeviceId !== deviceId) return;

        // 4. 영역 전환
        setVisible(emptyEl, false);
        setVisible(detailEl, true);

        // 5. 상세 정보 렌더링
        infoEl.innerHTML = "";
        const rows = [
            ["Device ID", data.deviceId],
            ["Device Name", data.deviceName],
            ["Power Status", data.powerStatus, true],
            ["Last Used", data.lastUsed],
            ["Total Usage Hours", data.totalUsageHours != null ? `${data.totalUsageHours} hrs` : null],
            ["Weekly Usage Count", data.weeklyUsageCount],
            ["Health Status", data.healthStatus, true],
            ["Remark", data.remark],
        ];

        rows.forEach(([label, value, isBadge]) => {
            const labelEl = document.createElement("div");
            labelEl.className = "label";
            labelEl.textContent = label;

            const valueEl = document.createElement("div");
            valueEl.className = "value";
            if (isBadge && value != null) {
                const badge = document.createElement("span");
                badge.className = badgeClass(value);
                badge.textContent = value;
                valueEl.appendChild(badge);
            } else {
                valueEl.textContent = value ?? "-";
            }

            infoEl.append(labelEl, valueEl);
        });

        // 6. 차트
        renderUsageChart(data.weeklyUsageTrend ?? []);
    } catch (err) {
        console.error("사용 현황 조회 실패:", err);
        setVisible(emptyEl, true);
        setVisible(detailEl, false);
    }
}

// TODO [요구사항 #2-D]: Chart.js를 사용하여 주간 사용량 Bar Chart를 그리세요.
//
function renderUsageChart(trend) {
    const ctx = document.getElementById("usageChart");

    // 1. 기존 차트 제거 (안 하면 canvas 재사용 에러)
    if (usageChart) usageChart.destroy();

    // 2. 새 차트 생성
    usageChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            datasets: [{
                label: "Weekly Usage Trend",
                data: trend,
                borderWidth: 1,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: { y: { beginAtZero: true } },
        },
    });
}


// =============================================================================
// 이벤트 바인딩 + 초기화
// =============================================================================
function bindEvents() {
    // [요구사항 #1] 완료 후 아래 주석을 해제하세요
    document.getElementById("subscriber-search").addEventListener("input", renderSubscribers);
    document.getElementById("subscriber-status-filter").addEventListener("change", renderSubscribers);

    // [요구사항 #2] 완료 후 아래 주석을 해제하세요
    document.getElementById("device-search").addEventListener("input", renderDevices);
    document.getElementById("device-status-filter").addEventListener("change", renderDevices);
}

bindEvents();

// [요구사항 #1] 완료 후 아래 주석을 해제하세요
fetchSubscribers();
