#!/usr/bin/env python3
"""
SPECTRA Community Calibration Harvester (`Pr0xyA-91/spectra-captures`)
======================================================================
Fetches community-submitted `[Offset Fix + Capture]` GitHub Issues from
`Pr0xyA-91/spectra-captures` (or local test JSON files), verifies embedded
`spectra.offset_patch.v1` EEPROM offset proofs, and merges verified US/EU
model variants & counter mappings into `docs/models/*.json` for upcoming
SPECTRA releases.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import tls_utils


DEFAULT_COMMUNITY_REPO = "Pr0xyA-91/spectra-captures"
DEFAULT_TARGET_PR_REPO = "Pr0xyA-91/spectra"
DEFAULT_BASE_BRANCH = "main"
PR_LINKED_MARKER = "[SPECTRA-PR-LINKED]"
DEFAULT_MODELS_DIR = os.path.join(PROJECT_DIR, "docs", "models")


def _detect_default_pr_repo() -> str:
    """Resolve target PR repo from SPECTRA_PR_REPO env or git remote.origin.url, falling back to public repo."""
    env_repo = os.environ.get("SPECTRA_PR_REPO", "").strip()
    if env_repo:
        return env_repo
    try:
        out = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=PROJECT_DIR,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
        ).decode("utf-8").strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return DEFAULT_TARGET_PR_REPO

_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _parse_addr_int(raw: Any) -> Optional[int]:
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    s = str(raw or "").strip().lower()
    if not s:
        return None
    try:
        return int(s, 16) if s.startswith("0x") or any(c in "abcdef" for c in s) else int(s, 10)
    except ValueError:
        return None


def _safe_filename_token(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(text or "").strip()).strip("_")
    return cleaned or "UNKNOWN"


def extract_payloads_from_issue_body(body: str) -> List[Dict[str, Any]]:
    """Extract candidate `spectra.offset_patch.v1` or capture bundle JSON blocks from an issue body."""
    found: List[Dict[str, Any]] = []
    for match in _JSON_FENCE_RE.finditer(body or ""):
        blob = match.group(1).strip()
        try:
            obj = json.loads(blob)
        except Exception:
            continue
        if isinstance(obj, dict) and (
            obj.get("schema") == "spectra.offset_patch.v1"
            or isinstance(obj.get("override"), dict)
            or isinstance(obj.get("ai_offset_fix"), dict)
        ):
            found.append(obj)
    return found


def verify_calibration_patch(
    payload: Dict[str, Any],
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validate structural integrity and raw EEPROM consistency of a submitted
    calibration payload (`spectra.offset_patch.v1` or capture bundle).
    """
    if not isinstance(payload, dict):
        return False, "Payload is not a JSON object", None

    ov = payload.get("override") or payload.get("ai_offset_fix") or payload
    if not isinstance(ov, dict):
        return False, "Missing override section", None

    ident = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    ef_code = str(ov.get("ef_code") or ident.get("ef_code") or "").strip().upper()
    model_name = str(ov.get("model_name") or ident.get("model_name") or "").strip()
    art_num = str(ov.get("article_number") or ident.get("article_number") or "").strip()
    serial_num = str(ov.get("serial_number") or ident.get("serial_number") or "").strip()
    market_region = str(ov.get("market_region") or ident.get("market_region") or "").strip()

    products = ov.get("products") if isinstance(ov.get("products"), list) else []
    maintenance = ov.get("maintenance") if isinstance(ov.get("maintenance"), list) else []
    maintenance_pct = ov.get("maintenance_pct") if isinstance(ov.get("maintenance_pct"), list) else []

    if not ef_code and not art_num and not model_name:
        return False, "Missing machine identifier (ef_code, article_number, or model_name)", None

    has_identity_only = bool(model_name or art_num or serial_num)
    if not products and not maintenance and not has_identity_only:
        return False, "Patch contains neither verified counters nor machine identity fields", None

    raw_eeprom = payload.get("eeprom_words") if isinstance(payload.get("eeprom_words"), dict) else {}
    eeprom_int: Dict[int, int] = {}
    for k, v in raw_eeprom.items():
        ak = _parse_addr_int(k)
        if ak is not None and isinstance(v, int):
            eeprom_int[ak] = v

    checked_prods: List[Dict[str, Any]] = []
    for p in products:
        if not isinstance(p, dict):
            continue
        addr_i = _parse_addr_int(p.get("addr") if "addr" in p else p.get("addr_hex"))
        if addr_i is None:
            continue
        joe_cnt = p.get("joe_count")
        if eeprom_int and addr_i in eeprom_int and isinstance(joe_cnt, int) and joe_cnt > 0:
            if eeprom_int[addr_i] != joe_cnt:
                return False, f"Product '{p.get('name')}' at 0x{addr_i:04X} mismatches raw EEPROM ({eeprom_int[addr_i]} != {joe_cnt})", None
        checked_prods.append({
            "name": str(p.get("name") or f"0x{addr_i:04X}").strip(),
            "addr": addr_i,
            "addr_hex": f"0x{addr_i:04X}",
            "is_double": bool(p.get("is_double", False)),
        })

    checked_maint: List[Dict[str, Any]] = []
    for m in maintenance:
        if not isinstance(m, dict):
            continue
        addr_i = _parse_addr_int(m.get("addr") if "addr" in m else m.get("addr_hex"))
        if addr_i is None:
            continue
        joe_cnt = m.get("joe_count")
        if eeprom_int and addr_i in eeprom_int and isinstance(joe_cnt, int) and joe_cnt > 0:
            if eeprom_int[addr_i] != joe_cnt:
                return False, f"Maintenance '{m.get('name')}' at 0x{addr_i:04X} mismatches raw EEPROM ({eeprom_int[addr_i]} != {joe_cnt})", None
        checked_maint.append({
            "name": str(m.get("name") or f"0x{addr_i:04X}").strip(),
            "addr": addr_i,
            "addr_hex": f"0x{addr_i:04X}",
        })

    normalized = {
        "ef_code": ef_code,
        "model_name": model_name,
        "article_number": art_num,
        "serial_number": serial_num,
        "market_region": market_region,
        "products": checked_prods,
        "maintenance": checked_maint,
        "maintenance_pct": maintenance_pct,
        "notes": str(ov.get("notes") or "").strip(),
        "source": str(ov.get("source") or "community_calibration").strip(),
    }
    return True, "Verified", normalized


