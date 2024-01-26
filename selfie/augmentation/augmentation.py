import logging

from selfie.memory_index import MemoryIndex
from selfie.types import CompletionRequest, ChatCompletionRequest, Message

logger = logging.getLogger(__name__)


async def augment(request: CompletionRequest | ChatCompletionRequest, completion):
    chat_mode = isinstance(request, ChatCompletionRequest)
    memory_stream = MemoryIndex("n/a", completion=completion)
    if chat_mode:
        # Provide the last 15 user messages as context
        context = ""
        i = len(request.messages) - 1
        while i >= 0 and len(context) < 512 and len(context.split("\n")) < 15:
            message = request.messages[i]
            if message.role != "system":
                context = f"{message.content}\n{context}"
            i -= 1

        # Strategy A: use the last user message as the query
        # logger.debug("Using strategy: use the last user message as the query")
        # last_user_message = next(
        #     (
        #         message
        #         for message in reversed(request.messages)
        #         if message.role == "user"
        #     ),
        #     None,
        # )
        #
        # recall_query = last_user_message.content if last_user_message else ""
        # End strategy

        # Strategy B: generate a query for relevant context based on the conversation history
        logger.debug("Using strategy: generate a query for relevant context based on the conversation history")
        prompt_prefix = f"Given only the conversation snippet below, what is the most salient topic whose answer would be relevant in continuing the conversation? For example, if the conversation was about fire and moved on to scuba diving, you should answer 'scuba diving, ocean, favorite hobbies' (only an example!). State your answer without explanation, your entire response will be fed directly into a query engine:"
        prompt = f"{prompt_prefix}:\n\n{context}\nSalient query: "
        logger.debug(f"Prompt: {prompt}")
        topic = (await completion(prompt)).strip()
        # End strategy

        logger.debug(f"Recall query: {topic}")
        memories = await memory_stream.recall(topic, context)

        # Augment the request by prepending the memory summary to the system message.
        # Find the first system message and insert the memory summary at the end. If there isn't one,
        # insert a new system message at the beginning.
        # TODO: fetch these via DataManager.
        name = "Tim"
        personality = "Tim's personality is The Visionary: Deeply motivated, independent thinker, creative problem solver, open to criticism, and team-oriented with a penchant for risk-taking."
        description = "Tim is from Austin, TX and works at the startup Vana."

        system_message = f"[About {name}: {description} {personality}]']\n[{name} recalls that: {memories['summary']}]"

        system_msgs = [m for m in request.messages if m.role == "system"]
        if system_msgs:
            system_msgs[0].content += f"\n\n{system_message}"
        else:
            request.messages.insert(0, Message(role="system", content=system_message))
    else:
        memories = await memory_stream.recall(request.prompt)
        request.prompt = f"[Recalled from memory: {memories['summary']}]\n\n{request.prompt}"
