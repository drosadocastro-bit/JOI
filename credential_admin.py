import getpass

from security.credential_provider import CredentialAccessError, DpapiCredentialStore


_PROVIDERS = {'openai', 'elevenlabs'}
_ACTIONS = {'set', 'delete', 'verify'}


def main() -> int:
    provider = input('Provider (openai/elevenlabs): ').strip().lower()
    if provider not in _PROVIDERS:
        print('Unsupported provider. Enter only openai or elevenlabs.')
        return 2
    action = input('Action (set/delete/verify): ').strip().lower()
    if action not in _ACTIONS:
        print('Unsupported action. Enter only set, delete, or verify.')
        return 2

    store = DpapiCredentialStore()
    try:
        if action == 'set':
            credential = getpass.getpass('Credential: ')
            confirmation = getpass.getpass('Confirm credential: ')
            if not credential or credential != confirmation:
                print('Credential confirmation failed.')
                return 2
            store.set_credential(provider, credential)
        elif action == 'delete':
            store.delete_credential(provider)
        else:
            store.get_credential(provider)
    except CredentialAccessError:
        print(f'{provider} credential operation failed closed.')
        return 1

    print(f'{provider} credential {action} completed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())