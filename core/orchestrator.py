from brain.local_llm import LocalLMStudioBrain
from core.router import BrainRouter
from core.state import JoiState
from memory.session_memory import SessionMemory
from voice.voice_router import KokoroVoiceRouter


class JoiOrchestrator:
    def __init__(self, settings, system_prompt, logger):
        self.settings = settings
        self.logger = logger
        self.state = JoiState(
            voice_enabled=settings.voice_enabled,
            vision_enabled=settings.vision_enabled,
            cloud_enabled=settings.cloud_enabled,
            memory_mode=settings.memory_mode,
        )
        self.memory = SessionMemory(system_prompt)
        local_brain = LocalLMStudioBrain(settings.lmstudio_base_url, settings.local_model, settings.request_timeout_seconds)
        self.brain = BrainRouter(local_brain)
        self.voice = None
        if settings.voice_enabled:
            self.voice = KokoroVoiceRouter(
                python_executable=settings.kokoro_python,
                model_path=settings.kokoro_model_path,
                voices_path=settings.kokoro_voices_path,
                voice=settings.tts_voice,
                language=settings.tts_language,
                output_path=settings.tts_output_path,
                timeout_seconds=settings.tts_timeout_seconds,
            )
            self.state.active_voice = 'kokoro'

    def status(self):
        return {
            'app_name': self.settings.app_name,
            'brain': self.brain.health(),
            'voice': 'ON (KOKORO)' if self.state.voice_enabled else 'DISABLED',
            'vision': 'ON' if self.state.vision_enabled else 'OFF',
            'memory': self.state.memory_mode.upper(),
            'cloud': 'ON' if self.state.cloud_enabled else 'OFF',
        }

    def reset(self):
        self.memory.reset()
        self.logger.info('Session reset')

    def chat(self, user_text: str):
        previous_messages = self.memory.snapshot()
        self.memory.add_user(user_text)
        try:
            reply = self.brain.chat(self.memory.snapshot())
        except Exception:
            self.memory.messages = previous_messages
            self.logger.exception('Brain request failed')
            raise
        self.memory.add_assistant(reply)
        return reply

    def speak(self, text: str):
        if self.voice is None:
            return None
        try:
            return self.voice.speak(text)
        except Exception:
            self.logger.exception('Voice synthesis failed')
            raise
