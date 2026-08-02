import json
import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser
from app.models import (
    ChatAudioTranscriptionPublic,
    ChatCompletionCreate,
    ChatCompletionPublic,
    ChatConversation,
    ChatConversationCreate,
    ChatConversationPublic,
    ChatConversationsPublic,
    ChatConversationUpdate,
    ChatMessageDB,
    ChatMessagePublic,
    ChatMessagesPublic,
    get_datetime_utc,
)
from app.models import Message as ApiMessage
from app.services.audio_transcription import transcribe_audio
from app.services.chat_completion import (
    generate_chat_response,
    generate_chat_response_stream,
)

router = APIRouter(prefix="/chats", tags=["chats"])

MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024
SUPPORTED_AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
    "audio/x-wav",
    "video/mp4",
    "video/webm",
}


def _normalize_audio_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


async def _get_owned_conversation(
    *, current_user: CurrentUser, conversation_id: uuid.UUID
) -> ChatConversation:
    conversation = await ChatConversation.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not current_user.is_superuser and conversation.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return conversation


@router.get("/", response_model=ChatConversationsPublic)
async def read_conversations(
    current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    if current_user.is_superuser:
        count = await ChatConversation.find().count()
        conversations = (
            await ChatConversation.find()
            .sort("-updated_at")
            .skip(skip)
            .limit(limit)
            .to_list()
        )
    else:
        count = await ChatConversation.find(
            ChatConversation.owner_id == current_user.id
        ).count()
        conversations = (
            await ChatConversation.find(ChatConversation.owner_id == current_user.id)
            .sort("-updated_at")
            .skip(skip)
            .limit(limit)
            .to_list()
        )
    return ChatConversationsPublic(
        data=[
            ChatConversationPublic.model_validate(conversation, from_attributes=True)
            for conversation in conversations
        ],
        count=count,
    )


@router.post("/", response_model=ChatConversationPublic)
async def create_conversation(
    *, current_user: CurrentUser, conversation_in: ChatConversationCreate
) -> Any:
    now = get_datetime_utc()
    conversation = ChatConversation(
        **conversation_in.model_dump(),
        owner_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    await conversation.insert()
    return conversation


@router.post("/audio/transcriptions", response_model=ChatAudioTranscriptionPublic)
async def create_audio_transcription(
    *,
    _current_user: CurrentUser,
    audio: UploadFile = File(...),
) -> Any:
    content_type = _normalize_audio_content_type(audio.content_type)
    if content_type not in SUPPORTED_AUDIO_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Formato de audio no soportado. Usa webm, wav, mp3, mp4, m4a u ogg.",
        )

    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="El audio está vacío.")
    if len(content) > MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="El audio supera el tamaño máximo permitido de 25 MB.",
        )

    try:
        text = await transcribe_audio(
            content=content,
            filename=audio.filename or "recording.webm",
            content_type=content_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error al transcribir audio con OpenAI: {exc}",
        ) from exc

    return ChatAudioTranscriptionPublic(text=text)


@router.patch("/{conversation_id}", response_model=ChatConversationPublic)
async def update_conversation(
    *,
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    conversation_in: ChatConversationUpdate,
) -> Any:
    conversation = await _get_owned_conversation(
        current_user=current_user, conversation_id=conversation_id
    )
    update_data = conversation_in.model_dump(exclude_unset=True)
    if update_data:
        update_data["updated_at"] = get_datetime_utc()
        await conversation.set(update_data)
    return conversation


@router.delete("/{conversation_id}", response_model=ApiMessage)
async def delete_conversation(
    current_user: CurrentUser, conversation_id: uuid.UUID
) -> ApiMessage:
    conversation = await _get_owned_conversation(
        current_user=current_user, conversation_id=conversation_id
    )
    await ChatMessageDB.find(ChatMessageDB.conversation_id == conversation.id).delete()
    await conversation.delete()
    return ApiMessage(message="Conversation deleted successfully")


