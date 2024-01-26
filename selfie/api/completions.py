from fastapi import APIRouter
from litellm import ModelResponse as LitellmCompletionResponse
from llama_cpp import (
    CreateCompletionResponse as LlamaCppCompletionResponse,
    CreateChatCompletionResponse as LlamaCppChatCompletionResponse,
)
from selfie.types import ChatCompletionRequest, CompletionRequest

from selfie.augmentation import completion

router = APIRouter()


@router.post("/v1/chat/completions")
async def create_chat_completion(
        request: ChatCompletionRequest,
) -> LlamaCppChatCompletionResponse | LitellmCompletionResponse:
    return await completion(request)


# TODO can StreamingResponse's schema be defined?
@router.post("/v1/completions")
async def create_completion(
        request: CompletionRequest,
) -> LlamaCppCompletionResponse | LitellmCompletionResponse:
    return await completion(request)


@router.post("/v1/memory/v1/chat/completions")
async def create_memory_chat_completion(
        request: ChatCompletionRequest,
) -> LlamaCppChatCompletionResponse | LitellmCompletionResponse:
    return await completion(request, use_memory=True)


@router.post("/v1/memory/v1/completions")
async def create_memory_completion(
        request: CompletionRequest,
) -> LlamaCppCompletionResponse | LitellmCompletionResponse:
    return await completion(request, use_memory=True)
