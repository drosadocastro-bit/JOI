class TerminalInterface:
    def __init__(self, joi):
        self.joi = joi

    def _print_status(self):
        s = self.joi.status()
        b = s['brain']
        print()
        print(s['app_name'])
        print('=' * len(s['app_name']))
        print(f"Local Brain: {'ONLINE' if b.get('ok') else 'OFFLINE'}")
        print(f"Model:       {b.get('selected_model', 'unknown')}")
        print(f"Voice:       {s['voice']}")
        print(f"Vision:      {s['vision']}")
        print(f"Memory:      {s['memory']}")
        print(f"Cloud:       {s['cloud']}")
        if not b.get('ok'):
            print(f"Brain Error: {b.get('error')}")
        print()

    def run(self):
        self._print_status()
        print('Commands: /status  /reset  /help  /exit')
        while True:
            try:
                text = input('\nYou > ').strip()
            except (KeyboardInterrupt, EOFError):
                print('\nBye.')
                return
            if not text:
                continue
            low = text.lower()
            if low in {'/exit', '/quit'}:
                print('Bye.')
                return
            if low == '/status':
                self._print_status(); continue
            if low == '/reset':
                self.joi.reset(); print('Session memory reset.'); continue
            if low == '/help':
                print('Commands: /status  /reset  /help  /exit'); continue
            try:
                reply = self.joi.chat(text)
                print(f'\nJoi > {reply}')
            except Exception as exc:
                print(f'\n[JOI ERROR] {exc}')
                continue
            if self.joi.state.voice_enabled:
                try:
                    self.joi.speak(reply)
                except Exception as exc:
                    print(f'\n[VOICE ERROR] {exc}')
