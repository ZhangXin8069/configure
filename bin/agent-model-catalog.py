#!/usr/bin/env python3
"""Provider model catalog refresh and model/strength resolution for agent.sh."""

import argparse
import difflib
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


SCHEMA = "agent-model-catalog/v1"
DEFAULT_STRENGTHS = [
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
]
STRENGTH_RANK = {name: index for index, name in enumerate(DEFAULT_STRENGTHS)}


def eprint(message):
    print(message, file=sys.stderr)


def deep_merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(merged.get(key), value)
        return merged
    return override


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_config(base_path, custom_path):
    base = load_json(base_path)
    custom = load_json(custom_path)
    if not isinstance(base, dict) or not isinstance(custom, dict):
        raise ValueError("config root must be a JSON object")
    return deep_merge(base, custom)


def sanitize(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("_")
    return cleaned or "provider"


def bool_value(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def int_value(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def provider_config(config, provider):
    providers = config.get("providers") or {}
    value = providers.get(provider)
    return value if isinstance(value, dict) else {}


def static_model_entries(provider):
    entries = {}

    def add_model(model_id, metadata=None):
        model_id = str(model_id or "").strip()
        if not model_id:
            return
        model_id = model_id.split("/", 1)[-1]
        existing = entries.setdefault(model_id, {"id": model_id})
        if isinstance(metadata, dict):
            existing.update(metadata)

    models = provider.get("models")
    if isinstance(models, dict):
        for model_id, metadata in models.items():
            add_model(model_id, metadata)
    elif isinstance(models, list):
        for model in models:
            if isinstance(model, dict):
                add_model(model.get("id") or model.get("model") or model.get("name"), model)
            else:
                add_model(model)

    catalog = provider.get("model_catalog")
    if isinstance(catalog, dict):
        for model_id, metadata in catalog.items():
            add_model(model_id, metadata)
    elif isinstance(catalog, list):
        for model in catalog:
            if isinstance(model, dict):
                add_model(model.get("id") or model.get("model") or model.get("name"), model)
            else:
                add_model(model)

    opencode = provider.get("opencode") or {}
    if isinstance(opencode, dict):
        for model in opencode.get("models") or []:
            if isinstance(model, dict):
                add_model(model.get("id") or model.get("model") or model.get("name"), model)
            else:
                add_model(model)

    return entries


def extract_reasoning_strengths(entry):
    strengths = []
    values = entry.get("supported_strengths") if isinstance(entry, dict) else None
    if isinstance(values, str):
        values = [values]
    if isinstance(values, list):
        strengths.extend(str(value).strip().lower() for value in values if str(value).strip())
    options = entry.get("reasoning_options") if isinstance(entry, dict) else None
    if isinstance(options, list):
        for option in options:
            if not isinstance(option, dict) or str(option.get("type") or "") != "effort":
                continue
            for value in option.get("values") or []:
                value = str(value).strip().lower()
                if value and value not in strengths:
                    strengths.append(value)
    return strengths


def normalize_model_entry(model_id, metadata=None):
    entry = {"id": str(model_id)}
    if isinstance(metadata, dict):
        for key in ("id", "name", "display_name", "description", "context_window", "limit", "reasoning", "reasoning_options"):
            if key in metadata:
                entry[key] = metadata[key]
    entry["id"] = str(entry.get("id") or model_id)
    entry["supported_strengths"] = extract_reasoning_strengths(entry)
    if isinstance(entry.get("limit"), dict) and "context_window" not in entry:
        context = entry["limit"].get("context")
        if context is not None:
            entry["context_window"] = context
    return entry


def parse_models_payload(payload):
    entries = {}

    def add(model_id, metadata=None):
        model_id = str(model_id or "").strip()
        if not model_id:
            return
        entries[model_id] = normalize_model_entry(model_id, metadata)

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                add(item.get("id") or item.get("model") or item.get("name"), item)
            else:
                add(item)
    elif isinstance(payload, dict):
        data = payload.get("data")
        models = payload.get("models")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    add(item.get("id") or item.get("model") or item.get("name"), item)
                else:
                    add(item)
        elif isinstance(models, list):
            for item in models:
                if isinstance(item, dict):
                    add(item.get("id") or item.get("model") or item.get("name"), item)
                else:
                    add(item)
        elif isinstance(models, dict):
            for model_id, metadata in models.items():
                add(model_id, metadata)
        else:
            for model_id, metadata in payload.items():
                if isinstance(metadata, (dict, type(None))):
                    add(model_id, metadata)
    return entries


def fetch_bytes(url, headers, timeout):
    url = os.path.expandvars(str(url or ""))
    if not url:
        raise ValueError("empty URL")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception as primary_error:
        curl = shutil.which("curl")
        if not curl:
            raise primary_error
        config_lines = [
            "silent",
            "show-error",
            "fail",
            "location",
            "max-time = %d" % max(1, int(timeout)),
        ]
        for name, value in headers.items():
            safe_name = str(name).replace('"', '\\"')
            safe_value = str(value).replace("\\", "\\\\").replace('"', '\\"')
            config_lines.append('header = "%s: %s"' % (safe_name, safe_value))
        try:
            result = subprocess.run(
                [curl, "--config", "-", "--url", url],
                input=("\n".join(config_lines) + "\n").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(1, int(timeout)) + 2,
                check=False,
            )
        except Exception:
            raise primary_error
        if result.returncode != 0:
            raise primary_error
        return result.stdout


def decode_json(data, source):
    try:
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ValueError("无法解析 JSON（%s）：%s" % (source, exc))


def request_headers(provider):
    auth_mode = str(provider.get("models_auth") or "none").strip().lower()
    if auth_mode in {"", "none", "off"}:
        return {}
    env_name = str(provider.get("env_key") or "")
    token = os.environ.get(env_name, "") if env_name else ""
    if not token:
        raise RuntimeError("缺少模型目录认证变量 %s" % (env_name or "<未配置>"))
    if auth_mode in {"api_key", "x-api-key"}:
        return {"x-api-key": token}
    return {"Authorization": "Bearer %s" % token}


def load_cache(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        data = load_json(path)
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        return None
    return data


def cache_is_fresh(cache, ttl):
    if not cache:
        return False
    if ttl <= 0:
        return False
    try:
        age = int(os.environ.get("AGENT_MODEL_NOW", "")) - int(cache.get("updated_at", 0))
    except (TypeError, ValueError):
        return False
    return age >= 0 and age < ttl


def write_cache(path, cache):
    if not path:
        return
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    text = json.dumps(cache, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=".models.", dir=parent or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def metadata_url(config, provider):
    discovery = config.get("model_discovery") or {}
    value = os.environ.get("AGENT_MODEL_METADATA_URL") or discovery.get("metadata_url") or ""
    provider_name = str(provider.get("models_metadata_provider") or "")
    if not value or not provider_name:
        return ""
    return str(value)


def merge_model_maps(*maps):
    result = {}
    for entries in maps:
        if isinstance(entries, dict):
            for model_id, metadata in entries.items():
                normalized = normalize_model_entry(model_id, metadata)
                current = result.setdefault(model_id, {})
                for key, value in normalized.items():
                    if value not in (None, "", [], {}) or key not in current:
                        current[key] = value
                strengths = []
                for value in (current.get("supported_strengths") or []):
                    if value not in strengths:
                        strengths.append(value)
                current["supported_strengths"] = strengths
    return result


def refresh_catalog(config, provider_name, cache_path):
    provider = provider_config(config, provider_name)
    discovery = config.get("model_discovery") or {}
    enabled = bool_value(
        os.environ.get("AGENT_MODEL_DISCOVERY"),
        bool_value(discovery.get("enabled"), True),
    )
    ttl = int_value(os.environ.get("AGENT_MODEL_CACHE_TTL"), int_value(discovery.get("cache_ttl_seconds"), 21600))
    timeout = int_value(os.environ.get("AGENT_MODEL_HTTP_TIMEOUT"), int_value(discovery.get("timeout_seconds"), 5))
    static_entries = static_model_entries(provider)
    cached = load_cache(cache_path)
    warnings = []

    if not enabled or cache_is_fresh(cached, ttl):
        if not enabled and not cached:
            return {
                "schema": SCHEMA,
                "provider": provider_name,
                "updated_at": 0,
                "sources": ["static"],
                "models": static_entries,
            }, warnings
        return cached or {
            "schema": SCHEMA,
            "provider": provider_name,
            "updated_at": 0,
            "sources": ["static"],
            "models": static_entries,
        }, warnings

    dynamic_entries = {}
    metadata_entries = {}
    sources = []
    models_url = provider.get("models_url") or ""
    if models_url:
        try:
            payload = decode_json(
                fetch_bytes(models_url, request_headers(provider), timeout),
                str(models_url),
            )
            dynamic_entries = parse_models_payload(payload)
            if dynamic_entries:
                sources.append(str(models_url))
            else:
                warnings.append("模型接口 %s 未返回可用模型，已尝试其他来源" % models_url)
        except Exception as exc:
            warnings.append("模型清单刷新失败（%s）：%s，尝试其他来源" % (models_url, exc))
    elif provider.get("models_metadata_provider"):
        warnings.append("途径 %s 未配置 models_url，使用 models.dev 元数据" % provider_name)

    meta_url = metadata_url(config, provider)
    metadata_provider = str(provider.get("models_metadata_provider") or "")
    if meta_url and metadata_provider:
        try:
            metadata_payload = decode_json(fetch_bytes(meta_url, {}, timeout), meta_url)
            provider_metadata = metadata_payload.get(metadata_provider) if isinstance(metadata_payload, dict) else None
            metadata_models = provider_metadata.get("models") if isinstance(provider_metadata, dict) else None
            if isinstance(metadata_models, dict):
                metadata_entries = merge_model_maps(metadata_models)
                if metadata_entries:
                    sources.append(meta_url)
            else:
                warnings.append("models.dev 中没有途径 %s 的模型元数据" % metadata_provider)
        except Exception as exc:
            warnings.append("模型元数据刷新失败（%s）：%s" % (meta_url, exc))

    if not dynamic_entries and not metadata_entries:
        if cached:
            warnings.append("所有在线模型来源均失败，继续使用缓存目录")
            return cached, warnings
        warnings.append("所有在线模型来源均失败，继续使用静态模型目录")
        return {
            "schema": SCHEMA,
            "provider": provider_name,
            "updated_at": 0,
            "sources": ["static"],
            "models": static_entries,
        }, warnings

    if dynamic_entries:
        supported_ids = set(dynamic_entries)
        static_for_merge = {
            model_id: metadata
            for model_id, metadata in static_entries.items()
            if model_id in supported_ids
        }
        metadata_for_merge = {
            model_id: metadata
            for model_id, metadata in metadata_entries.items()
            if model_id in supported_ids
        }
        merged = merge_model_maps(static_for_merge, dynamic_entries, metadata_for_merge)
    else:
        merged = merge_model_maps(static_entries, metadata_entries)
    if not merged and cached:
        merged = cached.get("models") or {}
        sources = list(cached.get("sources") or ["cache"])
    updated = int(os.environ.get("AGENT_MODEL_NOW", "0") or 0)
    if updated <= 0:
        try:
            import time
            updated = int(time.time())
        except Exception:
            updated = 0
    result = {
        "schema": SCHEMA,
        "provider": provider_name,
        "updated_at": updated,
        "sources": sources,
        "models": merged,
    }
    write_cache(cache_path, result)
    return result, warnings


def strip_context_suffix(value):
    match = re.search(r"(\[[^\]]+\])$", value)
    if not match:
        return value, ""
    return value[: match.start()], match.group(1)


def strip_provider_prefix(value, provider_name, provider):
    if "/" not in value:
        return value, ""
    prefix, rest = value.split("/", 1)
    aliases = {
        provider_name,
        str(provider.get("opencode_provider_id") or ""),
    }
    if prefix in aliases and rest:
        return rest, prefix
    return value, ""


def normalization_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def token_sequence(query, candidate):
    query_tokens = [token for token in re.split(r"[^a-z0-9]+", query.lower()) if token]
    candidate_tokens = [token for token in re.split(r"[^a-z0-9]+", candidate.lower()) if token]
    if not query_tokens:
        return False
    index = 0
    for token in candidate_tokens:
        if index < len(query_tokens) and token == query_tokens[index]:
            index += 1
    return index == len(query_tokens)


def match_score(query, candidate):
    q_lower = query.lower()
    c_lower = candidate.lower()
    q_key = normalization_key(query)
    c_key = normalization_key(candidate)
    if q_lower == c_lower:
        return 200.0
    if q_key and q_key == c_key:
        return 190.0
    if q_key and q_key in c_key:
        return 170.0 - (len(c_key) - len(q_key)) * 0.2
    if c_key and c_key in q_key:
        return 160.0 - (len(q_key) - len(c_key)) * 0.2
    if token_sequence(query, candidate):
        return 145.0 - abs(len(q_key) - len(c_key)) * 0.1
    ratio = difflib.SequenceMatcher(None, q_key, c_key).ratio()
    if ratio >= 0.68:
        return ratio * 120.0
    return 0.0


def model_match(entries, query, assert_match):
    query = str(query or "").strip()
    if not query:
        raise ValueError("模型名为空")
    base, suffix = strip_context_suffix(query)
    if any(char in base for char in "*?[]"):
        matches = [
            model_id
            for model_id in entries
            if fnmatch.fnmatch(model_id.lower(), base.lower())
        ]
    else:
        matches = []
        for model_id, entry in entries.items():
            aliases = [model_id]
            display = entry.get("display_name") or entry.get("name")
            if display:
                aliases.append(str(display))
            if any(match_score(base, alias) > 0 for alias in aliases):
                matches.append(model_id)
    if not matches:
        if assert_match:
            raise ValueError("模型 '%s' 未在途径模型清单中匹配到可用模型" % query)
        return base + suffix, "unknown"

    ranked = []
    for model_id in matches:
        entry = entries.get(model_id) or {}
        aliases = [model_id]
        display = entry.get("display_name") or entry.get("name")
        if display:
            aliases.append(str(display))
        score = max(match_score(base, alias) for alias in aliases)
        ranked.append((score, model_id))
    ranked.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    best_score = ranked[0][0]
    best = [model_id for score, model_id in ranked if abs(score - best_score) < 0.01]
    if len(best) > 1:
        starts = [model_id for model_id in best if normalization_key(model_id).startswith(normalization_key(base))]
        if len(starts) == 1:
            best = starts
        else:
            raise ValueError(
                "模型 '%s' 匹配到多个候选：%s（请补充名称）"
                % (query, ", ".join(sorted(best)[:6]))
            )
    canonical = best[0]
    mode = "exact" if normalization_key(canonical) == normalization_key(base) else "fuzzy"
    return canonical + suffix, mode


def resolve_strength(entry, requested, provider):
    requested = str(requested or "").strip().lower()
    if not requested:
        requested = "max"
    supported = list(entry.get("supported_strengths") or [])
    if not supported:
        values = provider.get("supported_strengths") or []
        if isinstance(values, str):
            values = [values]
        supported = [str(value).strip().lower() for value in values if str(value).strip()]
    if not supported:
        supported = list(DEFAULT_STRENGTHS)

    known_supported = sorted(
        {value for value in supported if value in STRENGTH_RANK},
        key=lambda value: STRENGTH_RANK[value],
    )
    if requested not in STRENGTH_RANK or not known_supported:
        return requested, "unverified"
    if requested in known_supported:
        return requested, "exact"
    lower = [value for value in known_supported if STRENGTH_RANK[value] < STRENGTH_RANK[requested]]
    if lower:
        return lower[-1], "clamped"
    return known_supported[0], "clamped"


def final_model_id(agent, provider_name, provider, model_id):
    if agent != "opencode":
        return model_id
    if "/" in model_id:
        return model_id
    provider_id = str(provider.get("opencode_provider_id") or provider_name)
    return "%s/%s" % (provider_id, model_id)


def codex_compatibility(provider, entry, model_id):
    codex_config = provider.get("codex") or {}
    if not isinstance(codex_config, dict):
        codex_config = {}
    wire_api = str(entry.get("codex_wire_api") or provider.get("wire_api") or "responses")
    bridge_patterns = codex_config.get("bridge_models") or []
    if isinstance(bridge_patterns, str):
        bridge_patterns = [bridge_patterns]
    model_key = str(model_id or "").lower()
    for pattern in bridge_patterns:
        pattern = str(pattern or "").strip().lower()
        if pattern and fnmatch.fnmatchcase(model_key, pattern):
            return wire_api, "", str(codex_config.get("bridge_protocol") or "chat_completions")
    patterns = codex_config.get("unsupported_models") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    for pattern in patterns:
        pattern = str(pattern or "").strip().lower()
        if pattern and fnmatch.fnmatchcase(model_key, pattern):
            return "unsupported", str(
                codex_config.get("unsupported_reason")
                or "该模型不支持 Codex 所需的 Responses 协议"
            ), ""
    return wire_api, "", ""


def claude_compatibility(provider, entry, model_id):
    claude_config = provider.get("claude") or {}
    if not isinstance(claude_config, dict):
        claude_config = {}
    wire_api = str(entry.get("claude_wire_api") or "messages")
    bridge_patterns = claude_config.get("bridge_models") or []
    if isinstance(bridge_patterns, str):
        bridge_patterns = [bridge_patterns]
    model_key = str(model_id or "").lower()
    for pattern in bridge_patterns:
        pattern = str(pattern or "").strip().lower()
        if pattern and fnmatch.fnmatchcase(model_key, pattern):
            return wire_api, "", str(claude_config.get("bridge_protocol") or "chat_completions")
    patterns = claude_config.get("unsupported_models") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    for pattern in patterns:
        pattern = str(pattern or "").strip().lower()
        if pattern and fnmatch.fnmatchcase(model_key, pattern):
            return "unsupported", str(
                claude_config.get("unsupported_reason")
                or "该模型不支持 Anthropic Messages 协议"
            ), ""
    return wire_api, "", ""


def resolve_selection(config, provider_name, agent, model_query, strength_query, assert_model_match, cache_path):
    provider = provider_config(config, provider_name)
    catalog, warnings = refresh_catalog(config, provider_name, cache_path)
    entries = catalog.get("models") or static_model_entries(provider)

    model_base, context_suffix = strip_context_suffix(str(model_query or "").strip())
    model_base, prefix = strip_provider_prefix(model_base, provider_name, provider)
    resolved_base, model_mode = model_match(entries, model_base + context_suffix, assert_model_match)
    resolved_base, matched_suffix = strip_context_suffix(resolved_base)
    context_suffix = matched_suffix or context_suffix
    model_id = final_model_id(agent, provider_name, provider, resolved_base + context_suffix)
    if prefix and agent == "opencode" and "/" not in model_id:
        model_id = "%s/%s" % (prefix, model_id)

    entry = entries.get(resolved_base) or {}
    if model_mode == "unknown":
        strength = str(strength_query or "max").strip().lower()
        strength_mode = "unverified"
    else:
        strength, strength_mode = resolve_strength(entry, strength_query, provider)
    codex_wire_api, codex_unsupported_reason, codex_bridge_protocol = codex_compatibility(
        provider, entry, resolved_base
    )
    claude_wire_api, claude_unsupported_reason, claude_bridge_protocol = claude_compatibility(
        provider, entry, resolved_base
    )
    if model_mode == "fuzzy":
        warnings.append("模型 '%s' 未精确匹配，已使用 '%s'" % (model_query, model_id))
    if strength_mode == "clamped":
        warnings.append(
            "模型 '%s' 不支持强度 '%s'，已顺延为 '%s'"
            % (resolved_base, str(strength_query or "max").lower(), strength)
        )
    return {
        "provider": provider_name,
        "agent": agent,
        "model": model_id,
        "model_base": resolved_base,
        "model_match": model_mode,
        "strength": strength,
        "strength_match": strength_mode,
        "codex_wire_api": codex_wire_api,
        "codex_unsupported_reason": codex_unsupported_reason,
        "codex_bridge_protocol": codex_bridge_protocol,
        "claude_wire_api": claude_wire_api,
        "claude_unsupported_reason": claude_unsupported_reason,
        "claude_bridge_protocol": claude_bridge_protocol,
        "warnings": warnings,
        "sources": catalog.get("sources") or [],
    }, warnings


def shell_quote(value):
    value = str(value or "")
    return "'" + value.replace("'", "'\"'\"'") + "'"


def emit_shell(result, warnings):
    print("RESOLVED_MODEL=%s" % shell_quote(result["model"]))
    print("RESOLVED_MODEL_BASE=%s" % shell_quote(result["model_base"]))
    print("RESOLVED_MODEL_MATCH=%s" % shell_quote(result["model_match"]))
    print("RESOLVED_STRENGTH=%s" % shell_quote(result["strength"]))
    print("RESOLVED_STRENGTH_MATCH=%s" % shell_quote(result["strength_match"]))
    print("RESOLVED_CODEX_WIRE_API=%s" % shell_quote(result["codex_wire_api"]))
    print("RESOLVED_CODEX_UNSUPPORTED_REASON=%s" % shell_quote(result["codex_unsupported_reason"]))
    print("RESOLVED_CODEX_BRIDGE_PROTOCOL=%s" % shell_quote(result["codex_bridge_protocol"]))
    print("RESOLVED_CLAUDE_WIRE_API=%s" % shell_quote(result["claude_wire_api"]))
    print("RESOLVED_CLAUDE_UNSUPPORTED_REASON=%s" % shell_quote(result["claude_unsupported_reason"]))
    print("RESOLVED_CLAUDE_BRIDGE_PROTOCOL=%s" % shell_quote(result["claude_bridge_protocol"]))
    print("RESOLVED_WARNING_COUNT=%d" % len(warnings))
    for index, warning in enumerate(warnings):
        print("RESOLVED_WARNING_%d=%s" % (index, shell_quote(warning)))


def provider_json(config, base_json, provider_name, cache_path):
    try:
        base = json.loads(base_json or "{}")
    except Exception:
        base = {}
    provider = provider_config(config, provider_name)
    provider_id = str(provider.get("opencode_provider_id") or provider_name)
    cache = load_cache(cache_path)
    models = {}
    if isinstance(cache, dict):
        models.update(cache.get("models") or {})
    if not models:
        models.update(static_model_entries(provider))
    block = base.get(provider_id)
    if isinstance(block, dict) and isinstance(block.get("models"), dict):
        block["models"] = {model_id: {} for model_id in sorted(models)}
    print(json.dumps(base, ensure_ascii=False, separators=(",", ":")))


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--custom-config", required=True)
    parser.add_argument("--cache")
    subparsers = parser.add_subparsers(dest="command", required=True)

    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--provider", required=True)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--provider", required=True)
    resolve.add_argument("--agent", required=True)
    resolve.add_argument("--model", default="")
    resolve.add_argument("--strength", default="")
    resolve.add_argument("--assert-model-match", action="store_true")

    provider = subparsers.add_parser("provider-json")
    provider.add_argument("--provider", required=True)
    provider.add_argument("--base-json", default="{}")
    return parser


def main():
    args = build_parser().parse_args()
    try:
        config = load_config(args.config, args.custom_config)
        if args.command == "refresh":
            result, warnings = refresh_catalog(config, args.provider, args.cache)
        elif args.command == "provider-json":
            provider_json(config, args.base_json, args.provider, args.cache)
            return 0
        else:
            result, warnings = resolve_selection(
                config,
                args.provider,
                args.agent,
                args.model,
                args.strength,
                args.assert_model_match,
                args.cache,
            )
            emit_shell(result, warnings)
            return 0
    except Exception as exc:
        eprint("agent-model-catalog: ERROR: %s" % exc)
        return 64

    result["warnings"] = warnings
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
