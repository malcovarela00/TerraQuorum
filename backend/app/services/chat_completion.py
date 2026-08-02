import json
import os
import re
import time
import unicodedata
from collections.abc import AsyncGenerator, Sequence
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.models import ChatMessageDB

_PROVIDER_ERROR = (
    "Provider not supported. Use 'openai', 'anthropic', 'deepseek' or 'google'."
)
_PROVIDER_NAMES = {
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "google": "Google",
}


def _openai_compatible_kwargs(*, provider: str) -> dict[str, Any]:
    if provider == "openai":
        return {}
    if provider == "deepseek":
        if not settings.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY is required to use DeepSeek.")
        return {
            "api_key": settings.DEEPSEEK_API_KEY,
            "base_url": settings.DEEPSEEK_BASE_URL,
        }
    raise ValueError(_PROVIDER_ERROR)


def _extract_provider_error_detail(exc: Exception) -> tuple[int | None, str]:
    status_code = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    message = ""

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            raw_message = error.get("message")
            if isinstance(raw_message, str):
                message = raw_message

    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)

    if not message and response is not None:
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                raw_message = error.get("message")
                if isinstance(raw_message, str):
                    message = raw_message

    return status_code if isinstance(status_code, int) else None, message or str(exc)


def _format_provider_error(exc: Exception, *, provider: str) -> str:
    normalized_provider = provider.lower().strip()
    provider_name = _PROVIDER_NAMES.get(normalized_provider, "el proveedor del modelo")
    status_code, message = _extract_provider_error_detail(exc)
    normalized_message = message.lower()

    if status_code == 402 or "insufficient balance" in normalized_message:
        return (
            f"Saldo insuficiente en {provider_name}. "
            "Recarga crédito en la cuenta del proveedor o selecciona otro modelo."
        )

    return str(exc)


def _build_model(
    *, provider: str, model: str, temperature: float
) -> ChatOpenAI | ChatAnthropic | ChatGoogleGenerativeAI:
    normalized_provider = provider.lower().strip()
    if normalized_provider in {"openai", "deepseek"}:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            **_openai_compatible_kwargs(provider=normalized_provider),
        )
    if normalized_provider == "anthropic":
        return ChatAnthropic(
            model_name=model,
            temperature=temperature,
            timeout=None,
            stop=None,
        )
    if normalized_provider == "google":
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is required to use Google models.")
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=settings.GOOGLE_API_KEY,
        )
    raise ValueError(_PROVIDER_ERROR)


def _to_langchain_messages(
    *,
    history: Sequence[ChatMessageDB],
    user_prompt: str,
    system_prompt: str | None,
) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))

    for message in history:
        if message.role == "assistant":
            messages.append(AIMessage(content=message.content))
        elif message.role == "system":
            messages.append(SystemMessage(content=message.content))
        else:
            messages.append(HumanMessage(content=message.content))

    messages.append(HumanMessage(content=user_prompt))
    return messages


def _extract_response_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())

    return ""


_PER_COUNTRY_PATTERNS = [
    r"\bpor pa[ií]s\b",
    r"\bde cada pa[ií]s\b",
    r"\btodos los pa[ií]ses\b",
    r"\bpor pa[ií]ses\b",
    r"\bcada pa[ií]s\b",
    r"\blos pa[ií]ses\b",
    r"\bby country\b",
    r"\bper country\b",
    r"\ball countries\b",
]


_STORED_COUNTRY_DATA_PATTERNS = [
    r"\bbase de datos\b",
    r"\bmongodb\b",
    r"\bmongo\b",
    r"\bdatos guardados\b",
    r"\bdatos almacenados\b",
    r"\bya investigaste\b",
    r"\bya investigado\b",
    r"\bya guardaste\b",
    r"\bque datos tengo de\b",
    r"\bque datos hay de\b",
]


_COMPARE_COUNTRY_DATA_PATTERNS = [
    r"\bcompar[aei]\w*\b",
    r"\branking\b",
    r"\btop\s+\d+\b",
    r"\bpromedio\b",
    r"\bmedia\b",
    r"\bm[aá]ximo\b",
    r"\bm[ií]nimo\b",
]


_AVAILABLE_KEYS_PATTERNS = [
    r"\bclaves disponibles\b",
    r"\bdatos disponibles\b",
    r"\bindicadores disponibles\b",
    r"\bque datos tengo\b",
    r"\bqué datos tengo\b",
    r"\bque datos hay\b",
    r"\bqué datos hay\b",
    r"\bque puedo visualizar\b",
    r"\bqué puedo visualizar\b",
    r"\bvisualizar en (?:el )?mapa\b",
]