def build_or_merge_model_spec(
    verified: Dict[str, Any],
    existing_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build or merge a `docs/models/*.json` specification from a verified calibration."""
    spec: Dict[str, Any] = dict(existing_spec) if isinstance(existing_spec, dict) else {}

    ef_code = verified.get("ef_code") or spec.get("ef_code") or ""
    model_name = verified.get("model_name") or spec.get("model_family") or ef_code or "Unknown"
    art_num = str(verified.get("article_number") or "").strip()
    market_region = str(verified.get("market_region") or "").strip()

    if ef_code:
        spec["ef_code"] = ef_code
    spec.setdefault("model_family", model_name)
    if model_name and (spec.get("model_family") in ("", "Unknown", "Unknown Jura")):
        spec["model_family"] = model_name

    if art_num and art_num.lower() != "unknown":
        spec.setdefault("article_number", art_num)
        arts = [str(a).strip() for a in (spec.get("article_numbers") or []) if str(a).strip()]
        if art_num not in arts:
            arts.append(art_num)
        spec["article_numbers"] = sorted(arts)
        if not spec.get("appliance_type") and model_name:
            spec["appliance_type"] = f"{art_num} {model_name}"

    if market_region:
        regions = [str(r).strip() for r in (spec.get("market_regions") or []) if str(r).strip()]
        if market_region not in regions:
            regions.append(market_region)
        spec["market_regions"] = sorted(regions)
        variants = dict(spec.get("market_variants") or {})
        v_key = f"{art_num or market_region}"
        variants[v_key] = {
            "model_name": model_name,
            "article_number": art_num,
            "market_region": market_region,
        }
        spec["market_variants"] = variants

    spec.setdefault("address_width", 4)
    spec.setdefault("max_words", 512)

    custom_regs = dict(spec.get("custom_registers") or {})
    if verified.get("products"):
        if not spec.get("products"):
            spec["products"] = [
                {
                    "code": idx,
                    "name": p["name"],
                    "is_double": bool(p.get("is_double", False)),
                    "active": True,
                }
                for idx, p in enumerate(verified["products"], start=1)
            ]
        for p in verified["products"]:
            hex_k = p["addr_hex"].replace("0x", "").upper().zfill(4)
            custom_regs[hex_k] = {
                "name": f"Product_{_safe_filename_token(p['name'])}",
                "description": f"Community-verified beverage counter: {p['name']}",
            }

    if verified.get("maintenance"):
        if not spec.get("maintenance_counters"):
            spec["maintenance_counters"] = [m["name"] for m in verified["maintenance"]]
        for m in verified["maintenance"]:
            hex_k = m["addr_hex"].replace("0x", "").upper().zfill(4)
            custom_regs[hex_k] = {
                "name": _safe_filename_token(m["name"]),
                "description": f"Community-verified maintenance counter: {m['name']}",
            }

    if custom_regs:
        spec["custom_registers"] = dict(sorted(custom_regs.items()))

    if verified.get("products") or verified.get("maintenance") or verified.get("maintenance_pct"):
        spec["verified_offsets"] = {
            "products": verified.get("products", []),
            "maintenance": verified.get("maintenance", []),
            "maintenance_pct": verified.get("maintenance_pct", []),
        }

    return spec


def _spec_output_filename(spec: Dict[str, Any]) -> str:
    ef = _safe_filename_token(str(spec.get("ef_code") or ""))
    fam = _safe_filename_token(str(spec.get("model_family") or ""))
    art = _safe_filename_token(str(spec.get("article_number") or ""))
    if ef != "UNKNOWN" and fam != "UNKNOWN":
        return f"{ef}_{fam}.json"
    if ef != "UNKNOWN":
        return f"{ef}.json"
    if art != "UNKNOWN":
        return f"ART_{art}_{fam}.json" if fam != "UNKNOWN" else f"ART_{art}.json"
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    return f"{fam}_{digest}.json"


def _github_api_request(
    method: str,
    url: str,
    token: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    """Execute a GitHub REST API JSON request using SPECTRA's hardened TLS context."""
    ctx = tls_utils.get_ssl_context()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SPECTRA-Calibration-Harvester/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data_bytes: Optional[bytes] = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
    with urllib.request.urlopen(req, context=ctx, timeout=15.0) as resp:
        raw = resp.read().decode("utf-8").strip()
    return json.loads(raw) if raw else None


def _issue_has_pr_marker(repo: str, issue_num: int, token: Optional[str] = None) -> bool:
    """Return True if any comment on `issue_num` already carries `PR_LINKED_MARKER`."""
    url = f"https://api.github.com/repos/{repo}/issues/{issue_num}/comments?per_page=100"
    try:
        comments = _github_api_request("GET", url, token=token)
    except Exception:
        return False
    if not isinstance(comments, list):
        return False
    return any(isinstance(c, dict) and PR_LINKED_MARKER in str(c.get("body") or "") for c in comments)


def _post_issue_pr_comment(
    repo: str,
    issue_num: int,
    pr_url: str,
    pr_number: int,
    token: str,
) -> None:
    """Post a deduplication comment linking a source capture issue to the integration PR."""
    url = f"https://api.github.com/repos/{repo}/issues/{issue_num}/comments"
    body = f"{PR_LINKED_MARKER} Verified calibration queued in Pull Request #{pr_number}: {pr_url}"
    _github_api_request("POST", url, token=token, payload={"body": body})


def build_pr_markdown_body(harvested_entries: List[Dict[str, Any]], source_repo: str) -> str:
    """Build a human-reviewable Markdown summary table and issue cross-references for a PR."""
    lines = [
        "## Community Calibration Integration Summary",
        "",
        f"Automatically harvested and EEPROM-verified from `{source_repo}` open capture issues.",
        "",
        "| Source Issue | EF Code | Model | Article # | Market | Counters (Prod / Maint) | Target Spec |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    ref_issues: List[int] = []
    seen_refs = set()
    for entry in harvested_entries:
        issue_num = entry.get("issue_number")
        issue_col = f"#{issue_num}" if isinstance(issue_num, int) and issue_num > 0 else "Local"
        if isinstance(issue_num, int) and issue_num > 0 and issue_num not in seen_refs:
            seen_refs.add(issue_num)
            ref_issues.append(issue_num)
        ef = entry.get("ef_code") or "—"
        model = entry.get("model_name") or "—"
        art = entry.get("article_number") or "—"
        market = entry.get("market_region") or "—"
        prods = int(entry.get("products_count") or 0)
        maint = int(entry.get("maintenance_count") or 0)
        target = entry.get("target_file") or "—"
        lines.append(
            f"| {issue_col} | `{ef}` | {model} | `{art}` | {market} | {prods} / {maint} | `{target}` |"
        )

    if ref_issues:
        lines.extend(["", "### Referenced Capture Issues", ""])
        for num in ref_issues:
            lines.append(f"- Refs {source_repo}#{num}")

    return "\n".join(lines) + "\n"


def create_calibration_pull_request(
    pr_repo: str,
    base_branch: str,
    file_changes: Dict[str, str],
    harvested_entries: List[Dict[str, Any]],
    source_repo: str,
    token: str,
    branch_name: Optional[str] = None,
    comment_issues: bool = False,
) -> Dict[str, Any]:
    """Commit verified `docs/models/*.json` specs to a branch and open/update a review PR."""
    if not token:
        raise ValueError("GitHub token is required to create a calibration Pull Request.")
    if not file_changes:
        raise ValueError("No verified calibration file changes to commit.")

    if not branch_name:
        digest = hashlib.sha256(
            json.dumps(sorted(file_changes.items()), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        branch_name = f"calibrations/community-sync-{digest[:10]}"

    base_ref = _github_api_request(
        "GET",
        f"https://api.github.com/repos/{pr_repo}/git/ref/heads/{base_branch}",
        token=token,
    )
    base_sha = base_ref["object"]["sha"]

    try:
        _github_api_request(
            "GET",
            f"https://api.github.com/repos/{pr_repo}/git/ref/heads/{branch_name}",
            token=token,
        )
    except Exception:
        _github_api_request(
            "POST",
            f"https://api.github.com/repos/{pr_repo}/git/refs",
            token=token,
            payload={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )

    files_committed: List[str] = []
    for rel_path, content_str in sorted(file_changes.items()):
        blob_sha: Optional[str] = None
        try:
            existing = _github_api_request(
                "GET",
                f"https://api.github.com/repos/{pr_repo}/contents/{rel_path}?ref={branch_name}",
                token=token,
            )
            if isinstance(existing, dict):
                blob_sha = existing.get("sha")
        except Exception:
            blob_sha = None

        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
        put_payload: Dict[str, Any] = {
            "message": f"chore(calibrations): update {os.path.basename(rel_path)} from community capture",
            "content": content_b64,
            "branch": branch_name,
        }
        if blob_sha:
            put_payload["sha"] = blob_sha

        _github_api_request(
            "PUT",
            f"https://api.github.com/repos/{pr_repo}/contents/{rel_path}",
            token=token,
            payload=put_payload,
        )
        files_committed.append(rel_path)

    owner = pr_repo.split("/")[0]
    existing_prs = _github_api_request(
        "GET",
        f"https://api.github.com/repos/{pr_repo}/pulls?state=open&head={owner}:{branch_name}&base={base_branch}",
        token=token,
    )

    pr_title = f"chore(calibrations): integrate {len(harvested_entries)} verified community offset fix(es)"
    pr_body = build_pr_markdown_body(harvested_entries, source_repo)

    if isinstance(existing_prs, list) and existing_prs:
        pr_num = int(existing_prs[0]["number"])
        pr_resp = _github_api_request(
            "PATCH",
            f"https://api.github.com/repos/{pr_repo}/pulls/{pr_num}",
            token=token,
            payload={"title": pr_title, "body": pr_body},
        )
        created_bool = False
    else:
        pr_resp = _github_api_request(
            "POST",
            f"https://api.github.com/repos/{pr_repo}/pulls",
            token=token,
            payload={"title": pr_title, "head": branch_name, "base": base_branch, "body": pr_body},
        )
        created_bool = True

    pr_number = int(pr_resp["number"])
    pr_url = str(pr_resp.get("html_url") or pr_resp.get("url") or "")

    if comment_issues:
        commented = set()
        for entry in harvested_entries:
            issue_num = entry.get("issue_number")
            if isinstance(issue_num, int) and issue_num > 0 and issue_num not in commented:
                commented.add(issue_num)
                _post_issue_pr_comment(source_repo, issue_num, pr_url, pr_number, token)

    return {
        "created": created_bool,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "branch_name": branch_name,
        "pr_repo": pr_repo,
        "base_branch": base_branch,
        "files_committed": files_committed,
    }


def _fetch_github_issues(repo: str, token: Optional[str] = None, max_pages: int = 3) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=50&page={page}"
        batch = _github_api_request("GET", url, token=token)
        if not isinstance(batch, list) or not batch:
            break
        issues.extend(batch)
        if len(batch) < 50:
            break
    return issues


def sync_calibrations(
    repo: str = DEFAULT_COMMUNITY_REPO,
    models_dir: str = DEFAULT_MODELS_DIR,
    apply_changes: bool = False,
    input_file: Optional[str] = None,
    token: Optional[str] = None,
    create_pr: bool = False,
    pr_repo: str = DEFAULT_TARGET_PR_REPO,
    base_branch: str = DEFAULT_BASE_BRANCH,
    branch_name: Optional[str] = None,
    comment_issues: bool = False,
    include_linked: bool = False,
) -> Dict[str, Any]:
    """
    Harvest verified community calibrations into `models_dir` and optionally open
    a reviewable Pull Request in `pr_repo`.
    Returns summary dict containing verified specs, skipped entries, written file paths,
    and optional `pull_request` metadata.
    """
    os.makedirs(models_dir, exist_ok=True)
    issues: List[Dict[str, Any]] = []
    if input_file:
        with open(input_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            issues = raw
        elif isinstance(raw, dict):
            if "body" in raw:
                issues = [raw]
            else:
                issues = [{"number": 0, "title": "Local Patch", "body": f"```json\n{json.dumps(raw)}\n```"}]
    else:
        issues = _fetch_github_issues(repo, token=token)

    existing_by_key: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    for fname in sorted(os.listdir(models_dir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(models_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                sdata = json.load(f)
            if isinstance(sdata, dict):
                if sdata.get("ef_code"):
                    existing_by_key[str(sdata["ef_code"]).strip().upper()] = (fpath, sdata)
                if sdata.get("article_number"):
                    existing_by_key[f"ART:{str(sdata['article_number']).strip()}"] = (fpath, sdata)
        except Exception:
            continue

    verified_count = 0
    skipped: List[Dict[str, Any]] = []
    updated_files: List[str] = []
    file_changes: Dict[str, str] = {}
    harvested_entries: List[Dict[str, Any]] = []

    for issue in issues:
        if not isinstance(issue, dict) or issue.get("pull_request"):
            continue
        issue_num = issue.get("number")
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")

        if not input_file and not include_linked and isinstance(issue_num, int) and issue_num > 0:
            if PR_LINKED_MARKER in body or _issue_has_pr_marker(repo, issue_num, token=token):
                skipped.append({"issue": issue_num, "title": title, "reason": "Already linked to a calibration PR"})
                continue

        payloads = extract_payloads_from_issue_body(body)
        if not payloads:
            continue

        for payload in payloads:
            ok, reason, verified = verify_calibration_patch(payload)
            if not ok or verified is None:
                skipped.append({"issue": issue_num, "title": title, "reason": reason})
                continue

            ef = verified.get("ef_code") or ""
            art = verified.get("article_number") or ""
            target_path: Optional[str] = None
            existing_spec: Optional[Dict[str, Any]] = None

            if ef and ef in existing_by_key:
                target_path, existing_spec = existing_by_key[ef]
            elif art and f"ART:{art}" in existing_by_key:
                target_path, existing_spec = existing_by_key[f"ART:{art}"]

            merged = build_or_merge_model_spec(verified, existing_spec=existing_spec)
            if not target_path:
                target_path = os.path.join(models_dir, _spec_output_filename(merged))

            if ef:
                existing_by_key[ef] = (target_path, merged)
            if art:
                existing_by_key[f"ART:{art}"] = (target_path, merged)

            serialized = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
            rel_repo_path = f"docs/models/{os.path.basename(target_path)}"
            file_changes[rel_repo_path] = serialized
            harvested_entries.append({
                "issue_number": issue_num,
                "title": title,
                "ef_code": ef,
                "model_name": verified.get("model_name") or merged.get("model_family") or "",
                "article_number": art,
                "market_region": verified.get("market_region") or "",
                "products_count": len(verified.get("products") or []),
                "maintenance_count": len(verified.get("maintenance") or []),
                "target_file": rel_repo_path,
            })

            if apply_changes:
                with open(target_path, "w", encoding="utf-8") as out:
                    out.write(serialized)
                if target_path not in updated_files:
                    updated_files.append(target_path)
            verified_count += 1

    result: Dict[str, Any] = {
        "ok": True,
        "issues_scanned": len(issues),
        "verified_calibrations": verified_count,
        "skipped": skipped,
        "updated_files": updated_files,
        "applied": apply_changes,
        "harvested_entries": harvested_entries,
    }

    if create_pr and file_changes:
        result["pull_request"] = create_calibration_pull_request(
            pr_repo=pr_repo,
            base_branch=base_branch,
            file_changes=file_changes,
            harvested_entries=harvested_entries,
            source_repo=repo,
            token=token or "",
            branch_name=branch_name,
            comment_issues=comment_issues,
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest verified SPECTRA calibrations from GitHub captures repo.")
    parser.add_argument("--repo", default=DEFAULT_COMMUNITY_REPO, help="GitHub repository (default: Pr0xyA-91/spectra-captures)")
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR, help="Target docs/models directory")
    parser.add_argument("--input-file", default=None, help="Optional local JSON file (issue list or patch) for offline harvesting")
    parser.add_argument("--apply", action="store_true", help="Write verified specs into docs/models/*.json")
    parser.add_argument("--create-pr", action="store_true", help="Create or update a GitHub Pull Request with verified docs/models/*.json changes")
    parser.add_argument("--pr-repo", default=_detect_default_pr_repo(), help="Target repository for calibration Pull Requests")
    parser.add_argument("--base-branch", default=DEFAULT_BASE_BRANCH, help="Target base branch for Pull Requests (default: main)")
    parser.add_argument("--branch-name", default=None, help="Optional explicit branch name for the calibration PR")
    parser.add_argument("--comment-issues", action="store_true", help="Post [SPECTRA-PR-LINKED] comment on source capture issues")
    parser.add_argument("--include-linked", action="store_true", help="Include issues already commented with [SPECTRA-PR-LINKED]")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or None
    if not token:
        try:
            import github_auth
            resolved = github_auth.resolve_token()
            if resolved:
                token = resolved.get("token")
        except Exception:
            pass

    res = sync_calibrations(
        repo=args.repo,
        models_dir=args.models_dir,
        apply_changes=bool(args.apply),
        input_file=args.input_file,
        token=token,
        create_pr=bool(args.create_pr),
        pr_repo=args.pr_repo,
        base_branch=args.base_branch,
        branch_name=args.branch_name,
        comment_issues=bool(args.comment_issues),
        include_linked=bool(args.include_linked),
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
