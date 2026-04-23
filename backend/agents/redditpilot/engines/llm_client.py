"""
RedditPilot LLM Client
Multi-provider LLM client with fallback chain.
Supports OpenAI, Anthropic, Groq (free), and Ollama (local).
Adapted from MiloAgent's dual-LLM system.
"""

import os
import json
import time
import logging
from typing import Optional
from ..core.config import LLMConfig

logger = logging.getLogger("redditpilot.llm")


class LLMClient:
    """Multi-provider LLM client with automatic failover."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._primary = None
        self._fallback = None
        self._init_providers()

    def _init_providers(self):
        """Initialize LLM providers lazily."""
        pass  # Providers are initialized on first call

    def generate(self, prompt: str, max_tokens: int = None,
                 temperature: float = None, system_prompt: str = None) -> str:
        """
        Generate text from prompt. Tries primary provider, falls back if needed.
        """
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        # Try primary
        try:
            result = self._call_provider(
                provider=self.config.primary_provider,
                model=self.config.primary_model,
                api_key=self.config.primary_api_key or os.environ.get("OPENAI_API_KEY", ""),
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"Primary LLM ({self.config.primary_provider}) failed: {e}")

        # Try fallback
        try:
            logger.info(f"Falling back to {self.config.fallback_provider}")
            result = self._call_provider(
                provider=self.config.fallback_provider,
                model=self.config.fallback_model,
                api_key=self.config.fallback_api_key or os.environ.get("GROQ_API_KEY", ""),
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
            if result:
                return result
        except Exception as e:
            logger.error(f"Fallback LLM ({self.config.fallback_provider}) also failed: {e}")

        raise RuntimeError("All LLM providers failed")

    def _call_provider(self, provider: str, model: str, api_key: str,
                       prompt: str, max_tokens: int, temperature: float,
                       system_prompt: str = None) -> Optional[str]:
        """Route to the appropriate provider."""
        if provider == "openai":
            return self._call_openai(model, api_key, prompt, max_tokens, temperature, system_prompt)
        elif provider == "anthropic":
            return self._call_anthropic(model, api_key, prompt, max_tokens, temperature, system_prompt)
        elif provider == "groq":
            return self._call_groq(model, api_key, prompt, max_tokens, temperature, system_prompt)
        elif provider == "ollama":
            return self._call_ollama(model, prompt, max_tokens, temperature, system_prompt)
        else:
            # Generic OpenAI-compatible endpoint
            return self._call_openai_compatible(provider, model, api_key, prompt, max_tokens, temperature, system_prompt)

    def _call_openai(self, model: str, api_key: str, prompt: str,
                     max_tokens: int, temperature: float,
                     system_prompt: str = None) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, model: str, api_key: str, prompt: str,
                        max_tokens: int, temperature: float,
                        system_prompt: str = None) -> str:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = client.messages.create(**kwargs)
        return response.content[0].text.strip()

    def _call_groq(self, model: str, api_key: str, prompt: str,
                   max_tokens: int, temperature: float,
                   system_prompt: str = None) -> str:
        from groq import Groq
        client = Groq(api_key=api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

    def _call_ollama(self, model: str, prompt: str,
                     max_tokens: int, temperature: float,
                     system_prompt: str = None) -> str:
        import requests
        url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        response = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["response"].strip()

    def _call_openai_compatible(self, provider: str, model: str, api_key: str,
                                prompt: str, max_tokens: int, temperature: float,
                                system_prompt: str = None) -> str:
        """Call any OpenAI-compatible API (OpenRouter, Together, etc.)."""
        import requests
        base_urls = {
            "openrouter": "https://openrouter.ai/api/v1",
            "together": "https://api.together.xyz/v1",
        }
        base_url = base_urls.get(provider, f"https://api.{provider}.com/v1")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
