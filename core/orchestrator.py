import hashlib

from brain.local_llm import LocalLMStudioBrain
from brain.openai_compact_provider import OpenAICompactSummarizerProvider
from core.router import BrainRouter
from core.state import JoiState
from memory.compact_memory import (
    CompactEvaluationStore,
    CompactMemoryEvaluator,
    CompactMemoryManager,
    CompactMemoryStore,
    CompactMemoryWorker,
    ExtractiveCompactSummarizer,
    ModelCompactMemoryManager,
    ModelCompactMemoryStore,
    ModelCompactMemoryWorker,
    ModelCompactSummarizer,
    ProviderBackedCompactSummarizer,
)
from memory.contextual_retrieval import (
    ContextualRetrievalApproval,
    render_approved_context,
)
from memory.graph_memory import (
    ExplicitEntityExtractor,
    GraphMemoryManager,
    GraphMemoryStore,
    GraphMemoryWorker,
)
from memory.graph_retrieval import GraphShadowRetriever, ShadowReceiptStore
from memory.memory_store import EpisodicMemoryStore
from memory.session_memory import SessionMemory
from security.credential_provider import CredentialProvider, write_audit_event
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
        self.credential_provider = CredentialProvider(
            audit_sink=lambda event: write_audit_event(
                settings.credential_audit_path,
                event,
            ),
        )
        self.memory_store = None
        self.memory_store_error = None
        self.compact_memory_worker = None
        self.compact_memory_error = None
        self.model_compact_memory_worker = None
        self.model_compact_memory_error = None
        self.graph_memory_manager = None
        self.graph_memory_worker = None
        self.graph_memory_error = None
        self.graph_retriever = None
        self.last_graph_retrieval_receipt = None
        self.graph_retrieval_error = None
        self.contextual_retrieval_approval = ContextualRetrievalApproval()
        if settings.persistent_memory_enabled:
            try:
                self.memory_store = EpisodicMemoryStore(settings.memory_store_path)
            except Exception as exc:
                self.memory_store_error = str(exc)
                self.logger.exception('Persistent memory initialization failed')
        if settings.compact_memory_enabled and self.memory_store is not None:
            try:
                compact_manager = CompactMemoryManager(
                    store=CompactMemoryStore(settings.compact_memory_path),
                    summarizer=ExtractiveCompactSummarizer(
                        max_characters=settings.compact_memory_max_characters,
                    ),
                )
                self.compact_memory_worker = CompactMemoryWorker(compact_manager, logger)
            except Exception as exc:
                self.compact_memory_error = str(exc)
                self.logger.exception('Compact memory initialization failed')
        if (
            getattr(settings, 'graph_memory_enabled', False)
            and self.memory_store is not None
        ):
            try:
                self.graph_memory_manager = GraphMemoryManager(
                    store=GraphMemoryStore(settings.graph_memory_path),
                    extractor=ExplicitEntityExtractor(),
                )
                self.graph_memory_worker = GraphMemoryWorker(
                    self.graph_memory_manager,
                    logger,
                )
            except Exception as exc:
                self.graph_memory_manager = None
                self.graph_memory_error = str(exc)
                self.logger.exception('Graph memory initialization failed')
        if (
            getattr(settings, 'graph_retrieval_enabled', False)
            and self.graph_memory_manager is not None
            and self.memory_store is not None
        ):
            try:
                self.graph_retriever = GraphShadowRetriever(
                    ShadowReceiptStore(settings.graph_retrieval_receipt_path)
                )
            except Exception as exc:
                self.graph_retrieval_error = str(exc)
                self.logger.exception('Graph retrieval initialization failed')
        local_brain = LocalLMStudioBrain(settings.lmstudio_base_url, settings.local_model, settings.request_timeout_seconds)
        self.brain = BrainRouter(local_brain)
        if (
            getattr(settings, 'model_compact_memory_enabled', False)
            and self.compact_memory_worker is not None
            and self.memory_store is not None
        ):
            try:
                if getattr(settings, 'compact_memory_provider', 'local') == 'openai':
                    provider = OpenAICompactSummarizerProvider(
                        credential_provider=self.credential_provider,
                        model=settings.openai_model,
                        cloud_authorized=lambda: self.state.cloud_enabled,
                        base_url=settings.openai_base_url,
                        timeout_seconds=settings.openai_timeout_seconds,
                    )
                    summarizer = ProviderBackedCompactSummarizer(provider)
                else:
                    model_brain = LocalLMStudioBrain(
                        settings.lmstudio_base_url,
                        settings.local_model,
                        settings.request_timeout_seconds,
                    )
                    summarizer = ModelCompactSummarizer(
                        model_brain,
                        settings.local_model,
                    )
                model_manager = ModelCompactMemoryManager(
                    store=ModelCompactMemoryStore(settings.model_compact_memory_path),
                    summarizer=summarizer,
                    policy_revision_reader=lambda: (
                        self.memory_store.effective_snapshot().policy_revision
                    ),
                )
                evaluator = CompactMemoryEvaluator(
                    manager=model_manager,
                    report_store=CompactEvaluationStore(
                        settings.compact_memory_evaluation_path
                    ),
                    max_source_characters=settings.compact_memory_max_characters,
                )
                self.model_compact_memory_worker = ModelCompactMemoryWorker(
                    evaluator,
                    logger,
                )
            except Exception as exc:
                self.model_compact_memory_error = str(exc)
                self.logger.exception('Model compact memory initialization failed')
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
                    credential_provider=self.credential_provider,
                    voice_id=settings.elevenlabs_voice_id,
                    model_id=settings.elevenlabs_model_id,
                    base_url=settings.elevenlabs_base_url,
                    output_path=settings.tts_output_path,
                    timeout_seconds=settings.elevenlabs_timeout_seconds,
                    cloud_authorized=lambda: self.state.cloud_enabled,
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
        memory_status = self.state.memory_mode.upper()
        if self.state.memory_mode == 'persistent' and self.memory_store is None:
            memory_status = 'PERSISTENT (UNAVAILABLE)'
        return {
            'app_name': self.settings.app_name,
            'brain': self.brain.health(),
            'mic': 'ON' if self.state.mic_enabled else 'OFF',
            'voice': f'ON ({voice_mode.upper()})' if self.state.voice_enabled else 'DISABLED',
            'vision': 'ON' if self.state.vision_enabled else 'OFF',
            'memory': memory_status,
            'cloud': 'ON' if self.state.cloud_enabled else 'OFF',
        }

    def set_runtime_state(self, control: str, value: str):
        control = control.lower()
        value = value.lower()
        if control == 'memory':
            if value not in {'off', 'persistent', 'session'}:
                raise ValueError('MEMORY must be OFF, PERSISTENT, or SESSION')
            if value == 'persistent':
                if not self.settings.persistent_memory_enabled:
                    raise ValueError('PERSISTENT memory is not configured')
                if self.memory_store is None:
                    raise ValueError('PERSISTENT memory is unavailable')
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

    def chat(self, user_text: str, context_approval_id: str | None = None):
        context = self._consume_context_approval(user_text, context_approval_id)
        if self.state.memory_mode == 'off':
            messages = [
                {'role': 'system', 'content': self.memory.system_prompt},
                {'role': 'user', 'content': user_text},
            ]
            if context is not None:
                messages.insert(1, {'role': 'system', 'content': context})
            try:
                return self.brain.chat(messages)
            except Exception:
                self.logger.exception('Brain request failed')
                raise

        previous_messages = self.memory.snapshot()
        self.memory.add_user(user_text)
        messages = self.memory.snapshot()
        if context is not None:
            messages.insert(1, {'role': 'system', 'content': context})
        try:
            reply = self.brain.chat(messages)
        except Exception:
            self.memory.messages = previous_messages
            self.logger.exception('Brain request failed')
            raise
        self.memory.add_assistant(reply)
        if self.state.memory_mode == 'persistent':
            self._persist_exchange(user_text, reply)
        return reply

    def contextual_retrieval_propose(self, user_text: str) -> dict:
        if not getattr(self.settings, 'contextual_retrieval_enabled', False):
            raise ValueError('Contextual retrieval is not enabled')
        if self.state.memory_mode != 'persistent':
            raise ValueError('Contextual retrieval requires persistent memory')
        if self.graph_retriever is None or self.graph_memory_manager is None:
            raise ValueError('Contextual retrieval is unavailable')
        snapshot = self._require_memory_store().effective_snapshot()
        query_turn_id = 'context-query-' + hashlib.sha256(
            user_text.encode('utf-8')
        ).hexdigest()[:24]
        receipt = self.graph_retriever.retrieve(
            query_turn_id=query_turn_id,
            content=user_text,
            historical_state=self.graph_memory_manager.state,
            effective_snapshot=snapshot,
        )
        return self.contextual_retrieval_approval.create(receipt, snapshot)

    def contextual_retrieval_inspect(self, approval_id: str) -> dict:
        if not getattr(self.settings, 'contextual_retrieval_enabled', False):
            raise ValueError('Contextual retrieval is not enabled')
        return self.contextual_retrieval_approval.inspect(approval_id)

    def contextual_retrieval_approve(self, approval_id: str) -> dict:
        if not getattr(self.settings, 'contextual_retrieval_enabled', False):
            raise ValueError('Contextual retrieval is not enabled')
        return self.contextual_retrieval_approval.approve(approval_id)

    def _consume_context_approval(
        self,
        user_text: str,
        approval_id: str | None,
    ) -> str | None:
        if approval_id is None:
            return None
        if not getattr(self.settings, 'contextual_retrieval_enabled', False):
            raise ValueError('Contextual retrieval is not enabled')
        proposal = self.contextual_retrieval_approval.inspect(approval_id)
        query_sha256 = hashlib.sha256(user_text.encode('utf-8')).hexdigest()
        if proposal['query_sha256'] != query_sha256:
            raise ValueError('context approval does not match the current query')
        consumed = self.contextual_retrieval_approval.consume(approval_id)
        return render_approved_context(consumed)

    def _persist_exchange(self, user_text: str, assistant_text: str):
        if self.memory_store is None:
            return
        effective_snapshot = None
        if self.graph_retriever is not None:
            try:
                effective_snapshot = self.memory_store.effective_snapshot()
            except Exception as exc:
                self.graph_retrieval_error = str(exc)
                self.logger.exception('Graph retrieval snapshot failed')
        try:
            turns = self.memory_store.append_exchange(user_text, assistant_text)
        except Exception as exc:
            self.memory_store = None
            self.memory_store_error = str(exc)
            self.logger.exception('Persistent memory write failed')
            return
        if (
            self.graph_retriever is not None
            and effective_snapshot is not None
            and self.graph_memory_manager is not None
            and self.graph_memory_manager.state is not None
        ):
            try:
                self.last_graph_retrieval_receipt = self.graph_retriever.retrieve(
                    query_turn_id=turns[0].turn_id,
                    content=user_text,
                    historical_state=self.graph_memory_manager.state,
                    effective_snapshot=effective_snapshot,
                )
            except Exception as exc:
                self.graph_retrieval_error = str(exc)
                self.logger.exception('Graph shadow retrieval failed')
        if self.compact_memory_worker is not None:
            self.compact_memory_worker.submit(turns)
        if self.graph_memory_worker is not None:
            try:
                self.graph_memory_worker.submit(turns)
            except Exception as exc:
                self.graph_memory_error = str(exc)
                self.logger.exception('Graph memory submission failed')
        self._submit_model_compact_snapshot()

    def _submit_model_compact_snapshot(self):
        if self.model_compact_memory_worker is None or self.memory_store is None:
            return
        try:
            snapshot = self.memory_store.effective_snapshot()
            self.model_compact_memory_worker.submit(snapshot)
        except Exception:
            self.logger.exception('Model compact memory snapshot failed')

    def _require_memory_store(self):
        if self.memory_store is None:
            if not self.settings.persistent_memory_enabled:
                raise ValueError('Persistent memory is not configured')
            raise ValueError('Persistent memory is unavailable')
        return self.memory_store

    def memory_store_status(self):
        return self._require_memory_store().status()

    def memory_recent(self, limit: int = 10):
        return self._require_memory_store().inspect_recent(limit=limit)

    def memory_why(self, turn_id: str):
        return self._require_memory_store().inspect_turn(turn_id)

    def memory_correct(self, turn_id: str, replacement_content: str):
        policy = self._require_memory_store().correct_turn(
            turn_id,
            replacement_content,
            reason='explicit user correction',
        )
        self._submit_graph_policy(policy)
        self._submit_model_compact_snapshot()
        return policy

    def memory_forget(self, turn_id: str, reason: str | None = None):
        policy = self._require_memory_store().forget_turn(turn_id, reason=reason)
        self._submit_graph_policy(policy)
        self._submit_model_compact_snapshot()
        return policy

    def _require_graph_memory_manager(self):
        if self.graph_memory_manager is None:
            if not getattr(self.settings, 'graph_memory_enabled', False):
                raise ValueError('Graph memory is not configured')
            raise ValueError('Graph memory is unavailable')
        return self.graph_memory_manager

    def graph_memory_status(self):
        return self._require_graph_memory_manager().status()

    def graph_memory_recent(self, limit: int = 10):
        return self._require_graph_memory_manager().recent(limit)

    def graph_memory_why(self, item_id: str):
        return self._require_graph_memory_manager().why(item_id)

    def _submit_graph_policy(self, policy):
        if self.graph_memory_worker is None:
            return
        try:
            self.graph_memory_worker.submit_policy(policy)
        except Exception as exc:
            self.graph_memory_error = str(exc)
            self.logger.exception('Graph memory policy submission failed')

    def close(self):
        if self.compact_memory_worker is not None:
            self.compact_memory_worker.close()
        if self.model_compact_memory_worker is not None:
            self.model_compact_memory_worker.close()
        if self.graph_memory_worker is not None:
            self.graph_memory_worker.close()

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