@router.get("/{conversation_id}/messages", response_model=ChatMessagesPublic)
async def read_conversation_messages(
    current_user: CurrentUser, conversation_id: uuid.UUID
) -> Any:
    conversation = await _get_owned_conversation(
        current_user=current_user, conversation_id=conversation_id
    )
    count = await ChatMessageDB.find(
        ChatMessageDB.conversation_id == conversation.id
    ).count()
    messages = (
        await ChatMessageDB.find(ChatMessageDB.conversation_id == conversation.id)
        .sort("created_at")
        .to_list()
    )
    return ChatMessagesPublic(
        data=[
            ChatMessagePublic.model_validate(message, from_attributes=True)
            for message in messages
        ],
        count=count,
    )


@router.post("/{conversation_id}/messages", response_model=ChatCompletionPublic)
async def create_conversation_message(
    *,
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    body: ChatCompletionCreate,
) -> Any:
    conversation = await _get_owned_conversation(
        current_user=current_user, conversation_id=conversation_id
    )
    history = (
        await ChatMessageDB.find(ChatMessageDB.conversation_id == conversation.id)
        .sort("created_at")
        .to_list()
    )

    try:
        assistant_response = await generate_chat_response(
            history=history,
            user_prompt=body.message,
            provider=body.provider,
            model=body.model,
            temperature=body.temperature,
            system_prompt=body.system_prompt,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error while generating model response: {exc}",
        ) from exc

    now = get_datetime_utc()
    user_message = ChatMessageDB(
        conversation_id=conversation.id,
        role="user",
        content=body.message,
        provider=body.provider,
        model=body.model,
        created_at=now,
    )
    assistant_message = ChatMessageDB(
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_response,
        provider=body.provider,
        model=body.model,
        created_at=now,
    )

    await user_message.insert()
    await assistant_message.insert()
    await conversation.set({"updated_at": now})

    return ChatCompletionPublic(
        conversation=ChatConversationPublic.model_validate(
            conversation, from_attributes=True
        ),
        user_message=ChatMessagePublic.model_validate(
            user_message, from_attributes=True
        ),
        assistant_message=ChatMessagePublic.model_validate(
            assistant_message, from_attributes=True
        ),
    )


@router.post("/{conversation_id}/messages/stream")
async def stream_conversation_message(
    *,
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    body: ChatCompletionCreate,
) -> StreamingResponse:
    conversation = await _get_owned_conversation(
        current_user=current_user, conversation_id=conversation_id
    )
    history = (
        await ChatMessageDB.find(ChatMessageDB.conversation_id == conversation.id)
        .sort("created_at")
        .to_list()
    )

    now = get_datetime_utc()
    user_message = ChatMessageDB(
        conversation_id=conversation.id,
        role="user",
        content=body.message,
        provider=body.provider,
        model=body.model,
        created_at=now,
    )
    await user_message.insert()

    async def _event_generator():
        # Emit user message confirmation
        yield (
            f"event: user_message\n"
            f"data: {json.dumps({'id': str(user_message.id)}, ensure_ascii=False)}\n\n"
        )

        content_text = ""
        thinking_text = ""
        tool_calls: list[dict] = []

        async for event in generate_chat_response_stream(
            history=history,
            user_prompt=body.message,
            provider=body.provider,
            model=body.model,
            temperature=body.temperature,
            system_prompt=body.system_prompt,
        ):
            # Parse event to capture accumulated data from the done event
            if event.startswith("event: done\n"):
                data_line = event.split("data: ", 1)[1].split("\n")[0]
                done_data = json.loads(data_line)
                content_text = done_data.get("content", "")
                thinking_text = done_data.get("thinking", "")
                tool_calls = done_data.get("tool_calls", [])

                # Save assistant message to DB
                save_now = get_datetime_utc()
                metadata = {}
                if thinking_text:
                    metadata["thinking"] = thinking_text
                if tool_calls:
                    metadata["tool_calls"] = tool_calls

                assistant_message = ChatMessageDB(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=content_text,
                    provider=body.provider,
                    model=body.model,
                    metadata=metadata or None,
                    created_at=save_now,
                )
                await assistant_message.insert()
                await conversation.set({"updated_at": save_now})

                # Replace done event with one containing message IDs
                yield (
                    f"event: done\n"
                    f"data: {json.dumps({'user_message_id': str(user_message.id), 'assistant_message_id': str(assistant_message.id)}, ensure_ascii=False)}\n\n"
                )
            else:
                yield event

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
