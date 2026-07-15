import json
import os
import re
import shutil
import subprocess


OPENCLI = os.environ.get("OPENCLI_BIN") or shutil.which("opencli")


class OpenCliError(RuntimeError):
    pass


def parse_human_count(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "")
    if not s or s == "-":
        return 0
    mult = 1
    low = s.lower()
    if low.endswith("万"):
        mult, s = 10000, s[:-1]
    elif low.endswith("亿"):
        mult, s = 100000000, s[:-1]
    elif low.endswith("k"):
        mult, s = 1000, s[:-1]
    elif low.endswith("m"):
        mult, s = 1000000, s[:-1]
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return int(float(m.group(0)) * mult) if m else 0


def browser_connected(timeout=12):
    if not OPENCLI:
        return False
    try:
        r = subprocess.run([OPENCLI, "daemon", "status"], capture_output=True, text=True, timeout=timeout)
    except Exception:
        return False
    return r.returncode == 0 and "Extension: connected" in (r.stdout or "")


def run_json(args, timeout=60):
    if not OPENCLI:
        raise OpenCliError("opencli not found")
    env = os.environ.copy()
    env.setdefault("OPENCLI_BROWSER_COMMAND_TIMEOUT", str(max(10, timeout - 5)))
    try:
        r = subprocess.run([OPENCLI, *args], capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise OpenCliError(f"timeout after {timeout}s") from e
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip().splitlines()
        raise OpenCliError(msg[-1] if msg else f"opencli exited {r.returncode}")
    try:
        return json.loads(r.stdout or "[]")
    except json.JSONDecodeError as e:
        raise OpenCliError(f"invalid json: {e}") from e


def dedupe(signals):
    seen, out = set(), []
    for sig in signals:
        key = sig.get("id") or sig.get("url")
        if key in seen:
            continue
        seen.add(key)
        out.append(sig)
    return out
