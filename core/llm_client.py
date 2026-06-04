import json
import re
import requests
import google.generativeai as genai
import config

class LLMClient:
    @staticmethod
    def sanitize_text(value: str) -> str:
        """Remove invalid control characters and malformed Unicode that break JSON parsing."""
        if not isinstance(value, str):
            return ""
        cleaned = ''.join(ch for ch in value if ch in '\n\r\t' or ord(ch) >= 32)
        cleaned = cleaned.encode('utf-8', 'ignore').decode('utf-8', 'ignore')
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)

    @staticmethod
    def call_llm(system_prompt: str, user_prompt: str, provider: str = None) -> str:
        """
        Routes the LLM request to the selected provider (gemini, groq, openrouter).
        Returns the raw string output.
        """
        if not provider:
            provider = config.DEFAULT_LLM_PROVIDER

        provider = provider.lower().strip()
        system_prompt = LLMClient.sanitize_text(system_prompt)
        user_prompt = LLMClient.sanitize_text(user_prompt)
        
        if provider == "gemini":
            return LLMClient._call_gemini(system_prompt, user_prompt)
        elif provider == "groq":
            return LLMClient._call_groq(system_prompt, user_prompt)
        elif provider == "openrouter":
            return LLMClient._call_openrouter(system_prompt, user_prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    @staticmethod
    def _call_gemini(system_prompt: str, user_prompt: str) -> str:
        if not config.GEMINI_API_KEY:
            raise ValueError("Gemini API key is not configured.")
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=system_prompt,
        )
        
        import time
        max_retries = 4
        for attempt in range(max_retries):
            try:
                response = model.generate_content(user_prompt)
                return response.text.strip()
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    time.sleep(15)  # Wait 15 seconds to clear the rate limit
                    continue
                raise e

    @staticmethod
    def _call_groq(system_prompt: str, user_prompt: str) -> str:
        if not config.GROQ_API_KEY:
            raise ValueError("Groq API key is not configured (set GROQ_API_KEY).")
        
        import time
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": config.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }

        max_retries = 5
        for attempt in range(max_retries):
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 429 and attempt < max_retries - 1:
                # Parse retry-after hint from error, default to exponential backoff
                wait = 20 * (attempt + 1)  # 20s, 40s, 60s, 80s
                try:
                    err = response.json()
                    msg = err.get("error", {}).get("message", "")
                    import re as _re
                    m = _re.search(r"try again in ([\d.]+)s", msg)
                    if m:
                        wait = float(m.group(1)) + 2  # add 2s buffer
                except Exception:
                    pass
                print(f"Groq rate limited (attempt {attempt+1}/{max_retries}), waiting {wait:.0f}s...")
                time.sleep(wait)
                continue
            if response.status_code != 200:
                raise Exception(f"Groq API Error: {response.text}")
            break
        
        res_json = response.json()
        return res_json["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _call_openrouter(system_prompt: str, user_prompt: str) -> str:
        if not config.OPENROUTER_API_KEY:
            raise ValueError("OpenRouter API key is not configured (set OPENROUTER_API_KEY).")
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": config.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            raise Exception(f"OpenRouter API Error: {response.text}")
        
        res_json = response.json()
        return res_json["choices"][0]["message"]["content"].strip()

    @staticmethod
    def clean_json_response(raw_text: str) -> dict:
        """
        Helper to strip markdown fences and parse the JSON.
        """
        if not isinstance(raw_text, str):
            raise ValueError("LLM response must be a string.")

        clean_text = LLMClient.sanitize_text(raw_text)
        clean_text = re.sub(r"^```(?:json)?", "", clean_text, flags=re.MULTILINE).strip()
        clean_text = re.sub(r"```$", "", clean_text, flags=re.MULTILINE).strip()

        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            # Try to remove any remaining invalid control characters and extract the object.
            fallback = re.sub(r'[\x00-\x1f\x7f]', '', clean_text)
            try:
                return json.loads(fallback)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', fallback, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(0))
                    except json.JSONDecodeError:
                        pass
                raise ValueError("LLM returned malformed JSON after sanitization. Please try again.")
