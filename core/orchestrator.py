from brain.local_llm import LocalLMStudioBrain
from core.router import BrainRouter
from core.state import JoiState
from memory.session_memory import SessionMemory
from voice.voice_router import ElevenLabsVoiceProvider, KokoroVoiceRouter, VoiceRouter


class JoiOrchestrator:
    def __init__(self, settings, system_prompt, logger):
        self.settings = settings
        self.logger = logger
        self.state = JoiState(
            mic_enabled=False,
            voice_enabled=settings.voice_enabled,
            vision_enabled=settings.vision_enabled,
            cloud_enabled=settings.cloud_enabled,
            memory_mode=settings.memory_mode,
        )
        self.configured_capabilities = {
            'mic': False,
            'voice': settings.voice_enabled,
            'vision': settings.vision_enabled,
            'cloud': settings.cloud_enabled,
        }
        self.memory = SessionMemory(system_prompt)
        local_brain = LocalLMStudioBrain(settings.lmstudio_base_url, settings.local_model, settings.request_timeout_seconds)
        self.brain = BrainRouter(local_brain)
        self.voice = None
        if settings.voice_enabled:
            if settings.voice_mode in {'online', 'hybrid'} and not settings.cloud_enabled:
                raise ValueError(f'{settings.voice_mode} voice mode requires cloud opt-in')

            local_provider = None
            if settings.voice_mode in {'local', 'hybrid'}:
                local_provider = KokoroVoiceRouter(
                    python_executable=settings.kokoro_python,
                    model_path=settings.kokoro_model_path,
                    voices_path=settings.kokoro_voices_path,
                    voice=settings.tts_voice,
                    language=settings.tts_language,
                    output_path=settings.tts_output_path,
                    timeout_seconds=settings.tts_timeout_seconds,
                )

            online_provider = None
            if settings.voice_mode in {'online', 'hybrid'}:
                online_provider = ElevenLabsVoiceProvider(
                    api_key=settings.elevenlabs_api_key,
                    voice_id=settings.elevenlabs_voice_id,
                    model_id=settings.elevenlabs_model_id,
                    base_url=settings.elevenlabs_base_url,
                    output_path=settings.tts_output_path,
                    timeout_seconds=settings.elevenlabs_timeout_seconds,
                )

            self.voice = VoiceRouter(
                mode=settings.voice_mode,
                local_provider=local_provider,
                online_provider=online_provider,
                logger=logger,
            )
            self.state.active_voice = self.voice.active_provider

    def status(self):
        voice_mode = self.voice.mode if self.voice is not None else self.settings.voice_mode
        return {
            'app_name': self.settings.app_name,
            'brain': self.brain.health(),
            'mic': 'ON' if self.state.mic_enabled else 'OFF',
            'voice': f'ON ({voice_mode.upper()})' if self.state.voice_enabled else 'DISABLED',
            'vision': 'ON' if self.state.vision_enabled else 'OFF',
            'memory': self.state.memory_mode.upper(),
            'cloud': 'ON' if self.state.cloud_enabled else 'OFF',
        }

    def set_runtime_state(self, control: str, value: str):
        control = control.lower()
        value = value.lower()
        if control == 'memory':
            if value not in {'off', 'session'}:
                raise ValueError('MEMORY must be OFF or SESSION')
            if value == 'off':
                self.memory.reset()
            self.state.memory_mode = value
            self.logger.info('Runtime state changed: MEMORY=%s', value.upper())
            return f'Memory: {value.upper()}'

        attributes = {
            'mic': 'mic_enabled',
            'voice': 'voice_enabled',
            'vision': 'vision_enabled',
            'cloud': 'cloud_enabled',
        }
        if control not in attributes:
            raise ValueError(f'unknown runtime state: {control}')
        if value not in {'on', 'off'}:
            raise ValueError(f'{control.upper()} must be ON or OFF')

        enabled = value == 'on'
        if enabled and not self.configured_capabilities[control]:
            raise ValueError(f'{control.upper()} is not configured')
        if control == 'voice' and enabled and self.settings.voice_mode == 'online':
            if not self.state.cloud_enabled:
                raise ValueError('VOICE requires CLOUD ON in online mode')

        setattr(self.state, attributes[control], enabled)
        if control in {'cloud', 'voice'}:
            self._sync_voice_route()
        self.logger.info('Runtime state changed: %s=%s', control.upper(), value.upper())
        return f'{control.title()}: {value.upper()}'

    def _sync_voice_route(self):
        if self.voice is None:
            return
        configured_mode = self.settings.voice_mode
        if configured_mode == 'hybrid':
            self.voice.mode = 'hybrid' if self.state.cloud_enabled else 'local'
        elif configured_mode == 'online' and not self.state.cloud_enabled:
            self.state.voice_enabled = False

        if not self.state.voice_enabled:
            self.state.active_voice = 'disabled'
        else:
            self.state.active_voice = 'local' if self.voice.mode == 'local' else 'online'

    def reset(self):
        self.memory.reset()
        self.logger.info('Session reset')

    def chat(self, user_text: str):
        if self.state.memory_mode == 'off':
            messages = [
                {'role': 'system', 'content': self.memory.system_prompt},
                {'role': 'user', 'content': user_text},
            ]
            try:
                return self.brain.chat(messages)
            except Exception:
                self.logger.exception('Brain request failed')
                raise

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
        if self.voice is None or not self.state.voice_enabled:
            return None
        try:
            result = self.voice.speak(text)
            self.state.active_voice = self.voice.active_provider
            return result
        except Exception:
            self.logger.exception('Voice synthesis failed')
            raise
