import pytest
from pytest import MonkeyPatch

from app.services import chat_completion
from app.services.chat_completion import (
    _build_model,
    _build_streaming_model,
    _extract_country_from_prompt,
    _format_provider_error,
    _select_country_tool_call,
)


class FakeChatOpenAI:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class FakeProviderError(Exception):
    status_code = 402
    body = {
        "error": {
            "message": "Insufficient Balance",
            "type": "unknown_error",
            "code": "invalid_request_error",
        }
    }


def test_extract_country_trims_database_suffix() -> None:
    prompt = "Qué datos tengo de Argentina en mi base de datos?"
    assert _extract_country_from_prompt(prompt) == "Argentina"


def test_select_country_tool_call_uses_stored_data_tool() -> None:
    prompt = "Qué datos tengo de Argentina en mi base de datos?"
    tool_call = _select_country_tool_call(prompt)

    assert tool_call is not None
    tool_name, tool_args, timeout = tool_call
    assert tool_name == "get_country_stored_data"
    assert tool_args == {"country": "Argentina"}
    assert timeout == 20.0


def test_select_country_tool_call_keeps_web_search_for_regular_country_query() -> None:
    prompt = "Cuál es la capital de Argentina?"
    tool_call = _select_country_tool_call(prompt)

    assert tool_call is not None
    tool_name, tool_args, timeout = tool_call
    assert tool_name == "search_country_web"
    assert tool_args == {
        "country": "Argentina",
        "question": "Cuál es la capital de Argentina?",
    }
    assert timeout == 20.0


def test_select_country_tool_call_uses_compare_tool_for_stored_ranking_query() -> None:
    prompt = "Haz un ranking top 5 de población por países con datos guardados en la base de datos"
    tool_call = _select_country_tool_call(prompt)

    assert tool_call is not None
    tool_name, tool_args, timeout = tool_call
    assert tool_name == "compare_countries_on_key"
    assert tool_args == {"data_key": "poblacion", "top_n": 5}
    assert timeout == 20.0


def test_select_country_tool_call_extracts_pbi_from_natural_compare_prompt() -> None:
    prompt = "Comparame los países que tengo en mi base de datos por PBI"
    tool_call = _select_country_tool_call(prompt)

    assert tool_call is not None
    tool_name, tool_args, timeout = tool_call
    assert tool_name == "compare_countries_on_key"
    assert tool_args == {"data_key": "pbi"}
    assert timeout == 20.0


def test_build_model_supports_deepseek(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(chat_completion, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(chat_completion.settings, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(chat_completion.settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    model = _build_model(provider=" deepseek ", model="deepseek-v4", temperature=0.2)

    assert isinstance(model, FakeChatOpenAI)
    assert model.kwargs == {
        "model": "deepseek-v4",
        "temperature": 0.2,
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
    }


def test_build_streaming_model_supports_deepseek(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(chat_completion, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(chat_completion.settings, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(chat_completion.settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    model = _build_streaming_model(provider="deepseek", model="deepseek-v4", temperature=0.2)

    assert isinstance(model, FakeChatOpenAI)
    assert model.kwargs == {
        "model": "deepseek-v4",
        "temperature": 0.2,
        "streaming": True,
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
    }


def test_build_model_requires_deepseek_api_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(chat_completion, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(chat_completion.settings, "DEEPSEEK_API_KEY", "")

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        _build_model(provider="deepseek", model="deepseek-v4", temperature=0.2)


def test_format_provider_error_handles_deepseek_insufficient_balance() -> None:
    message = _format_provider_error(FakeProviderError(), provider="deepseek")

    assert message == (
        "Saldo insuficiente en DeepSeek. "
        "Recarga crédito en la cuenta del proveedor o selecciona otro modelo."
    )


# ---------------------------------------------------------------------------
# Stance / vote / alliance routing
# ---------------------------------------------------------------------------


def test_select_country_tool_call_routes_vote_query_for_single_country() -> None:
    prompt = "¿Cómo votaría Argentina sobre el embargo a Rusia?"
    tool_call = _select_country_tool_call(prompt)

    assert tool_call is not None
    tool_name, tool_args, timeout = tool_call
    assert tool_name == "get_country_stance"
    assert tool_args["country"] == "Argentina"
    assert tool_args["stance_type"] == "vote"
    assert "rusia" in tool_args["topic"].lower()
    assert timeout == 30.0


def test_select_country_tool_call_routes_position_query_per_country() -> None:
    prompt = (
        "¿Qué posición tendría cada país sobre la prohibición global de plásticos "
        "de un solo uso?"
    )
    tool_call = _select_country_tool_call(prompt)

    assert tool_call is not None
    tool_name, tool_args, timeout = tool_call
    assert tool_name == "research_country_stance"
    assert tool_args["stance_type"] == "position"
    assert "plasticos" in _normalize_for_assert(tool_args["topic"])
    assert timeout == 600.0


def test_select_country_tool_call_routes_allies_query() -> None:
    prompt = "¿Qué aliados puede tener España en la guerra de Ucrania?"
    tool_call = _select_country_tool_call(prompt)

    assert tool_call is not None
    tool_name, tool_args, timeout = tool_call
    assert tool_name == "find_country_allies"
    assert tool_args["country"] == "España"
    assert "ucrania" in tool_args["topic"].lower()
    assert tool_args["stance_type"] == "alliance"
    assert timeout == 600.0


def test_select_country_tool_call_routes_research_stance_for_global_vote() -> None:
    prompt = (
        "Investiga cómo votarían todos los países la propuesta de impuesto a las "
        "transacciones financieras."
    )
    tool_call = _select_country_tool_call(prompt)

    assert tool_call is not None
    tool_name, tool_args, _timeout = tool_call
    assert tool_name == "research_country_stance"
    assert tool_args["stance_type"] == "vote"


def _normalize_for_assert(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in normalized if not unicodedata.combining(c))