_COVERAGE_PATTERNS = [
    r"\bcobertura\b",
    r"\bcoverage\b",
    r"\bfaltan\b",
    r"\bfalta\b",
    r"\bsin dato\b",
    r"\bsin datos\b",
    r"\bcuantos paises tienen\b",
    r"\bcuántos países tienen\b",
    r"\bque paises tienen\b",
    r"\bqué países tienen\b",
]


_FILTER_PATTERNS = [
    r"\bfiltra\w*\b",
    r"\bpaises con\b",
    r"\bpaíses con\b",
    r"\bpaises donde\b",
    r"\bpaíses donde\b",
    r"\bmayor(?:es)? (?:a|que)\b",
    r"\bmenor(?:es)? (?:a|que)\b",
]


# ---------------------------------------------------------------------------
# Stance / vote / alliance queries
# ---------------------------------------------------------------------------

# Patterns that strongly indicate the user wants a stance/vote/position
# analysis on a topic, proposal or conflict.
_STANCE_PATTERNS = [
    r"\bcomo\s+votar(?:i|í)an?\b",
    r"\bvotar(?:i|í)an?\s+(?:a\s+favor|en\s+contra|por|contra)\b",
    r"\bqu[eé]\s+(?:posici[oó]n|postura|opini[oó]n|actitud|stance)\b",
    r"\b(?:postura|posici[oó]n|opini[oó]n|actitud)\s+(?:de|del|sobre|respecto)\b",
    r"\bdame\s+(?:la|el)?\s*(?:postura|posici[oó]n|opini[oó]n|actitud|voto)\b",
    r"\b(?:que|cu[aá]l)\s+ser(?:i|í)a\s+(?:la\s+)?(?:posici[oó]n|postura)\b",
    r"\bse\s+(?:opondr|opone|opondría|opondrian)\w*\b",
    r"\bapoyar(?:i|í)an?\b",
    r"\bestar(?:i|í)an?\s+(?:a\s+favor|en\s+contra)\b",
    r"\bvotar(?:i|í)an?\s+a\s+favor\b",
    r"\brespaldar(?:i|í)an?\b",
    r"\brechazar(?:i|í)an?\b",
    r"\bse\s+(?:alinear|alinear[ií]an?|alinearia)\b",
    r"\bvoto\s+(?:de|del|sobre|en|para)\b",
]

# Patterns specifically about asking who would be allies / coalition partners.
_ALLIES_PATTERNS = [
    r"\baliados?\s+(?:de|para|en|sobre|respecto|contra|puede|podr[ií]a)\b",
    r"\bqu[eé]\s+aliados?\b",
    r"\bcu[aá]l(?:es)?\s+ser(?:i|í)an?\s+(?:sus\s+)?aliados?\b",
    r"\bcoalici[oó]n\s+(?:con|para|en|de|podr[ií]a)\b",
    r"\balianzas?\s+(?:con|de|para|en|sobre|podr[ií]a|formar[ií]a)\b",
    r"\b(?:formar|formar[ií]a|formar[ií]an)\s+(?:una|sus)?\s*(?:alianzas?|coalici[oó]n|coaliciones)\b",
    r"\bqui[eé]nes?\s+apoyar(?:i|í)an?\b",
]


def _is_stance_query(prompt: str) -> bool:
    normalized = _normalize_prompt(prompt)
    return any(re.search(pattern, normalized) for pattern in _STANCE_PATTERNS)


def _is_allies_query(prompt: str) -> bool:
    normalized = _normalize_prompt(prompt)
    return any(re.search(pattern, normalized) for pattern in _ALLIES_PATTERNS)


def _infer_stance_type(prompt: str) -> str:
    """Infer 'vote' | 'alliance' | 'position' from the prompt keywords."""
    normalized = _normalize_prompt(prompt)
    if re.search(
        r"\b(?:aliad|alianza|coalici[oó]n|aliars|aliarse|rival|enemig)\w*\b",
        normalized,
    ):
        return "alliance"
    if re.search(
        r"\b(?:votar|votaria|votarian|voto|votos|votacion|elegir|"
        r"asamblea|resoluci[oó]n|propuesta)\w*\b",
        normalized,
    ):
        return "vote"
    return "position"


_STANCE_TOPIC_INTRO_PATTERNS = (
    r"\bsobre\b",
    r"\brespecto\s+(?:a|de|al)\b",
    r"\bacerca\s+de\b",
    r"\ben\s+cuanto\s+a\b",
    r"\bante\s+(?:la\s+propuesta\s+de|el\s+tema\s+de|la\s+resoluci[oó]n\s+de|el\s+conflicto\s+de)\b",
    r"\bante\b",
    r"\bsi\s+se\s+votara\b",
    r"\bfrente\s+(?:a|al)\b",
    r"\bcon\s+respecto\s+(?:a|al)\b",
    r"\bal\s+(?:tema|propuesta|conflicto|tratado)\s+de\b",
)


