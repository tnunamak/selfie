import json
from selfie.memory_index.base_scorer import BaseScorer
from selfie.memory_index.memory_types import Memory


class ImportanceScorer(BaseScorer):
    def __init__(self, score_weight, use_local_llm=True):
        super().__init__(score_weight)
        self.use_local_llm = use_local_llm

    def calculate_raw_score(self, memory: Memory):
        """
        Calculate the raw importance score for a memory using OpenAI's API.
        """
        extract_importance_prompt = """
        On the scale of 1 to 10, where 1 is purely mundane (e.g., brushing teeth, making bed) and 10 is extremely 
        poignant (e.g., a break up, college acceptance), rate the likely poignancy of the following piece of memory.
        Memory: {memory}
        """.format(
            memory=memory.content
        )

        rate_memory = {
            "name": "rate_memory",
            "description": "This function rates memory importance for the given part of the conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "importanceScore": {
                        "type": "number",
                        "description": "Importance score on the scale of 1 to 10, where 1 is purely mundane and 10 is extremely poignant",
                    },
                },
                "required": ["importanceScore"],
            },
        }

        try:
            if self.use_local_llm:
                from txtai.pipeline import LLM

                llm = LLM(
                    "meetkai/functionary-7b-v2-GGUF/functionary-7b-v2.q4_0.gguf",
                    n_gpu_layers=-1,
                    method="llama.cpp",
                    chat_format="functionary",
                    n_ctx=4096,
                ).generator.llm
                chat_completion = llm.create_chat_completion
            else:
                from litellm import completion

                chat_completion = completion

            tool_choice = {"type": "function", "function": {"name": "rate_memory"}}

            rate_memory_tool = {"type": "function", "function": rate_memory}

            response = chat_completion(
                # model='gpt-3.5-turbo',
                messages=[{"role": "user", "content": extract_importance_prompt}],
                # functions=[rate_memory],
                # function_call={
                #     'name': rate_memory['name'],
                # },
                tools=[rate_memory_tool],
                tool_choice=tool_choice,
            )

            json_data = json.loads(
                response["choices"][0]["message"]["function_call"]["arguments"]
            )
            # json_data = json.loads(openai_response.choices[0].message.function_call.arguments)
            return json_data["importanceScore"]
        except Exception as e:
            print("Error calculating importance score:", str(e))
            return 0

    def normalize_score(self, score):
        """
        Normalize the score to a range of [0, 1].
        Assumes the original score is in [1, 10].
        """
        return 0 if score is 0 else (score - 1) / 9
