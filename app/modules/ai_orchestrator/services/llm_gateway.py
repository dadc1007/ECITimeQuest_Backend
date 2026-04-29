import json
from openai import OpenAI, APIError, RateLimitError
from app.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)


class LLMGatewayException(Exception):
    pass


def generate_structured_json(system_prompt: str, user_prompt: str) -> dict:
    """Wrapper to call OpenAI guaranteeing a validated JSON response."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        content = response.choices[0].message.content

        if not content:
            raise LLMGatewayException("Empty response from LLM")

        return json.loads(content)
    except RateLimitError as e:
        raise e
    except APIError as e:
        raise LLMGatewayException(f"OpenAI API Error: {str(e)}")
    except json.JSONDecodeError:
        raise LLMGatewayException("The LLM did not return a valid JSON")
