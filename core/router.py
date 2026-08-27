class BrainRouter:
    '''Phase 1 router: local brain only.'''

    def __init__(self, local_brain):
        self.local_brain = local_brain

    def chat(self, messages):
        return self.local_brain.chat(messages)

    def health(self):
        return self.local_brain.health()
