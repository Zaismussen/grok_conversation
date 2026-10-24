"""Tests for xAI STT keyterm (vocabulary) support."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechMetadata,
    SpeechResultState,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grok_conversation.config_flow import (
    RECOMMENDED_OPTIONS,
    validate_stt_keyterms,
)
from custom_components.grok_conversation.stt import XAIGrokSTTEntity
from custom_components.grok_conversation.voice_api import async_stt
from custom_components.grok_conversation.voice_const import (
    CONF_STT_KEYTERMS,
    STT_KEYTERM_MAX_COUNT,
    STT_KEYTERM_MAX_LENGTH,
    parse_stt_keyterms,
    split_stt_keyterms,
)


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   ", "\n,\n", []])
def test_parse_empty(raw: Any) -> None:
    """Empty / blank values produce no keyterms."""
    assert parse_stt_keyterms(raw) == []


def test_parse_newlines_commas_dedupe() -> None:
    """Newlines, commas and semicolons split; whitespace collapsed; case-insensitive dedupe."""
    raw = "Elowen\n  Grok ,elowen;Home   Assistant\n\nSkynet Prime"
    assert parse_stt_keyterms(raw) == [
        "Elowen",
        "Grok",
        "Home Assistant",
        "Skynet Prime",
    ]


def test_parse_accepts_list() -> None:
    """A list value (e.g. from YAML / future list selector) also works."""
    assert parse_stt_keyterms([" Elowen ", "", "Grok"]) == ["Elowen", "Grok"]


def test_parse_enforces_limits() -> None:
    """Over-length terms are skipped and the count is capped at the API max."""
    too_long = "x" * (STT_KEYTERM_MAX_LENGTH + 1)
    ok_len = "y" * STT_KEYTERM_MAX_LENGTH
    many = [f"term{i}" for i in range(STT_KEYTERM_MAX_COUNT + 20)]
    terms = parse_stt_keyterms([too_long, ok_len, *many])
    assert too_long not in terms
    assert terms[0] == ok_len
    assert len(terms) == STT_KEYTERM_MAX_COUNT


def test_validate_stt_keyterms() -> None:
    """Options validation flags inputs over xAI limits."""
    assert validate_stt_keyterms(None) is None
    assert validate_stt_keyterms("Elowen\nGrok") is None
    assert (
        validate_stt_keyterms("a" * (STT_KEYTERM_MAX_LENGTH + 1))
        == "stt_keyterm_too_long"
    )
    assert (
        validate_stt_keyterms(
            "\n".join(f"t{i}" for i in range(STT_KEYTERM_MAX_COUNT + 1))
        )
        == "stt_keyterms_too_many"
    )
    # Duplicates don't count toward the limit
    assert validate_stt_keyterms("\n".join(["Elowen"] * 500)) is None
    assert split_stt_keyterms("Elowen\nelowen") == ["Elowen"]


# --- HTTP request ------------------------------------------------------------


def _mock_session() -> tuple[MagicMock, dict[str, Any]]:
    """Session whose post() captures the multipart form."""
    captured: dict[str, Any] = {}
    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(return_value={"text": "Elowen is hungry"})
    resp.text = AsyncMock(return_value="")
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)

    def _post(url: str, **kwargs: Any) -> MagicMock:
        captured["url"] = url
        captured["form"] = kwargs["data"]
        return ctx

    session = MagicMock()
    session.post = MagicMock(side_effect=_post)
    return session, captured


def _form_fields(form: Any) -> list[tuple[str, Any]]:
    return [(opts["name"], value) for opts, _headers, value in form._fields]


async def test_async_stt_sends_keyterms_before_file() -> None:
    """Each keyterm is sent as a repeated `keyterm` field, ahead of `file`."""
    session, captured = _mock_session()
    text = await async_stt(
        session,
        "test-key",
        audio=b"\x00\x00" * 160,
        language="en",
        is_raw_pcm=True,
        keyterms=["Elowen", "Skynet Prime"],
    )
    assert text == "Elowen is hungry"
    fields = _form_fields(captured["form"])
    names = [n for n, _ in fields]
    assert [v for n, v in fields if n == "keyterm"] == ["Elowen", "Skynet Prime"]
    assert names[-1] == "file"
    assert names.index("keyterm") < names.index("file")


@pytest.mark.parametrize("keyterms", [None, []])
async def test_async_stt_omits_keyterms_when_empty(keyterms: Any) -> None:
    """No keyterm field is sent when none are configured (unchanged behavior)."""
    session, captured = _mock_session()
    await async_stt(
        session,
        "test-key",
        audio=b"\x00\x00" * 160,
        language="en",
        is_raw_pcm=True,
        keyterms=keyterms,
    )
    names = [n for n, _ in _form_fields(captured["form"])]
    assert "keyterm" not in names
    assert names == ["language", "format", "file"]


# --- STT entity --------------------------------------------------------------


def _metadata() -> SpeechMetadata:
    return SpeechMetadata(
        language="en",
        format=AudioFormats.WAV,
        codec=AudioCodecs.PCM,
        bit_rate=AudioBitRates.BITRATE_16,
        sample_rate=AudioSampleRates.SAMPLERATE_16000,
        channel=AudioChannels.CHANNEL_MONO,
    )


async def _stream():
    yield b"\x00\x00" * 160


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        ("Elowen\nGrok, elowen", ["Elowen", "Grok"]),
        ("", []),
        (None, []),
    ],
)
async def test_stt_entity_passes_keyterms_from_options(
    hass: HomeAssistant, option: str | None, expected: list[str]
) -> None:
    """The STT entity reads the option and forwards parsed keyterms."""
    options = dict(RECOMMENDED_OPTIONS)
    if option is None:
        options.pop(CONF_STT_KEYTERMS, None)
    else:
        options[CONF_STT_KEYTERMS] = option
    entry = MockConfigEntry(
        domain="grok_conversation", data={"api_key": "test-key"}, options=options
    )
    entity = XAIGrokSTTEntity(entry)
    entity.hass = hass

    with patch(
        "custom_components.grok_conversation.stt.async_stt",
        AsyncMock(return_value="Elowen"),
    ) as mock_stt:
        result = await entity.async_process_audio_stream(_metadata(), _stream())

    assert result.result == SpeechResultState.SUCCESS
    assert result.text == "Elowen"
    assert mock_stt.await_args.kwargs["keyterms"] == expected


# --- Options flow ------------------------------------------------------------


@pytest.fixture
def _options_flow_patches(mock_openai_client: MagicMock):
    with (
        patch(
            "custom_components.grok_conversation.config_flow.openai.AsyncOpenAI",
            return_value=mock_openai_client,
        ),
        patch(
            "custom_components.grok_conversation.config_flow.get_async_client",
            return_value=None,
        ),
        patch(
            "custom_components.grok_conversation.config_flow.async_list_chat_models",
            AsyncMock(return_value=["grok-4.3-latest", "grok-4.3"]),
        ),
        patch(
            "custom_components.grok_conversation.async_setup_entry",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.grok_conversation.async_unload_entry",
            AsyncMock(return_value=True),
        ),
    ):
        yield


async def test_options_flow_saves_stt_keyterms(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    _options_flow_patches: None,
) -> None:
    """The Configure form shows the field and saves it."""
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert CONF_STT_KEYTERMS in {
        getattr(k, "schema", k) for k in result["data_schema"].schema
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"recommended": True, CONF_STT_KEYTERMS: "Elowen\nSkynet Prime"},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_STT_KEYTERMS] == "Elowen\nSkynet Prime"


async def test_options_flow_default_empty(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    _options_flow_patches: None,
) -> None:
    """Saving without touching the field stores an empty value."""
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"recommended": True}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options.get(CONF_STT_KEYTERMS, "") == ""


async def test_options_flow_rejects_too_long_keyterm(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    _options_flow_patches: None,
) -> None:
    """A term over 50 characters shows a field error instead of saving."""
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"recommended": True, CONF_STT_KEYTERMS: "z" * (STT_KEYTERM_MAX_LENGTH + 1)},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_STT_KEYTERMS: "stt_keyterm_too_long"}
