"""Source ingestion and interpretable candidate scoring.

The bundled spreadsheet contains positive editorial examples, not a training set.
Scores in this module are prioritization indices, never calibrated probabilities.
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

DATA = Path(__file__).parent / "data" / "curated.json"
OPENALEX = "https://api.openalex.org/works"
ALIASES = {
    "ии": "artificial intelligence", "искусственный интеллект": "artificial intelligence",
    "финтех": "financial technology", "робот": "robotics",
    "кибербезопас": "cybersecurity", "защита ии": "AI security",
    "индустриал": "industrial artificial intelligence",
    "платеж": "payments", "edge": "edge computing",
    "квант": "quantum computing", "медицин": "medical technology",
    "энергет": "energy technology", "био": "biotechnology",
}
AREAS = {
    "Индустриальный ИИ": "industrial ai manufacturing production predictive maintenance",
    "Инфраструктура ИИ": "ai artificial intelligence llm model compute infrastructure",
    "Защита ИИ": "ai agents model security safety red teaming identity cybersecurity",
    "Финтех": "fintech banking finance payment financial digital assets",
    "Роботы": "robotics robot humanoid actuator tactile manipulation",
    "Edge": "edge on-device device inference embedded distributed",
}
STOP = set("the and for with from using based via under toward towards through approach new novel recent study review survey analysis applications application methods method framework system systems model models artificial intelligence machine learning large language technology technologies research development performance improved efficient an in of on to by a as at is are be or this that into it its their we our can using towards".split())
MATURE = {"large language model", "blockchain technology", "cloud computing", "generative artificial intelligence", "internet of things", "machine learning", "deep learning", "convolutional neural network", "chatgpt", "transformer model"}


def _words(s):
    return set(re.findall(r"[\w-]{3,}", s.lower()))


def _safe_url(url):
    return url if isinstance(url, str) and urlparse(url).scheme in ("https", "http") else ""


def _source(item, *, curated=False):
    url = _safe_url(item.get("url", ""))
    host = urlparse(url).hostname or ""
    primary = bool(re.search(r"(^|\.)(nature\.com|arxiv\.org|acm\.org|ieee\.org|springer\.com|sciencedirect\.com|pubmed\.ncbi\.nlm\.nih\.gov|doi\.org|bis\.org|europa\.eu|nist\.gov)$", host))
    return {
        "title": item.get("title", host), "url": url,
        "date": item.get("date") or None,
        "type": item.get("type") or ("Научная публикация" if not curated else "Ссылка из исходной подборки"),
        "language": item.get("language") or ("ru" if re.search("[А-Яа-я]", item.get("title", "")) else "не определён"),
        "trust": "высокое" if primary else "требует проверки",
        "note": "Метаданные OpenAlex; содержание первоисточника не проверено автоматически" if not curated else "Ссылка из авторской подборки; дата и первоисточник могут требовать проверки",
    }


def _curated_rows():
    with DATA.open(encoding="utf-8") as f:
        return json.load(f)


def _match(row, query):
    q = query.strip().lower()
    area = row["area"]
    if not q or q in ("все", "все технологии", "технологии"):
        return True
    if q in area.lower() or any(token in row["title"].lower() for token in _words(q) if len(token) > 3):
        return True
    haystack = " ".join((row["title"], row["area"], row["rationale"], row["companies"])).lower()
    tokens = _words(q) - {"технологии", "области", "слабые", "сигналы", "перспективные", "решения", "тренды"}
    if any(t in haystack for t in tokens):
        return True
    if "ии" in q or "искусствен" in q:
        return area in ("Защита ИИ", "Инфраструктура ИИ", "Индустриальный ИИ")
    return False


def curated_search(query):
    rows = [r for r in _curated_rows() if _match(r, query)]
    rows.sort(key=lambda r: (-r["editorial_score"], r["id"]))
    results = []
    for r in rows[:15]:
        score = round(35 + r["editorial_score"] * 8)
        sources = [_source(s, curated=True) for s in r["sources"]]
        results.append({
            "id": f"demo-{r['id']}", "title": r["title"], "area": r["area"],
            "score": min(score, 91), "score_label": "Редакционный индекс",
            "description": r["rationale"], "advantage": r["rationale"],
            "case": r["companies"], "stage": r["stage"], "momentum": r["momentum"],
            "first_observed": None, "recent_count": None, "historic_count": None,
            "explanation": ["Отобрано авторами исходной подборки", f"Оценка стадии и динамики: {r['editorial_score']} из 7", "Частоты и первый год упоминания в файле не измерены"],
            "sources": sources, "basis": "Редакционная подборка, сентябрь 2026; независимая проверка материалов не выполнена",
        })
    return {
        "query": query, "mode": "demo", "results": results, "candidate_count": len(rows),
        "source_count": sum(len(r["sources"]) for r in rows), "excluded": [],
        "score_note": "Индекс из оценки авторов таблицы (3–7); не вероятность модели. Данные исходного файла не содержат отрицательных примеров.",
        "coverage": "Подборка из 100 примеров в шести областях; по другим запросам может быть 0 результатов.",
    }


def normalize_query(query):
    q = query.strip()
    for key, value in sorted(ALIASES.items(), key=lambda x: -len(x[0])):
        if key in q.lower():
            return value
    return q


def fetch_works(query, start, end, per_page=150):
    params = urllib.parse.urlencode({
        "search": query, "filter": f"from_publication_date:{start},to_publication_date:{end},type:article|preprint|proceedings-article",
        "per-page": per_page, "select": "id,doi,title,publication_date,language,primary_location",
    })
    headers = {"User-Agent": "SignalRadarHackathon/1.0 (research prototype; mailto:team@example.org)", "Accept": "application/json"}
    if os.environ.get("OPENALEX_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["OPENALEX_API_KEY"]
    request = urllib.request.Request(f"{OPENALEX}?{params}", headers=headers)
    with urllib.request.urlopen(request, timeout=18) as response:
        payload = json.load(response)
    return payload.get("results", []), payload.get("meta", {}).get("count", 0)


def _phrases(title):
    words = re.findall(r"[a-z][a-z0-9-]{2,}", title.lower())
    phrases = set()
    for n in (2, 3, 4):
        for i in range(len(words) - n + 1):
            part = words[i:i+n]
            if part[0] in STOP or part[-1] in STOP or all(w in STOP for w in part):
                continue
            if any(len(w) < 3 for w in part) or sum(w not in STOP for w in part) < 2:
                continue
            phrase = " ".join(part)
            if phrase not in MATURE:
                phrases.add(phrase)
    return phrases


def _paper_source(p):
    loc = p.get("primary_location") or {}
    site = loc.get("source") or {}
    link = _safe_url(p.get("doi")) or _safe_url(loc.get("landing_page_url")) or _safe_url(p.get("id"))
    return _source({"title": p.get("title") or "Публикация", "url": link,
                    "date": p.get("publication_date"), "type": site.get("type") or "Научная публикация",
                    "language": p.get("language") or "не определён"})


def _score(recent, historic, years, sources):
    novelty = 1 / (1 + historic / max(recent, 1))
    evidence = min(1, math.log1p(recent) / math.log(7))
    recency = max(0, min(1, (max(years) - 2022) / 4)) if years else 0
    independent = min(1, len({s["url"] for s in sources if s["url"]}) / 3)
    return round(100 * (.37 * novelty + .29 * evidence + .16 * recency + .18 * independent))


def _trained_score(recent, historic, years, sources):
    """Opt-in expert-trained classifier; a model is never downloaded automatically."""
    path = os.environ.get("SIGNAL_MODEL")
    if not path:
        return None
    from joblib import load
    artifact = load(path)  # Only load a model trained locally by this project.
    values = {"recent_count": recent, "historic_count": historic,
              "independent_sources": len({s["url"] for s in sources}),
              "first_seen_year": min(years) if years else 0}
    vector = [[values[key] for key in artifact["features"]]]
    return round(100 * float(artifact["model"].predict_proba(vector)[0][1]))


def live_search(query, recent=None, historical=None):
    """Fetch two finite samples. Counts and first year always refer to these samples."""
    english = normalize_query(query)
    if recent is None or historical is None:
        current = date.today().year
        recent, total_recent = fetch_works(english, f"{current-2}-01-01", date.today().isoformat())
        historical, total_historical = fetch_works(english, f"{current-7}-01-01", f"{current-3}-12-31", 100)
    else:
        total_recent, total_historical = len(recent), len(historical)
    recent = [p for p in recent if p.get("title")]
    historical = [p for p in historical if p.get("title")]
    recent_map = defaultdict(list)
    old_map = Counter()
    for p in recent:
        for phrase in _phrases(p["title"]):
            recent_map[phrase].append(p)
    for p in historical:
        old_map.update(_phrases(p["title"]))
    candidates, excluded = [], []
    for phrase, papers in recent_map.items():
        unique = list({p.get("id") or p["title"]: p for p in papers}.values())
        if len(unique) < 2:
            continue
        old = old_map[phrase]
        if old >= len(unique) * 3:
            excluded.append({"title": phrase, "reason": f"Часто встречается в исторической выборке: {old} против {len(unique)} новых публикаций"})
            continue
        sources = [_paper_source(p) for p in unique[:4]]
        sources = [s for s in sources if s["url"]]
        if len(sources) < 2:
            excluded.append({"title": phrase, "reason": "Менее двух публикаций со ссылками на первоисточник"})
            continue
        years = [int(p["publication_date"][:4]) for p in unique if p.get("publication_date") and re.match(r"\d{4}", p["publication_date"])]
        case = unique[0]["title"]
        trained = _trained_score(len(unique), old, years, sources)
        score = trained if trained is not None else _score(len(unique), old, years, sources)
        candidates.append({
            "id": "live-" + re.sub(r"[^a-z0-9]+", "-", phrase).strip("-"),
            "title": phrase, "area": query,
            "score": score, "score_label": "Оценка классификатора" if trained is not None else "Индекс раннего сигнала",
            "description": f"Тема «{phrase}» обнаружена в заголовках {len(unique)} публикаций по запросу «{query}». Требуется экспертное изучение содержания работ.",
            "advantage": "Потенциальная прикладная выгода пока не доказана автоматически; изучите связанные публикации и оцените применимость.",
            "case": case, "stage": "Исследовательские публикации", "momentum": f"{len(unique)} публикаций в новой выборке; {old} в исторической",
            "first_observed": min(years) if years else None,
            "recent_count": len(unique), "historic_count": old,
            "explanation": [f"{len(unique)} публикаций в новой выборке против {old} в исторической", f"Первый год в новой выборке: {min(years) if years else 'нет даты'}", f"Проверяемых ссылок: {len(sources)}", "Упоминания считаются по ограниченной выборке, а не по всему корпусу"],
            "sources": sources, "basis": "Автоматическая группировка заголовков OpenAlex; содержательные выводы требуют экспертной проверки",
        })
    candidates.sort(key=lambda c: (-c["score"], -c["recent_count"], c["title"]))
    # Prevent near-duplicate n-grams from occupying the entire list.
    picked = []
    for c in candidates:
        tokens = set(c["title"].split())
        if any(len(tokens & set(p["title"].split())) / min(len(tokens), len(p["title"].split())) >= .75 for p in picked):
            excluded.append({"title": c["title"], "reason": "Почти повторяет более приоритетный кандидат"})
            continue
        picked.append(c)
        if len(picked) == 15:
            break
    trained_mode = bool(os.environ.get("SIGNAL_MODEL"))
    return {"query": query, "normalized_query": english, "mode": "live", "results": picked,
            "candidate_count": len(candidates), "source_count": len(recent) + len(historical),
            "excluded": excluded[:30], "total_matches": total_recent + total_historical,
            "score_note": ("Оценка вероятности классификатора, обученного на размеченных данных. Качество смотрите в файле метрик; для новой области требуется отдельная проверка." if trained_mode else "Эвристический индекс 0–100 по новизне, частоте, свежести и числу независимых ссылок. Это не вероятность и не оценка точности классификатора."),
            "coverage": f"OpenAlex: до {len(recent)} новых и {len(historical)} исторических записей по запросу «{english}». Первый год и частоты относятся только к полученной выборке."}
