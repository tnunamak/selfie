from selfie.augmentation.augmentation import augment
from selfie.types import SelfieCompletionResponse, ChatCompletionRequest, CompletionRequest
from selfie.augmentation.completion import completion as _completion


async def completion(
        request: CompletionRequest | ChatCompletionRequest, do_augmentation: bool = False
) -> SelfieCompletionResponse:
    if do_augmentation:
        async def augmentation_completion(prompt):
            simple_result = await completion(ChatCompletionRequest(
                api_base=request.api_base,
                api_key=request.api_key,
                method=request.method,
                model=request.model,
                # TODO: Add a system message?
                messages=[{"content": prompt, "role": "user"}],
                max_tokens=512,
            ))

            # TODO: test whether this is necessary
            if isinstance(simple_result, dict):
                return simple_result["choices"][0]["message"]["content"]
            else:
                return simple_result.choices[0].message.content

        await augment(request, augmentation_completion)

    return await _completion(request)
