"""Country geopolitical stance analysis (votes, positions, alliances).

This module powers the MCP tools that estimate, for one or many countries,
how each one would vote on a proposal, what position they would take on a
topic, or who would be their allies. It uses the country's stored
``custom_data`` (population, languages, religion, GDP, etc.) plus a small
LLM reasoning step to produce a discrete category that can be visualised
on the world map.

Categories are intentionally small and discrete so the frontend can render
them directly with the existing categorical color palette.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger("country_stance")


# ---------------------------------------------------------------------------
# Stance types & categories
# ---------------------------------------------------------------------------

# Each stance type defines a closed set of categories. The categories are
# kept short and machine-friendly (snake_case) so they double as map values.
STANCE_TYPES: dict[str, dict[str, Any]] = {
    "vote": {
        "categories": ["a_favor", "en_contra", "abstencion", "no_participa"],
        "default": "abstencion",
        "label": "voto",
    },
    "position": {
        "categories": ["a_favor", "en_contra", "neutral", "mixto"],
        "default": "neutral",
        "label": "postura",
    },
    "alliance": {
        "categories": ["aliado", "no_aliado", "neutral", "rival"],
        "default": "neutral",
        "label": "alianza",
    },
}

DEFAULT_STANCE_TYPE = "position"

# Suffixes used to store metadata on the same custom_data document.
RATIONALE_SUFFIX = "__rationale"
META_SUFFIX = "__meta"

# Used to detect generated metadata keys when filtering custom_data for the
# map / item table.
METADATA_SUFFIXES = (RATIONALE_SUFFIX, META_SUFFIX)


def is_metadata_key(key: str) -> bool:
    """Return True if a custom_data key is internal stance metadata."""
    return any(key.endswith(suffix) for suffix in METADATA_SUFFIXES)


def normalize_stance_type(value: str | None) -> str:
    """Normalize the stance_type argument with a safe fallback."""
    if not isinstance(value, str):
        return DEFAULT_STANCE_TYPE
    cleaned = value.strip().lower()
    return cleaned if cleaned in STANCE_TYPES else DEFAULT_STANCE_TYPE


def get_allowed_categories(stance_type: str) -> list[str]:
    return STANCE_TYPES[normalize_stance_type(stance_type)]["categories"]


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a",
    "ante",
    "bajo",
    "con",
    "como",
    "contra",
    "cual",
    "cuales",
    "de",
    "del",
    "desde",
    "donde",
    "el",
    "en",
    "entre",
    "es",
    "ese",
    "esa",
    "esos",
    "esas",
    "este",
    "esta",
    "estos",
    "estas",
    "hacia",
    "hasta",
    "la",
    "las",
    "le",
    "les",
    "lo",
    "los",
    "mas",
    "menos",
    "mi",
    "mis",
    "mucho",
    "muchos",
    "muy",
    "nada",
    "ni",
    "no",
    "nos",
    "o",
    "para",
    "pero",
    "por",
    "que",
    "qu",
    "se",
    "sea",
    "segun",
    "ser",
    "si",
    "sin",
    "sobre",
    "su",
    "sus",
    "tan",
    "tanto",
    "te",
    "tu",
    "tus",
    "un",
    "una",
    "unos",
    "unas",
    "usar",
    "usando",
    "y",
    "ya",
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def slugify_topic(text: str, *, prefix: str = "") -> str:
    """Generate a snake_case slug suitable as a custom_data key."""
    if not isinstance(text, str):
        text = str(text or "")
    normalized = _strip_accents(text).lower()
    words = re.findall(r"[a-z0-9]+", normalized)
    words = [w for w in words if w not in _STOP_WORDS and len(w) > 2]
    body = "_".join(words[:6]) or "stance"
    full = f"{prefix.strip('_')}_{body}" if prefix else body
    full = re.sub(r"_+", "_", full).strip("_")
    return full or "stance"


def stance_key_for(
    topic: str, stance_type: str, *, custom_key: str | None = None
) -> str:
    """Build the canonical custom_data key for a (topic, stance_type) pair."""
    if isinstance(custom_key, str) and custom_key.strip():
        candidate = slugify_topic(custom_key)
        return candidate
    stype = normalize_stance_type(stance_type)
    label = STANCE_TYPES[stype]["label"]
    return slugify_topic(topic, prefix=label)


# ---------------------------------------------------------------------------
# Country context construction
# ---------------------------------------------------------------------------

# Subset of indicators we surface to the LLM if present in custom_data. We
# avoid dumping ALL custom_data so the prompt stays compact and cheap.
_CONTEXT_KEYS_PRIORITY: tuple[str, ...] = (
    "languages",
    "idiomas",
    "religion",
    "religiones",
    "region",
    "subregion",
    "capital",
    "currencies",
    "monedas",
    "poblacion",
    "population",
    "pib",
    "gdp",
    "pib_per_capita",
    "gdp_per_capita",
    "esperanza_de_vida",
    "tasa_alfabetizacion",
    "indice_gini",
    "regimen_politico",
    "gobierno",
    "alianzas_internacionales",
    "miembro_otan",
    "miembro_ue",
    "conflictos_recientes",
    "ideologia_dominante",
)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return f"{value:g}" if isinstance(value, float) else str(value)
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(value)
    if value is None:
        return ""
    return str(value)


def build_country_context(
    country_doc: dict[str, Any], *, max_extra_keys: int = 8
) -> str:
    """Build a compact, human-readable context for one country."""
    name = str(country_doc.get("country_name", "") or "").strip() or "País sin nombre"
    iso = str(country_doc.get("iso_numeric", "") or "").strip()
    custom_data: dict[str, Any] = country_doc.get("custom_data") or {}

    lines: list[str] = [f"País: {name}"]
    if iso:
        lines.append(f"Código ISO numérico: {iso}")

    seen_keys: set[str] = set()

    for key in _CONTEXT_KEYS_PRIORITY:
        if key in custom_data and not is_metadata_key(key):
            value = _stringify(custom_data[key])
            if value:
                lines.append(f"- {key}: {value}")
                seen_keys.add(key)

    # Include a few additional non-metadata keys to give the LLM extra signal
    # without exploding the prompt size.
    extras_added = 0
    for key, raw_value in custom_data.items():
        if extras_added >= max_extra_keys:
            break
        if key in seen_keys or is_metadata_key(key):
            continue
        value = _stringify(raw_value)
        if not value:
            continue
        if len(value) > 200:
            value = value[:197] + "..."
        lines.append(f"- {key}: {value}")
        seen_keys.add(key)
        extras_added += 1

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "Eres un analista geopolítico imparcial. Estimas la postura más probable "
    "de un país sobre un tema o propuesta, basándote en su contexto cultural, "
    "religioso, económico, histórico y político. NO inventas datos: usas solo "
    "el contexto provisto y conocimiento general bien establecido. Tu salida "
    "es SIEMPRE un JSON válido con dos campos: 'stance' (una de las "
    "categorías permitidas) y 'rationale' (1-2 frases en español, máximo 280 "
    "caracteres, sin citas ni saltos de línea). Si la información es "
    "insuficiente devuelves la categoría neutra/abstencion correspondiente y "
    "lo dices brevemente en el rationale."
)


def _build_user_prompt(
    *,
    topic: str,
    stance_type: str,
    country_context: str,
    reference_country: str | None,
) -> str:
    stype = normalize_stance_type(stance_type)
    cfg = STANCE_TYPES[stype]
    categories_csv = ", ".join(f'"{c}"' for c in cfg["categories"])

    if stype == "vote":
        framing = (
            "Eres un analista de la ONU. La pregunta es: ¿cómo votaría este "
            f"país una propuesta sobre el tema descrito? Categorías válidas: {categories_csv}."
        )
    elif stype == "alliance":
        ref = (reference_country or "").strip() or "el país de referencia indicado"
        framing = (
            f"Evalúa la relación de alianza con {ref} respecto al tema descrito. "
            f"Categorías válidas: {categories_csv}. 'aliado' = apoyaría/cooperaría; "
            "'rival' = se opondría activamente; 'no_aliado' = distante; 'neutral' = sin postura clara."
        )
    else:
        framing = (
            "Estima la postura general de este país sobre el tema descrito. "
            f"Categorías válidas: {categories_csv}."
        )

    return (
        f"{framing}\n\n"
        f"Tema/propuesta:\n{topic.strip()}\n\n"
        f"Contexto del país:\n{country_context}\n\n"
        'Responde SOLO con JSON: {"stance": "<categoría>", "rationale": "<1-2 frases>"}'
    )


# ---------------------------------------------------------------------------
# LLM execution
# ---------------------------------------------------------------------------

_MODEL_NAME = "gpt-4o-mini"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_REQUEST_TIMEOUT = 25.0
_MAX_TOKENS = 200


class CountryStanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stance: str
    rationale: str = Field(min_length=1, max_length=320)


def _json_schema_response_format(
    *,
    name: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


def _country_stance_response_format(stance_type: str) -> dict[str, Any]:
    schema = CountryStanceOutput.model_json_schema()
    schema["properties"]["stance"]["enum"] = get_allowed_categories(stance_type)
    schema["additionalProperties"] = False
    return _json_schema_response_format(name="country_stance", schema=schema)


def _parse_stance_payload(answer: str) -> CountryStanceOutput | None:
    try:
        return CountryStanceOutput.model_validate_json(answer)
    except (ValidationError, ValueError) as exc:
        log.warning(
            "Invalid structured stance payload: [%s] %s", type(exc).__name__, exc
        )
        return None


def _normalize_stance_value(value: Any, *, stance_type: str) -> str:
    cfg = STANCE_TYPES[normalize_stance_type(stance_type)]
    allowed: list[str] = cfg["categories"]
    default: str = cfg["default"]

    if not isinstance(value, str):
        return default
    cleaned = _strip_accents(value).strip().lower().replace(" ", "_").replace("-", "_")
    cleaned = re.sub(r"[^a-z0-9_]+", "", cleaned)

    if cleaned in allowed:
        return cleaned

    aliases = {
        "favor": "a_favor",
        "afavor": "a_favor",
        "apoya": "a_favor",
        "apoyaria": "a_favor",
        "si": "a_favor",
        "yes": "a_favor",
        "support": "a_favor",
        "for": "a_favor",
        "contra": "en_contra",
        "encontra": "en_contra",
        "rechaza": "en_contra",
        "no": "en_contra",
        "against": "en_contra",
        "opposed": "en_contra",
        "abstain": "abstencion",
        "abstain_": "abstencion",
        "abstenerse": "abstencion",
        "abstención": "abstencion",
        "abstencion_": "abstencion",
        "ally": "aliado",
        "aliada": "aliado",
        "rival_": "rival",
        "enemigo": "rival",
        "enemy": "rival",
        "no_aliado_": "no_aliado",
        "noaligned": "no_aliado",
        "non_aligned": "no_aliado",
        "neutro": "neutral",
        "mixed": "mixto",
        "ambiguo": "mixto",
        "no_participa_": "no_participa",
        "absent": "no_participa",
    }
    aliased = aliases.get(cleaned)
    if aliased and aliased in allowed:
        return aliased
    return default


def _normalize_rationale(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", value).strip().strip('"').strip("'")
    if len(cleaned) > 320:
        cleaned = cleaned[:317] + "..."
    return cleaned


async def _call_openai(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    user_prompt: str,
    stance_type: str,
) -> CountryStanceOutput | None:
    try:
        resp = await client.post(
            _OPENAI_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _MODEL_NAME,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": _MAX_TOKENS,
                "response_format": _country_stance_response_format(stance_type),
            },
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
        refusal = message.get("refusal")
        if refusal:
            log.warning("OpenAI stance call refused: %s", refusal)
            return None
        raw_answer = message.get("content")
        if not isinstance(raw_answer, str) or not raw_answer.strip():
            log.warning("OpenAI stance call returned empty structured content")
            return None
        return _parse_stance_payload(raw_answer)
    except Exception as exc:
        log.warning("OpenAI stance call failed: [%s] %s", type(exc).__name__, exc)
        return None


async def analyze_country_stance(
    *,
    client: httpx.AsyncClient,
    api_key: str,
    topic: str,
    stance_type: str,
    country_context: str,
    reference_country: str | None = None,
) -> dict[str, str] | None:
    """Estimate the stance of a single country and return {stance, rationale}.

    Returns ``None`` if the LLM cannot be reached at all (no API key or
    network failure with no fallback). Otherwise always returns a dict with
    a category from the allowed set.
    """
    if not api_key:
        return None

    user_prompt = _build_user_prompt(
        topic=topic,
        stance_type=stance_type,
        country_context=country_context,
        reference_country=reference_country,
    )

    payload = await _call_openai(
        client,
        api_key=api_key,
        user_prompt=user_prompt,
        stance_type=stance_type,
    )
    if payload is None:
        return None

    stance_value = _normalize_stance_value(payload.stance, stance_type=stance_type)
    rationale = _normalize_rationale(payload.rationale)
    return {"stance": stance_value, "rationale": rationale}


async def analyze_all_countries_stance(
    *,
    api_key: str,
    countries: list[dict[str, Any]],
    topic: str,
    stance_type: str,
    reference_country: str | None = None,
    concurrency: int = 8,
    progress_callback: Any = None,
) -> dict[str, dict[str, str]]:
    """Analyze stance for every country concurrently.

    Returns a dict keyed by ``str(country['_id'])`` with the stance + rationale.
    """
    if not api_key or not countries:
        return {}

    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: dict[str, dict[str, str]] = {}

    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT + 5.0,
        limits=httpx.Limits(
            max_connections=concurrency * 2, max_keepalive_connections=concurrency
        ),
    ) as client:

        async def _process(doc: dict[str, Any]) -> None:
            doc_id = str(
                doc.get("_id") or doc.get("iso_numeric") or doc.get("country_name")
            )
            context = build_country_context(doc)
            async with semaphore:
                outcome = await analyze_country_stance(
                    client=client,
                    api_key=api_key,
                    topic=topic,
                    stance_type=stance_type,
                    country_context=context,
                    reference_country=reference_country,
                )
            if outcome is not None:
                results[doc_id] = outcome
            if callable(progress_callback):
                try:
                    progress_callback(len(results), len(countries))
                except Exception:
                    pass

        await asyncio.gather(*[_process(doc) for doc in countries])

    return results


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def build_persistence_payload(
    *,
    data_key: str,
    stance: str,
    rationale: str,
    topic: str,
    stance_type: str,
    reference_country: str | None,
) -> dict[str, Any]:
    """Build the {field: value} update for a country in MongoDB."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        f"custom_data.{data_key}": stance,
        f"custom_data.{data_key}{RATIONALE_SUFFIX}": rationale,
        f"custom_data.{data_key}{META_SUFFIX}": {
            "topic": topic,
            "stance_type": normalize_stance_type(stance_type),
            "reference_country": reference_country,
            "model": _MODEL_NAME,
            "researched_at": now_iso,
        },
    }


