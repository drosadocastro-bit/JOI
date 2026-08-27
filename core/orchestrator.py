from brain.local_llm import LocalLMStudioBrain
from core.router import BrainRouter
from core.state import JoiState
from memory.session_memory import SessionMemory


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

    def status(self):
        return {
            'app_name': self.settings.app_name,
            'brain': self.brain.health(),
            'voice': 'ON' if self.state.voice_enabled else 'DISABLED',
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
