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
            if low.startswith('/memory '):
                if self._handle_memory_command(text):
                    continue
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

    def _handle_memory_command(self, text: str) -> bool:
        parts = text.split(maxsplit=3)
        action = parts[1].lower() if len(parts) > 1 else ''
        if action in {'off', 'session', 'persistent'}:
            return False
        try:
            if action == 'status' and len(parts) == 2:
                status = self.joi.memory_store_status()
                print(
                    'Memory store: '
                    f"schema={status['schema_version']} "
                    f"turns={status['turn_count']} "
                    f"exchanges={status['exchange_count']} "
                    f"policies={status['policy_count']}"
                )
                print(
                    f"Corrected: {status['corrected_turn_count']} | "
                    f"Forgotten: {status['forgotten_turn_count']}"
                )
            elif action == 'recent' and len(parts) in {2, 3}:
                limit = int(parts[2]) if len(parts) == 3 else 10
                for item in self.joi.memory_recent(limit):
                    content = item.effective_content or '[suppressed]'
                    print(
                        f'{item.turn.turn_id} | {item.turn.role.upper()} | '
                        f'{item.status.upper()} | {content}'
                    )
            elif action == 'why' and len(parts) == 3:
                self._print_memory_provenance(self.joi.memory_why(parts[2]))
            elif action == 'correct' and len(parts) == 4:
                policy = self.joi.memory_correct(parts[2], parts[3])
                print(f'Correction recorded: {policy.policy_id}')
            elif action == 'forget' and len(parts) in {3, 4}:
                reason = parts[3] if len(parts) == 4 else None
                policy = self.joi.memory_forget(parts[2], reason)
                print(f'Forget policy recorded: {policy.policy_id}')
            else:
                print(self._memory_usage())
        except (ValueError, RuntimeError) as exc:
            print(f'[MEMORY ERROR] {exc}')
        return True

    @staticmethod
    def _print_memory_provenance(item):
        print(f'Turn: {item.turn.turn_id}')
        print(f'Exchange: {item.turn.exchange_id}')
        print(f'Role: {item.turn.role.upper()}')
        print(f'Timestamp: {item.turn.created_at_utc}')
        print(f'Status: {item.status.upper()}')
        print(f'Raw: {item.turn.content}')
        print(f"Effective: {item.effective_content or '[suppressed]'}")
        for policy in item.policies:
            supersedes = policy.supersedes_policy_id or 'none'
            reason = policy.reason or 'none'
            print(
                f'{policy.policy_id} | {policy.action.upper()} | '
                f'supersedes={supersedes} | reason={reason}'
            )

    @staticmethod
    def _memory_usage():
        return (
            'Memory: /memory status | /memory recent [limit] | '
            '/memory why <turn-id> | /memory correct <turn-id> <replacement> | '
            '/memory forget <turn-id> [reason]'
        )

    @staticmethod
    def _print_help():
        print('Commands: /status  /reset  /help  /exit')
        print('State: /mic <on|off>  /voice <on|off>  /vision <on|off>')
        print('       /memory <off|session|persistent>  /cloud <on|off>')
        print(TerminalInterface._memory_usage())
