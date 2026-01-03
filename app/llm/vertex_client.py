"""
Vertex AI Production Client
Enterprise-grade LLM client with retry logic, rate limiting, cost tracking
"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
import threading
import json

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Singleton instance holder
_vertex_client_instance = None
_client_lock = threading.Lock()


@dataclass
class TokenUsage:
    """Track token usage for cost calculation"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    @property
    def estimated_cost_usd(self) -> float:
        """Estimate cost based on Gemini 1.5 Flash pricing"""
        # Pricing as of 2024: Flash = $0.00075/1K input, $0.003/1K output
        input_cost = (self.input_tokens / 1000) * 0.00075
        output_cost = (self.output_tokens / 1000) * 0.003
        return input_cost + output_cost
    
    @property
    def estimated_cost_inr(self) -> float:
        """Convert to INR (approx 83 per USD)"""
        return self.estimated_cost_usd * 83


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting"""
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000
    _request_timestamps: List[float] = field(default_factory=list)
    _token_usage: Dict[str, int] = field(default_factory=lambda: {"minute": 0, "last_reset": time.time()})
    
    def can_proceed(self, estimated_tokens: int = 500) -> bool:
        """Check if we can make a request"""
        now = time.time()
        
        # Clean old timestamps (older than 1 minute)
        self._request_timestamps = [ts for ts in self._request_timestamps if now - ts < 60]
        
        # Reset token counter every minute
        if now - self._token_usage["last_reset"] >= 60:
            self._token_usage["minute"] = 0
            self._token_usage["last_reset"] = now
        
        # Check limits
        if len(self._request_timestamps) >= self.requests_per_minute:
            return False
        if self._token_usage["minute"] + estimated_tokens > self.tokens_per_minute:
            return False
        
        return True
    
    def record_request(self, tokens_used: int):
        """Record a request"""
        self._request_timestamps.append(time.time())
        self._token_usage["minute"] += tokens_used
    
    async def wait_if_needed(self, estimated_tokens: int = 500):
        """Wait if rate limited"""
        while not self.can_proceed(estimated_tokens):
            wait_time = 1.0
            logger.warning(f"Rate limited, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)


class VertexAIClient:
    """
    Production-grade Vertex AI client with:
    - Automatic retry with exponential backoff
    - Rate limiting
    - Token usage tracking
    - Connection pooling (singleton pattern)
    - Cost monitoring
    - Fallback to Gemini API if Vertex unavailable
    """
    
    # Model configurations
    MODELS = {
        "gemini-1.5-flash": {
            "name": "gemini-1.5-flash-002",
            "context_window": 1000000,
            "input_price_per_1k": 0.00075,
            "output_price_per_1k": 0.003,
            "rpm_limit": 360,
            "tpm_limit": 4000000,
        },
        "gemini-1.5-pro": {
            "name": "gemini-1.5-pro-002",
            "context_window": 2000000,
            "input_price_per_1k": 0.00125,
            "output_price_per_1k": 0.005,
            "rpm_limit": 120,
            "tpm_limit": 4000000,
        },
        "gemini-2.0-flash": {
            "name": "gemini-2.0-flash-exp",
            "context_window": 1000000,
            "input_price_per_1k": 0.00075,
            "output_price_per_1k": 0.003,
            "rpm_limit": 360,
            "tpm_limit": 4000000,
        }
    }
    
    def __init__(
        self,
        model_name: str = "gemini-1.5-flash",
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        use_vertex: bool = True,
    ):
        self.model_name = model_name
        self.model_config = self.MODELS.get(model_name, self.MODELS["gemini-1.5-flash"])
        self.project_id = project_id or settings.google_cloud_project_id
        self.location = location or settings.google_cloud_location or "asia-south1"
        self.use_vertex = use_vertex and bool(self.project_id)
        
        # Rate limiting
        self.rate_limiter = RateLimitBucket(
            requests_per_minute=self.model_config["rpm_limit"],
            tokens_per_minute=self.model_config["tpm_limit"]
        )
        
        # Usage tracking
        self.total_usage = TokenUsage()
        self.hourly_usage: Dict[str, TokenUsage] = {}
        self.daily_usage: Dict[str, TokenUsage] = {}
        
        # Initialize client
        self._client = None
        self._init_client()
        
        logger.info(f"🚀 VertexAIClient initialized: model={model_name}, vertex={self.use_vertex}")
    
    def _init_client(self):
        """Initialize the appropriate client"""
        if self.use_vertex:
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel, GenerationConfig, SafetySetting, HarmCategory, HarmBlockThreshold
                
                vertexai.init(
                    project=self.project_id,
                    location=self.location
                )
                
                # Safety settings for voice agent (allow more conversational content)
                safety_settings = [
                    SafetySetting(
                        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                    ),
                    SafetySetting(
                        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                    ),
                    SafetySetting(
                        category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                    ),
                    SafetySetting(
                        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                    ),
                ]
                
                self._client = GenerativeModel(
                    self.model_config["name"],
                    safety_settings=safety_settings,
                    generation_config=GenerationConfig(
                        temperature=0.7,
                        top_p=0.95,
                        top_k=40,
                        max_output_tokens=512,  # Keep responses concise for voice
                    )
                )
                self._client_type = "vertex"
                logger.info(f"✅ Vertex AI client initialized: {self.project_id}/{self.location}")
                
            except ImportError:
                logger.warning("google-cloud-aiplatform not installed, falling back to Gemini API")
                self._init_gemini_api()
            except Exception as e:
                logger.warning(f"Vertex AI init failed: {e}, falling back to Gemini API")
                self._init_gemini_api()
        else:
            self._init_gemini_api()
    
    def _init_gemini_api(self):
        """Fallback to Gemini API with key"""
        try:
            import google.generativeai as genai
            
            if not settings.gemini_api_key:
                raise ValueError("No Gemini API key configured")
            
            genai.configure(api_key=settings.gemini_api_key)
            
            self._client = genai.GenerativeModel(
                model_name=self.model_config["name"],
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 512,
                }
            )
            self._client_type = "gemini_api"
            self.use_vertex = False
            logger.info("✅ Gemini API client initialized (fallback)")
            
        except Exception as e:
            logger.error(f"Failed to initialize any Gemini client: {e}")
            raise
    
    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> tuple[str, TokenUsage]:
        """
        Generate response with retry logic and rate limiting
        
        Returns:
            tuple of (response_text, token_usage)
        """
        # Estimate tokens for rate limiting
        estimated_input_tokens = len(prompt.split()) * 1.3  # rough estimate
        
        # Wait for rate limit
        await self.rate_limiter.wait_if_needed(int(estimated_input_tokens))
        
        last_error = None
        
        for attempt in range(retry_count):
            try:
                start_time = time.time()
                
                if self._client_type == "vertex":
                    response = await self._generate_vertex(prompt, system_instruction, temperature, max_tokens)
                else:
                    response = await self._generate_gemini_api(prompt, system_instruction, temperature, max_tokens)
                
                # Extract usage
                usage = self._extract_usage(response)
                
                # Record for rate limiting
                self.rate_limiter.record_request(usage.total_tokens)
                
                # Track usage
                self._track_usage(usage)
                
                # Log performance
                latency = (time.time() - start_time) * 1000
                logger.debug(f"LLM response in {latency:.0f}ms, tokens: {usage.total_tokens}")
                
                # Extract text
                text = self._extract_text(response)
                
                return text, usage
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # Check for rate limit errors
                if "429" in error_str or "quota" in error_str or "rate" in error_str:
                    wait_time = retry_delay * (2 ** attempt) * 2  # Double wait for rate limits
                    logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{retry_count})")
                    await asyncio.sleep(wait_time)
                    continue
                
                # Check for transient errors
                if "500" in error_str or "503" in error_str or "unavailable" in error_str:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.warning(f"Transient error, retrying in {wait_time}s (attempt {attempt + 1}/{retry_count}): {e}")
                    await asyncio.sleep(wait_time)
                    continue
                
                # Non-retryable error
                logger.error(f"LLM generation failed: {e}")
                raise
        
        # All retries exhausted
        raise Exception(f"LLM generation failed after {retry_count} attempts: {last_error}")
    
    async def _generate_vertex(
        self,
        prompt: str,
        system_instruction: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ):
        """Generate using Vertex AI"""
        from vertexai.generative_models import GenerationConfig
        
        # Build contents
        contents = []
        if system_instruction:
            contents.append({"role": "user", "parts": [{"text": f"[System]: {system_instruction}"}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        
        # Override generation config if needed
        config = None
        if temperature is not None or max_tokens is not None:
            config = GenerationConfig(
                temperature=temperature or 0.7,
                max_output_tokens=max_tokens or 512,
            )
        
        # Generate (async)
        response = await asyncio.to_thread(
            self._client.generate_content,
            contents,
            generation_config=config,
        )
        
        return response
    
    async def _generate_gemini_api(
        self,
        prompt: str,
        system_instruction: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ):
        """Generate using Gemini API"""
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"[System Instruction]: {system_instruction}\n\n[User]: {prompt}"
        
        # Generate (async)
        response = await asyncio.to_thread(
            self._client.generate_content,
            full_prompt,
        )
        
        return response
    
    async def generate_chat(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        retry_count: int = 3,
    ) -> tuple[str, TokenUsage]:
        """Generate response for chat messages"""
        # Convert chat format to single prompt for Gemini
        prompt_parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_instruction = content
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
            else:
                prompt_parts.append(f"User: {content}")
        
        prompt = "\n".join(prompt_parts)
        if prompt_parts:
            prompt += "\nAssistant:"
        
        return await self.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            retry_count=retry_count,
        )
    
    def _extract_text(self, response) -> str:
        """Extract text from response"""
        try:
            if hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content.parts:
                    return candidate.content.parts[0].text
            return str(response)
        except Exception as e:
            logger.warning(f"Failed to extract text: {e}")
            return ""
    
    def _extract_usage(self, response) -> TokenUsage:
        """Extract token usage from response"""
        try:
            if hasattr(response, 'usage_metadata'):
                metadata = response.usage_metadata
                return TokenUsage(
                    input_tokens=getattr(metadata, 'prompt_token_count', 0),
                    output_tokens=getattr(metadata, 'candidates_token_count', 0),
                    total_tokens=getattr(metadata, 'total_token_count', 0),
                )
        except Exception:
            pass
        
        # Estimate if not available
        return TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
    
    def _track_usage(self, usage: TokenUsage):
        """Track usage for cost monitoring"""
        # Total usage
        self.total_usage.input_tokens += usage.input_tokens
        self.total_usage.output_tokens += usage.output_tokens
        self.total_usage.total_tokens += usage.total_tokens
        
        # Hourly tracking
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
        if hour_key not in self.hourly_usage:
            self.hourly_usage[hour_key] = TokenUsage()
        self.hourly_usage[hour_key].input_tokens += usage.input_tokens
        self.hourly_usage[hour_key].output_tokens += usage.output_tokens
        self.hourly_usage[hour_key].total_tokens += usage.total_tokens
        
        # Daily tracking
        day_key = datetime.now().strftime("%Y-%m-%d")
        if day_key not in self.daily_usage:
            self.daily_usage[day_key] = TokenUsage()
        self.daily_usage[day_key].input_tokens += usage.input_tokens
        self.daily_usage[day_key].output_tokens += usage.output_tokens
        self.daily_usage[day_key].total_tokens += usage.total_tokens
        
        # Clean old entries (keep last 24 hours and 7 days)
        self._cleanup_old_usage()
    
    def _cleanup_old_usage(self):
        """Remove old usage data"""
        now = datetime.now()
        
        # Keep last 24 hours
        cutoff_hour = (now - timedelta(hours=24)).strftime("%Y-%m-%d-%H")
        self.hourly_usage = {
            k: v for k, v in self.hourly_usage.items()
            if k >= cutoff_hour
        }
        
        # Keep last 7 days
        cutoff_day = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        self.daily_usage = {
            k: v for k, v in self.daily_usage.items()
            if k >= cutoff_day
        }
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_usage = self.daily_usage.get(today, TokenUsage())
        
        return {
            "total": {
                "tokens": self.total_usage.total_tokens,
                "cost_usd": self.total_usage.estimated_cost_usd,
                "cost_inr": self.total_usage.estimated_cost_inr,
            },
            "today": {
                "tokens": today_usage.total_tokens,
                "cost_usd": today_usage.estimated_cost_usd,
                "cost_inr": today_usage.estimated_cost_inr,
            },
            "model": self.model_name,
            "using_vertex": self.use_vertex,
            "project": self.project_id if self.use_vertex else "api_key",
        }


def get_vertex_client(
    model_name: str = "gemini-1.5-flash",
    force_new: bool = False
) -> VertexAIClient:
    """
    Get singleton Vertex AI client instance
    Uses connection pooling for efficiency
    """
    global _vertex_client_instance
    
    if force_new or _vertex_client_instance is None:
        with _client_lock:
            if force_new or _vertex_client_instance is None:
                _vertex_client_instance = VertexAIClient(model_name=model_name)
    
    return _vertex_client_instance


# Convenience function for quick generation
async def generate_quick(
    prompt: str,
    system_instruction: Optional[str] = None,
    model: str = "gemini-1.5-flash"
) -> str:
    """Quick generation helper"""
    client = get_vertex_client(model)
    text, _ = await client.generate(prompt, system_instruction)
    return text
