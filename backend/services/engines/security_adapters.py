from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


def run_nuclei_scan(target_url: str, *, timeout_sec: int = 120) -> dict[str, Any]:
    nuclei = shutil.which("nuclei")
    if not nuclei:
        return {
            "status": "skipped",
            "engine": "nuclei",
            "findings": [],
            "detail": {"reason": "nuclei 未安装或不在 PATH"},
        }
    cmd = [nuclei, "-u", target_url, "-jsonl", "-silent", "-severity", "medium,high,critical"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return {"status": "error", "engine": "nuclei", "findings": [], "detail": {"reason": "timeout"}}
    findings: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            findings.append(
                {
                    "vul_type": row.get("info", {}).get("name") or row.get("template-id"),
                    "risk_level": (row.get("info", {}).get("severity") or "medium").upper(),
                    "test_payload": [row.get("matched-at") or target_url],
                    "scan_strategy": "nuclei",
                    "engine": "nuclei",
                }
            )
        except json.JSONDecodeError:
            continue
    status = "passed" if proc.returncode == 0 and not findings else "failed" if findings else "passed"
    return {
        "status": status,
        "engine": "nuclei",
        "findings": findings,
        "detail": {"exit_code": proc.returncode, "finding_count": len(findings)},
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
    }


def run_zap_baseline(target_url: str, *, timeout_sec: int = 300) -> dict[str, Any]:
    zap = shutil.which("zap.sh") or shutil.which("zap-baseline.py")
    if not zap:
        return {
            "status": "skipped",
            "engine": "zap",
            "findings": [],
            "detail": {"reason": "OWASP ZAP 未安装（需 zap.sh 或 zap-baseline.py）"},
        }
    cmd = [zap, "-cmd", "-quickurl", target_url, "-quickprogress"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return {"status": "error", "engine": "zap", "findings": [], "detail": {"reason": "timeout"}}
    findings: list[dict[str, Any]] = []
    if "FAIL" in (proc.stdout or "") or proc.returncode != 0:
        findings.append(
            {
                "vul_type": "ZAP Baseline Alert",
                "risk_level": "中",
                "test_payload": [target_url],
                "scan_strategy": "zap_baseline",
                "engine": "zap",
            }
        )
    return {
        "status": "failed" if findings else "passed",
        "engine": "zap",
        "findings": findings,
        "detail": {"exit_code": proc.returncode},
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
    }


def run_external_security_engine(engine: str, target_url: str) -> dict[str, Any]:
    if engine == "nuclei":
        return run_nuclei_scan(target_url)
    if engine == "zap":
        return run_zap_baseline(target_url)
    return {"status": "skipped", "engine": engine, "findings": [], "detail": {"reason": f"unknown engine: {engine}"}}
