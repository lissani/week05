# requirement_2 검증 Report (TE 실습)

| 항목 | 내용 |
|------|------|
| **프로젝트** | webOS Subscription Management Dashboard |
| **검증 대상** | requirement_2.md |
| **검증 일시** | 2026-10-01 16:42:31 |
| **작성자** | (여기에 이름을 적으세요) |

**총 14건 중 PASS 14 / FAIL 0 — Pass Rate 100.0%**

| TC ID | 테스트 시나리오 | 기대 결과 | 실제 결과 | 판정 |
|:-----:|----------------|-----------|-----------|:----:|
| DEV-01 | get_devices_by_user('U001') 직접 호출 | D001, D002 반환 | 2개: ['D001', 'D002'] | ✅ PASS |
| DEV-02 | get_device_usage('D001') 직접 호출 | D001 사용 현황과 7일 데이터 반환 | deviceId=D001, trend=[2, 3, 1, 4, 2, 3, 3] | ✅ PASS |
| TE-01 | GET /api/subscribers/U001/devices | 200, D001/D002 두 개 반환 | status=200, devices=['D001', 'D002'] | ✅ PASS |
| TE-02 | GET /api/subscribers/U005/devices | 200, 빈 배열 반환 | status=200, body=[] | ✅ PASS |
| TE-03 | GET /api/subscribers/U999/devices | 404 반환 | status=404, body={'detail': 'Subscriber U999 not found'} | ✅ PASS |
| TE-04 | U001 클릭 시 가전 Table 표시 | D001, D002 렌더링 | API=['D001', 'D002'], selectSubscriber 구현=True, 행 클릭 구현=True | ✅ PASS |
| TE-05 | U005 클릭 시 안내 메시지 | No registered devices 표시 | 빈 목록=[], 안내 문구 구현=True | ✅ PASS |
| TE-06 | 모델명/타입/상태/ID/위치 검색 | 각 검색어에 맞는 가전만 표시 | results={'type=TV': ['D001'], 'model=WashTower': ['D002'], 'status=Offline': ['D002'], 'deviceId=D001': ['D001'], 'location=Dormitory': ['D001']}, JS 필드/이벤트=True/True | ✅ PASS |
| TE-07 | Online/Offline/Standby/Error 상태 필터 | 선택한 상태의 가전만 표시 | results={'Online': ['D001', 'D003', 'D004', 'D005', 'D007'], 'Offline': ['D002'], 'Standby': ['D008'], 'Error': ['D006']}, 이벤트=True | ✅ PASS |
| TE-08 | GET /api/devices/D001/usage | 사용 현황 JSON 반환 | status=200, fields=['deviceId', 'deviceName', 'healthStatus', 'lastUsedAt', 'powerStatus', 'remark', 'totalUsageHours', 'weeklyUsageCount', 'weeklyUsageTrend'] | ✅ PASS |
| TE-09 | GET /api/devices/D999/usage | 404 반환 | status=404, body={'detail': 'Device D999 not found'} | ✅ PASS |
| TE-10 | D001 클릭 시 사용 현황 표시 | 전원 상태, 누적 시간 등 상세 정보 표시 | 8개 필드 구현=True, 상세 영역 전환=True | ✅ PASS |
| TE-11 | D001 클릭 시 주간 사용량 Bar Chart 표시 | Mon~Sun 7개 막대 표시 | trend=[2, 3, 1, 4, 2, 3, 3], 차트 구현/호출=True/True | ✅ PASS |
| TE-12 | 다른 가전 클릭 시 차트 갱신 | 기존 차트 제거 후 새 데이터 표시 | D002 status=200, trend=[0, 1, 0, 1, 1, 0, 1], destroy→new Chart=True | ✅ PASS |

> 본 Report는 `tests/req2_test_template.py`로 생성되었습니다.
