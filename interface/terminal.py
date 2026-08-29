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
        print(f"Mic:         {s['mic']}")
        print(f"Voice:       {s['voice']}")
        print(f"Vision:      {s['vision']}")
        print(f"Memory:      {s['memory']}")
        print(f"Cloud:       {s['cloud']}")
        if not b.get('ok'):
            print(f"Brain Error: {b.get('error')}")
        print()

    def run(self):
        self._print_status()
        self._print_help()
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
                self._print_help(); continue
            parts = low.split()
            if parts[0] in {'/mic', '/voice', '/vision', '/memory', '/cloud'}:
                if len(parts) != 2:
                    print(f'Usage: {parts[0]} <on|off>')
                    continue
                try:
                    print(self.joi.set_runtime_state(parts[0][1:], parts[1]))
                except ValueError as exc:
                    print(f'[STATE ERROR] {exc}')
                continue
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

    @staticmethod
    def _print_help():
        print('Commands: /status  /reset  /help  /exit')
        print('State: /mic <on|off>  /voice <on|off>  /vision <on|off>')
        print('       /memory <session|off>  /cloud <on|off>')
