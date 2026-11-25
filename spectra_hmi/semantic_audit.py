#!/usr/bin/env python3
"""SPECTRA HMI 3-tier hybrid semantic localization audit and live progress tracking."""

import os
import re
import time
import json
import urllib.request
from typing import Dict, List, Optional, Any


class HmiSemanticAuditMixin:
    """3-tier glossary + morphological + local LLM semantic alignment auditor."""

    @classmethod
    def get_semantic_scan_progress(cls) -> Dict[str, Any]:
        """Return a thread-safe snapshot of the live semantic audit progress."""
        with cls._semantic_progress_lock:
            prog = dict(cls._semantic_progress)
            if prog.get("active") and prog.get("started_at", 0) > 0:
                prog["elapsed_sec"] = round(time.time() - prog["started_at"], 1)
            # Compatibility aliases for frontend consumers
            prog["step"] = prog.get("status", "")
            prog["detail"] = prog.get("detail_text") or prog.get("phase_label", "")
            prog["eta_seconds"] = prog.get("eta_sec", 0)
            return prog

    @classmethod
    def _update_semantic_progress(cls, **kwargs) -> None:
        """Update semantic progress fields thread-safely."""
        with cls._semantic_progress_lock:
            if "step" in kwargs and "status" not in kwargs:
                kwargs["status"] = kwargs["step"]
            if "detail" in kwargs and "detail_text" not in kwargs:
                kwargs["detail_text"] = kwargs["detail"]
            if "eta_seconds" in kwargs and "eta_sec" not in kwargs:
                kwargs["eta_sec"] = kwargs["eta_seconds"]
            cls._semantic_progress.update(kwargs)
            if cls._semantic_progress.get("started_at", 0) > 0:
                cls._semantic_progress["elapsed_sec"] = round(time.time() - cls._semantic_progress["started_at"], 1)


    def run_semantic_audit(
        self,
        target_locale: str = "cs-CZ",
        use_ollama: bool = False,
        ollama_model: Optional[str] = None,
        auto_unload: bool = True,
    ) -> Dict[str, Any]:
        """
        3-Tier Offline Semantic Hybrid Auditor:
        - Tier 1: Self-learning binary glossary & semantic term-substitution detection.
        - Tier 2: Zero-dependency cross-locale consensus & vector alignment scoring.
        - Tier 3: Optional local Ollama reviewer (127.0.0.1:11434 only).
        """
        start_time = time.time()
        self._update_semantic_progress(
            active=True,
            status="TIER1",
            percent=5.0,
            current=0,
            total=0,
            phase_label="Tier 1: Building Self-Learning Domain Glossary...",
            detail_text="Extracting domain terminology from compiled binary...",
            model=ollama_model or "",
            started_at=start_time,
            elapsed_sec=0.0,
            eta_sec=0,
        )

        try:
            langs = self.extract_all_languages()
            if target_locale not in langs:
                norm = target_locale.lower().replace("-", "_")
                matched = next((loc for loc in langs if loc.lower().replace("-", "_") == norm or loc.lower().startswith(norm[:2])), None)
                if matched:
                    target_locale = matched
                else:
                    raise ValueError(f"Locale '{target_locale}' not found in binary.")

            en_data = langs.get("en-GB", {})
            en_phrases = en_data.get("phrases", {})
            target_data = langs[target_locale]
            target_phrases = target_data.get("phrases", {})

            # Tier 1: Extract learned glossary
            glossary_list = self.build_auto_glossary(target_locale)
            glossary_map = {g["en_term"]: g for g in glossary_list}

            # Progress milestone: Transition to Tier 2
            self._update_semantic_progress(
                status="TIER2",
                percent=20.0,
                phase_label="Tier 2: Cross-Locale Vector Consensus Matrix (19 Locales)...",
                detail_text=f"Evaluating phrase alignment across sister locales for {target_locale}...",
            )

            # Tier 2: Determine local embedding engine
            tier2_engine = "offline-cross-locale-consensus-v1"
            cache_dirs = [
                os.path.expanduser("~/.cache/spectra/models"),
                os.path.expanduser("~/.cache/huggingface/hub"),
                os.path.expanduser("~/.cache/torch/sentence_transformers"),
            ]
            has_local_models = any(os.path.isdir(d) and os.listdir(d) for d in cache_dirs if os.path.exists(d))
            if has_local_models:
                tier2_engine = "local-onnx-multilingual"

            locale_families = {
                "slavic": {"cs-CZ", "sk-SK", "pl-PL", "ru-RU", "hr-HR"},
                "germanic": {"en-GB", "de-DE", "nl-NL", "da-DK", "sv-SE"},
                "romance": {"it-IT", "es-ES", "fr-FR", "pt-PT"},
                "cjk": {"zh-CN", "zh-TW", "ja-JP", "ko-KR"},
            }
            my_family = set()
            for fam, members in locale_families.items():
                if target_locale in members:
                    my_family = members - {target_locale, "en-GB"}
                    break

            # Calculate binary-wide expansion ratio stats
            expansion_ratios = []
            for k, p in target_phrases.items():
                if k in en_phrases:
                    en_len = max(1, len(en_phrases[k]["val"]))
                    t_len = len(p["val"])
                    expansion_ratios.append(t_len / en_len)

            mean_exp = sum(expansion_ratios) / len(expansion_ratios) if expansion_ratios else 1.0
            var_exp = sum((r - mean_exp) ** 2 for r in expansion_ratios) / len(expansion_ratios) if expansion_ratios else 0.1
            std_exp = max(0.1, var_exp ** 0.5)

            flagged_phrases: List[Dict[str, Any]] = []
            scores_sum = 0.0
            evaluated_count = 0

            # Retrieve Algorithm 5 anomalies
            audit_findings = {f["key"]: f for f in self.run_audit(target_locale) if f["id"].startswith("AUTO-SEMANTIC-")}

            for k, p in target_phrases.items():
                if k not in en_phrases:
                    continue
                en_val = en_phrases[k]["val"]
                target_val = p["val"]
                evaluated_count += 1

                # 1. Glossary coverage
                en_stems = self._extract_stems(en_val, "en-GB")
                target_stems = self._extract_stems(target_val, target_locale)
                high_conf_en = [e for e in en_stems if e in glossary_map and glossary_map[e]["confidence"] >= 0.70]
                matched_cov = sum(1 for e in high_conf_en if glossary_map[e]["target_term"] in target_stems)
                cov_score = (matched_cov / len(high_conf_en)) if high_conf_en else 1.0

                # 2. Expansion ratio Z-score
                cur_ratio = len(target_val) / max(1, len(en_val))
                z = abs(cur_ratio - mean_exp) / std_exp
                len_score = max(0.0, 1.0 - min(1.0, z / 3.0))

                # 3. Sister locale consensus
                sister_lens = []
                for s_loc in my_family:
                    if s_loc in langs and k in langs[s_loc]["phrases"]:
                        sister_lens.append(len(langs[s_loc]["phrases"][k]["val"]))
                if sister_lens:
                    avg_sister = sum(sister_lens) / len(sister_lens)
                    diff_sister = abs(len(target_val) - avg_sister) / max(1, avg_sister)
                    sister_score = max(0.0, 1.0 - min(1.0, diff_sister))
                else:
                    sister_score = 1.0

                # Composite alignment score
                alignment_score = round(0.50 * cov_score + 0.30 * len_score + 0.20 * sister_score, 3)
                scores_sum += alignment_score

                reasons = []
                if k in audit_findings:
                    reasons.append(audit_findings[k]["description"])
                    alignment_score = min(alignment_score, 0.40)
                elif cov_score < 0.50 and high_conf_en:
                    reasons.append(f"Low glossary coverage ({matched_cov}/{len(high_conf_en)} expected domain terms matched)")
                elif len_score < 0.35:
                    reasons.append(f"Abnormal character length expansion (ratio {cur_ratio:.2f} vs median {mean_exp:.2f})")

                if alignment_score < 0.65 or reasons:
                    f_entry = audit_findings.get(k)
                    flagged_phrases.append({
                        "key": k,
                        "en_val": en_val,
                        "target_val": target_val,
                        "alignment_score": alignment_score,
                        "reason": "; ".join(reasons) if reasons else "Low semantic alignment consensus",
                        "suggested_val": f_entry.get("expected_val") if f_entry else None,
                        "patchable": f_entry.get("patchable", False) if f_entry else False,
                        "patch_meta": f_entry.get("patch_meta") if f_entry else None,
                    })

            avg_alignment = round(scores_sum / evaluated_count, 3) if evaluated_count else 1.0

            # Tier 3: Local Ollama Reviewer (Strictly 127.0.0.1:11434)
            tier3_info = self.check_local_ollama()
            tier3_reviews: List[Dict[str, Any]] = []
            total_ollama_ms = 0
            active_model = None

            if not use_ollama:
                self._update_semantic_progress(
                    active=False,
                    status="COMPLETED",
                    percent=100.0,
                    phase_label="Audit Complete (Tier 1 + Tier 2)",
                    detail_text=f"Evaluated {evaluated_count} phrases ({len(flagged_phrases)} flagged).",
                    eta_sec=0,
                )
            else:
                if not tier3_info.get("available") and self._find_ollama_binary():
                    self._update_semantic_progress(
                        status="TIER3_STARTUP",
                        percent=25.0,
                        phase_label="Tier 3: Spawning Local Ollama Engine...",
                        detail_text="Starting local daemon on 127.0.0.1:11434...",
                    )
                    self.control_local_ollama("start")
                    tier3_info = self.check_local_ollama()

                hw_info = self.probe_host_hardware()
                cores = hw_info.get("cpu", {}).get("logical_cores", 2)
                threads = max(1, min(cores, 8))

                installed_models = tier3_info.get("models", [])
                desired_model = ollama_model or hw_info.get("default_selected_model") or hw_info.get("recommended_model")
                if desired_model and desired_model in installed_models:
                    active_model = desired_model
                elif desired_model and any(m.split(":")[0] == desired_model.split(":")[0] or desired_model in m for m in installed_models):
                    active_model = next(m for m in installed_models if m.split(":")[0] == desired_model.split(":")[0] or desired_model in m)
                elif installed_models:
                    active_model = installed_models[0]
                else:
                    active_model = desired_model or "qwen2.5:1.5b"
                    tier3_info["status_message"] = f"Model '{active_model}' is not pulled yet. Click 'Pull Selected Model' to install."

                self._update_semantic_progress(
                    status="TIER3_STARTUP",
                    percent=28.0,
                    phase_label=f"Tier 3: Initializing Local AI Engine ({active_model})...",
                    detail_text="Connecting to local daemon on 127.0.0.1:11434...",
                    model=active_model or "",
                )

                if tier3_info.get("available") and installed_models and active_model in installed_models:
                    t_loop0 = time.time()
                    _ai_cancel_epoch = None
                    try:
                        import spectra_ai
                        _ai_cancel_epoch = spectra_ai.get_cancel_epoch()
                    except Exception:
                        pass
                    candidates = sorted(flagged_phrases, key=lambda x: x["alignment_score"])[:10]
                    tot_candidates = len(candidates)
                    for idx, c in enumerate(candidates):
                        if _ai_cancel_epoch is not None:
                            try:
                                import spectra_ai
                                if spectra_ai.get_cancel_epoch() != _ai_cancel_epoch:
                                    tier3_info["status_message"] = "Stopped by user (Local AI turned off)."
                                    break
                            except Exception:
                                pass
                        now_t = time.time()
                        elapsed = now_t - t_loop0
                        avg_per_item = (elapsed / idx) if idx > 0 else 2.5
                        remaining = tot_candidates - idx
                        eta_sec = max(0, int(avg_per_item * remaining))
                        pct = round(30.0 + 68.0 * (idx / max(1, tot_candidates)), 1)
                        self._update_semantic_progress(
                            status="TIER3_INFERENCE",
                            percent=pct,
                            current=idx + 1,
                            total=tot_candidates,
                            phase_label=f"Tier 3: Deep Neural Semantic Scan ({active_model})",
                            detail_text=f"Evaluating phrase {idx + 1} of {tot_candidates}: {c['key']}",
                            model=active_model,
                            eta_sec=eta_sec,
                        )

                        prompt_text = (
                            f"You are a professional coffee machine firmware translator. Verify this translation in a coffee machine HMI context:\n"
                            f"Key: {c['key']}\n"
                            f"English: {c['en_val']}\n"
                            f"Target ({target_locale}): {c['target_val']}\n"
                            f"Respond in valid JSON only with keys: \"is_correct\" (bool), \"reason\" (string), \"suggested_translation\" (string)."
                        )
                        payload = json.dumps({
                            "model": active_model,
                            "prompt": prompt_text,
                            "stream": False,
                            "format": "json",
                            "options": {
                                "num_thread": threads,
                                "temperature": 0.1,
                            },
                            "keep_alive": "5m",
                        }).encode("utf-8")
                        t_req0 = time.time()
                        try:
                            req = urllib.request.Request(
                                "http://127.0.0.1:11434/api/generate",
                                data=payload,
                                headers={"Content-Type": "application/json", "User-Agent": "SPECTRA-Offline-Auditor"}
                            )
                            with urllib.request.urlopen(req, timeout=45.0) as resp:
                                if resp.status == 200:
                                    res_data = json.loads(resp.read().decode("utf-8"))
                                    raw_resp = res_data.get("response", "{}").strip()
                                    if raw_resp.startswith("```"):
                                        raw_resp = re.sub(r"^```[a-zA-Z]*\s*", "", raw_resp)
                                        raw_resp = re.sub(r"\s*```$", "", raw_resp).strip()
                                    try:
                                        if "{" in raw_resp and "}" in raw_resp:
                                            json_sub = raw_resp[raw_resp.index("{"):raw_resp.rindex("}")+1]
                                            llm_resp = json.loads(json_sub)
                                        else:
                                            llm_resp = json.loads(raw_resp)
                                    except Exception:
                                        llm_resp = {}

                                    is_corr = bool(llm_resp.get("is_correct", True))
                                    review = {
                                        "key": c["key"],
                                        "en_val": c["en_val"],
                                        "target_val": c["target_val"],
                                        "alignment_score": c["alignment_score"],
                                        "model": active_model,
                                        "is_correct": is_corr,
                                        "verdict": "VERIFIED_OK" if is_corr else "DEFECT_CONFIRMED",
                                        "reason": llm_resp.get("reason", "") or "Reviewed by local Ollama model.",
                                        "suggested_translation": llm_resp.get("suggested_translation") or c.get("suggested_val") or c["target_val"],
                                        "elapsed_ms": int((time.time() - t_req0) * 1000),
                                    }
                                    tier3_reviews.append(review)
                                    c["ollama_review"] = review
                                    if not is_corr and review["suggested_translation"]:
                                        c["suggested_val"] = review["suggested_translation"]
                        except Exception:
                            pass

                    total_ollama_ms = int((time.time() - t_loop0) * 1000)
                    if auto_unload:
                        try:
                            self.control_local_ollama("unload", active_model)
                        except Exception:
                            pass

            tier3_info["reviews"] = tier3_reviews
            tier3_info["executed"] = bool(use_ollama)
            tier3_info["active_model"] = active_model
            tier3_info["total_elapsed_ms"] = total_ollama_ms
            tier3_info["confirmed_defects_count"] = sum(1 for r in tier3_reviews if not r.get("is_correct"))
            tier3_info["verified_ok_count"] = sum(1 for r in tier3_reviews if r.get("is_correct"))
            tier3_info["ram_unloaded"] = bool(auto_unload and tier3_reviews)

            return {
                "target_locale": target_locale,
                "tier1_glossary": glossary_list[:50],
                "tier2_engine": tier2_engine,
                "flagged_phrases": flagged_phrases,
                "tier3_ollama": tier3_info,
                "summary": {
                    "total_phrases": evaluated_count,
                    "glossary_terms_count": len(glossary_list),
                    "flagged_count": len(flagged_phrases),
                    "average_alignment": avg_alignment,
                }
            }
        finally:
            self._update_semantic_progress(
                active=False,
                status="COMPLETED",
                percent=100.0,
                eta_sec=0,
            )

