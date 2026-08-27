from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class JoiState:
    voice_enabled: bool = False
    vision_enabled: bool = False
    cloud_enabled: bool = False
    memory_mode: str = 'session'
    active_brain: str = 'local'
    active_voice: str = 'disabled'
    messages: List[Dict[str, str]] = field(default_factory=list)
