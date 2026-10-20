#!/usr/bin/env python3
"""Search scholarly sources and retrieve arXiv LaTeX sources safely."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import io
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any


USER_AGENT = "configure-get-paper/1.0"
MAX_METADATA_BYTES = 32 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
DEFAULT_EXTRACT_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_FILES = 10_000
TEXT_SCAN_BYTES = 4 * 1024 * 1024
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "their", "this", "to", "using",
    "via", "with", "we", "our", "can", "will", "主任务", "论文", "研究",
}
GREEK_TRANSLATION = str.maketrans(
    {
        "α": " alpha ",
        "β": " beta ",
        "γ": " gamma ",
        "δ": " delta ",
        "κ": " k ",
        "λ": " lambda ",
        "μ": " mu ",
        "ν": " nu ",
        "π": " pi ",
        "ρ": " rho ",
        "σ": " sigma ",
        "τ": " tau ",
        "φ": " phi ",
        "χ": " chi ",
        "ψ": " psi ",
        "ω": " omega ",
    }
)


class GetPaperError(RuntimeError):
    """Base error for deterministic CLI failures."""


class NetworkError(GetPaperError):
    """Network access failed after bounded retries."""


class UnsafeArchiveError(GetPaperError):
    """An archive violates extraction safety limits."""


def sanitized_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    query = "?<redacted>" if parsed.query else ""
    return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, query, ""))


def sanitized_error(error: BaseException) -> str:
    return re.sub(
        r"(?i)([?&](?:mailto|api[_-]?key|key|token|secret|password)=)[^&\s]+",
        r"\1<redacted>",
        str(error),
    )


def validate_remote_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise NetworkError(f"拒绝非 HTTPS URL: {sanitized_url(url)}")
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    if not hostname or hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise NetworkError(f"拒绝本地主机 URL: {sanitized_url(url)}")
    try:
        addresses = socket.getaddrinfo(
            hostname,
            parsed.port or 443,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise NetworkError(f"拒绝私有或特殊地址 URL: {sanitized_url(url)}")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Any:
        target = urllib.parse.urljoin(req.full_url, newurl)
        validate_remote_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


@dataclass
class Paper:
    title: str
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    oa_url: str | None = None
    license: str | None = None
    oa_status: str | None = None
    citation_count: int = 0
    sources: list[str] = field(default_factory=list)
    source_ids: dict[str, str] = field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_markup(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return normalize_space(text)


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def tokenize(value: str) -> list[str]:
    normalized = value.casefold().translate(GREEK_TRANSLATION)
    normalized = re.sub(r"(\d+)\s*/\s*(\d+)", r"\1-\2", normalized)
    raw = re.findall(r"[a-z0-9][a-z0-9+.-]*|[\u4e00-\u9fff]{2,}", normalized)
    return [token.strip(".-") for token in raw if token.strip(".-") and token not in STOPWORDS]


def compact_query(task: str, max_terms: int = 16) -> str:
    counts = Counter(tokenize(task))
    selected = sorted(counts, key=lambda token: (-counts[token], token))[:max_terms]
    return " ".join(selected) if selected else normalize_space(task)[:240]


def arxiv_search_expressions(query: str) -> list[str]:
    original = normalize_space(query)
    if not original:
        return []
    if re.search(r"\b(?:AND|OR|ANDNOT)\b|(?:^|\s)[a-z][a-z-]*:", original):
        return [original]
    clean = original.replace('"', " ").strip()
    terms = tokenize(clean)[:12]
    expressions = [f'all:"{clean}"']
    if len(terms) >= 4:
        expressions.append(f'all:"{" ".join(terms[:4])}"')
    if len(terms) >= 2:
        expressions.append(" AND ".join(f"all:{term}" for term in terms[:6]))
    return list(dict.fromkeys(expressions))


def relevance_score(task: str, title: str, abstract: str) -> float:
    task_terms = set(tokenize(task))
    if not task_terms:
        return 0.0
    title_terms = set(tokenize(title))
    document_terms = title_terms | set(tokenize(abstract))
    document_coverage = len(task_terms & document_terms) / len(task_terms)
    title_coverage = len(task_terms & title_terms) / len(task_terms)
    return round(min(1.0, 0.65 * document_coverage + 0.35 * title_coverage), 6)


def ranking_score(paper: Paper, relevance: float) -> float:
    current_year = datetime.now(timezone.utc).year
    freshness = 1.0 if not paper.year else max(0.0, 1.0 - max(0, current_year - paper.year) / 25.0)
    citation = math.log1p(max(0, paper.citation_count)) / math.log1p(10_000)
    return round(0.95 * relevance + 0.03 * freshness + 0.02 * min(1.0, citation), 6)


def parse_year(value: Any) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def arxiv_id_from_text(value: str) -> str | None:
    text = urllib.parse.unquote(value.strip())
    modern_id = r"\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}"
    old_id = r"[a-z-]+(?:\.[a-z-]+)?/\d{7}"
    arxiv_path = re.search(
        rf"arxiv\.org/(?:abs|pdf|src)/({modern_id}|{old_id})(v\d+)?",
        text,
        re.IGNORECASE,
    )
    if arxiv_path:
        return f"{arxiv_path.group(1)}{arxiv_path.group(2) or ''}"
    explicit = re.match(rf"^arxiv\s*:\s*({modern_id}|{old_id})(v\d+)?$", text, re.IGNORECASE)
    if explicit:
        return f"{explicit.group(1)}{explicit.group(2) or ''}"
    arxiv_doi = re.match(
        rf"^(?:https?://(?:dx\.)?doi\.org/)?10\.48550/arxiv\.({modern_id})(v\d+)?$",
        text,
        re.IGNORECASE,
    )
    if arxiv_doi:
        return f"{arxiv_doi.group(1)}{arxiv_doi.group(2) or ''}"
    modern = re.fullmatch(rf"({modern_id})(v\d+)?", text, re.IGNORECASE)
    if modern:
        return f"{modern.group(1)}{modern.group(2) or ''}"
    old = re.fullmatch(rf"({old_id})(v\d+)?", text, re.IGNORECASE)
    if old:
        return f"{old.group(1)}{old.group(2) or ''}"
    return None


def doi_from_text(value: str) -> str | None:
    match = re.search(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", value, re.IGNORECASE)
    return match.group(0).rstrip(".,;") if match else None


def request_bytes(
    url: str,
    *,
    timeout: float = 30.0,
    attempts: int = 3,
    max_bytes: int = MAX_METADATA_BYTES,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    validate_remote_url(url)
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    request_headers.update(headers or {})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers=request_headers, method="GET")
            opener = urllib.request.build_opener(SafeRedirectHandler)
            with opener.open(request, timeout=timeout) as response:
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise NetworkError(f"响应超过大小上限 {max_bytes} bytes: {sanitized_url(url)}")
                metadata = {
                    "url": response.geturl(),
                    "status": str(getattr(response, "status", 200)),
                    "content_type": response.headers.get("Content-Type", ""),
                }
                return data, metadata
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code != 429 and error.code < 500:
                raise NetworkError(f"HTTP {error.code}: {sanitized_url(url)}") from error
            retry_after = error.headers.get("Retry-After", "")
            delay = min(30.0, float(retry_after)) if retry_after.isdigit() else float(2 ** (attempt - 1))
            if attempt < attempts:
                time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(float(2 ** (attempt - 1)))
    raise NetworkError(
        f"请求失败（{attempts} 次）{sanitized_url(url)}: {sanitized_error(last_error)}"
    ) from last_error


def request_text(url: str, **kwargs: Any) -> tuple[str, dict[str, str]]:
    data, metadata = request_bytes(url, **kwargs)
    return data.decode("utf-8", errors="replace"), metadata


def request_json(url: str, **kwargs: Any) -> tuple[dict[str, Any], dict[str, str]]:
    data, metadata = request_bytes(url, **kwargs)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NetworkError(f"JSON 解析失败: {sanitized_url(url)}") from error
    if not isinstance(value, dict):
        raise NetworkError(f"JSON 顶层不是对象: {sanitized_url(url)}")
    return value, metadata


def arxiv_query_text(params: dict[str, str]) -> str:
    query = urllib.parse.urlencode(params)
    errors: list[str] = []
    for index, base_url in enumerate(
        ("https://export.arxiv.org/api/query", "https://arxiv.org/api/query")
    ):
        try:
            text, _ = request_text(f"{base_url}?{query}", timeout=20, attempts=1)
            return text
        except NetworkError as error:
            errors.append(str(error))
            if index == 0:
                time.sleep(3)
    raise NetworkError("arXiv API 备用入口均失败: " + " | ".join(errors))


def merge_paper(target: Paper, incoming: Paper) -> Paper:
    target.title = target.title or incoming.title
    target.abstract = max((target.abstract, incoming.abstract), key=len)
    if len(incoming.authors) > len(target.authors):
        target.authors = incoming.authors
    target.year = target.year or incoming.year
    target.doi = target.doi or incoming.doi
    target.arxiv_id = target.arxiv_id or incoming.arxiv_id
    target.url = target.url or incoming.url
    target.pdf_url = target.pdf_url or incoming.pdf_url
    target.oa_url = target.oa_url or incoming.oa_url
    target.license = target.license or incoming.license
    target.oa_status = target.oa_status or incoming.oa_status
    target.citation_count = max(target.citation_count, incoming.citation_count)
    for source in incoming.sources:
        if source not in target.sources:
            target.sources.append(source)
    target.source_ids.update(incoming.source_ids)
    return target


def same_paper(left: Paper, right: Paper) -> bool:
    if left.arxiv_id and right.arxiv_id:
        return left.arxiv_id.split("v")[0] == right.arxiv_id.split("v")[0]
    if left.doi and right.doi:
        return left.doi.casefold() == right.doi.casefold()
    if not left.title or normalize_title(left.title) != normalize_title(right.title):
        return False
    if not left.year or not right.year or left.year != right.year:
        return False
    if not left.authors or not right.authors:
        return False
    left_author = normalize_title(left.authors[0]).split()
    right_author = normalize_title(right.authors[0]).split()
    return bool(left_author and right_author and left_author[-1] == right_author[-1])


def deduplicate(papers: list[Paper]) -> list[Paper]:
    merged: list[Paper] = []
    for paper in papers:
        for existing in merged:
            if same_paper(existing, paper):
                merge_paper(existing, paper)
                break
        else:
            merged.append(paper)
    return merged


def search_arxiv(query: str, limit: int) -> list[Paper]:
    root = None
    for expression in arxiv_search_expressions(query):
        text = arxiv_query_text(
            {
                "search_query": expression,
                "start": "0",
                "max_results": str(limit),
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        candidate_root = ET.fromstring(text)
        if candidate_root.findall("atom:entry", ATOM_NS):
            root = candidate_root
            break
    if root is None:
        return []
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = normalize_space(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
        summary = normalize_space(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
        identifier = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
        arxiv_id = arxiv_id_from_text(identifier)
        pdf_url = None
        for link in entry.findall("atom:link", ATOM_NS):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href")
                break
        authors = [
            normalize_space(author.findtext("atom:name", default="", namespaces=ATOM_NS))
            for author in entry.findall("atom:author", ATOM_NS)
        ]
        published = entry.findtext("atom:published", default="", namespaces=ATOM_NS)
        doi = normalize_space(entry.findtext("arxiv:doi", default="", namespaces=ATOM_NS)) or None
        papers.append(
            Paper(
                title=title,
                abstract=summary,
                authors=[author for author in authors if author],
                year=parse_year(published),
                doi=doi,
                arxiv_id=arxiv_id,
                url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else identifier,
                pdf_url=pdf_url,
                oa_url=pdf_url,
                sources=["arxiv"],
                source_ids={"arxiv": arxiv_id or identifier},
            )
        )
    return papers


def reconstruct_openalex_abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in index.items():
        if isinstance(indexes, list):
            positions.extend((int(position), str(word)) for position in indexes if isinstance(position, int))
    return " ".join(word for _, word in sorted(positions))


def openalex_location_url(location: Any, key: str) -> str | None:
    if isinstance(location, dict):
        value = location.get(key)
        return str(value) if value else None
    return None


def openalex_to_paper(record: dict[str, Any]) -> Paper:
    locations = record.get("locations") if isinstance(record.get("locations"), list) else []
    best = record.get("best_oa_location") or {}
    if not record.get("is_oa") or not isinstance(best, dict):
        best = {}
    if not best:
        best = next(
            (
                location
                for location in locations
                if isinstance(location, dict) and location.get("is_oa")
            ),
            {},
        )
    arxiv_id = None
    for location in [best, *locations]:
        if not isinstance(location, dict):
            continue
        for key in ("landing_page_url", "pdf_url"):
            arxiv_id = arxiv_id or arxiv_id_from_text(str(location.get(key) or ""))
    doi = normalize_space(str(record.get("doi") or "")).replace("https://doi.org/", "") or None
    authors: list[str] = []
    for authorship in record.get("authorships") or []:
        author = authorship.get("author") if isinstance(authorship, dict) else None
        if isinstance(author, dict) and author.get("display_name"):
            authors.append(str(author["display_name"]))
    paper = Paper(
        title=normalize_space(record.get("display_name") or record.get("title")),
        abstract=reconstruct_openalex_abstract(record.get("abstract_inverted_index")),
        authors=authors,
        year=parse_year(record.get("publication_year")),
        doi=doi,
        arxiv_id=arxiv_id,
        url=normalize_space(record.get("id") or "") or None,
        pdf_url=openalex_location_url(best, "pdf_url"),
        oa_url=openalex_location_url(best, "landing_page_url") or openalex_location_url(best, "pdf_url"),
        license=str(best.get("license")) if best.get("license") else None,
        oa_status=str(record.get("oa_status")) if record.get("oa_status") else None,
        citation_count=int(record.get("cited_by_count") or 0),
        sources=["openalex"],
        source_ids={"openalex": str(record.get("id") or "")},
    )
    return paper


def search_openalex(query: str, limit: int) -> list[Paper]:
    params: dict[str, str] = {
        "search": query,
        "per-page": str(limit),
        "sort": "relevance_score:desc",
    }
    mailto = os.environ.get("OPENALEX_MAILTO") or os.environ.get("CONTACT_EMAIL")
    if mailto:
        params["mailto"] = mailto
    payload, _ = request_json(f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}", timeout=45)
    return [openalex_to_paper(record) for record in payload.get("results", []) if isinstance(record, dict)]


def search_semantic_scholar(query: str, limit: int) -> list[Paper]:
    params = urllib.parse.urlencode(
        {
            "query": query,
            "limit": str(limit),
            "fields": "title,abstract,year,citationCount,externalIds,openAccessPdf,url,authors",
        }
    )
    headers: dict[str, str] = {}
    if os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
    payload, _ = request_json(
        f"https://api.semanticscholar.org/graph/v1/paper/search?{params}",
        timeout=45,
        headers=headers,
    )
    papers: list[Paper] = []
    for record in payload.get("data", []):
        if not isinstance(record, dict):
            continue
        external = record.get("externalIds") if isinstance(record.get("externalIds"), dict) else {}
        oa = record.get("openAccessPdf") if isinstance(record.get("openAccessPdf"), dict) else {}
        papers.append(
            Paper(
                title=normalize_space(record.get("title")),
                abstract=normalize_space(record.get("abstract")),
                authors=[str(author.get("name")) for author in record.get("authors", []) if author.get("name")],
                year=parse_year(record.get("year")),
                doi=str(external.get("DOI")) if external.get("DOI") else None,
                arxiv_id=str(external.get("ArXiv")) if external.get("ArXiv") else None,
                url=str(record.get("url")) if record.get("url") else None,
                pdf_url=str(oa.get("url")) if oa.get("url") else None,
                oa_url=str(oa.get("url")) if oa.get("url") else None,
                citation_count=int(record.get("citationCount") or 0),
                sources=["semantic-scholar"],
                source_ids={"semantic-scholar": str(record.get("paperId") or "")},
            )
        )
    return papers


def search_crossref(query: str, limit: int) -> list[Paper]:
    params: dict[str, str] = {
        "query.bibliographic": query,
        "rows": str(limit),
        "select": "DOI,title,abstract,author,issued,is-referenced-by-count,URL,license,type",
    }
    mailto = os.environ.get("CROSSREF_MAILTO") or os.environ.get("CONTACT_EMAIL")
    if mailto:
        params["mailto"] = mailto
    payload, _ = request_json(f"https://api.crossref.org/works?{urllib.parse.urlencode(params)}", timeout=45)
    papers: list[Paper] = []
    for record in payload.get("message", {}).get("items", []):
        if not isinstance(record, dict):
            continue
        titles = record.get("title") if isinstance(record.get("title"), list) else []
        authors: list[str] = []
        for author in record.get("author", []):
            if not isinstance(author, dict):
                continue
            name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
            if name:
                authors.append(name)
        issued_parts = ((record.get("issued") or {}).get("date-parts") or [[None]])[0]
        year = issue_year = None
        if issued_parts:
            issue_year = parse_year(issued_parts[0])
        year = issue_year
        license_values = record.get("license") if isinstance(record.get("license"), list) else []
        license_url = next(
            (str(item.get("URL")) for item in license_values if isinstance(item, dict) and item.get("URL")),
            None,
        )
        papers.append(
            Paper(
                title=normalize_space(titles[0] if titles else ""),
                abstract=strip_markup(record.get("abstract")),
                authors=authors,
                year=year,
                doi=str(record.get("DOI") or "") or None,
                url=str(record.get("URL") or "") or None,
                license=license_url,
                citation_count=int(record.get("is-referenced-by-count") or 0),
                sources=["crossref"],
                source_ids={"crossref": str(record.get("DOI") or "")},
            )
        )
    return papers


SEARCH_ADAPTERS = {
    "arxiv": search_arxiv,
    "openalex": search_openalex,
    "semantic-scholar": search_semantic_scholar,
    "crossref": search_crossref,
}


def search_sources(task: str, query: str, sources: list[str], limit: int) -> dict[str, Any]:
    papers: list[Paper] = []
    source_status: dict[str, Any] = {}
    for source in sources:
        adapter = SEARCH_ADAPTERS.get(source)
        if adapter is None:
            source_status[source] = {"ok": False, "error": "unknown source", "result_count": 0}
            continue
        try:
            found = adapter(query, limit)
            papers.extend(found)
            source_status[source] = {"ok": True, "result_count": len(found)}
        except Exception as error:
            source_status[source] = {
                "ok": False,
                "error": sanitized_error(error),
                "result_count": 0,
            }

    merged = deduplicate(papers)
    results: list[dict[str, Any]] = []
    for paper in merged:
        relevance = relevance_score(task, paper.title, paper.abstract)
        result = asdict(paper)
        result["relevance_score"] = relevance
        result["ranking_score"] = ranking_score(paper, relevance)
        result["sources"] = sorted(result["sources"])
        results.append(result)
    results.sort(key=lambda item: (item["ranking_score"], item["relevance_score"]), reverse=True)
    for index, result in enumerate(results, start=1):
        result["rank"] = index
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "task": task,
        "query": query,
        "sources": source_status,
        "results": results,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def safe_member_path(destination: Path, member_name: str) -> Path:
    root = destination.resolve()
    normalized = member_name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        normalized.startswith("/")
        or normalized.startswith("//")
        or re.match(r"^[a-z]:/", normalized, re.IGNORECASE)
        or ".." in pure.parts
    ):
        raise UnsafeArchiveError(f"拒绝绝对或越界归档路径: {member_name}")
    target = (root / pure).resolve()
    if root != target and root not in target.parents:
        raise UnsafeArchiveError(f"归档路径越界: {member_name}")
    return target


def directory_digest(root: Path) -> str:
    if root.is_symlink():
        raise UnsafeArchiveError(f"源码树根目录是符号链接: {root}")
    digest = hashlib.sha256()
    paths = sorted(root.rglob("*"))
    for path in paths:
        if path.is_symlink():
            raise UnsafeArchiveError(f"源码树包含符号链接: {path.relative_to(root)}")
    for path in (candidate for candidate in paths if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def extract_tar(blob: bytes, destination: Path, max_bytes: int, max_files: int) -> list[str]:
    destination = destination.resolve()
    files: list[str] = []
    total = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) > max_files:
            raise UnsafeArchiveError(f"归档文件数超限: {len(members)} > {max_files}")
        for member in members:
            if member.issym() or member.islnk() or member.isdev():
                raise UnsafeArchiveError(f"拒绝链接或设备文件: {member.name}")
            target = safe_member_path(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise UnsafeArchiveError(f"拒绝非常规归档成员: {member.name}")
            total += member.size
            if total > max_bytes:
                raise UnsafeArchiveError(f"归档解压大小超限: {total} > {max_bytes}")
            source = archive.extractfile(member)
            if source is None:
                raise UnsafeArchiveError(f"无法读取归档成员: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            files.append(str(target.relative_to(destination)))
    return files


def extract_zip(blob: bytes, destination: Path, max_bytes: int, max_files: int) -> list[str]:
    destination = destination.resolve()
    files: list[str] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        members = archive.infolist()
        if len(members) > max_files:
            raise UnsafeArchiveError(f"归档文件数超限: {len(members)} > {max_files}")
        for member in members:
            target = safe_member_path(destination, member.filename)
            mode = (member.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise UnsafeArchiveError(f"拒绝符号链接: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            total += member.file_size
            if total > max_bytes:
                raise UnsafeArchiveError(f"归档解压大小超限: {total} > {max_bytes}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            files.append(str(target.relative_to(destination)))
    return files


def extract_artifact(
    blob: bytes,
    *,
    content_type: str,
    destination: Path,
    max_bytes: int,
    max_files: int,
    replace: bool = False,
) -> dict[str, Any]:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not replace:
        raise UnsafeArchiveError(f"解包目标已存在；需要覆盖时显式使用 --force: {destination}")
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    content_type = content_type.casefold()
    try:
        if "text/html" in content_type or blob.lstrip()[:64].lower().startswith((b"<!doctype", b"<html")):
            raise GetPaperError("上游返回 HTML 而非论文源码或 PDF")
        if blob.startswith(b"%PDF"):
            (staging / "paper.pdf").write_bytes(blob)
            result = {"kind": "pdf", "files": ["paper.pdf"], "main_tex": None}
        elif "application/pdf" in content_type:
            raise GetPaperError("PDF Content-Type 与实际 magic 不一致")
        elif blob.startswith(b"PK\x03\x04"):
            files = extract_zip(blob, staging, max_bytes, max_files)
            result = {"kind": "zip", "files": files, "main_tex": find_main_tex(staging)}
        elif blob.startswith(b"\x1f\x8b"):
            try:
                files = extract_tar(blob, staging, max_bytes, max_files)
                result = {"kind": "tar", "files": files, "main_tex": find_main_tex(staging)}
            except tarfile.TarError:
                with gzip.GzipFile(fileobj=io.BytesIO(blob)) as source:
                    data = source.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise UnsafeArchiveError(f"gzip 解压大小超限: {max_bytes}")
                if b"\\documentclass" not in data or b"\\begin{document}" not in data:
                    raise GetPaperError("gzip 内容不是完整 LaTeX 主文档")
                target = staging / "source.tex"
                target.write_bytes(data)
                result = {"kind": "gzip", "files": [target.name], "main_tex": "source.tex"}
        elif b"\\documentclass" in blob[:TEXT_SCAN_BYTES] and b"\\begin{document}" in blob[:TEXT_SCAN_BYTES]:
            target = staging / "source.tex"
            target.write_bytes(blob)
            result = {"kind": "plain", "files": [target.name], "main_tex": "source.tex"}
        else:
            raise GetPaperError(f"无法识别下载内容类型: {content_type or 'unknown'}")
        result["tree_sha256"] = directory_digest(staging)
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        staging.replace(destination)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def find_main_tex(root: Path) -> str | None:
    candidates: list[tuple[int, str]] = []
    for path in root.rglob("*.tex"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            sample = path.read_bytes()[:TEXT_SCAN_BYTES].decode("utf-8", errors="replace")
        except OSError:
            continue
        if "\\documentclass" in sample and "\\begin{document}" in sample:
            score = 20 + len(sample)
            stem = path.stem.casefold()
            if stem in {"main", "paper", "manuscript", "ms", "article"}:
                score += 1_000_000
            if path.parent == root:
                score += 100_000
            candidates.append((score, str(path.relative_to(root))))
    return max(candidates, default=(0, None))[1]


class MetaTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "meta":
            return
        attributes = {key.casefold(): value or "" for key, value in attrs}
        name = attributes.get("name") or attributes.get("property")
        if name and "content" in attributes:
            self.values.setdefault(name.casefold(), []).append(html.unescape(attributes["content"]))


@lru_cache(maxsize=128)
def arxiv_abs_page(arxiv_id: str) -> tuple[dict[str, list[str]], str | None]:
    try:
        text, _ = request_text(f"https://arxiv.org/abs/{arxiv_id}", timeout=30, attempts=2)
    except NetworkError:
        return {}, None
    parser = MetaTagParser()
    parser.feed(text)
    matches = re.findall(r"https?://(?:www\.)?creativecommons\.org/[^\"' ]+|https?://arxiv\.org/licenses/[^\"' ]+", text)
    return parser.values, matches[0] if matches else None


def arxiv_license(arxiv_id: str) -> str | None:
    return arxiv_abs_page(arxiv_id)[1]


def arxiv_abs_metadata(arxiv_id: str) -> Paper | None:
    metadata, license_url = arxiv_abs_page(arxiv_id)
    titles = metadata.get("citation_title", [])
    if not titles:
        return None
    abstracts = metadata.get("og:description") or metadata.get("description") or []
    author_values = metadata.get("citation_author", [])
    authors = [normalize_space(author.replace(",", " ", 1)) for author in author_values]
    doi_values = metadata.get("citation_doi", [])
    dates = metadata.get("citation_date", [])
    return Paper(
        title=normalize_space(titles[0]),
        abstract=normalize_space(abstracts[0] if abstracts else ""),
        authors=[author for author in authors if author],
        year=parse_year(dates[0]) if dates else None,
        doi=normalize_space(doi_values[0]) if doi_values else None,
        arxiv_id=arxiv_id,
        url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        oa_url=f"https://arxiv.org/pdf/{arxiv_id}",
        license=license_url,
        oa_status="green",
        sources=["arxiv"],
        source_ids={"arxiv": arxiv_id},
    )


def arxiv_metadata(arxiv_id: str) -> Paper | None:
    text = arxiv_query_text({"id_list": arxiv_id, "max_results": "1"})
    root = ET.fromstring(text)
    entry = root.find("atom:entry", ATOM_NS)
    if entry is None:
        return None
    title = normalize_space(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
    if not title:
        return None
    authors = [
        normalize_space(author.findtext("atom:name", default="", namespaces=ATOM_NS))
        for author in entry.findall("atom:author", ATOM_NS)
    ]
    published = entry.findtext("atom:published", default="", namespaces=ATOM_NS)
    doi = normalize_space(entry.findtext("arxiv:doi", default="", namespaces=ATOM_NS)) or None
    return Paper(
        title=title,
        abstract=normalize_space(entry.findtext("atom:summary", default="", namespaces=ATOM_NS)),
        authors=[author for author in authors if author],
        year=parse_year(published),
        doi=doi,
        arxiv_id=arxiv_id,
        url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        oa_url=f"https://arxiv.org/pdf/{arxiv_id}",
        sources=["arxiv"],
        source_ids={"arxiv": arxiv_id},
    )


def metadata_for_identifier(identifier: str) -> Paper | None:
    arxiv_id = arxiv_id_from_text(identifier)
    if arxiv_id:
        paper = arxiv_abs_metadata(arxiv_id)
        if paper is not None:
            return paper
        try:
            paper = arxiv_metadata(arxiv_id)
            if paper is not None:
                return paper
        except (GetPaperError, ET.ParseError):
            pass
        return Paper(
            title=f"arXiv:{arxiv_id}",
            arxiv_id=arxiv_id,
            url=f"https://arxiv.org/abs/{arxiv_id}",
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
            oa_url=f"https://arxiv.org/pdf/{arxiv_id}",
            sources=["arxiv"],
            source_ids={"arxiv": arxiv_id},
        )
    doi = doi_from_text(identifier)
    if not doi:
        return None
    candidates: list[Paper] = []
    params = urllib.parse.urlencode({"mailto": os.environ.get("CONTACT_EMAIL", "")})
    openalex_url = f"https://api.openalex.org/works/{urllib.parse.quote(f'https://doi.org/{doi}', safe='')}"
    if params != "mailto=":
        openalex_url += f"?{params}"
    for loader in (
        lambda: openalex_to_paper(request_json(openalex_url, timeout=45)[0]),
        lambda: request_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}", timeout=45)[0],
    ):
        try:
            value = loader()
            if isinstance(value, dict):
                message = value.get("message") if isinstance(value, dict) else None
                if message:
                    papers = search_crossref_from_records([message])
                    candidates.extend(papers)
                else:
                    candidates.append(openalex_to_paper(value))
            else:
                candidates.append(value)
        except Exception:
            continue
    return deduplicate(candidates)[0] if candidates else None


def search_crossref_from_records(records: list[dict[str, Any]]) -> list[Paper]:
    papers: list[Paper] = []
    for record in records:
        title_values = record.get("title") if isinstance(record.get("title"), list) else []
        authors: list[str] = []
        for author in record.get("author", []):
            if isinstance(author, dict):
                name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
                if name:
                    authors.append(name)
        issued = ((record.get("issued") or {}).get("date-parts") or [[None]])[0]
        license_values = record.get("license") if isinstance(record.get("license"), list) else []
        license_url = next(
            (str(item.get("URL")) for item in license_values if isinstance(item, dict) and item.get("URL")),
            None,
        )
        papers.append(
            Paper(
                title=normalize_space(title_values[0] if title_values else ""),
                abstract=strip_markup(record.get("abstract")),
                authors=authors,
                year=parse_year(issued[0]) if issued else None,
                doi=str(record.get("DOI") or "") or None,
                url=str(record.get("URL") or "") or None,
                license=license_url,
                citation_count=int(record.get("is-referenced-by-count") or 0),
                sources=["crossref"],
                source_ids={"crossref": str(record.get("DOI") or "")},
            )
        )
    return papers


def download_arxiv_source(
    arxiv_id: str,
    destination: Path,
    max_bytes: int,
    max_files: int,
    *,
    force: bool,
) -> dict[str, Any]:
    blob, metadata = request_bytes(
        f"https://arxiv.org/src/{arxiv_id}",
        timeout=90,
        attempts=3,
        max_bytes=MAX_ARTIFACT_BYTES,
        headers={"Accept": "application/gzip, application/x-tar, application/zip, application/pdf, */*"},
    )
    extracted = extract_artifact(
        blob,
        content_type=metadata.get("content_type", ""),
        destination=destination,
        max_bytes=max_bytes,
        max_files=max_files,
        replace=force,
    )
    extracted.update(
        {
            "retrieval_url": sanitized_url(metadata["url"]),
            "content_type": metadata["content_type"],
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        }
    )
    return extracted


def download_pdf(url: str, destination: Path, *, force: bool) -> dict[str, Any]:
    blob, metadata = request_bytes(url, timeout=90, attempts=3, max_bytes=MAX_ARTIFACT_BYTES)
    result = extract_artifact(
        blob,
        content_type=metadata.get("content_type", ""),
        destination=destination,
        max_bytes=MAX_ARTIFACT_BYTES,
        max_files=1,
        replace=force,
    )
    result.update(
        {
        "retrieval_url": sanitized_url(metadata["url"]),
        "content_type": metadata["content_type"],
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
        }
    )
    return result


def slugify(value: str, fallback: str = "paper") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:80] or fallback


def folder_for_identifier(identifier: str) -> str:
    arxiv_id = arxiv_id_from_text(identifier)
    if arxiv_id:
        return slugify(f"arxiv-{arxiv_id}")
    doi = doi_from_text(identifier)
    if doi:
        return slugify(f"doi-{doi.replace('/', '-')}")
    return f"record-{hashlib.sha256(identifier.encode('utf-8', errors='surrogateescape')).hexdigest()[:16]}"


def validate_cached_payload(destination: Path, payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 1 or not isinstance(payload.get("paper"), dict):
        raise GetPaperError(f"缓存元数据结构无效；需要刷新时使用 --force: {destination / 'metadata.json'}")
    artifact = payload.get("artifact")
    if artifact is None:
        return
    if not isinstance(artifact, dict) or not isinstance(artifact.get("files"), list):
        raise GetPaperError(f"缓存 artifact 结构无效；需要刷新时使用 --force: {destination / 'metadata.json'}")
    source_dir = destination / "source"
    for relative in artifact["files"]:
        if not isinstance(relative, str):
            raise GetPaperError("缓存 artifact 文件清单包含非字符串路径；请使用 --force")
        path = safe_member_path(source_dir, relative)
        if not path.is_file():
            raise GetPaperError(f"缓存 artifact 文件缺失；请使用 --force: {path}")
    main_tex = artifact.get("main_tex")
    if main_tex and not safe_member_path(source_dir, str(main_tex)).is_file():
        raise GetPaperError(f"缓存主 TeX 缺失；请使用 --force: {source_dir / str(main_tex)}")
    expected_tree = artifact.get("tree_sha256")
    if not isinstance(expected_tree, str) or directory_digest(source_dir) != expected_tree:
        raise GetPaperError(f"缓存源码树哈希不匹配；请使用 --force: {source_dir}")


def load_cached_payload(destination: Path, task: str) -> dict[str, Any]:
    metadata_path = destination / "metadata.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GetPaperError(f"缓存 metadata.json 无法读取；请使用 --force: {metadata_path}") from error
    if not isinstance(payload, dict):
        raise GetPaperError(f"缓存 metadata.json 顶层不是对象；请使用 --force: {metadata_path}")
    validate_cached_payload(destination, payload)
    paper_data = payload.get("paper") if isinstance(payload.get("paper"), dict) else {}
    payload["task"] = task
    payload["task_sha256"] = hashlib.sha256(task.encode("utf-8")).hexdigest()
    payload["relevance_score"] = relevance_score(
        task,
        str(paper_data.get("title") or ""),
        str(paper_data.get("abstract") or ""),
    )
    payload["reused"] = True
    payload["path"] = str(destination)
    write_json(metadata_path, payload)
    return payload


def fetch_paper(
    identifier: str,
    output_root: Path,
    *,
    task: str,
    pdf_fallback: bool,
    force: bool,
    max_extract_bytes: int,
    max_files: int,
) -> dict[str, Any]:
    destination = output_root / folder_for_identifier(identifier)
    metadata_path = destination / "metadata.json"
    if metadata_path.exists() and not force:
        return load_cached_payload(destination, task)
    paper = metadata_for_identifier(identifier)
    if paper is None:
        raise GetPaperError(f"无法解析标识符或取得元数据: {identifier}")
    arxiv_id = paper.arxiv_id or arxiv_id_from_text(identifier)
    if arxiv_id:
        paper.arxiv_id = arxiv_id

    destination.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "identifier": identifier,
        "fetched_at": utc_now(),
        "task": task,
        "task_sha256": hashlib.sha256(task.encode("utf-8")).hexdigest(),
        "paper": asdict(paper),
        "relevance_score": relevance_score(task, paper.title, paper.abstract),
        "source_kind": None,
        "artifact": None,
        "license_url": None,
        "usage_note": "Verify the source license before redistribution; this tool does not bypass paywalls.",
    }
    errors: list[str] = []
    if arxiv_id:
        payload["license_url"] = arxiv_license(arxiv_id)
        try:
            payload["artifact"] = download_arxiv_source(
                arxiv_id,
                destination / "source",
                max_extract_bytes,
                max_files,
                force=force,
            )
            payload["source_kind"] = payload["artifact"]["kind"]
        except (GetPaperError, OSError) as error:
            errors.append(f"arXiv source: {sanitized_error(error)}")
    if payload["artifact"] is None and pdf_fallback:
        pdf_url = paper.pdf_url or paper.oa_url
        if pdf_url:
            try:
                payload["artifact"] = download_pdf(pdf_url, destination / "source", force=force)
                payload["source_kind"] = "pdf"
            except (GetPaperError, OSError) as error:
                errors.append(f"OA PDF: {sanitized_error(error)}")
    if payload["artifact"] is None and errors:
        raise GetPaperError("; ".join(errors))
    payload["errors"] = errors
    payload["path"] = str(destination)
    write_json(metadata_path, payload)
    return payload


def output_manifest_path(output: str | None) -> Path | None:
    if not output:
        return None
    path = Path(output).expanduser()
    if path.suffix.casefold() == ".json":
        return path
    return path / "search-manifest.json"


def command_search(args: argparse.Namespace) -> int:
    task = args.task
    if args.task_file:
        task = Path(args.task_file).read_text(encoding="utf-8")
    if not normalize_space(task):
        raise GetPaperError("search 需要非空 --task 或 --task-file")
    query = normalize_space(args.query) or compact_query(task)
    sources = [source.strip() for source in args.sources.split(",") if source.strip()]
    payload = search_sources(task, query, sources, args.max_results)
    if args.min_relevance > 0:
        payload["results"] = [item for item in payload["results"] if item["relevance_score"] >= args.min_relevance]
        for index, item in enumerate(payload["results"], start=1):
            item["rank"] = index
    manifest_path = output_manifest_path(args.output)
    if args.fetch_top:
        if not args.output:
            raise GetPaperError("--fetch-top 需要 --output 指定下载根目录")
        if Path(args.output).suffix.casefold() == ".json":
            raise GetPaperError("--fetch-top 需要目录型 --output，不能使用 .json 文件路径")
        fetched = []
        for result in payload["results"][: args.fetch_top]:
            identifier = (
                f"arXiv:{result['arxiv_id']}" if result.get("arxiv_id") else (result.get("doi") or result.get("url"))
            )
            if not identifier:
                continue
            try:
                fetched.append(
                    fetch_paper(
                        identifier,
                        Path(args.output).expanduser(),
                        task=task,
                        pdf_fallback=True,
                        force=args.force,
                        max_extract_bytes=args.max_extract_bytes,
                        max_files=args.max_files,
                    )
                )
            except GetPaperError as error:
                fetched.append({"identifier": identifier, "error": str(error)})
        payload["fetched"] = fetched
    if manifest_path:
        payload["manifest_path"] = str(manifest_path)
        write_json(manifest_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["results"] else 5


def command_fetch(args: argparse.Namespace) -> int:
    task = args.task
    if args.task_file:
        task = Path(args.task_file).read_text(encoding="utf-8")
    if not normalize_space(task):
        raise GetPaperError("fetch 需要非空 --task 或 --task-file，以记录主任务相关性")
    payload = fetch_paper(
        args.identifier,
        Path(args.output).expanduser(),
        task=task,
        pdf_fallback=not args.no_pdf_fallback,
        force=args.force,
        max_extract_bytes=args.max_extract_bytes,
        max_files=args.max_files,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search papers across scholarly APIs and retrieve arXiv LaTeX sources safely.",
    )
    parser.add_argument("--version", action="version", version="get-paper 1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search multiple scholarly sources and rank against the main task")
    task_group = search.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task", help="main task text used for relevance ranking")
    task_group.add_argument("--task-file", help="file containing the main task text")
    search.add_argument("--query", help="source query; derived from --task when omitted")
    search.add_argument(
        "--sources",
        default="arxiv,openalex,semantic-scholar,crossref",
        help="comma-separated sources: arxiv,openalex,semantic-scholar,crossref",
    )
    search.add_argument("--max-results", type=int, default=10, choices=range(1, 51), metavar="N")
    search.add_argument("--min-relevance", type=float, default=0.0, help="drop results below this 0..1 lexical relevance")
    search.add_argument("--output", help="JSON manifest path or output directory")
    search.add_argument("--fetch-top", type=int, default=0, choices=range(0, 11), metavar="N")
    search.add_argument("--force", action="store_true")
    search.add_argument("--max-extract-bytes", type=int, default=DEFAULT_EXTRACT_BYTES)
    search.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    search.set_defaults(func=command_search)

    fetch = subparsers.add_parser("fetch", help="retrieve arXiv source or an open-access PDF")
    fetch.add_argument("identifier", help="arXiv URL/ID or DOI URL/ID")
    fetch.add_argument("--output", required=True, help="download root directory")
    task_group = fetch.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task", help="main task text used for relevance recording")
    task_group.add_argument("--task-file", help="file containing the main task text")
    fetch.add_argument("--no-pdf-fallback", action="store_true", help="do not download a PDF when LaTeX source is absent")
    fetch.add_argument("--force", action="store_true", help="replace an existing metadata.json")
    fetch.add_argument("--max-extract-bytes", type=int, default=DEFAULT_EXTRACT_BYTES)
    fetch.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    fetch.set_defaults(func=command_fetch)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "max_extract_bytes", 1) <= 0 or getattr(args, "max_files", 1) <= 0:
        parser.error("--max-extract-bytes 和 --max-files 必须为正数")
    try:
        return int(args.func(args))
    except (GetPaperError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"get-paper: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
