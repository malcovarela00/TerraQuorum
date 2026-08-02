import asyncio
import csv
import io
import json
import logging
import math
import os
import re
import sys
import unicodedata
import zipfile
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

MCP_DIR = Path(__file__).resolve().parent
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

import httpx  # noqa: E402, I001
from app.mcp_servers.country_iso_codes import (  # noqa: E402, I001
    ALPHA3_TO_ISO_NUMERIC,
    resolve_iso_numeric,
)
from app.mcp_servers.country_stance import (  # noqa: E402, I001
    METADATA_SUFFIXES,
    STANCE_TYPES,
    analyze_all_countries_stance,
    analyze_country_stance,
    build_country_context,
    build_persistence_payload,
    is_metadata_key,
    normalize_stance_type,
    split_allies_and_opponents,
    stance_key_for,
    summarize_distribution,
)
from fastmcp import FastMCP  # noqa: E402, I001
from pydantic import BaseModel, ConfigDict, Field, ValidationError  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[MCP %(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("country_tools")

# ---------------------------------------------------------------------------
# .env + config
# ---------------------------------------------------------------------------


def _load_env() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        log.warning(".env not found at %s", env_path)
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env()


def _is_running_in_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    if Path(__file__).resolve().as_posix().startswith("/app/"):
        return True
    try:
        return any(
            marker in Path("/proc/1/cgroup").read_text()
            for marker in ("docker", "containerd", "kubepods")
        )
    except OSError:
        return False


def _get_mongodb_target() -> tuple[str, str]:
    server = os.environ.get("MONGODB_SERVER", "localhost")
    port = os.environ.get("MONGODB_PORT", "27017")
    if _is_running_in_container() and server in {"", "localhost", "127.0.0.1"}:
        log.info("Using Docker service target for MongoDB: db:27017")
        return "db", "27017"
    return server, port


MONGODB_SERVER, MONGODB_PORT = _get_mongodb_target()
MONGODB_USER = os.environ.get("MONGODB_USER", "")
MONGODB_PASSWORD = os.environ.get("MONGODB_PASSWORD", "")
MONGODB_DB = os.environ.get("MONGODB_DB", "terraquorum_db")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

if MONGODB_USER and MONGODB_PASSWORD:
    MONGODB_URL = (
        f"mongodb://{MONGODB_USER}:{MONGODB_PASSWORD}"
        f"@{MONGODB_SERVER}:{MONGODB_PORT}/{MONGODB_DB}?authSource=admin"
    )
else:
    MONGODB_URL = f"mongodb://{MONGODB_SERVER}:{MONGODB_PORT}/{MONGODB_DB}"

log.info("MongoDB: %s:%s/%s", MONGODB_SERVER, MONGODB_PORT, MONGODB_DB)
log.info("OpenAI key present: %s", bool(OPENAI_API_KEY))

# ---------------------------------------------------------------------------
# FastMCP
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="CountryToolsServer",
    instructions=(
        "Use search_country_web when the user asks for factual data about a "
        "single country and internet lookup is needed. Use "
        "get_country_stored_data when the user asks what data is already stored "
        "for a specific country in the database without researching anything new. "
        "Use list_available_country_data_keys when the user asks what indicators "
        "or map data are already available. Use get_country_data_coverage when "
        "the user asks which countries have or are missing a stored data key. "
        "Use compare_selected_countries when the user asks to compare specific "
        "countries on one or more stored data keys. Use filter_countries_by_data "
        "when the user asks for countries matching a condition on stored data. "
        "Use compare_countries_on_key when the user asks to compare, rank, or "
        "summarize countries using a key that is already stored in custom_data. "
        "Use research_and_store_country_data when the user asks "
        "for a specific data point across ALL countries (e.g. 'birth rate by "
        "country', 'population by country'). "
        "Use research_country_stance when the user asks how ALL countries would "
        "vote, what position they would take, or how they would align on a "
        "concrete topic, proposal or treaty. Use get_country_stance for the "
        "same kind of question but limited to ONE specific country. Use "
        "find_country_allies when the user asks which countries would be "
        "allies (or rivals) of a specific country regarding a given topic."
    ),
)

# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------

_WIKIPEDIA_UA = (
    "terraquorum-mcp/1.0 (https://github.com/malcovarela00/TerraQuorum) httpx/0.27"
)
_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_shared_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": _BROWSER_UA},
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            follow_redirects=True,
        )
    return _shared_client


# ---------------------------------------------------------------------------
# World Bank API  (FREE, no auth, structured data for ALL countries at once)
# ---------------------------------------------------------------------------

_WB_COMMON_INDICATORS: dict[str, str] = {
    "SP.POP.TOTL": "Población total",
    "SP.DYN.CBRT.IN": "Tasa de natalidad (por 1.000 habitantes)",
    "SP.DYN.CDRT.IN": "Tasa de mortalidad (por 1.000 habitantes)",
    "NY.GDP.PCAP.CD": "PIB per cápita (USD corrientes)",
    "NY.GDP.MKTP.CD": "PIB total (USD corrientes)",
    "SP.DYN.LE00.IN": "Esperanza de vida al nacer (años)",
    "EN.POP.DNST": "Densidad de población (personas/km²)",
    "SL.UEM.TOTL.ZS": "Tasa de desempleo (% de fuerza laboral)",
    "FP.CPI.TOTL.ZG": "Inflación (precios al consumidor, % anual)",
    "SE.ADT.LITR.ZS": "Tasa de alfabetización adulta (%)",
    "SH.DYN.MORT": "Mortalidad infantil (por 1.000 nacidos vivos)",
    "AG.SRF.TOTL.K2": "Superficie total (km²)",
    "IT.NET.USER.ZS": "Usuarios de internet (% de población)",
    "EG.USE.ELEC.KH.PC": "Consumo eléctrico per cápita (kWh)",
    "SI.POV.GINI": "Índice de Gini",
    "VC.IHR.PSRC.P5": "Homicidios intencionales (por 100.000 habitantes)",
}

_WB_DATE_RANGE = "2018:2024"
_WB_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
_ISO_NUMERIC_TO_ALPHA3 = {
    numeric: alpha3 for alpha3, numeric in ALPHA3_TO_ISO_NUMERIC.items()
}

_REST_COUNTRIES_FIELDS: dict[str, str] = {
    "languages": "Idiomas oficiales",
    "currencies": "Monedas",
    "capital": "Capital",
    "region": "Región",
    "subregion": "Subregión",
}

CountryDataValue = float | str


class QuestionClassificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    indicator: str | None
    field: str | None
    value_type: str


class NumericValueExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None


class TextValueExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = Field(max_length=500)


def _json_schema_response_format(
    *,
    name: str,
    schema: dict,
) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


def _question_classification_response_format() -> dict:
    schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["worldbank", "restcountries", "websearch"],
            },
            "indicator": {
                "anyOf": [
                    {"type": "string", "enum": sorted(_WB_COMMON_INDICATORS)},
                    {"type": "null"},
                ],
            },
            "field": {
                "anyOf": [
                    {"type": "string", "enum": sorted(_REST_COUNTRIES_FIELDS)},
                    {"type": "null"},
                ],
            },
            "value_type": {"type": "string", "enum": ["number", "text"]},
        },
        "required": ["source", "indicator", "field", "value_type"],
        "additionalProperties": False,
    }
    return _json_schema_response_format(name="country_data_source", schema=schema)


def _value_extraction_response_format(value_type: str) -> dict:
    model = (
        NumericValueExtractionOutput
        if value_type == "number"
        else TextValueExtractionOutput
    )
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    return _json_schema_response_format(name="country_data_value", schema=schema)


def _parse_classification_payload(answer: str) -> QuestionClassificationOutput | None:
    try:
        return QuestionClassificationOutput.model_validate_json(answer)
    except (ValidationError, ValueError) as exc:
        log.warning(
            "Invalid structured classification payload: [%s] %s",
            type(exc).__name__,
            exc,
        )
        return None


def _parse_numeric_extraction_payload(
    answer: str,
) -> NumericValueExtractionOutput | None:
    try:
        return NumericValueExtractionOutput.model_validate_json(answer)
    except (ValidationError, ValueError) as exc:
        log.warning(
            "Invalid structured numeric extraction payload: [%s] %s",
            type(exc).__name__,
            exc,
        )
        return None


def _parse_text_extraction_payload(answer: str) -> TextValueExtractionOutput | None:
    try:
        return TextValueExtractionOutput.model_validate_json(answer)
    except (ValidationError, ValueError) as exc:
        log.warning(
            "Invalid structured text extraction payload: [%s] %s",
            type(exc).__name__,
            exc,
        )
        return None


def _classification_to_dict(output: QuestionClassificationOutput) -> dict[str, str]:
    if output.source == "worldbank" and output.indicator in _WB_COMMON_INDICATORS:
        return {
            "source": "worldbank",
            "indicator": output.indicator,
            "field": "",
            "value_type": "number",
        }
    if output.source == "restcountries" and output.field in _REST_COUNTRIES_FIELDS:
        return {
            "source": "restcountries",
            "indicator": "",
            "field": output.field,
            "value_type": "text",
        }
    if output.source == "websearch":
        value_type = (
            output.value_type if output.value_type in {"number", "text"} else "text"
        )
        return {
            "source": "websearch",
            "indicator": "",
            "field": "",
            "value_type": value_type,
        }
    return {"source": "websearch", "indicator": "", "field": "", "value_type": "text"}


