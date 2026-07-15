# collectors/huggingface.py — Hugging Face（trending 模型 + Spaces，公开无 key）
# 信号类型：launch（新发布 / Alpha 技术窗口）。Spaces 自带"想自部署 / 想用"的需求。
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_json, http_get, write_raw, mk_signal, detect_signal_type, extract_keywords

# 注：HF API 不接受 sort=trending（返回 400）。likes7d = 近 7 天热度（即 trending 窗口）；
# 默认端点本身也按 trendingScore 排序，作为兜底。两者都带 trendingScore 字段。
MODELS_URLS = [
    "https://huggingface.co/api/models?sort=likes7d&limit=40",
    "https://huggingface.co/api/models?limit=40",
]
SPACES_URLS = [
    "https://huggingface.co/api/spaces?sort=likes7d&limit=40",
    "https://huggingface.co/api/spaces?limit=40",
]


def _int(v):
    try:
        return int(v or 0)
    except Exception:
        return 0


def fetch_first(urls, label):
    """依次尝试候选 URL，返回首个成功的列表；全失败返回 []。"""
    for url in urls:
        try:
            data = get_json(url)
            if isinstance(data, list):
                return data
        except Exception as e:
            print(f"  hf {label} feed fail ({url}): {e}")
    return []


def run():
    seen = {}

    # —— trending 模型 ——
    models = fetch_first(MODELS_URLS, "models")
    for m in models or []:
        mid = m.get("id") or m.get("modelId")
        if not mid:
            continue
        key = f"model::{mid}"
        if key in seen:
            continue
        tag = m.get("pipeline_tag") or "model"
        likes = _int(m.get("likes"))
        downloads = _int(m.get("downloads"))
        text = f"{tag} · likes {likes}" + (f" · downloads {downloads}" if downloads else "")
        seen[key] = mk_signal(
            id=f"huggingface-model-{mid}", source="huggingface", source_label="Hugging Face",
            region="海外", lang="en", title=mid, text=text,
            url=f"https://huggingface.co/{mid}",
            popularity=likes, comments=0,
            created_at=m.get("createdAt") or "", signal_type="launch",
            keywords=extract_keywords(f"{mid} {tag}", "en"))

    time.sleep(0.5)

    # —— trending Spaces ——
    spaces = fetch_first(SPACES_URLS, "spaces")
    for s in spaces or []:
        sid = s.get("id")
        if not sid:
            continue
        key = f"space::{sid}"
        if key in seen:
            continue
        sdk = s.get("sdk") or "space"
        likes = _int(s.get("likes"))
        text = f"{sdk} · likes {likes}"
        seen[key] = mk_signal(
            id=f"huggingface-space-{sid}", source="huggingface", source_label="Hugging Face",
            region="海外", lang="en", title=sid, text=text,
            url=f"https://huggingface.co/spaces/{sid}",
            popularity=likes, comments=0,
            created_at=s.get("createdAt") or "", signal_type="launch",
            keywords=extract_keywords(f"{sid} {sdk}", "en"))

    write_raw("huggingface", list(seen.values()))


if __name__ == "__main__":
    run()
