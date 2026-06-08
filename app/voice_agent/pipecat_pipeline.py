"""
Pipecat voice pipeline (P3) — graceful-import skeleton.

Architecture (full wiring NEXT phase):
    FreeSWITCH (Docker, Vobiz SIP trunk) --ESL socket / audio-fork-->
        LeadgenVoicePipeline (yeh module)
            --> STT (Vosk / Whisper, free)
            --> LLM (LLMBrain → Gemini)
            --> TTS (EdgeTTS, free)
        --audio wapas--> FreeSWITCH --> caller

pipecat-ai OPTIONAL dependency hai (heavy — requirements.txt me commented).
Bina pipecat ke bhi module import-safe rehta hai: PIPECAT_AVAILABLE=False,
aur respond_text() existing LLMBrain se text-level kaam karta rehta hai
(web-call / smoke tests ke liye kaafi).

Install (jab audio wiring karni ho):  pip install pipecat-ai
"""

from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Graceful pipecat import — module hamesha import hona chahiye, pipecat na ho
# tab bhi (Windows dev venv / VPS jab tak heavy install nahi hui).
# ---------------------------------------------------------------------------
PIPECAT_AVAILABLE = False
_PIPECAT_IMPORT_ERROR: str | None = None

try:  # pragma: no cover - environment dependent
    import pipecat  # noqa: F401
    from pipecat.frames import frames as _pc_frames  # noqa: F401
    from pipecat.pipeline.pipeline import Pipeline as _PCPipeline  # noqa: F401
    from pipecat.pipeline.runner import PipelineRunner as _PCRunner  # noqa: F401
    from pipecat.pipeline.task import PipelineTask as _PCTask  # noqa: F401

    PIPECAT_AVAILABLE = True
except Exception as e:  # ImportError ya transitive dep failures dono
    _PIPECAT_IMPORT_ERROR = str(e)
    logger.debug(f"pipecat unavailable ({e}) — voice pipeline in text-only mode")

_INSTALL_HINT = (
    "pipecat-ai installed nahi hai — audio pipeline ke liye chahiye. "
    "Install: pip install pipecat-ai  (heavy; requirements.txt me commented line dekho)"
)


class LeadgenVoicePipeline:
    """FreeSWITCH <-> STT/LLM/TTS bridge.

    Abhi skeleton: websocket/ESL audio transport NEXT phase me wire hoga.
    Text-path (respond_text) aaj hi kaam karta hai via LLMBrain.
    """

    def __init__(
        self,
        niche: str = "general",
        client_name: str = "LeadGen AI",
        client_service: str = "AI voice agent for lead generation",
    ):
        self.niche = niche
        self.client_name = client_name
        self.client_service = client_service
        self._brain = None  # lazy — import cost / creds tabhi jab zaroorat ho

    # ------------------------------------------------------------------
    # Audio path (placeholder — pipecat Pipeline yahan banegi)
    # ------------------------------------------------------------------
    async def run_websocket_transport(self, websocket: Any) -> None:
        """FreeSWITCH audio-fork / mod_audio_stream websocket ko pipecat
        Pipeline me feed karega: transport -> STT -> LLMBrain -> TTS -> transport.

        Abhi placeholder: pipecat na ho to clear RuntimeError with install hint;
        ho to bhi full wiring next phase me aayegi (transport adapters pending).
        """
        if not PIPECAT_AVAILABLE:
            raise RuntimeError(f"{_INSTALL_HINT} (import error: {_PIPECAT_IMPORT_ERROR})")

        # --- NEXT PHASE: yahan actual pipecat graph banega, roughly: ---
        # transport = <FreeSWITCH websocket serializer/transport>
        # pipeline = _PCPipeline([
        #     transport.input(),
        #     <STT service: Vosk/Whisper local>,
        #     <LLM adapter: LLMBrain.generate_response>,
        #     <TTS service: EdgeTTS>,
        #     transport.output(),
        # ])
        # await _PCRunner().run(_PCTask(pipeline))
        raise RuntimeError(
            "LeadgenVoicePipeline.run_websocket_transport: audio wiring next phase me "
            "hai (FreeSWITCH transport adapter pending). Text path ke liye respond_text() use karo."
        )

    # ------------------------------------------------------------------
    # Text path (kaam karta hai aaj) — existing LLMBrain bridge
    # ------------------------------------------------------------------
    async def respond_text(
        self,
        text: str,
        niche: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """User ke text utterance ka agent reply — LLMBrain.generate_response se.

        FreeSWITCH/pipecat ke bina bhi (web-call, tests) yeh path live hai.
        """
        if self._brain is None:
            from app.voice_agent.llm_brain import LLMBrain  # import inside — optional deps safe

            self._brain = LLMBrain()

        history: list[dict[str, str]] = list(conversation_history or [])
        history.append({"role": "user", "content": text})

        return await self._brain.generate_response(
            conversation_history=history,
            niche=niche or self.niche,
            client_name=self.client_name,
            client_service=self.client_service,
        )


def pipecat_status() -> dict[str, Any]:
    """Quick diagnostic — health/debug endpoints ke liye."""
    return {
        "pipecat_available": PIPECAT_AVAILABLE,
        "import_error": _PIPECAT_IMPORT_ERROR,
        "install_hint": None if PIPECAT_AVAILABLE else _INSTALL_HINT,
    }