async def _classify_question_with_llm(question: str) -> dict[str, str]:
    """Classify the question into a structured source or a generic web lookup."""
    if not OPENAI_API_KEY:
        log.warning("No OPENAI_API_KEY, using keyword fallback for classification")
        return _classify_question_keywords(question)

    indicator_list = "\n".join(
        f"- {code}: {desc}" for code, desc in _WB_COMMON_INDICATORS.items()
    )
    restcountries_list = "\n".join(
        f"- {field}: {desc}" for field, desc in _REST_COUNTRIES_FIELDS.items()
    )

    prompt = (
        f'Clasifica esta pregunta: "{question}"\n\n'
        f"Indicadores del World Bank disponibles:\n{indicator_list}\n\n"
        f"Campos de REST Countries disponibles:\n{restcountries_list}\n\n"
        "Clasifica la mejor fuente. Si usas World Bank, source='worldbank', "
        "indicator debe ser uno de los códigos disponibles, field=null y "
        "value_type='number'. Si usas REST Countries, source='restcountries', "
        "field debe ser uno de los campos disponibles, indicator=null y "
        "value_type='text'. Si no coincide con ninguno, source='websearch', "
        "indicator=null, field=null y value_type='number' o 'text' según el dato.\n\n"
        "Usa value_type=number solo si el dato esperado es una cifra medible. "
        "Usa value_type=text para categorías o textos como idioma, religión, moneda, régimen político, etc."
    )

    try:
        client = await _get_http_client()
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 80,
                "response_format": _question_classification_response_format(),
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
        refusal = message.get("refusal")
        if refusal:
            log.warning("LLM classification refused: %s", refusal)
            return _classify_question_keywords(question)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return _classify_question_keywords(question)
        answer = content.strip()
        parsed = _parse_classification_payload(answer)
        if parsed is None:
            return _classify_question_keywords(question)
        classification = _classification_to_dict(parsed)
        log.info("LLM classification: %s", classification)
        return classification
    except Exception as exc:
        log.warning("LLM classification failed: [%s] %s", type(exc).__name__, exc)
        return _classify_question_keywords(question)


def _classify_question_keywords(question: str) -> dict[str, str]:
    """Keyword-based fallback when OpenAI is not available."""
    q = unicodedata.normalize("NFKD", question.lower())
    q = "".join(c for c in q if not unicodedata.combining(c))

    mapping = {
        "poblacion": "SP.POP.TOTL",
        "habitantes": "SP.POP.TOTL",
        "natalidad": "SP.DYN.CBRT.IN",
        "nacimiento": "SP.DYN.CBRT.IN",
        "mortalidad": "SP.DYN.CDRT.IN",
        "defuncion": "SP.DYN.CDRT.IN",
        "pib per capita": "NY.GDP.PCAP.CD",
        "pib": "NY.GDP.MKTP.CD",
        "gdp": "NY.GDP.MKTP.CD",
        "esperanza de vida": "SP.DYN.LE00.IN",
        "densidad": "EN.POP.DNST",
        "desempleo": "SL.UEM.TOTL.ZS",
        "inflacion": "FP.CPI.TOTL.ZG",
        "alfabetizacion": "SE.ADT.LITR.ZS",
        "mortalidad infantil": "SH.DYN.MORT",
        "superficie": "AG.SRF.TOTL.K2",
        "internet": "IT.NET.USER.ZS",
        "gini": "SI.POV.GINI",
        "homicidio": "VC.IHR.PSRC.P5",
        "homicidios": "VC.IHR.PSRC.P5",
        "tasa de homicidio": "VC.IHR.PSRC.P5",
        "indice de homicidio": "VC.IHR.PSRC.P5",
        "indice homicidio": "VC.IHR.PSRC.P5",
    }
    for keyword, code in mapping.items():
        if keyword in q:
            log.info("Keyword classification: '%s' → %s", keyword, code)
            return {"source": "worldbank", "indicator": code, "value_type": "number"}

    restcountries_mapping = {
        "idioma": "languages",
        "idiomas": "languages",
        "lengua": "languages",
        "lenguas": "languages",
        "language": "languages",
        "languages": "languages",
        "moneda": "currencies",
        "monedas": "currencies",
        "currency": "currencies",
        "currencies": "currencies",
        "capital": "capital",
        "region": "region",
        "subregion": "subregion",
        "sub-region": "subregion",
    }
    for keyword, field in restcountries_mapping.items():
        if keyword in q:
            log.info("Keyword classification: '%s' → REST Countries %s", keyword, field)
            return {"source": "restcountries", "field": field, "value_type": "text"}

    return {"source": "websearch", "value_type": "text"}


def _parse_worldbank_indicator_payload(data: object) -> dict[str, float]:
    if not isinstance(data, list) or len(data) < 2:
        log.error("World Bank API returned unexpected format: %s", str(data)[:200])
        return {}

    records = data[1]
    if not isinstance(records, list):
        log.error("World Bank API records not a list")
        return {}

    log.info("World Bank returned %d records", len(records))

    best: dict[str, tuple[str, float]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        iso3 = rec.get("countryiso3code", "")
        value = rec.get("value")
        date_str = rec.get("date", "0")
        if not iso3 or value is None:
            continue
        try:
            val = float(value)
        except (ValueError, TypeError):
            continue

        existing = best.get(iso3)
        if existing is None or date_str > existing[0]:
            best[iso3] = (date_str, val)

    result = {iso3: val for iso3, (_, val) in best.items()}
    log.info("World Bank: extracted values for %d countries", len(result))
    return result


async def _fetch_worldbank_indicator_url(url: str, *, retries: int = 2) -> dict[str, float]:
    client = await _get_http_client()
    for attempt in range(retries + 1):
        log.info("Fetching World Bank: %s", url)
        try:
            resp = await client.get(url, timeout=30.0)
            if resp.status_code in _WB_TRANSIENT_STATUSES and attempt < retries:
                log.warning(
                    "World Bank transient status %d; retrying %d/%d",
                    resp.status_code,
                    attempt + 1,
                    retries,
                )
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            resp.raise_for_status()
            return _parse_worldbank_indicator_payload(resp.json())
        except Exception as exc:
            if attempt < retries:
                log.warning(
                    "World Bank request failed; retrying %d/%d: [%s] %s",
                    attempt + 1,
                    retries,
                    type(exc).__name__,
                    exc,
                )
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            log.error("World Bank API failed: [%s] %s", type(exc).__name__, exc)
            return {}
    return {}


async def _fetch_worldbank_indicator(indicator_code: str) -> dict[str, float]:
    """Fetch a World Bank indicator for ALL countries in one API call.

    Returns: {iso_alpha3: value, ...}
    """
    url = (
        f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}"
        f"?format=json&per_page=20000&date={_WB_DATE_RANGE}"
    )
    return await _fetch_worldbank_indicator_url(url)


def _parse_worldbank_csv_download(
    content: bytes,
    *,
    alpha3_codes: set[str] | None = None,
) -> dict[str, float]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        log.error("World Bank CSV download did not return a ZIP file")
        return {}

    data_filename = next(
        (
            name
            for name in archive.namelist()
            if name.endswith(".csv")
            and not name.rsplit("/", 1)[-1].startswith("Metadata_")
        ),
        "",
    )
    if not data_filename:
        log.error("World Bank CSV download did not include an indicator CSV")
        return {}

    try:
        raw_text = archive.read(data_filename).decode("utf-8-sig")
    except Exception as exc:
        log.error("World Bank CSV decode failed: [%s] %s", type(exc).__name__, exc)
        return {}

    start_year, end_year = (int(part) for part in _WB_DATE_RANGE.split(":", 1))
    lines = raw_text.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines[:10])
            if line.startswith('"Country Name","Country Code",')
            or line.startswith("Country Name,Country Code,")
        ),
        None,
    )
    if header_index is None:
        log.error("World Bank CSV header not found")
        return {}

    result: dict[str, float] = {}
    reader = csv.DictReader(lines[header_index:])
    for row in reader:
        iso3 = str(row.get("Country Code", "")).strip().upper()
        if not iso3 or (alpha3_codes is not None and iso3 not in alpha3_codes):
            continue

        for year in range(end_year, start_year - 1, -1):
            raw_value = str(row.get(str(year), "")).strip()
            if not raw_value:
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue
            if math.isfinite(value):
                result[iso3] = value
                break

    log.info("World Bank CSV download: extracted values for %d countries", len(result))
    return result


async def _fetch_worldbank_indicator_download(
    indicator_code: str,
    alpha3_codes: list[str],
    *,
    retries: int = 2,
) -> dict[str, float]:
    requested = {code.strip().upper() for code in alpha3_codes if code.strip()}
    if not requested:
        return {}

    url = (
        f"https://api.worldbank.org/v2/en/indicator/{indicator_code}"
        "?downloadformat=csv"
    )
    client = await _get_http_client()
    for attempt in range(retries + 1):
        log.info("Fetching World Bank CSV download: %s", url)
        try:
            resp = await client.get(url, timeout=60.0)
            if resp.status_code in _WB_TRANSIENT_STATUSES and attempt < retries:
                log.warning(
                    "World Bank CSV transient status %d; retrying %d/%d",
                    resp.status_code,
                    attempt + 1,
                    retries,
                )
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            resp.raise_for_status()
            return _parse_worldbank_csv_download(resp.content, alpha3_codes=requested)
        except Exception as exc:
            if attempt < retries:
                log.warning(
                    "World Bank CSV download failed; retrying %d/%d: [%s] %s",
                    attempt + 1,
                    retries,
                    type(exc).__name__,
                    exc,
                )
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            log.error(
                "World Bank CSV download failed: [%s] %s",
                type(exc).__name__,
                exc,
            )
            return {}
    return {}


async def _fetch_worldbank_indicator_for_alpha3(
    indicator_code: str,
    alpha3_codes: list[str],
) -> dict[str, float]:
    """Fetch a World Bank indicator only for the requested ISO alpha-3 countries."""
    unique_codes = sorted(
        {code.strip().upper() for code in alpha3_codes if code.strip()}
    )
    if not unique_codes:
        return {}

    values: dict[str, float] = {}
    # Multi-country selectors are convenient but have been returning 502s
    # intermittently. Single-country requests are slower but much more stable.
    chunk_size = 1
    for index in range(0, len(unique_codes), chunk_size):
        chunk = unique_codes[index : index + chunk_size]
        selector = ";".join(chunk)
        per_page = max(1000, len(chunk) * 10)
        url = (
            f"https://api.worldbank.org/v2/country/{selector}/indicator/{indicator_code}"
            f"?format=json&per_page={per_page}&date={_WB_DATE_RANGE}"
        )
        values.update(await _fetch_worldbank_indicator_url(url))

    log.info(
        "World Bank targeted fetch: extracted values for %d/%d requested countries",
        len(values),
        len(unique_codes),
    )
    return values


