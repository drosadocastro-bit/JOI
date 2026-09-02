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
        if text.lower().startswith('/memory graph'):
            return self._handle_graph_command(text)
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

    def _handle_graph_command(self, text: str) -> bool:
        parts = text.split(maxsplit=3)
        action = parts[2].lower() if len(parts) > 2 else ''
        try:
            if action == 'status' and len(parts) == 3:
                status = self.joi.graph_memory_status()
                print(
                    'Graph memory: '
                    f"schema={status['schema_version']} "
                    f"extractor={status['extractor_version']}"
                )
                print(
                    f"Exchanges: {status['processed_exchange_count']} | "
                    f"Nodes: {status['node_count']} | Edges: {status['edge_count']} | "
                    f"Suppressed sources: {status['suppressed_source_count']}"
                )
            elif action == 'recent' and len(parts) in {3, 4}:
                limit = int(parts[3]) if len(parts) == 4 else 10
                for node in self.joi.graph_memory_recent(limit):
                    self._print_graph_node(node, include_sources=False)
            elif action in {'node', 'why'} and len(parts) == 4:
                self._print_graph_item(self.joi.graph_memory_why(parts[3]))
            else:
                print(self._graph_usage())
        except (ValueError, RuntimeError) as exc:
            print(f'[MEMORY ERROR] {exc}')
        return True

    @classmethod
    def _print_graph_item(cls, item):
        if hasattr(item, 'source_refs'):
            cls._print_graph_node(item, include_sources=True)
            return
        print(
            f'{item.edge_id} | {item.relation.upper()} | '
            f'{item.source_node_id} -> {item.target_node_id} | weight={item.weight}'
        )
        print(f"Sources: {', '.join(item.source_exchange_ids)}")

    @staticmethod
    def _print_graph_node(node, include_sources: bool):
        print(
            f'{node.node_id} | {node.entity_type.upper()} | '
            f'{node.canonical_label} | observations={node.observation_count}'
        )
        if not include_sources:
            return
        for source in node.source_refs:
            policies = ','.join(policy or 'none' for policy in source.policy_ids)
            status = 'SUPPRESSED' if source.suppressed else 'ACTIVE'
            print(
                f'{source.exchange_id} | turns={",".join(source.turn_ids)} | '
                f'policies={policies} | {status}'
            )

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
            '/memory forget <turn-id> [reason]\n'
            f'{TerminalInterface._graph_usage()}'
        )

    @staticmethod
    def _graph_usage():
        return (
            'Graph: /memory graph status | /memory graph recent [limit] | '
            '/memory graph node <id> | /memory graph why <node-or-edge-id>'
        )

    @staticmethod
    def _print_help():
        print('Commands: /status  /reset  /help  /exit')
        print('State: /mic <on|off>  /voice <on|off>  /vision <on|off>')
        print('       /memory <off|session|persistent>  /cloud <on|off>')
        print(TerminalInterface._memory_usage())
