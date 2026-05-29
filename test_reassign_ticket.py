"""
Quick test script to reassign an htm-api v3 task to a different user.

Ticket:   454cd202-a548-4ec5-94f0-f9deab9e8641  (CDGC asset)
Process:  0051b6f7-1baf-43ea-9af6-32b42bdcb16a  (htm-api process)
Task:     45d9b78e-b691-3c77-9810-65029611cfe7  (open task, currently Bryan)
New user: 2TpHXcgSokmg81JN6sl5m6               (shayes_rcg_dq_POC)
"""

VERSION = "20260528"

import json
import requests
from auth import get_session

PROCESS_GUID = "0051b6f7-1baf-43ea-9af6-32b42bdcb16a"
TASK_GUID    = "45d9b78e-b691-3c77-9810-65029611cfe7"
NEW_USER_ID  = "2TpHXcgSokmg81JN6sl5m6"

session = get_session()
base    = session.cdgc_api_url   # https://cdgc-api.dm-us.informaticacloud.com
headers = session.workflow_headers()
headers["Content-Type"] = "application/json"
headers["x-infa-htm-application"] = "cdgc"


def show(label, resp):
    print(f"\n{'='*60}")
    print(f"{label}  [{resp.status_code}]")
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)


# ------------------------------------------------------------------
# 1. Confirm current task state
# ------------------------------------------------------------------
resp = requests.get(
    f"{base}/htm-api/api/v3/tickets/{PROCESS_GUID}",
    params={"include": "TASKS_ALL"},
    headers=headers,
)
show("GET ticket (current state)", resp)


TICKET_ID    = "0c5a43cc53c911f1835eb9b97c0a7496"

cdgc_headers  = session.cdgc_headers()
cdgc_headers["Content-Type"] = "application/json"
ccgf_headers  = session.cdgc_internal_headers()

# ------------------------------------------------------------------
# 2. ccgf-issue-management: try task sub-resource and forward/transfer
# ------------------------------------------------------------------
for path, body in [
    (f"/ccgf-issue-management/api/v1/tickets/{TICKET_ID}/tasks/{TASK_GUID}/reassign",
     {"assignee": NEW_USER_ID}),
    (f"/ccgf-issue-management/api/v1/tickets/{TICKET_ID}/tasks/{TASK_GUID}/forward",
     {"to": NEW_USER_ID}),
    (f"/ccgf-issue-management/api/v1/tasks/{TASK_GUID}/reassign",
     {"assignee": NEW_USER_ID}),
    (f"/ccgf-issue-management/api/v1/tasks/{TASK_GUID}",
     {"assignee": NEW_USER_ID}),
]:
    r = requests.post(f"{base}{path}", headers=ccgf_headers, json=body)
    if r.status_code == 500 and "No static resource" in r.text:
        print(f"\n[SKIP - no route] POST {path}")
        continue
    show(f"POST {path}", r)
    if r.status_code in (200, 201, 204):
        break

# ------------------------------------------------------------------
# 3. htm-carbon: does it have task management endpoints?
# ------------------------------------------------------------------
for path in [
    f"/htm-carbon/api/v1/tasks/{TASK_GUID}/reassign",
    f"/htm-carbon/api/v1/process/{PROCESS_GUID}/tasks/{TASK_GUID}",
]:
    r = requests.post(f"{base}{path}", headers=headers,
                      json={"assignee": NEW_USER_ID})
    if r.status_code == 500 and "No static resource" in r.text:
        print(f"\n[SKIP - no route] POST {path}")
        continue
    show(f"POST htm-carbon {path}", r)
    if r.status_code in (200, 201, 204):
        break

# ------------------------------------------------------------------
# 4. htm-api with full CDGC headers (not workflow headers)
# ------------------------------------------------------------------
cdgc_htm_headers = cdgc_headers.copy()
cdgc_htm_headers["x-infa-htm-application"] = "cdgc"

for method, path, body in [
    ("patch", f"/htm-api/api/v3/tasks/{TASK_GUID}",
     {"candidateAcl": {"roles": [], "userGroups": [], "users": [NEW_USER_ID]}}),
    ("post",  f"/htm-api/api/v3/tickets/{PROCESS_GUID}/tasks",
     {"guid": TASK_GUID, "candidateAcl": {"users": [NEW_USER_ID]}}),
]:
    r = getattr(requests, method)(f"{base}{path}", headers=cdgc_htm_headers, json=body)
    if r.status_code == 500 and "No static resource" in r.text:
        print(f"\n[SKIP - no route] {method.upper()} {path}")
        continue
    show(f"{method.upper()} htm-api (cdgc headers) {path}", r)
    if r.status_code in (200, 201, 204):
        break


# ------------------------------------------------------------------
# 3. Re-fetch to confirm
# ------------------------------------------------------------------
resp = requests.get(
    f"{base}/htm-api/api/v3/tickets/{PROCESS_GUID}",
    params={"include": "TASKS_ALL"},
    headers=headers,
)
show("GET ticket (after patch)", resp)