async def _fetch_alpha3_to_numeric_mapping() -> dict[str, str]:
    """Get ISO alpha-3 → ISO numeric mapping from REST Countries API."""
    url = "https://restcountries.com/v3.1/all?fields=cca3,ccn3"
    client = await _get_http_client()
    try:
        resp = await client.get(url, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.error("REST Countries mapping failed: [%s] %s", type(exc).__name__, exc)
        return dict(ALPHA3_TO_ISO_NUMERIC)

    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            entries = data["data"]
        elif isinstance(data.get("countries"), list):
            entries = data["countries"]
        else:
            entries = list(data.values())
    elif isinstance(data, list):
        entries = data
    else:
        log.warning("REST Countries mapping returned unexpected payload: %s", type(data))
        return dict(ALPHA3_TO_ISO_NUMERIC)

    mapping: dict[str, str] = {}
    pending = list(entries)
    while pending:
        entry = pending.pop()
        if isinstance(entry, list):
            pending.extend(entry)
            continue
        if not isinstance(entry, dict):
            continue
        cca3 = str(entry.get("cca3") or entry.get("alpha3Code") or "").strip()
        ccn3 = str(entry.get("ccn3") or entry.get("numericCode") or "").strip()
        if cca3 and ccn3:
            mapping[cca3.upper()] = ccn3.zfill(3)
            continue
        for value in entry.values():
            if isinstance(value, dict):
                pending.append(value)
            elif isinstance(value, list):
                pending.extend(value)
    if len(mapping) < len(ALPHA3_TO_ISO_NUMERIC):
        missing = [
            alpha3
            for alpha3 in ALPHA3_TO_ISO_NUMERIC
            if alpha3 not in mapping
        ]
        if missing:
            log.warning(
                "REST Countries mapping incomplete; using local fallback for %d ISO alpha-3 codes",
                len(missing),
            )
    mapping.update(
        {k: v for k, v in ALPHA3_TO_ISO_NUMERIC.items() if k not in mapping}
    )
    log.info("REST Countries: loaded %d alpha3→numeric mappings", len(mapping))
    return mapping


def _format_restcountries_field(entry: dict, field: str) -> str | None:
    raw_value = entry.get(field)
    if field == "languages" and isinstance(raw_value, dict):
        values = sorted(
            str(value).strip() for value in raw_value.values() if str(value).strip()
        )
        return ", ".join(values) if values else None
    if field == "currencies" and isinstance(raw_value, dict):
        values = []
        for currency in raw_value.values():
            if not isinstance(currency, dict):
                continue
            name = str(currency.get("name", "")).strip()
            symbol = str(currency.get("symbol", "")).strip()
            if name and symbol:
                values.append(f"{name} ({symbol})")
            elif name:
                values.append(name)
        return ", ".join(sorted(values)) if values else None
    if field == "capital" and isinstance(raw_value, list):
        values = [str(value).strip() for value in raw_value if str(value).strip()]
        return ", ".join(values) if values else None
    if isinstance(raw_value, str):
        return raw_value.strip() or None
    return None


async def _fetch_restcountries_field(field: str) -> dict[str, str]:
    """Fetch a text field for all countries from REST Countries."""
    if field not in _REST_COUNTRIES_FIELDS:
        return {}

    url = f"https://restcountries.com/v3.1/all?fields=ccn3,{field}"
    client = await _get_http_client()
    try:
        resp = await client.get(url, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.error("REST Countries field fetch failed: [%s] %s", type(exc).__name__, exc)
        return {}

    values: dict[str, str] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        ccn3 = str(entry.get("ccn3", "")).strip()
        value = _format_restcountries_field(entry, field)
        if ccn3 and value:
            values[ccn3.zfill(3)] = value
    log.info("REST Countries: extracted %d values for field %s", len(values), field)
    return values


# ---------------------------------------------------------------------------
# Web search (fallback for questions that don't map to a structured API)
# ---------------------------------------------------------------------------


def _clean_html_snippet(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return unescape(cleaned)


async def _search_wikipedia(query: str, retries: int = 1) -> str:
    params: dict[str, str | int] = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 3,
        "utf8": 1,
        "format": "json",
    }
    for attempt in range(retries + 1):
        try:
            client = await _get_http_client()
            resp = await client.get(
                "https://es.wikipedia.org/w/api.php",
                params=params,
                headers={"User-Agent": _WIKIPEDIA_UA},
            )
            resp.raise_for_status()
            payload = resp.json()
            break
        except Exception as exc:
            log.warning(
                "Wikipedia %d/%d for '%s': [%s] %s",
                attempt + 1,
                retries + 1,
                query,
                type(exc).__name__,
                exc,
            )
            if attempt < retries:
                await asyncio.sleep(1.0)
            else:
                return ""

    matches = payload.get("query", {}).get("search", [])
    if not isinstance(matches, list) or not matches:
        return ""

    lines: list[str] = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        snippet = _clean_html_snippet(str(item.get("snippet", "")))
        if title:
            lines.append(f"- {title}: {snippet}")
    return "\n".join(lines)


def _normalize_result_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        raw_url = f"https:{raw_url}"
    parsed = urlparse(raw_url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return raw_url


async def _search_duckduckgo_html(query: str) -> str:
    try:
        client = await _get_http_client()
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        log.warning("DDG HTML for '%s': [%s] %s", query, type(exc).__name__, exc)
        return ""

    link_matches = re.findall(
        r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>',
        html,
        flags=re.DOTALL,
    )
    snippet_matches = re.findall(
        r'<a class="result__snippet" href=".*?">(.*?)</a>',
        html,
        flags=re.DOTALL,
    )
    if not link_matches:
        return ""

    lines: list[str] = []
    for idx, (raw_url, raw_title) in enumerate(link_matches[:5]):
        title = _clean_html_snippet(raw_title)
        source_url = _normalize_result_url(unescape(raw_url.strip()))
        snip = (
            _clean_html_snippet(snippet_matches[idx])
            if idx < len(snippet_matches)
            else ""
        )
        lines.append(
            f"- {title}: {snip} (Fuente: {source_url})"
            if snip
            else f"- {title} (Fuente: {source_url})"
        )
    return "\n".join(lines)


async def _web_search(query: str) -> str:
    result = await _search_wikipedia(query)
    if result:
        log.debug("Wikipedia returned %d chars", len(result))
        return result
    result = await _search_duckduckgo_html(query)
    if result:
        log.debug("DDG HTML returned %d chars", len(result))
        return result
    log.warning("ALL search sources empty for '%s'", query)
    return ""


# ---------------------------------------------------------------------------
# LLM value extraction (fallback for web search results)
# ---------------------------------------------------------------------------


async def _extract_value_with_llm(
    search_text: str,
    question: str,
    country_name: str,
    value_type: str = "text",
) -> CountryDataValue | None:
    if not OPENAI_API_KEY:
        return (
            _extract_numeric_value_regex(search_text)
            if value_type == "number"
            else None
        )

    prompt = (
        f"Del siguiente texto, extrae el dato que responde a '{question}' "
        f"para '{country_name}'.\n"
        f"Tipo esperado: {value_type}.\n"
        "Devuelve el valor extraído en el campo 'value'. "
        "Si el tipo esperado es number, value debe ser un número, no texto. "
        "Si hay varios valores textuales principales, sepáralos con coma. "
        "No inventes datos que no aparezcan en el texto. "
        "Si no encuentras el dato, usa value=null.\n\n"
        f"Texto:\n{search_text[:2000]}"
    )
    try:
        client = await _get_http_client()
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 120,
                "response_format": _value_extraction_response_format(value_type),
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
        refusal = message.get("refusal")
        if refusal:
            log.warning("LLM extraction refused for %s: %s", country_name, refusal)
            return (
                _extract_numeric_value_regex(search_text)
                if value_type == "number"
                else None
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return (
                _extract_numeric_value_regex(search_text)
                if value_type == "number"
                else None
            )
        answer = content.strip()
        if value_type == "number":
            numeric_payload = _parse_numeric_extraction_payload(answer)
            if numeric_payload is None:
                return _extract_numeric_value_regex(search_text)
            if numeric_payload.value is None:
                return None
            numeric = float(numeric_payload.value)
            return numeric if math.isfinite(numeric) else None

        text_payload = _parse_text_extraction_payload(answer)
        if text_payload is None or text_payload.value is None:
            return None
        cleaned = re.sub(r"\s+", " ", text_payload.value).strip()
        if cleaned:
            return cleaned
        return None
    except Exception as exc:
        log.warning(
            "LLM extraction failed for %s: [%s] %s",
            country_name,
            type(exc).__name__,
            exc,
        )
        return (
            _extract_numeric_value_regex(search_text)
            if value_type == "number"
            else None
        )


def _extract_numeric_value_regex(text: str) -> float | None:
    if not text:
        return None
    text = text.replace("\xa0", " ")
    for match in re.finditer(r"(\d[\d.,]*\d|\d+)", text):
        raw = match.group(1)
        cleaned = raw
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            parts = cleaned.split(",")
            cleaned = (
                cleaned.replace(",", ".")
                if len(parts) == 2 and len(parts[1]) <= 2
                else cleaned.replace(",", "")
            )
        elif "." in cleaned:
            parts = cleaned.split(".")
            if len(parts) > 2:
                cleaned = cleaned.replace(".", "")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if value == 0 or 1900 < value < 2100:
            continue
        return value
    return None


def _slugify(text: str) -> str:
    stop_words = {
        "dame",
        "los",
        "las",
        "el",
        "la",
        "de",
        "del",
        "por",
        "para",
        "cada",
        "todos",
        "todas",
        "pais",
        "paises",
        "que",
        "es",
        "son",
        "cuales",
        "cual",
        "como",
        "una",
        "uno",
        "unos",
        "unas",
        "con",
        "sin",
        "sus",
        "mas",
        "dime",
        "quiero",
        "saber",
        "ver",
        "muestra",
        "muestrame",
    }
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    words = re.findall(r"[a-z]+", normalized)
    words = [w for w in words if w not in stop_words and len(w) > 2]
    return "_".join(words[:4]) or "dato"


def _normalize_question_for_search(question: str) -> str:
    """Improve ambiguous questions before web search extraction."""
    q = unicodedata.normalize("NFKD", question.lower())
    q = "".join(c for c in q if not unicodedata.combining(c))
    if "homicidio" in q:
        return "tasa de homicidios por 100000 habitantes"
    return question


def _normalize_country_name(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _parse_numeric_candidate(raw_value: str) -> float | None:
    cleaned = raw_value.strip().replace("\xa0", " ")
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        cleaned = (
            cleaned.replace(",", ".")
            if len(parts) == 2 and len(parts[1]) <= 6
            else cleaned.replace(",", "")
        )
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 2:
            cleaned = cleaned.replace(".", "")

    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _coerce_stored_numeric_value(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    if not stripped:
        return None
    direct = _parse_numeric_candidate(stripped)
    if direct is not None:
        return direct

    for match in re.finditer(r"[-+]?(?:\d[\d.,]*\d|\d+)", stripped):
        parsed = _parse_numeric_candidate(match.group(0))
        if parsed is not None:
            return parsed
    return None


def _format_numeric_value(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _normalize_data_key_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _simplify_data_key_name(value: str) -> str:
    stop_words = {
        "dato",
        "datos",
        "pais",
        "paises",
        "country",
        "countries",
        "base",
        "database",
        "mongo",
        "mongodb",
        "mi",
        "mis",
        "tengo",
        "tenemos",
        "quiero",
        "comparar",
        "compare",
        "ranking",
        "top",
        "por",
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "en",
    }
    tokens = [
        token
        for token in _normalize_data_key_name(value).split("_")
        if token and token not in stop_words
    ]
    return "_".join(tokens)


def _collect_available_custom_data_keys(countries: list[dict]) -> list[str]:
    keys: set[str] = set()
    for doc in countries:
        custom_data = doc.get("custom_data")
        if not isinstance(custom_data, dict):
            continue
        for key in custom_data:
            if isinstance(key, str) and key.strip():
                keys.add(key.strip())
    return sorted(keys)


def _resolve_compare_data_key(
    requested_key: str,
    countries: list[dict],
) -> tuple[str | None, list[str]]:
    available_keys = _collect_available_custom_data_keys(countries)
    if not available_keys:
        return None, []

    exact_map = {_normalize_data_key_name(key): key for key in available_keys}
    requested_normalized = _normalize_data_key_name(requested_key)
    if requested_normalized in exact_map:
        return exact_map[requested_normalized], available_keys

    simplified_map: dict[str, list[str]] = {}
    requested_simplified = _simplify_data_key_name(requested_key)
    for key in available_keys:
        simplified = _simplify_data_key_name(key)
        if not simplified:
            continue
        simplified_map.setdefault(simplified, []).append(key)

    if (
        requested_simplified in simplified_map
        and len(simplified_map[requested_simplified]) == 1
    ):
        return simplified_map[requested_simplified][0], available_keys

    if requested_simplified:
        partial_matches = [
            key
            for simplified, keys in simplified_map.items()
            if simplified
            and (
                simplified == requested_simplified
                or simplified in requested_simplified
                or requested_simplified in simplified
            )
            for key in keys
        ]
        unique_matches = sorted(set(partial_matches))
        if len(unique_matches) == 1:
            return unique_matches[0], available_keys

    return None, available_keys


def _normalize_filter_values(raw_value: object) -> set[str]:
    if isinstance(raw_value, str):
        values = [raw_value]
    elif isinstance(raw_value, list):
        values = [item for item in raw_value if isinstance(item, str)]
    else:
        values = []
    return {_normalize_country_name(item) for item in values if item.strip()}


def _matches_compare_filters(
    document: dict,
    filters: dict[str, object] | None,
) -> bool:
    if not filters:
        return True

    country_names = _normalize_filter_values(filters.get("country_names"))
    if country_names:
        country_name = _normalize_country_name(str(document.get("country_name", "")))
        if country_name not in country_names:
            return False

    iso_numeric_filters = _normalize_filter_values(filters.get("iso_numeric"))
    if iso_numeric_filters:
        iso_numeric = _normalize_country_name(str(document.get("iso_numeric", "")))
        if iso_numeric not in iso_numeric_filters:
            return False

    custom_data = document.get("custom_data")
    custom_data = custom_data if isinstance(custom_data, dict) else {}

    custom_data_exists = _normalize_filter_values(filters.get("custom_data_exists"))
    if custom_data_exists:
        existing_keys = {_normalize_country_name(key) for key in custom_data}
        if not custom_data_exists.issubset(existing_keys):
            return False

    custom_data_equals = filters.get("custom_data_equals")
    if isinstance(custom_data_equals, dict):
        normalized_custom_data = {
            _normalize_country_name(str(key)): value
            for key, value in custom_data.items()
        }
        for raw_key, expected_value in custom_data_equals.items():
            key = _normalize_country_name(str(raw_key))
            if key not in normalized_custom_data:
                return False
            stored_value = normalized_custom_data[key]
            if isinstance(expected_value, str):
                if _normalize_country_name(
                    str(stored_value)
                ) != _normalize_country_name(expected_value):
                    return False
            elif stored_value != expected_value:
                return False

    return True


def _build_compare_summary(
    *,
    requested_data_key: str,
    resolved_data_key: str,
    countries: list[dict],
    top_n: int,
    filters: dict[str, object] | None,
) -> str:
    ranked: list[tuple[str, float]] = []
    text_values: list[tuple[str, str]] = []
    missing_countries: list[str] = []

    for doc in countries:
        name = str(doc.get("country_name", "")).strip()
        custom_data = doc.get("custom_data")
        custom_data = custom_data if isinstance(custom_data, dict) else {}
        raw_value = custom_data.get(resolved_data_key)
        numeric_value = _coerce_stored_numeric_value(raw_value)

        if numeric_value is not None:
            ranked.append((name, numeric_value))
            continue

        if isinstance(raw_value, str) and raw_value.strip():
            text_values.append((name, raw_value.strip()))
        else:
            if name:
                missing_countries.append(name)

    ranked.sort(key=lambda item: item[1], reverse=True)

    lines = [
        f"Comparación completada para la clave '{resolved_data_key}'.",
        f"Países considerados: {len(countries)}",
        f"Países con dato numérico: {len(ranked)}",
        f"Países sin dato: {len(missing_countries)}",
    ]
    if requested_data_key != resolved_data_key:
        lines.insert(
            1,
            f"Clave solicitada: '{requested_data_key}'. Se usó la clave almacenada '{resolved_data_key}'.",
        )
    if filters:
        lines.append(
            "Filtros aplicados: "
            + json.dumps(filters, ensure_ascii=False, sort_keys=True)
        )

    if ranked:
        values = [value for _, value in ranked]
        average = sum(values) / len(values)
        max_country, max_value = ranked[0]
        min_country, min_value = ranked[-1]
        lines.append(f"Media: {_format_numeric_value(average)}")
        lines.append(
            f"Valor mínimo: {_format_numeric_value(min_value)} ({min_country})"
        )
        lines.append(
            f"Valor máximo: {_format_numeric_value(max_value)} ({max_country})"
        )

        ranking_limit = min(top_n, len(ranked))
        lines.append(f"Ranking (top {ranking_limit}):")
        for position, (country_name, value) in enumerate(
            ranked[:ranking_limit], start=1
        ):
            lines.append(
                f"  {position}. {country_name}: {_format_numeric_value(value)}"
            )

    if text_values:
        text_values.sort(key=lambda item: item[0])
        lines.append("Datos encontrados:")
        for country_name, text_value in text_values[:top_n]:
            lines.append(f"  - {country_name}: {text_value}")
        if len(text_values) > top_n:
            lines.append(f"  ... y {len(text_values) - top_n} más")

    if missing_countries:
        lines.append("Países sin dato:")
        lines.append("  - " + ", ".join(sorted(missing_countries)))

    return "\n".join(lines)


def _get_custom_data(document: dict) -> dict:
    custom_data = document.get("custom_data")
    return custom_data if isinstance(custom_data, dict) else {}


def _is_present_custom_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _profile_custom_data_key(
    countries: list[dict],
    data_key: str,
    max_examples: int,
) -> dict[str, object]:
    present_count = 0
    numeric_count = 0
    text_count = 0
    other_count = 0
    examples: list[str] = []

    for doc in countries:
        custom_data = _get_custom_data(doc)
        value = custom_data.get(data_key)
        if not _is_present_custom_value(value):
            continue

        present_count += 1
        numeric_value = _coerce_stored_numeric_value(value)
        if numeric_value is not None:
            numeric_count += 1
        elif isinstance(value, str):
            text_count += 1
        else:
            other_count += 1

        if len(examples) < max_examples:
            country_name = str(doc.get("country_name", "")).strip() or "País sin nombre"
            examples.append(f"{country_name}: {value}")

    if present_count == 0:
        value_type = "empty"
    elif numeric_count == present_count:
        value_type = "number"
    elif text_count == present_count:
        value_type = "text"
    else:
        value_type = "mixed"

    return {
        "key": data_key,
        "type": value_type,
        "countries_with_data": present_count,
        "countries_without_data": max(0, len(countries) - present_count),
        "numeric_values": numeric_count,
        "text_values": text_count,
        "other_values": other_count,
        "examples": examples,
    }


def _resolve_country_documents(
    countries: list[dict],
    requested_country_names: list[str],
) -> tuple[list[dict], list[str]]:
    normalized_to_doc = {
        _normalize_country_name(str(doc.get("country_name", ""))): doc
        for doc in countries
        if str(doc.get("country_name", "")).strip()
    }
    resolved: list[dict] = []
    missing: list[str] = []
    seen_ids: set[str] = set()

    for raw_name in requested_country_names:
        requested_name = raw_name.strip()
        if not requested_name:
            continue
        normalized = _normalize_country_name(requested_name)
        document = normalized_to_doc.get(normalized)
        if document is None:
            matches = [
                doc
                for key, doc in normalized_to_doc.items()
                if normalized and (normalized in key or key in normalized)
            ]
            if len(matches) == 1:
                document = matches[0]
        if document is None:
            missing.append(requested_name)
            continue

        country_id = str(
            document.get("_id")
            or document.get("iso_numeric")
            or document.get("country_name")
        )
        if country_id not in seen_ids:
            seen_ids.add(country_id)
            resolved.append(document)

    return resolved, missing


def _format_custom_data_value(value: object) -> str:
    numeric_value = _coerce_stored_numeric_value(value)
    if numeric_value is not None:
        return _format_numeric_value(numeric_value)
    if _is_present_custom_value(value):
        return str(value)
    return "sin dato"


def _coerce_filter_number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, str):
        lowered = _normalize_country_name(value)
        multiplier = 1.0
        if re.search(r"\b(millon|millones|million|millions)\b", lowered):
            multiplier = 1_000_000.0
        elif re.search(r"\b(mil|thousand)\b", lowered):
            multiplier = 1_000.0
        parsed = _coerce_stored_numeric_value(value)
        return parsed * multiplier if parsed is not None else None
    return None


def _matches_data_condition(
    raw_value: object, operator: str, expected_value: object
) -> bool:
    normalized_operator = operator.strip().lower()
    if normalized_operator in {"exists", "present", "has_data"}:
        return _is_present_custom_value(raw_value)
    if normalized_operator in {"missing", "is_missing", "no_data"}:
        return not _is_present_custom_value(raw_value)

    if not _is_present_custom_value(raw_value):
        return False

    if normalized_operator in {"gt", "gte", "lt", "lte", ">", ">=", "<", "<="}:
        actual_number = _coerce_stored_numeric_value(raw_value)
        expected_number = _coerce_filter_number(expected_value)
        if actual_number is None or expected_number is None:
            return False
        if normalized_operator in {"gt", ">"}:
            return actual_number > expected_number
        if normalized_operator in {"gte", ">="}:
            return actual_number >= expected_number
        if normalized_operator in {"lt", "<"}:
            return actual_number < expected_number
        return actual_number <= expected_number

    actual_text = _normalize_country_name(str(raw_value))
    expected_text = _normalize_country_name(str(expected_value))
    if normalized_operator in {"eq", "equals", "=", "=="}:
        actual_number = _coerce_stored_numeric_value(raw_value)
        expected_number = _coerce_filter_number(expected_value)
        if actual_number is not None and expected_number is not None:
            return math.isclose(actual_number, expected_number)
        return actual_text == expected_text
    if normalized_operator in {"ne", "not_equals", "!=", "<>"}:
        return actual_text != expected_text
    if normalized_operator in {"contains", "includes"}:
        return expected_text in actual_text
    if normalized_operator in {"not_contains", "excludes"}:
        return expected_text not in actual_text

    return False


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------


async def _get_mongo_collection():  # type: ignore[no-untyped-def]
    from pymongo import AsyncMongoClient

    client = AsyncMongoClient(MONGODB_URL)
    db = client[MONGODB_DB]
    return client, db["countries"]


async def _find_country_document(
    collection,
    country_name: str,  # type: ignore[no-untyped-def]
):
    country_name = country_name.strip()
    if not country_name:
        return None

    exact_match = await collection.find_one(
        {"country_name": {"$regex": f"^{re.escape(country_name)}$", "$options": "i"}},
        {"_id": 0, "country_name": 1, "iso_numeric": 1, "custom_data": 1},
    )
    if exact_match:
        return exact_match

    normalized_input = _normalize_country_name(country_name)
    candidates = await collection.find(
        {}, {"_id": 0, "country_name": 1, "iso_numeric": 1, "custom_data": 1}
    ).to_list()
    for candidate in candidates:
        stored_name = str(candidate.get("country_name", "")).strip()
        if stored_name and _normalize_country_name(stored_name) == normalized_input:
            return candidate
    return None


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool
async def search_country_web(
    country: str, question: str = "informacion general"
) -> str:
    """
    Busca en internet informacion relacionada con un pais.

    Args:
        country: Nombre del pais a consultar (ej. Bolivia).
        question: Pregunta concreta a investigar para ese pais.
    """
    country_clean = country.strip()
    question_clean = question.strip() or "informacion general"
    if not country_clean:
        return "No se recibio un pais valido."

    query = f"{question_clean} {country_clean}"
    log.info("search_country_web: query='%s'", query)
    result = await _web_search(query)
    if result:
        return f"Resultados para '{question_clean}' en {country_clean}:\n{result}"

    return (
        f"No encontre resultados utiles en internet para '{question_clean}' en "
        f"{country_clean}."
    )


@mcp.tool
async def get_country_stored_data(
    country: str,
    keys: list[str] | None = None,
) -> str:
    """
    Devuelve solo los datos ya almacenados en MongoDB para un pais, sin buscar
    informacion nueva en internet.

    Args:
        country: Nombre del pais a consultar.
        keys: Lista opcional de claves de custom_data a devolver.
    """
    country_clean = country.strip()
    if not country_clean:
        return "No se recibio un pais valido."

    mongo_client, collection = await _get_mongo_collection()
    try:
        document = await _find_country_document(collection, country_clean)
        if not document:
            return f"No encontre un pais guardado en la base de datos con nombre '{country_clean}'."

        custom_data = document.get("custom_data") or {}
        if not isinstance(custom_data, dict):
            custom_data = {}

        filtered_keys = [
            key.strip() for key in (keys or []) if isinstance(key, str) and key.strip()
        ]
        if filtered_keys:
            requested_key_set = set(filtered_keys)
            custom_data = {
                key: value
                for key, value in custom_data.items()
                if key in requested_key_set
            }

        payload = {
            "country_name": document.get("country_name", country_clean),
            "iso_numeric": document.get("iso_numeric"),
            "custom_data": custom_data,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    finally:
        await mongo_client.close()


@mcp.tool
async def list_available_country_data_keys(
    include_examples: bool = True,
    max_examples: int = 3,
) -> str:
    """
    Lista las claves disponibles en custom_data para saber que datos pueden
    consultarse, compararse o visualizarse en el mapa.

    Args:
        include_examples: Incluye algunos paises de ejemplo por clave.
        max_examples: Cantidad maxima de ejemplos por clave.
    """
    max_examples = max(0, min(max_examples, 10))
    mongo_client, collection = await _get_mongo_collection()
    try:
        countries = await collection.find(
            {}, {"_id": 1, "country_name": 1, "iso_numeric": 1, "custom_data": 1}
        ).to_list()
        if not countries:
            return "No hay paises en la base de datos."

        available_keys = _collect_available_custom_data_keys(countries)
        if not available_keys:
            return "No hay claves disponibles en custom_data."

        profiles = [
            _profile_custom_data_key(
                countries,
                key,
                max_examples=max_examples if include_examples else 0,
            )
            for key in available_keys
        ]
        payload = {
            "total_countries": len(countries),
            "total_keys": len(available_keys),
            "keys": profiles,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    finally:
        await mongo_client.close()


@mcp.tool
async def get_country_data_coverage(
    data_key: str,
    include_missing_countries: bool = True,
    max_countries: int = 50,
) -> str:
    """
    Resume la cobertura de una clave guardada: paises con dato, paises sin dato
    y tipo de valor detectado.

    Args:
        data_key: Clave existente dentro de custom_data.
        include_missing_countries: Incluye nombres de paises sin dato.
        max_countries: Cantidad maxima de paises a listar por grupo.
    """
    requested_key = data_key.strip()
    if not requested_key:
        return "Se requiere una clave valida en data_key."

    max_countries = max(1, min(max_countries, 200))
    mongo_client, collection = await _get_mongo_collection()
    try:
        countries = await collection.find(
            {}, {"_id": 1, "country_name": 1, "iso_numeric": 1, "custom_data": 1}
        ).to_list()
        if not countries:
            return "No hay paises en la base de datos."

        resolved_key, available_keys = _resolve_compare_data_key(
            requested_key, countries
        )
        if not resolved_key:
            if available_keys:
                return (
                    f"No encontré una clave almacenada que coincida con '{requested_key}'. "
                    "Claves disponibles: " + ", ".join(available_keys)
                )
            return "No hay claves disponibles en custom_data."

        countries_with_data: list[str] = []
        countries_without_data: list[str] = []
        for doc in countries:
            country_name = str(doc.get("country_name", "")).strip()
            if not country_name:
                continue
            value = _get_custom_data(doc).get(resolved_key)
            if _is_present_custom_value(value):
                countries_with_data.append(country_name)
            else:
                countries_without_data.append(country_name)

        profile = _profile_custom_data_key(countries, resolved_key, max_examples=5)
        payload = {
            "requested_key": requested_key,
            "resolved_key": resolved_key,
            "total_countries": len(countries),
            "countries_with_data_count": len(countries_with_data),
            "countries_without_data_count": len(countries_without_data),
            "coverage_percent": round(
                (len(countries_with_data) / len(countries)) * 100, 2
            ),
            "type": profile["type"],
            "examples": profile["examples"],
            "countries_with_data": sorted(countries_with_data)[:max_countries],
        }
        if include_missing_countries:
            payload["countries_without_data"] = sorted(countries_without_data)[
                :max_countries
            ]
            if len(countries_without_data) > max_countries:
                payload["countries_without_data_truncated"] = (
                    len(countries_without_data) - max_countries
                )

        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    finally:
        await mongo_client.close()


@mcp.tool
async def compare_selected_countries(
    country_names: list[str],
    data_keys: list[str],
    include_missing: bool = True,
) -> str:
    """
    Compara paises concretos usando una o varias claves ya almacenadas en
    custom_data, sin investigar informacion nueva.

    Args:
        country_names: Lista de paises a comparar.
        data_keys: Lista de claves existentes dentro de custom_data.
        include_missing: Incluye paises o datos no encontrados.
    """
    requested_countries = [
        name.strip() for name in country_names if isinstance(name, str) and name.strip()
    ]
    requested_keys = [
        key.strip() for key in data_keys if isinstance(key, str) and key.strip()
    ]
    if len(requested_countries) < 2:
        return "Se requieren al menos dos paises para comparar."
    if not requested_keys:
        return "Se requiere al menos una clave en data_keys."

    mongo_client, collection = await _get_mongo_collection()
    try:
        countries = await collection.find(
            {}, {"_id": 1, "country_name": 1, "iso_numeric": 1, "custom_data": 1}
        ).to_list()
        if not countries:
            return "No hay paises en la base de datos."

        selected_countries, missing_countries = _resolve_country_documents(
            countries,
            requested_countries,
        )
        if len(selected_countries) < 2:
            return (
                "No encontré suficientes paises guardados para comparar. "
                f"Paises no encontrados: {', '.join(missing_countries)}"
            )

        resolved_keys: list[str] = []
        unresolved_keys: list[str] = []
        for requested_key in requested_keys:
            resolved_key, _ = _resolve_compare_data_key(requested_key, countries)
            if resolved_key:
                resolved_keys.append(resolved_key)
            else:
                unresolved_keys.append(requested_key)

        if not resolved_keys:
            available_keys = _collect_available_custom_data_keys(countries)
            return (
                "No encontré claves almacenadas que coincidan con la solicitud. "
                "Claves disponibles: " + ", ".join(available_keys)
            )

        rows: list[dict[str, object]] = []
        for doc in selected_countries:
            row: dict[str, object] = {
                "country_name": doc.get("country_name"),
                "iso_numeric": doc.get("iso_numeric"),
            }
            custom_data = _get_custom_data(doc)
            for key in resolved_keys:
                row[key] = custom_data.get(key)
            rows.append(row)

        numeric_summaries: dict[str, dict[str, object]] = {}
        for key in resolved_keys:
            values: list[tuple[str, float]] = []
            for doc in selected_countries:
                value = _coerce_stored_numeric_value(_get_custom_data(doc).get(key))
                if value is not None:
                    values.append((str(doc.get("country_name", "")), value))
            if values:
                values.sort(key=lambda item: item[1], reverse=True)
                numeric_summaries[key] = {
                    "highest": {"country": values[0][0], "value": values[0][1]},
                    "lowest": {"country": values[-1][0], "value": values[-1][1]},
                    "average": sum(value for _, value in values) / len(values),
                }

        payload = {
            "requested_countries": requested_countries,
            "resolved_countries": [
                doc.get("country_name") for doc in selected_countries
            ],
            "requested_keys": requested_keys,
            "resolved_keys": resolved_keys,
            "data": rows,
            "numeric_summaries": numeric_summaries,
        }
        if include_missing:
            payload["missing_countries"] = missing_countries
            payload["unresolved_keys"] = unresolved_keys

        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    finally:
        await mongo_client.close()


@mcp.tool
async def filter_countries_by_data(
    data_key: str,
    operator: str,
    value: object | None = None,
    limit: int = 50,
) -> str:
    """
    Filtra paises por una condicion sobre un dato guardado en custom_data.

    Args:
        data_key: Clave existente dentro de custom_data.
        operator: Operador. Soporta gt, gte, lt, lte, eq, ne, contains,
            not_contains, exists y missing.
        value: Valor esperado para comparar, salvo en exists/missing.
        limit: Cantidad maxima de paises a devolver.
    """
    requested_key = data_key.strip()
    normalized_operator = operator.strip().lower()
    if not requested_key:
        return "Se requiere una clave valida en data_key."
    if not normalized_operator:
        return "Se requiere un operador valido."

    limit = max(1, min(limit, 200))
    mongo_client, collection = await _get_mongo_collection()
    try:
        countries = await collection.find(
            {}, {"_id": 1, "country_name": 1, "iso_numeric": 1, "custom_data": 1}
        ).to_list()
        if not countries:
            return "No hay paises en la base de datos."

        resolved_key, available_keys = _resolve_compare_data_key(
            requested_key, countries
        )
        if not resolved_key:
            if available_keys:
                return (
                    f"No encontré una clave almacenada que coincida con '{requested_key}'. "
                    "Claves disponibles: " + ", ".join(available_keys)
                )
            return "No hay claves disponibles en custom_data."

        matches: list[dict[str, object]] = []
        for doc in countries:
            raw_value = _get_custom_data(doc).get(resolved_key)
            if _matches_data_condition(raw_value, normalized_operator, value):
                matches.append(
                    {
                        "country_name": doc.get("country_name"),
                        "iso_numeric": doc.get("iso_numeric"),
                        "value": raw_value,
                    }
                )

        matches.sort(key=lambda item: str(item.get("country_name", "")))
        payload = {
            "requested_key": requested_key,
            "resolved_key": resolved_key,
            "operator": normalized_operator,
            "value": value,
            "total_matches": len(matches),
            "matches": matches[:limit],
        }
        if len(matches) > limit:
            payload["truncated"] = len(matches) - limit

        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    finally:
        await mongo_client.close()


@mcp.tool
async def research_and_store_country_data(data_key: str, question: str) -> str:
    """
    Busca un dato estadistico para TODOS los paises de la base de datos y
    lo guarda en custom_data.  Usa APIs estructuradas (World Bank, REST Countries)
    cuando es posible, y busqueda web como fallback.

    Args:
        data_key: Clave en snake_case (ej. 'poblacion', 'tasa_natalidad').
        question: Dato a buscar (ej. 'poblacion', 'tasa de natalidad').
    """
    data_key = data_key.strip() or _slugify(question)
    question = question.strip()
    if not question:
        return "Se requiere una pregunta concreta."

    log.info("=== START === key=%s, question='%s'", data_key, question)

    # ------------------------------------------------------------------
    # Step 1: Classify the question
    # ------------------------------------------------------------------
    classification = await _classify_question_with_llm(question)
    source = classification.get("source", "websearch")
    indicator = classification.get("indicator", "")
    restcountries_field = classification.get("field", "")
    value_type = classification.get(
        "value_type", "number" if source == "worldbank" else "text"
    )
    log.info(
        "Classification: source=%s, indicator=%s, field=%s, value_type=%s",
        source,
        indicator,
        restcountries_field,
        value_type,
    )

    # ------------------------------------------------------------------
    # Step 2: Connect to MongoDB and get our countries
    # ------------------------------------------------------------------
    mongo_client, collection = await _get_mongo_collection()

    try:
        countries = await collection.find(
            {}, {"_id": 1, "country_name": 1, "iso_numeric": 1}
        ).to_list()
        if not countries:
            return "No hay paises en la base de datos."
        log.info("Found %d countries in DB", len(countries))

        # Ensure all countries have iso_numeric
        for doc in countries:
            if not doc.get("iso_numeric"):
                resolved = resolve_iso_numeric(doc.get("country_name", ""))
                if resolved:
                    doc["iso_numeric"] = resolved
                    await collection.update_one(
                        {"_id": doc["_id"]}, {"$set": {"iso_numeric": resolved}}
                    )

        # ------------------------------------------------------------------
        # Step 3: Fetch data based on classification
        # ------------------------------------------------------------------
        values_by_numeric: dict[str, CountryDataValue] = {}

        if source == "worldbank" and indicator:
            log.info("Using World Bank API with indicator %s", indicator)

            target_alpha3_codes = sorted(
                {
                    _ISO_NUMERIC_TO_ALPHA3[iso]
                    for doc in countries
                    if (iso := str(doc.get("iso_numeric") or "").zfill(3))
                    in _ISO_NUMERIC_TO_ALPHA3
                }
            )
            wb_data = await _fetch_worldbank_indicator_for_alpha3(
                indicator,
                target_alpha3_codes,
            )
            if not wb_data:
                log.warning(
                    "World Bank targeted JSON fetch returned no data, trying CSV download"
                )
                wb_data = await _fetch_worldbank_indicator_download(
                    indicator,
                    target_alpha3_codes,
                )
            if not wb_data:
                log.warning(
                    "World Bank CSV download returned no data, trying all countries"
                )
                wb_data = await _fetch_worldbank_indicator(indicator)

            if wb_data:
                missing_alpha3 = [
                    alpha3 for alpha3 in wb_data if alpha3 not in ALPHA3_TO_ISO_NUMERIC
                ]
                alpha3_to_numeric = (
                    await _fetch_alpha3_to_numeric_mapping()
                    if missing_alpha3
                    else ALPHA3_TO_ISO_NUMERIC
                )

                for alpha3, value in wb_data.items():
                    numeric = alpha3_to_numeric.get(alpha3)
                    if numeric:
                        values_by_numeric[numeric] = value

                log.info(
                    "Mapped %d values to ISO numeric codes", len(values_by_numeric)
                )
            else:
                log.warning("World Bank returned no data, falling back to web search")
                source = "websearch"

        if source == "restcountries" and restcountries_field:
            log.info("Using REST Countries API with field %s", restcountries_field)
            restcountries_data = await _fetch_restcountries_field(restcountries_field)
            if restcountries_data:
                values_by_numeric.update(restcountries_data)
            else:
                log.warning(
                    "REST Countries returned no data, falling back to web search"
                )
                source = "websearch"

        if source == "websearch":
            log.info("Using web search fallback (per-country)")
            values_by_numeric = await _web_search_all_countries(
                countries,
                question,
                value_type,
            )

        # ------------------------------------------------------------------
        # Step 4: Save values to MongoDB
        # ------------------------------------------------------------------
        found_count = 0
        not_found_count = 0
        min_val: float | None = None
        max_val: float | None = None
        min_country = ""
        max_country = ""
        sample_results: list[str] = []
        not_found_countries: list[str] = []

        for doc in countries:
            iso = doc.get("iso_numeric", "")
            name = doc.get("country_name", "")
            data_value = values_by_numeric.get(iso)

            await collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {f"custom_data.{data_key}": data_value}},
            )

            if data_value is not None:
                found_count += 1
                numeric_value = (
                    data_value if isinstance(data_value, (int, float)) else None
                )
                if numeric_value is not None:
                    if min_val is None or numeric_value < min_val:
                        min_val = numeric_value
                        min_country = name
                    if max_val is None or numeric_value > max_val:
                        max_val = numeric_value
                        max_country = name
                if len(sample_results) < 10:
                    sample_results.append(f"  - {name}: {data_value}")
            else:
                not_found_count += 1
                if name:
                    not_found_countries.append(name)

        log.info("=== DONE === found=%d, not_found=%d", found_count, not_found_count)

        lines = [
            f"Investigacion completada para '{question}' (clave: {data_key}).",
            f"Fuente de datos: {source}"
            + (
                f" ({indicator})"
                if indicator
                else f" ({restcountries_field})"
                if restcountries_field
                else ""
            ),
            f"Total paises procesados: {len(countries)}",
            f"Datos encontrados: {found_count}",
            f"Sin datos: {not_found_count}",
        ]
        if min_val is not None:
            lines.append(f"Valor minimo: {min_val} ({min_country})")
            lines.append(f"Valor maximo: {max_val} ({max_country})")
        if sample_results:
            lines.append("Ejemplos:")
            lines.extend(sample_results)
        if not_found_countries:
            lines.append("Países sin dato:")
            lines.append("  - " + ", ".join(sorted(not_found_countries)))
        lines.append(
            "Los datos se guardaron en la base de datos y estan disponibles "
            "en el mapa del dashboard."
        )
        return "\n".join(lines)

    finally:
        await mongo_client.close()
        if _shared_client and not _shared_client.is_closed:
            await _shared_client.aclose()


@mcp.tool
async def compare_countries_on_key(
    data_key: str,
    top_n: int | None = None,
    filters: dict[str, object] | None = None,
) -> str:
    """
    Compara paises usando un dato ya almacenado en custom_data, sin investigar
    informacion nueva.

    Args:
        data_key: Clave existente dentro de custom_data.
        top_n: Cantidad opcional de paises a mostrar en el ranking descendente.
        filters: Filtros opcionales. Soporta country_names, iso_numeric,
            custom_data_exists y custom_data_equals.
    """
    data_key = data_key.strip()
    if not data_key:
        return "Se requiere una clave valida en data_key."

    if top_n is not None and top_n < 1:
        return "top_n debe ser mayor o igual a 1."

    ranking_size = top_n or 10

    mongo_client, collection = await _get_mongo_collection()
    try:
        countries = await collection.find(
            {}, {"_id": 0, "country_name": 1, "iso_numeric": 1, "custom_data": 1}
        ).to_list()
        if not countries:
            return "No hay paises en la base de datos."

        filtered_countries = [
            doc for doc in countries if _matches_compare_filters(doc, filters)
        ]
        if not filtered_countries:
            return "No hay paises que coincidan con los filtros solicitados."

        resolved_key, available_keys = _resolve_compare_data_key(
            data_key, filtered_countries
        )
        if not resolved_key:
            if available_keys:
                return (
                    f"No encontré una clave almacenada que coincida con '{data_key}'. "
                    "Claves disponibles: " + ", ".join(available_keys)
                )
            return "No hay claves disponibles en custom_data para comparar."

        return _build_compare_summary(
            requested_data_key=data_key,
            resolved_data_key=resolved_key,
            countries=filtered_countries,
            top_n=ranking_size,
            filters=filters,
        )
    finally:
        await mongo_client.close()


async def _web_search_all_countries(
    countries: list[dict],  # type: ignore[type-arg]
    question: str,
    value_type: str,
) -> dict[str, CountryDataValue]:
    """Fallback: search the web per country and use LLM to extract values."""
    semaphore = asyncio.Semaphore(5)
    result: dict[str, CountryDataValue] = {}
    processed = 0
    normalized_question = _normalize_question_for_search(question)

    async def _process(doc: dict) -> None:  # type: ignore[type-arg]
        nonlocal processed
        name = doc.get("country_name", "")
        iso = doc.get("iso_numeric", "")
        async with semaphore:
            raw = await _web_search(f"{normalized_question} {name}")
            await asyncio.sleep(0.5)
        processed += 1
        if processed % 20 == 0:
            log.info("Web search progress: %d/%d", processed, len(countries))
        if not raw:
            return
        value = await _extract_value_with_llm(raw, question, name, value_type)
        if value is not None and iso:
            result[iso] = value
            log.info("[%s] value=%s", name, value)
        else:
            log.info("[%s] no value extracted", name)

    await asyncio.gather(*[_process(doc) for doc in countries])
    return result


# ---------------------------------------------------------------------------
# Geopolitical stance tools (vote / position / alliance)
# ---------------------------------------------------------------------------


_STANCE_TYPES_LIST = sorted(STANCE_TYPES.keys())


def _format_categories_per_type() -> str:
    return ", ".join(
        f"{stype}: [{', '.join(STANCE_TYPES[stype]['categories'])}]"
        for stype in _STANCE_TYPES_LIST
    )


def _stance_examples_lines(
    by_country_stance: dict[str, str], limit: int = 8
) -> list[str]:
    if not by_country_stance:
        return []
    sample = sorted(by_country_stance.items())[:limit]
    return [f"  - {country}: {value}" for country, value in sample]


@mcp.tool
async def research_country_stance(
    topic: str,
    stance_type: str = "position",
    data_key: str | None = None,
    reference_country: str | None = None,
    force_refresh: bool = False,
    concurrency: int = 8,
) -> str:
    """
    Investiga la postura, voto o alianza de TODOS los paises de la base de
    datos sobre un tema, propuesta o conflicto concreto, y guarda el
    resultado categorico en custom_data para visualizarlo en el mapa.

    Args:
        topic: Tema, propuesta o conflicto concreto a evaluar.
        stance_type: Tipo de analisis: 'vote' (a_favor/en_contra/abstencion/
            no_participa), 'position' (a_favor/en_contra/neutral/mixto) o
            'alliance' (aliado/no_aliado/neutral/rival).
        data_key: Clave opcional en snake_case para custom_data. Si no se
            indica, se genera a partir del tema.
        reference_country: Solo para stance_type='alliance'. Pais respecto al
            cual se evalua la alianza.
        force_refresh: Si es True, reanaliza paises que ya tienen valor.
        concurrency: Llamadas en paralelo al modelo (por defecto 8).
    """
    topic_clean = (topic or "").strip()
    if not topic_clean:
        return "Se requiere un tema o propuesta concreta para analizar."
    if not OPENAI_API_KEY:
        return (
            "No hay OPENAI_API_KEY configurada. Esta tool requiere acceso a "
            "OpenAI para razonar la postura por pais."
        )

    stance_type_norm = normalize_stance_type(stance_type)
    resolved_key = stance_key_for(topic_clean, stance_type_norm, custom_key=data_key)
    reference_clean = (reference_country or "").strip() or None
    if stance_type_norm == "alliance" and not reference_clean:
        return (
            "Para stance_type='alliance' se requiere indicar 'reference_country' "
            "(pais respecto al cual se evalua la alianza)."
        )

    log.info(
        "=== STANCE START === topic='%s', type=%s, key=%s, ref=%s, refresh=%s",
        topic_clean[:80],
        stance_type_norm,
        resolved_key,
        reference_clean,
        force_refresh,
    )

    mongo_client, collection = await _get_mongo_collection()
    try:
        countries = await collection.find(
            {}, {"_id": 1, "country_name": 1, "iso_numeric": 1, "custom_data": 1}
        ).to_list()
        if not countries:
            return "No hay paises en la base de datos."

        if force_refresh:
            pending_countries = countries
        else:
            pending_countries = [
                doc
                for doc in countries
                if not isinstance(_get_custom_data(doc).get(resolved_key), str)
                or not str(_get_custom_data(doc).get(resolved_key)).strip()
            ]
        cached_countries = [doc for doc in countries if doc not in pending_countries]
        log.info(
            "Stance: %d to analyze, %d cached",
            len(pending_countries),
            len(cached_countries),
        )

        new_results: dict[str, dict[str, str]] = {}
        if pending_countries:
            new_results = await analyze_all_countries_stance(
                api_key=OPENAI_API_KEY,
                countries=pending_countries,
                topic=topic_clean,
                stance_type=stance_type_norm,
                reference_country=reference_clean,
                concurrency=max(1, min(concurrency, 16)),
            )

        # Persist new results
        for doc in pending_countries:
            doc_id = str(
                doc.get("_id") or doc.get("iso_numeric") or doc.get("country_name")
            )
            outcome = new_results.get(doc_id)
            if not outcome:
                continue
            payload = build_persistence_payload(
                data_key=resolved_key,
                stance=outcome["stance"],
                rationale=outcome["rationale"],
                topic=topic_clean,
                stance_type=stance_type_norm,
                reference_country=reference_clean,
            )
            await collection.update_one({"_id": doc["_id"]}, {"$set": payload})

        # Build a complete view (stored + new) for reporting
        by_country_stance: dict[str, str] = {}
        no_value: list[str] = []
        for doc in countries:
            name = str(doc.get("country_name", "") or "").strip()
            doc_id = str(doc.get("_id") or doc.get("iso_numeric") or name)
            outcome = new_results.get(doc_id)
            if outcome:
                by_country_stance[name] = outcome["stance"]
                continue
            stored_value = _get_custom_data(doc).get(resolved_key)
            if isinstance(stored_value, str) and stored_value.strip():
                by_country_stance[name] = stored_value.strip()
            else:
                if name:
                    no_value.append(name)

        distribution = summarize_distribution(
            stance_type=stance_type_norm,
            by_country=by_country_stance,
        )

        lines = [
            f"Investigacion de postura completada para: '{topic_clean}'.",
            f"Tipo: {stance_type_norm} | Clave guardada: {resolved_key}",
            f"Paises analizados: {len(by_country_stance)} de {len(countries)}",
        ]
        if reference_clean:
            lines.append(f"Pais de referencia: {reference_clean}")
        lines.append("Distribucion:")
        for category, count in distribution.items():
            lines.append(f"  - {category}: {count}")
        sample_lines = _stance_examples_lines(by_country_stance)
        if sample_lines:
            lines.append("Ejemplos:")
            lines.extend(sample_lines)
        if no_value:
            lines.append(f"Paises sin valor: {len(no_value)}")
            preview = ", ".join(sorted(no_value)[:15])
            lines.append(f"  - {preview}{'...' if len(no_value) > 15 else ''}")
        lines.append(
            "Los datos estan disponibles en el mapa del dashboard "
            f"seleccionando la clave '{resolved_key}'."
        )
        return "\n".join(lines)
    finally:
        await mongo_client.close()


@mcp.tool
async def get_country_stance(
    country: str,
    topic: str,
    stance_type: str = "position",
    reference_country: str | None = None,
    force_refresh: bool = False,
) -> str:
    """
    Estima la postura, voto o alianza de UN pais concreto sobre un tema,
    propuesta o conflicto. Reutiliza el dato cacheado en MongoDB cuando
    existe, salvo que se pida force_refresh.

    Args:
        country: Nombre del pais a analizar.
        topic: Tema, propuesta o conflicto concreto a evaluar.
        stance_type: 'vote', 'position' o 'alliance'.
        reference_country: Solo para stance_type='alliance'.
        force_refresh: Si es True, reanaliza aunque ya exista un valor cacheado.
    """
    country_clean = (country or "").strip()
    topic_clean = (topic or "").strip()
    if not country_clean:
        return "No se recibio un pais valido."
    if not topic_clean:
        return "Se requiere un tema o propuesta concreta."
    if not OPENAI_API_KEY:
        return "No hay OPENAI_API_KEY configurada."

    stance_type_norm = normalize_stance_type(stance_type)
    resolved_key = stance_key_for(topic_clean, stance_type_norm)
    reference_clean = (reference_country or "").strip() or None
    if stance_type_norm == "alliance" and not reference_clean:
        return "Para stance_type='alliance' se requiere 'reference_country'."

    mongo_client, collection = await _get_mongo_collection()
    try:
        document = await _find_country_document(collection, country_clean)
        if not document:
            return f"No encontre el pais '{country_clean}' en la base de datos."

        custom_data = _get_custom_data(document)
        cached_value = custom_data.get(resolved_key)
        cached_rationale = custom_data.get(f"{resolved_key}__rationale")

        if not force_refresh and isinstance(cached_value, str) and cached_value.strip():
            lines = [
                f"Postura cacheada de {document.get('country_name', country_clean)} "
                f"sobre '{topic_clean}':",
                f"- Tipo: {stance_type_norm}",
                f"- Categoria: {cached_value.strip()}",
            ]
            if isinstance(cached_rationale, str) and cached_rationale.strip():
                lines.append(f"- Justificacion: {cached_rationale.strip()}")
            lines.append(
                f"Clave en custom_data: {resolved_key} "
                "(usa force_refresh=True para reanalizar)."
            )
            return "\n".join(lines)

        # Need a full doc to build context (with custom_data already present)
        context = build_country_context(document)

        async with httpx.AsyncClient(timeout=30.0) as client:
            outcome = await analyze_country_stance(
                client=client,
                api_key=OPENAI_API_KEY,
                topic=topic_clean,
                stance_type=stance_type_norm,
                country_context=context,
                reference_country=reference_clean,
            )

        if not outcome:
            return (
                f"No se pudo obtener una postura analizable para "
                f"{document.get('country_name', country_clean)}."
            )

        # Need the full document _id for the update; refetch if missing
        target_id = document.get("_id")
        if target_id is None:
            full_doc = await collection.find_one(
                {"country_name": document.get("country_name", country_clean)},
                {"_id": 1},
            )
            target_id = full_doc.get("_id") if full_doc else None

        if target_id is not None:
            payload = build_persistence_payload(
                data_key=resolved_key,
                stance=outcome["stance"],
                rationale=outcome["rationale"],
                topic=topic_clean,
                stance_type=stance_type_norm,
                reference_country=reference_clean,
            )
            await collection.update_one({"_id": target_id}, {"$set": payload})

        lines = [
            f"Analisis de {document.get('country_name', country_clean)} "
            f"sobre '{topic_clean}':",
            f"- Tipo: {stance_type_norm}",
            f"- Categoria: {outcome['stance']}",
        ]
        if outcome.get("rationale"):
            lines.append(f"- Justificacion: {outcome['rationale']}")
        if reference_clean:
            lines.append(f"- Pais de referencia: {reference_clean}")
        lines.append(
            f"Guardado en custom_data como '{resolved_key}'. "
            "Disponible en el mapa del dashboard."
        )
        return "\n".join(lines)
    finally:
        await mongo_client.close()


@mcp.tool
async def find_country_allies(
    country: str,
    topic: str,
    stance_type: str = "position",
    max_results: int = 30,
    force_refresh: bool = False,
    concurrency: int = 8,
) -> str:
    """
    Identifica los paises que serian aliados u opositores de un pais
    concreto respecto a un tema. Primero analiza la postura del pais
    objetivo y luego compara con la postura del resto de paises.

    Args:
        country: Pais cuya alineacion queremos investigar.
        topic: Tema, propuesta o conflicto concreto.
        stance_type: 'vote' (default 'position'), 'position' o 'alliance'.
        max_results: Tope de paises a listar por bando.
        force_refresh: Reanaliza aunque haya datos cacheados.
        concurrency: Llamadas paralelas al modelo.
    """
    country_clean = (country or "").strip()
    topic_clean = (topic or "").strip()
    if not country_clean:
        return "Se requiere un pais de referencia."
    if not topic_clean:
        return "Se requiere un tema o propuesta."
    if not OPENAI_API_KEY:
        return "No hay OPENAI_API_KEY configurada."

    stance_type_norm = normalize_stance_type(stance_type)
    if stance_type_norm == "alliance":
        # Aliances are already framed against the reference country: reuse
        # the regular flow with the country as reference.
        resolved_key = stance_key_for(
            topic_clean,
            stance_type_norm,
            custom_key=None,
        )
        reference_country: str | None = country_clean
    else:
        resolved_key = stance_key_for(topic_clean, stance_type_norm)
        reference_country = None
    max_results = max(1, min(int(max_results), 100))

    mongo_client, collection = await _get_mongo_collection()
    try:
        countries = await collection.find(
            {}, {"_id": 1, "country_name": 1, "iso_numeric": 1, "custom_data": 1}
        ).to_list()
        if not countries:
            return "No hay paises en la base de datos."

        target_doc = None
        for doc in countries:
            stored_name = str(doc.get("country_name", "") or "").strip()
            if stored_name and (
                stored_name.casefold() == country_clean.casefold()
                or _normalize_country_name(stored_name)
                == _normalize_country_name(country_clean)
            ):
                target_doc = doc
                break

        if target_doc is None:
            return f"No encontre el pais '{country_clean}' en la base de datos."

        # Determine which countries need analysis
        if force_refresh:
            pending = countries
        else:
            pending = [
                doc
                for doc in countries
                if not isinstance(_get_custom_data(doc).get(resolved_key), str)
                or not str(_get_custom_data(doc).get(resolved_key)).strip()
            ]

        new_results: dict[str, dict[str, str]] = {}
        if pending:
            new_results = await analyze_all_countries_stance(
                api_key=OPENAI_API_KEY,
                countries=pending,
                topic=topic_clean,
                stance_type=stance_type_norm,
                reference_country=reference_country,
                concurrency=max(1, min(concurrency, 16)),
            )

        # Persist new results
        for doc in pending:
            doc_id = str(
                doc.get("_id") or doc.get("iso_numeric") or doc.get("country_name")
            )
            outcome = new_results.get(doc_id)
            if not outcome:
                continue
            payload = build_persistence_payload(
                data_key=resolved_key,
                stance=outcome["stance"],
                rationale=outcome["rationale"],
                topic=topic_clean,
                stance_type=stance_type_norm,
                reference_country=reference_country,
            )
            await collection.update_one({"_id": doc["_id"]}, {"$set": payload})

        # Build the global view
        by_country_stance: dict[str, str] = {}
        for doc in countries:
            name = str(doc.get("country_name", "") or "").strip()
            doc_id = str(doc.get("_id") or doc.get("iso_numeric") or name)
            outcome = new_results.get(doc_id)
            if outcome:
                by_country_stance[name] = outcome["stance"]
                continue
            stored_value = _get_custom_data(doc).get(resolved_key)
            if isinstance(stored_value, str) and stored_value.strip():
                by_country_stance[name] = stored_value.strip()

        target_name = str(target_doc.get("country_name", "") or country_clean).strip()
        target_stance = by_country_stance.get(target_name)
        if not target_stance:
            return (
                f"No se pudo determinar la postura de {target_name}. "
                "Vuelve a intentarlo."
            )

        groups = split_allies_and_opponents(
            stance_type=stance_type_norm,
            target_stance=target_stance,
            by_country_stance={
                name: stance
                for name, stance in by_country_stance.items()
                if name != target_name
            },
        )

        lines = [
            f"Analisis de aliados de {target_name} sobre '{topic_clean}':",
            f"- Tipo de analisis: {stance_type_norm}",
            f"- Postura del pais objetivo: {target_stance}",
            f"- Paises analizados: {len(by_country_stance)}",
            "",
            f"Aliados (misma postura, {len(groups['allies'])}):",
        ]
        if groups["allies"]:
            preview = ", ".join(groups["allies"][:max_results])
            extra = (
                f" (+{len(groups['allies']) - max_results} mas)"
                if len(groups["allies"]) > max_results
                else ""
            )
            lines.append(f"  {preview}{extra}")
        else:
            lines.append("  (ninguno)")

        lines.append("")
        lines.append(f"Opositores (postura opuesta, {len(groups['opposed'])}):")
        if groups["opposed"]:
            preview = ", ".join(groups["opposed"][:max_results])
            extra = (
                f" (+{len(groups['opposed']) - max_results} mas)"
                if len(groups["opposed"]) > max_results
                else ""
            )
            lines.append(f"  {preview}{extra}")
        else:
            lines.append("  (ninguno)")

        lines.append("")
        lines.append(
            f"Resultados guardados con la clave '{resolved_key}' y disponibles "
            "en el mapa del dashboard."
        )
        return "\n".join(lines)
    finally:
        await mongo_client.close()


# Expose the full list of allowed stance types for documentation/tests.
__all__ = [
    "mcp",
    "STANCE_TYPES",
    "METADATA_SUFFIXES",
    "is_metadata_key",
]


if __name__ == "__main__":
    mcp.run()