# Markers used to "trim" the head of the topic when extracting it after a
# country mention. These are stripped if they appear at the start of the tail.
_TOPIC_TRIM_PREFIXES = (
    r"sobre",
    r"respecto\s+(?:a|de|al)",
    r"acerca\s+de",
    r"en\s+cuanto\s+a",
    r"frente\s+(?:a|al)",
    r"con\s+respecto\s+(?:a|al)",
    r"ante",
    r"para",
    r"en\s+(?:la|el|los|las)\s+",
    r"en\s+",
    r"al\s+(?:tema|propuesta|conflicto|tratado)\s+de",
    r"al\s+",
    r"si\s+se\s+votara",
    # Common verb prefixes left over right after the country name:
    r"estar(?:[ií]an?)?\s+(?:a\s+favor|en\s+contra)\s+(?:de|del|al?)?",
    r"se\s+opondr(?:[ií]a|[ií]an)?\s+(?:a|al)?",
    r"votar(?:[ií]a|[ií]an)?\s+(?:a\s+favor|en\s+contra)?\s*(?:de|del|al?|sobre)?",
    r"apoyar(?:[ií]a|[ií]an)?\s*(?:a|al)?",
    r"rechazar(?:[ií]a|[ií]an)?\s*(?:a|al)?",
    r"podr(?:[ií]a|[ií]an)\s+(?:formar|tener|ser)\s+(?:una|sus)?\s*"
    r"(?:alianzas?|aliados?|coalici[oó]n|coaliciones)?\s*(?:con|de|para|en)?",
    r"(?:formar|formar[ií]an?)\s+(?:una|sus)?\s*(?:alianzas?|coalici[oó]n|coaliciones)\s*(?:con|de|para|en)?",
    r"puede\s+tener\s+(?:una|sus)?\s*(?:aliados?|alianzas?|coalici[oó]n|coaliciones)?\s*(?:con|de|para|en)?",
    r"tendr(?:[ií]a|[ií]an)?\s*(?:de)?",
)


def _trim_topic_prefixes(text: str) -> str:
    """Strip common verb / preposition fragments that survive at the start of the topic."""
    cleaned = text.strip(" ,.;:!?¿¡")
    changed = True
    safety_iterations = 6  # Avoid pathological loops on weird inputs.
    while changed and safety_iterations > 0:
        changed = False
        safety_iterations -= 1
        for prefix_pattern in _TOPIC_TRIM_PREFIXES:
            new_value = re.sub(
                rf"^(?:{prefix_pattern})\s+",
                "",
                cleaned,
                count=1,
                flags=re.IGNORECASE,
            )
            if new_value != cleaned:
                cleaned = new_value.strip(" ,.;:!?¿¡")
                changed = True
                break
    return cleaned


