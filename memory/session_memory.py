class SessionMemory:
    def __init__(self, system_prompt: str, max_messages: int = 41):
        if max_messages < 3:
            raise ValueError('max_messages must be at least 3')
        self.system_prompt = system_prompt
        self.max_messages = max_messages
        self.reset()

    def reset(self):
        self.messages = [{'role': 'system', 'content': self.system_prompt}]

    def add_user(self, text: str):
        self.messages.append({'role': 'user', 'content': text})
        self._trim()

    def add_assistant(self, text: str):
        self.messages.append({'role': 'assistant', 'content': text})
        self._trim()

    def snapshot(self):
        return list(self.messages)

    def _trim(self):
        while len(self.messages) > self.max_messages:
            del self.messages[1:3]