# ---------------------------------------------------------------------------
# Aggregations / reporting
# ---------------------------------------------------------------------------


def summarize_distribution(
    *,
    stance_type: str,
    by_country: dict[str, str],
) -> dict[str, int]:
    """Count countries per category, including all allowed categories."""
    counts: dict[str, int] = dict.fromkeys(get_allowed_categories(stance_type), 0)
    for value in by_country.values():
        if value in counts:
            counts[value] += 1
    return counts


def split_allies_and_opponents(
    *,
    stance_type: str,
    target_stance: str,
    by_country_stance: dict[str, str],
) -> dict[str, str | list[str]]:
    """Group country names according to whether they share or oppose a stance."""
    cfg = STANCE_TYPES[normalize_stance_type(stance_type)]
    allowed = cfg["categories"]
    target = target_stance if target_stance in allowed else cfg["default"]

    opposite_map = {
        "a_favor": "en_contra",
        "en_contra": "a_favor",
        "aliado": "rival",
        "rival": "aliado",
    }
    opposite = opposite_map.get(target)

    allies: list[str] = []
    opposed: list[str] = []
    others: list[str] = []
    for country, value in by_country_stance.items():
        if value == target:
            allies.append(country)
        elif opposite and value == opposite:
            opposed.append(country)
        else:
            others.append(country)

    return {
        "target_stance": target,
        "allies": sorted(allies),
        "opposed": sorted(opposed),
        "neutral_or_other": sorted(others),
    }