def _extract_stance_topic(prompt: str) -> str:
    """Pull the topic / proposal mentioned after a 'sobre/respecto a/etc' marker."""
    text = " ".join((prompt or "").strip().split())
    if not text:
        return ""

    for pattern in _STANCE_TOPIC_INTRO_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        tail = text[match.end() :].strip(" ,.;:!?")
        if not tail:
            continue
        if len(tail.split()) < 2:
            continue
        return tail

    # Fallback: drop typical prefixes and use the rest of the prompt.
    cleaned = re.sub(
        r"^(?:c[oó]mo|que|qu[eé]|cu[aá]l(?:es)?|dime|dame|quiero|saber|ver)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:votar(?:[ií]a|[ií]an)?|posici[oó]n|postura|opini[oó]n|aliados?|"
        r"alianza|coalici[oó]n|apoyar(?:[ií]a|[ií]an)?|estar[ií]an?\s+(?:a\s+favor|en\s+contra)|"
        r"se\s+opondr[ií]an?|se\s+oponen)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" ,.;:!?") or text


def _extract_stance_topic_after_country(prompt: str, country: str) -> str:
    """Return the stance topic by taking the prompt content after the country.

    This works much better than the generic ``_extract_stance_topic`` when the
    country acts as the explicit subject of the question, because we can use
    the country name as an unambiguous splitter and then strip leftover
    prepositions / verbs from the head of the tail.
    """
    text = " ".join((prompt or "").strip().split())
    if not text or not country:
        return _extract_stance_topic(prompt)

    match = re.search(rf"\b{re.escape(country)}\b", text, flags=re.IGNORECASE)
    if not match:
        return _extract_stance_topic(prompt)

    after = text[match.end() :].strip(" ,.;:!?¿¡")
    after = _trim_topic_prefixes(after)
    if not after or len(after.split()) < 2:
        return _extract_stance_topic(prompt)
    return after


def _split_prompt_at_topic_marker(prompt: str) -> tuple[str, str]:
    """Return (head, tail) splitting the prompt at the topic marker, if any."""
    text = " ".join((prompt or "").strip().split())
    if not text:
        return "", ""

    earliest: tuple[int, int] | None = None
    for pattern in _STANCE_TOPIC_INTRO_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and (earliest is None or match.start() < earliest[0]):
            earliest = (match.start(), match.end())

    if earliest is None:
        return text, ""
    return text[: earliest[0]].strip(), text[earliest[1] :].strip()


def _extract_subject_country_from_stance_prompt(prompt: str) -> str | None:
    """Find the country that is the subject of a stance/allies question.

    Looks for known country names *before* the topic marker, so we don't
    confuse "España" with the "Ucrania" mentioned in the topic.
    """
    head, _tail = _split_prompt_at_topic_marker(prompt)
    if not head:
        return None
    return _find_known_country_in_prompt(head)


def _normalize_prompt(prompt: str) -> str:
    normalized = unicodedata.normalize("NFKD", prompt.lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _is_per_country_query(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(re.search(p, lowered) for p in _PER_COUNTRY_PATTERNS)


def _is_stored_country_data_query(prompt: str) -> bool:
    normalized = _normalize_prompt(prompt)
    return any(
        re.search(pattern, normalized) for pattern in _STORED_COUNTRY_DATA_PATTERNS
    )


def _is_compare_stored_country_data_query(prompt: str) -> bool:
    normalized = _normalize_prompt(prompt)
    has_compare_signal = any(
        re.search(pattern, normalized) for pattern in _COMPARE_COUNTRY_DATA_PATTERNS
    )
    return has_compare_signal and _is_stored_country_data_query(prompt)


def _is_available_keys_query(prompt: str) -> bool:
    normalized = _normalize_prompt(prompt)
    return any(re.search(pattern, normalized) for pattern in _AVAILABLE_KEYS_PATTERNS)


def _is_coverage_query(prompt: str) -> bool:
    normalized = _normalize_prompt(prompt)
    return any(re.search(pattern, normalized) for pattern in _COVERAGE_PATTERNS)


def _is_filter_query(prompt: str) -> bool:
    normalized = _normalize_prompt(prompt)
    return any(re.search(pattern, normalized) for pattern in _FILTER_PATTERNS)


def _slugify_data_key(prompt: str) -> str:
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
        "indices",
        "tengo",
        "tenemos",
        "mi",
        "mis",
        "base",
        "dato",
        "datos",
        "haz",
        "hacer",
    }
    normalized = unicodedata.normalize("NFKD", prompt.lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    words = re.findall(r"[a-z]+", normalized)
    words = [w for w in words if w not in stop_words and len(w) > 2]
    return "_".join(words[:4]) or "dato"


def _extract_top_n_from_prompt(prompt: str) -> int | None:
    patterns = [
        r"\btop\s+(\d+)\b",
        r"\bprimer[oa]s?\s+(\d+)\b",
        r"\bmejores\s+(\d+)\b",
        r"\bmayores\s+(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _strip_common_data_words(text: str) -> str:
    cleaned = re.sub(
        r"\b(?:cobertura|coverage|faltan?|sin datos?|cuantos|cuántos|paises|países|"
        r"tienen|tiene|con|donde|filtra\w*|mayor(?:es)?|menor(?:es)?|igual|"
        r"superior(?:es)?|inferior(?:es)?|que|a|de|del|la|el|los|las|en|mi|"
        r"base|datos|guardados|almacenados|mongodb|mongo)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\d+(?:[.,]\d+)?", " ", cleaned)
    cleaned = re.sub(
        r"\b(?:mil|millon|millones|million|millions)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.split())


def _extract_compare_data_key(prompt: str) -> str:
    cleaned = re.sub(
        r"\b(?:haz|hacer|compar[aei]\w*|ranking|top\s+\d+|promedio|media|maximo|minimo)\b",
        "",
        prompt,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:base de datos|mongodb|mongo|datos guardados|datos almacenados|"
        r"ya investigaste|ya investigado|ya guardaste)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:por|de|del|para|con|sin|sobre|segun|según|usar|usando|los|las|"
        r"el|la|un|una|datos|guardados|almacenados|que|tengo|tenemos|mi|mis)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bpa[ií]ses\b", "", cleaned, flags=re.IGNORECASE)
    return _slugify_data_key(cleaned)


def _extract_coverage_data_key(prompt: str) -> str:
    return _slugify_data_key(_strip_common_data_words(prompt))


def _extract_filter_operator(prompt: str) -> str | None:
    normalized = _normalize_prompt(prompt)
    operator_patterns = [
        (r"\bmayor(?:es)?\s+(?:a|que)\b|\bsuperior(?:es)?\s+(?:a|que)\b|>", "gt"),
        (r"\bmenor(?:es)?\s+(?:a|que)\b|\binferior(?:es)?\s+(?:a|que)\b|<", "lt"),
        (r"\bigual(?:es)?\s+a\b|=", "eq"),
        (r"\bcontien(?:e|en)\b|\bincluy(?:e|en)\b", "contains"),
        (r"\bpaises con\b|\bpaíses con\b", "contains"),
        (r"\bsin dato\b|\bsin datos\b|\bfaltan\b", "missing"),
        (r"\bcon dato\b|\bcon datos\b|\btienen\b", "exists"),
    ]
    for pattern, operator in operator_patterns:
        if re.search(pattern, normalized):
            return operator
    return None


def _extract_filter_value(prompt: str, operator: str) -> object | None:
    if operator in {"exists", "missing"}:
        return None

    number_match = re.search(
        r"[-+]?\d+(?:[.,]\d+)?(?:\s*(?:mil|millon(?:es)?|million(?:s)?))?",
        prompt,
        flags=re.IGNORECASE,
    )
    if number_match:
        return number_match.group(0).strip()

    text_patterns = [
        r"\b(?:igual(?:es)?\s+a|contien(?:e|en)|incluy(?:e|en))\s+(.+)$",
    ]
    for pattern in text_patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" .,:;!?")
            return candidate or None
    if operator == "contains":
        match = re.search(r"\bpa[ií]ses\s+con\s+(.+)$", prompt, flags=re.IGNORECASE)
        if match:
            tokens = match.group(1).strip(" .,:;!?").split()
            if len(tokens) >= 2:
                return tokens[-1]
    return None


def _extract_filter_data_key(prompt: str, operator: str) -> str:
    cleaned = prompt
    if operator in {"gt", "lt", "eq"}:
        cleaned = re.split(
            r"\b(?:mayor(?:es)?\s+(?:a|que)|menor(?:es)?\s+(?:a|que)|"
            r"superior(?:es)?\s+(?:a|que)|inferior(?:es)?\s+(?:a|que)|igual(?:es)?\s+a)\b|[<>=]",
            prompt,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
    elif operator in {"contains"}:
        cleaned = re.split(
            r"\b(?:contien(?:e|en)|incluy(?:e|en))\b",
            prompt,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        match = re.search(r"\bpa[ií]ses\s+con\s+(.+)$", prompt, flags=re.IGNORECASE)
        if match:
            tokens = match.group(1).strip(" .,:;!?").split()
            if len(tokens) >= 2:
                cleaned = " ".join(tokens[:-1])
    return _slugify_data_key(_strip_common_data_words(cleaned))


def _extract_selected_countries_from_prompt(prompt: str) -> list[str]:
    match = re.search(
        r"\bcompar[aei]\w*\s+(?:entre\s+)?(.+?)(?:\s+(?:en|por|sobre|segun|según|usando|con)\s+.+)?$",
        prompt,
        flags=re.IGNORECASE,
    )
    if not match:
        return []

    country_part = match.group(1)
    country_part = re.sub(
        r"\b(?:paises|países)\b", " ", country_part, flags=re.IGNORECASE
    )
    pieces = re.split(r"\s*,\s*|\s+\b(?:y|e|vs|versus)\b\s+", country_part)
    countries = [
        piece.strip(" .,:;!?").title() for piece in pieces if piece.strip(" .,:;!?")
    ]
    return [country for country in countries if len(country) > 1]


def _extract_selected_compare_keys(prompt: str) -> list[str]:
    match = re.search(
        r"\b(?:en|por|sobre|segun|según|usando|con)\b\s+(.+)$",
        prompt,
        flags=re.IGNORECASE,
    )
    if not match:
        key = _extract_compare_data_key(prompt)
        return [key] if key else []

    key_part = match.group(1)
    key_part = re.sub(
        r"\b(?:base de datos|mongodb|mongo|datos guardados|datos almacenados)\b",
        "",
        key_part,
        flags=re.IGNORECASE,
    )
    pieces = re.split(r"\s*,\s*|\s+\b(?:y|e)\b\s+", key_part)
    keys = [_slugify_data_key(piece) for piece in pieces if piece.strip(" .,:;!?")]
    return [key for key in keys if key]


def _extract_question_topic(prompt: str) -> str:
    """Extract the core topic from the user prompt (without 'por país' etc.)."""
    cleaned = re.sub(
        r"\b(?:por|de cada|todos los|cada)\s+pa[ií]se?s?\b",
        "",
        prompt,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:dame|dime|quiero|muestra|muestrame|saber|ver)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:el|la|los|las|un|una|unos|unas|del)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.split()).strip() or prompt


def _build_country_lookup() -> dict[str, str]:
    """Map normalized country names → canonical Spanish names from the ISO list."""
    try:
        from app.mcp_servers.country_iso_codes import (  # type: ignore[import-untyped]
            COUNTRY_NAME_TO_ISO_NUMERIC,
        )
    except Exception:
        return {}

    lookup: dict[str, str] = {}
    for canonical_name in COUNTRY_NAME_TO_ISO_NUMERIC:
        normalized = unicodedata.normalize("NFKD", canonical_name.lower())
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))
        normalized = re.sub(r"[^a-z0-9 ]+", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        # Skip very short or parenthetical forms; they cause false positives.
        if not normalized or len(normalized) <= 2:
            continue
        lookup.setdefault(normalized, canonical_name)
    return lookup


_KNOWN_COUNTRY_LOOKUP = _build_country_lookup()


def _find_known_country_in_prompt(prompt: str) -> str | None:
    """Find the first known country name appearing in the prompt.

    When multiple countries are mentioned, the *earliest* one is returned
    (in stance queries the subject country usually comes first). Ties on
    position are broken by length (the longer canonical form wins) so
    "Estados Unidos de América" beats "Estados Unidos" when present.
    """
    if not _KNOWN_COUNTRY_LOOKUP or not prompt:
        return None

    normalized = unicodedata.normalize("NFKD", prompt.lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    earliest: tuple[int, int, str] | None = None  # (start, -length, canonical)
    for known_norm, canonical_name in _KNOWN_COUNTRY_LOOKUP.items():
        for match in re.finditer(
            rf"(?:^|\s){re.escape(known_norm)}(?:$|\s)",
            normalized,
        ):
            # Skip the leading whitespace if any so the start matches the
            # actual country word.
            start = match.start()
            if normalized[start : start + 1] == " ":
                start += 1
            sort_key = (start, -len(known_norm))
            if earliest is None or sort_key < (earliest[0], earliest[1]):
                earliest = (start, -len(known_norm), canonical_name)
    return earliest[2] if earliest else None


def _extract_country_from_prompt(prompt: str) -> str | None:
    normalized = " ".join(prompt.strip().split())
    if not normalized:
        return None

    def _clean_country_candidate(candidate: str) -> str:
        candidate = candidate.strip(" ,.;:!?")
        candidate = re.sub(
            r"\s+(?:en\s+(?:mi|la)\s+base\s+de\s+datos.*)$",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(
            r"\s+(?:guardad[oa]s?|almacenad[oa]s?|investigad[oa]s?).*$",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = candidate.strip(" ,.;:!?")
        if not candidate:
            return ""
        return candidate.title()

    # First: try the strong, explicit lookup using the canonical country list.
    known_country = _find_known_country_in_prompt(normalized)
    if known_country:
        return known_country

    patterns = [
        r"\bde\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*)",
        r"\ben\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            cleaned = _clean_country_candidate(match.group(1))
            if cleaned:
                return cleaned
    return None


def _select_country_tool_call(prompt: str) -> tuple[str, dict[str, Any], float] | None:
    if any(
        re.search(pattern, _normalize_prompt(prompt))
        for pattern in _COMPARE_COUNTRY_DATA_PATTERNS
    ):
        selected_countries = _extract_selected_countries_from_prompt(prompt)
        if len(selected_countries) >= 2:
            selected_keys = _extract_selected_compare_keys(prompt)
            if selected_keys:
                return (
                    "compare_selected_countries",
                    {"country_names": selected_countries, "data_keys": selected_keys},
                    20.0,
                )

    if _is_compare_stored_country_data_query(prompt):
        tool_args: dict[str, Any] = {
            "data_key": _extract_compare_data_key(prompt),
        }
        top_n = _extract_top_n_from_prompt(prompt)
        if top_n is not None:
            tool_args["top_n"] = top_n
        return ("compare_countries_on_key", tool_args, 20.0)

    if _is_filter_query(prompt):
        operator = _extract_filter_operator(prompt)
        if operator:
            return (
                "filter_countries_by_data",
                {
                    "data_key": _extract_filter_data_key(prompt, operator),
                    "operator": operator,
                    "value": _extract_filter_value(prompt, operator),
                },
                20.0,
            )

    country = _extract_country_from_prompt(prompt)

    # --- Geopolitical stance / vote / alliance routing ---
    is_allies_query = _is_allies_query(prompt)
    is_stance_query = _is_stance_query(prompt)

    if is_stance_query or is_allies_query:
        # For stance/allies queries we need the *subject* country (the one
        # whose stance we want), which usually appears before the topic
        # marker. Prefer that over the global match to avoid grabbing a
        # country mentioned only inside the topic itself.
        subject_country = _extract_subject_country_from_stance_prompt(prompt) or country
        if subject_country:
            topic = _extract_stance_topic_after_country(prompt, subject_country)
        else:
            topic = _extract_stance_topic(prompt) or prompt
        stance_type = _infer_stance_type(prompt)

        if is_allies_query and subject_country:
            return (
                "find_country_allies",
                {
                    "country": subject_country,
                    "topic": topic,
                    "stance_type": stance_type,
                },
                600.0,
            )

        if subject_country and not _is_per_country_query(prompt):
            return (
                "get_country_stance",
                {
                    "country": subject_country,
                    "topic": topic,
                    "stance_type": stance_type,
                },
                30.0,
            )
        return (
            "research_country_stance",
            {
                "topic": topic,
                "stance_type": stance_type,
            },
            600.0,
        )

    if country and _is_stored_country_data_query(prompt):
        return ("get_country_stored_data", {"country": country}, 20.0)

    if _is_available_keys_query(prompt):
        return ("list_available_country_data_keys", {}, 20.0)

    if _is_coverage_query(prompt):
        return (
            "get_country_data_coverage",
            {"data_key": _extract_coverage_data_key(prompt)},
            20.0,
        )

    if _is_per_country_query(prompt):
        return (
            "research_and_store_country_data",
            {
                "data_key": _slugify_data_key(prompt),
                "question": _extract_question_topic(prompt),
            },
            600.0,
        )

    if not country:
        return None

    return ("search_country_web", {"country": country, "question": prompt}, 20.0)


def _extract_mcp_result_text(data: object) -> str | None:
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        text_chunks = [
            chunk for chunk in data if isinstance(chunk, str) and chunk.strip()
        ]
        if text_chunks:
            return "\n".join(text_chunks)
    return str(data) if data else None


async def _fetch_country_tool_context(*, user_prompt: str) -> str | None:
    mcp_server_path = (
        Path(__file__).resolve().parents[1] / "mcp_servers" / "country_tools_server.py"
    )

    tool_call = _select_country_tool_call(user_prompt)
    if not tool_call:
        return None
    tool_name, tool_args, timeout = tool_call

    client = _country_mcp_client(mcp_server_path)
    async with client:
        result = await client.call_tool(tool_name, tool_args, timeout=timeout)
    return _extract_mcp_result_text(result.data)


def _compose_system_prompt(
    *, system_prompt: str | None, tool_context: str | None
) -> str | None:
    if not tool_context:
        return system_prompt

    tool_instruction = (
        "Usa la siguiente informacion recuperada desde una tool MCP. "
        "Responde en maximo dos frases, sin ofrecer acciones adicionales. "
        "Si la tool indica que guardo datos o metadata, dilo de forma breve. "
        "Si la informacion no alcanza para responder con certeza, dilo explicitamente.\n\n"
        f"{tool_context}"
    )
    if system_prompt:
        return f"{system_prompt}\n\n{tool_instruction}"
    return tool_instruction


async def generate_chat_response(
    *,
    history: Sequence[ChatMessageDB],
    user_prompt: str,
    provider: str,
    model: str,
    temperature: float,
    system_prompt: str | None,
) -> str:
    chat_model = _build_model(provider=provider, model=model, temperature=temperature)
    tool_context = await _fetch_country_tool_context(user_prompt=user_prompt)
    effective_system_prompt = _compose_system_prompt(
        system_prompt=system_prompt, tool_context=tool_context
    )
    messages = _to_langchain_messages(
        history=history,
        user_prompt=user_prompt,
        system_prompt=effective_system_prompt,
    )
    try:
        response = await chat_model.ainvoke(messages)
    except Exception as exc:
        raise RuntimeError(_format_provider_error(exc, provider=provider)) from exc
    response_text = _extract_response_text(response.content)
    if not response_text:
        raise ValueError("The selected model returned an empty response.")
    return response_text


# ---------------------------------------------------------------------------
# SSE streaming helpers
# ---------------------------------------------------------------------------


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_MCP_SERVER_PATH = (
    Path(__file__).resolve().parents[1] / "mcp_servers" / "country_tools_server.py"
)


def _country_mcp_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "MONGODB_SERVER": settings.MONGODB_SERVER,
            "MONGODB_PORT": str(settings.MONGODB_PORT),
            "MONGODB_DB": settings.MONGODB_DB,
            "MONGODB_USER": settings.MONGODB_USER,
            "MONGODB_PASSWORD": settings.MONGODB_PASSWORD,
            "OPENAI_API_KEY": settings.OPENAI_API_KEY,
        }
    )
    return env


def _country_mcp_client(server_path: Path) -> Client:
    transport = PythonStdioTransport(
        server_path,
        env=_country_mcp_env(),
        cwd=str(server_path.parents[2]),
    )
    return Client(transport)


async def _fetch_tool_context_streaming(
    *,
    user_prompt: str,
    acc: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Yield SSE events while calling MCP tools. Store results in *acc*."""
    tool_call = _select_country_tool_call(user_prompt)
    if not tool_call:
        return
    tool_name, tool_args, timeout = tool_call

    yield _sse_event("tool_call", {"tool_name": tool_name, "arguments": tool_args})

    start = time.monotonic()
    client = _country_mcp_client(_MCP_SERVER_PATH)
    async with client:
        result = await client.call_tool(tool_name, tool_args, timeout=timeout)
    duration_ms = int((time.monotonic() - start) * 1000)

    result_text = _extract_mcp_result_text(result.data) or ""
    acc["tool_context"] = result_text
    acc["tool_calls"] = [
        {
            "tool_name": tool_name,
            "arguments": tool_args,
            "result_summary": result_text[:500],
        }
    ]

    yield _sse_event(
        "tool_result",
        {
            "tool_name": tool_name,
            "result": result_text[:2000],
            "duration_ms": duration_ms,
        },
    )


_THINKING_MODELS = {
    "claude-3-5-sonnet-latest",
    "claude-3-7-sonnet-latest",
    "claude-sonnet-4-20250514",
}


def _build_streaming_model(
    *,
    provider: str,
    model: str,
    temperature: float,
) -> ChatOpenAI | ChatAnthropic | ChatGoogleGenerativeAI:
    normalized = provider.lower().strip()
    if normalized in {"openai", "deepseek"}:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=True,
            **_openai_compatible_kwargs(provider=normalized),
        )
    if normalized == "anthropic":
        kwargs: dict[str, Any] = {}
        if model in _THINKING_MODELS:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 10000}
            # Anthropic requires temperature=1 when extended thinking is on
            temperature = 1.0
        return ChatAnthropic(
            model_name=model,
            temperature=temperature,
            timeout=None,
            stop=None,
            streaming=True,
            **kwargs,
        )
    if normalized == "google":
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is required to use Google models.")
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=settings.GOOGLE_API_KEY,
            streaming=True,
        )
    raise ValueError(_PROVIDER_ERROR)


async def generate_chat_response_stream(
    *,
    history: Sequence[ChatMessageDB],
    user_prompt: str,
    provider: str,
    model: str,
    temperature: float,
    system_prompt: str | None,
) -> AsyncGenerator[str, None]:
    """Yield SSE events: tool_call, tool_result, thinking, content, done/error."""
    acc: dict[str, Any] = {
        "tool_context": None,
        "tool_calls": [],
        "thinking": "",
        "content": "",
    }

    try:
        # --- Phase 1: MCP tool calls ---
        async for event in _fetch_tool_context_streaming(
            user_prompt=user_prompt, acc=acc
        ):
            yield event

        # --- Phase 2: Build model & messages ---
        effective_system_prompt = _compose_system_prompt(
            system_prompt=system_prompt,
            tool_context=acc["tool_context"],
        )
        messages = _to_langchain_messages(
            history=history,
            user_prompt=user_prompt,
            system_prompt=effective_system_prompt,
        )
        chat_model = _build_streaming_model(
            provider=provider, model=model, temperature=temperature
        )

        # --- Phase 3: Stream LLM response ---
        async for chunk in chat_model.astream(messages):
            content = chunk.content
            if isinstance(content, str) and content:
                acc["content"] += content
                yield _sse_event("content", {"content": content})
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type", "")
                    if block_type == "thinking":
                        thinking_text = block.get("thinking", "")
                        if thinking_text:
                            acc["thinking"] += thinking_text
                            yield _sse_event("thinking", {"content": thinking_text})
                    elif block_type == "text":
                        text = block.get("text", "")
                        if text:
                            acc["content"] += text
                            yield _sse_event("content", {"content": text})

        if not acc["content"].strip():
            yield _sse_event(
                "error", {"detail": "El modelo devolvió una respuesta vacía."}
            )
            return

        # --- Phase 4: Done ---
        yield _sse_event(
            "done",
            {
                "content": acc["content"],
                "thinking": acc["thinking"],
                "tool_calls": acc["tool_calls"],
            },
        )
    except Exception as exc:
        yield _sse_event(
            "error", {"detail": _format_provider_error(exc, provider=provider)}
        )
