"""pytest 公共设施：API 客户端 + 服务启动夹具

说明：
- 测试跑在真实运行的 FastAPI 服务上（127.0.0.1:8000），会先重置数据库。
- 每个测试模块使用独立会计年度（2026/2030/2031/2032），互不干扰。
"""
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

import pytest

# e2e_test.py 是独立脚本（unittest 风格命令行），不参与 pytest 收集
import os as _os
_collect_ignore = [_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "e2e_test.py")]
collect_ignore = _collect_ignore

BASE = os.environ.get("TEST_API", "http://127.0.0.1:8000")
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def api(method, path, body=None, raw=False):
    url = BASE + urllib.parse.quote(path, safe="/?&=:%")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload))
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"detail": payload.decode(errors="replace")}


def get(path):
    return api("GET", path)


def post(path, body=None):
    return api("POST", path, body if body is not None else {})


def put(path, body=None):
    return api("PUT", path, body if body is not None else {})


def delete(path):
    return api("DELETE", path)


def upload(path, filename, data, field="file"):
    boundary = "----pytestboundary7f3a"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"detail": payload.decode(errors="replace")}


def acc_id(code, accounts=None):
    rows = accounts if accounts is not None else get("/api/accounts")[1]
    for a in rows:
        if a["code"] == code:
            return a["id"]
    raise AssertionError(f"科目不存在：{code}")


def entry(code, summary, debit=0, credit=0, accounts=None):
    return {"account_id": acc_id(code, accounts), "summary": summary,
            "debit": debit, "credit": credit}


def make_voucher(date, lines, vtype="记", accounts=None):
    """lines: [(code, summary, debit, credit), ...]"""
    entries = [entry(c, s, d, cr, accounts) for c, s, d, cr in lines]
    return post("/api/vouchers", {"date": date, "vtype": vtype, "entries": entries})


@pytest.fixture(scope="session")
def server():
    """重置并启动后端服务（整场测试只执行一次）"""
    subprocess.run(["bash", os.path.join(BACKEND_DIR, "restart.sh"), "fresh"],
                   check=True, stdout=subprocess.DEVNULL)
    st, h = get("/api/health")
    assert st == 200, f"服务未启动：{h}"
    yield


@pytest.fixture(scope="session")
def accounts(server):
    return get("/api/accounts")[1]
