import sqlite3
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DATABASE_SCHEMA_VERSION = 2
TURN_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = 1


class MemoryStoreError(RuntimeError):
	pass


@dataclass(frozen=True)
class EpisodicTurn:
	turn_id: str
	exchange_id: str
	role: str
	content: str
	created_at_utc: str
	schema_version: int


@dataclass(frozen=True)
class MemoryPolicyRecord:
	policy_id: str
	target_turn_id: str
	action: str
	replacement_content: str | None
	reason: str | None
	supersedes_policy_id: str | None
	created_at_utc: str
	schema_version: int


@dataclass(frozen=True)
class InspectedMemoryTurn:
	turn: EpisodicTurn
	status: str
	effective_content: str | None
	policies: tuple[MemoryPolicyRecord, ...]


class EpisodicMemoryStore:
	def __init__(
		self,
		path: str | Path,
		id_factory: Callable[[], str] | None = None,
		clock: Callable[[], datetime] | None = None,
	):
		self.path = Path(path)
		self.id_factory = id_factory or (lambda: str(uuid.uuid4()))
		self.clock = clock or (lambda: datetime.now(timezone.utc))
		self._initialize()

	@contextmanager
	def _connect(self) -> Generator[sqlite3.Connection, None, None]:
		connection = sqlite3.connect(self.path, timeout=5)
		try:
			connection.execute('PRAGMA foreign_keys = ON')
			with connection:
				yield connection
		finally:
			connection.close()

	def _initialize(self) -> None:
		try:
			self.path.parent.mkdir(parents=True, exist_ok=True)
			with self._connect() as connection:
				version = connection.execute('PRAGMA user_version').fetchone()[0]
				if version not in {0, 1, DATABASE_SCHEMA_VERSION}:
					raise MemoryStoreError(f'unsupported memory schema version: {version}')
				if version == 0:
					connection.execute(
						'''
						CREATE TABLE episodic_turns (
							turn_id TEXT PRIMARY KEY,
							exchange_id TEXT NOT NULL,
							sequence INTEGER NOT NULL CHECK (sequence IN (0, 1)),
							role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
							content TEXT NOT NULL CHECK (length(trim(content)) > 0),
							created_at_utc TEXT NOT NULL,
							schema_version INTEGER NOT NULL,
							UNIQUE (exchange_id, sequence)
						)
						'''
					)
					connection.execute(
						'''
						CREATE TRIGGER prevent_episodic_turn_update
						BEFORE UPDATE ON episodic_turns
						BEGIN
							SELECT RAISE(ABORT, 'episodic turns are append-only');
						END
						'''
					)
					connection.execute(
						'''
						CREATE TRIGGER prevent_episodic_turn_delete
						BEFORE DELETE ON episodic_turns
						BEGIN
							SELECT RAISE(ABORT, 'episodic turns are append-only');
						END
						'''
					)
					version = 1
				if version == 1:
					self._migrate_to_schema_v2(connection)
		except MemoryStoreError:
			raise
		except (OSError, sqlite3.Error) as exc:
			raise MemoryStoreError('could not initialize memory store') from exc

	@staticmethod
	def _migrate_to_schema_v2(connection: sqlite3.Connection) -> None:
		connection.execute(
			'''
			CREATE TABLE memory_policies (
				policy_id TEXT PRIMARY KEY,
				target_turn_id TEXT NOT NULL,
				action TEXT NOT NULL CHECK (action IN ('correct', 'forget')),
				replacement_content TEXT,
				reason TEXT,
				supersedes_policy_id TEXT,
				created_at_utc TEXT NOT NULL,
				schema_version INTEGER NOT NULL,
				FOREIGN KEY (target_turn_id) REFERENCES episodic_turns (turn_id),
				FOREIGN KEY (supersedes_policy_id) REFERENCES memory_policies (policy_id),
				CHECK (
					(action = 'correct' AND length(trim(replacement_content)) > 0)
					OR (action = 'forget' AND replacement_content IS NULL)
				)
			)
			'''
		)
		connection.execute(
			'''
			CREATE TRIGGER prevent_memory_policy_update
			BEFORE UPDATE ON memory_policies
			BEGIN
				SELECT RAISE(ABORT, 'memory policies are append-only');
			END
			'''
		)
		connection.execute(
			'''
			CREATE TRIGGER prevent_memory_policy_delete
			BEFORE DELETE ON memory_policies
			BEGIN
				SELECT RAISE(ABORT, 'memory policies are append-only');
			END
			'''
		)
		connection.execute(f'PRAGMA user_version = {DATABASE_SCHEMA_VERSION}')

	def append_exchange(
		self,
		user_content: str,
		assistant_content: str,
	) -> list[EpisodicTurn]:
		if not user_content or not user_content.strip():
			raise ValueError('user content must not be empty')
		if not assistant_content or not assistant_content.strip():
			raise ValueError('assistant content must not be empty')

		exchange_id = self.id_factory()
		timestamp = self.clock()
		if timestamp.tzinfo is None:
			raise ValueError('memory clock must return a timezone-aware datetime')
		created_at_utc = timestamp.astimezone(timezone.utc).isoformat()
		turns = [
			EpisodicTurn(
				turn_id=self.id_factory(),
				exchange_id=exchange_id,
				role='user',
				content=user_content,
				created_at_utc=created_at_utc,
				schema_version=TURN_SCHEMA_VERSION,
			),
			EpisodicTurn(
				turn_id=self.id_factory(),
				exchange_id=exchange_id,
				role='assistant',
				content=assistant_content,
				created_at_utc=created_at_utc,
				schema_version=TURN_SCHEMA_VERSION,
			),
		]

		try:
			with self._connect() as connection:
				connection.execute('BEGIN IMMEDIATE')
				connection.executemany(
					'''
					INSERT INTO episodic_turns (
						turn_id,
						exchange_id,
						sequence,
						role,
						content,
						created_at_utc,
						schema_version
					) VALUES (?, ?, ?, ?, ?, ?, ?)
					''',
					[
						(
							turn.turn_id,
							turn.exchange_id,
							sequence,
							turn.role,
							turn.content,
							turn.created_at_utc,
							turn.schema_version,
						)
						for sequence, turn in enumerate(turns)
					],
				)
		except (OSError, sqlite3.Error) as exc:
			raise MemoryStoreError('could not append exchange') from exc
		return turns

	def list_turns(self) -> list[EpisodicTurn]:
		try:
			with self._connect() as connection:
				rows = connection.execute(
					'''
					SELECT
						turn_id,
						exchange_id,
						role,
						content,
						created_at_utc,
						schema_version
					FROM episodic_turns
					ORDER BY rowid
					'''
				).fetchall()
		except (OSError, sqlite3.Error) as exc:
			raise MemoryStoreError('could not read memory store') from exc
		return [EpisodicTurn(*row) for row in rows]

	def correct_turn(
		self,
		turn_id: str,
		replacement_content: str,
		reason: str | None = None,
	) -> MemoryPolicyRecord:
		if not replacement_content or not replacement_content.strip():
			raise ValueError('replacement content must not be empty')
		return self._append_policy(
			turn_id=turn_id,
			action='correct',
			replacement_content=replacement_content,
			reason=reason,
		)

	def forget_turn(
		self,
		turn_id: str,
		reason: str | None = None,
	) -> MemoryPolicyRecord:
		return self._append_policy(
			turn_id=turn_id,
			action='forget',
			replacement_content=None,
			reason=reason,
		)

	def _append_policy(
		self,
		turn_id: str,
		action: str,
		replacement_content: str | None,
		reason: str | None,
	) -> MemoryPolicyRecord:
		policy_id = self.id_factory()
		timestamp = self.clock()
		if timestamp.tzinfo is None:
			raise ValueError('memory clock must return a timezone-aware datetime')
		created_at_utc = timestamp.astimezone(timezone.utc).isoformat()
		try:
			with self._connect() as connection:
				connection.execute('BEGIN IMMEDIATE')
				if connection.execute(
					'SELECT 1 FROM episodic_turns WHERE turn_id = ?',
					(turn_id,),
				).fetchone() is None:
					raise MemoryStoreError(f'turn not found: {turn_id}')
				latest = connection.execute(
					'''
					SELECT policy_id
					FROM memory_policies
					WHERE target_turn_id = ?
					ORDER BY rowid DESC
					LIMIT 1
					''',
					(turn_id,),
				).fetchone()
				supersedes_policy_id = latest[0] if latest is not None else None
				connection.execute(
					'''
					INSERT INTO memory_policies (
						policy_id,
						target_turn_id,
						action,
						replacement_content,
						reason,
						supersedes_policy_id,
						created_at_utc,
						schema_version
					) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
					''',
					(
						policy_id,
						turn_id,
						action,
						replacement_content,
						reason,
						supersedes_policy_id,
						created_at_utc,
						POLICY_SCHEMA_VERSION,
					),
				)
		except MemoryStoreError:
			raise
		except (OSError, sqlite3.Error) as exc:
			raise MemoryStoreError('could not append memory policy') from exc
		return MemoryPolicyRecord(
			policy_id=policy_id,
			target_turn_id=turn_id,
			action=action,
			replacement_content=replacement_content,
			reason=reason,
			supersedes_policy_id=supersedes_policy_id,
			created_at_utc=created_at_utc,
			schema_version=POLICY_SCHEMA_VERSION,
		)

	def inspect_turn(self, turn_id: str) -> InspectedMemoryTurn:
		try:
			with self._connect() as connection:
				row = connection.execute(
					'''
					SELECT turn_id, exchange_id, role, content, created_at_utc, schema_version
					FROM episodic_turns
					WHERE turn_id = ?
					''',
					(turn_id,),
				).fetchone()
				if row is None:
					raise MemoryStoreError(f'turn not found: {turn_id}')
				policy_rows = connection.execute(
					'''
					SELECT
						policy_id,
						target_turn_id,
						action,
						replacement_content,
						reason,
						supersedes_policy_id,
						created_at_utc,
						schema_version
					FROM memory_policies
					WHERE target_turn_id = ?
					ORDER BY rowid
					''',
					(turn_id,),
				).fetchall()
		except MemoryStoreError:
			raise
		except (OSError, sqlite3.Error) as exc:
			raise MemoryStoreError('could not inspect memory turn') from exc

		turn = EpisodicTurn(*row)
		policies = tuple(MemoryPolicyRecord(*policy_row) for policy_row in policy_rows)
		if not policies:
			return InspectedMemoryTurn(turn, 'original', turn.content, policies)
		latest = policies[-1]
		if latest.action == 'forget':
			return InspectedMemoryTurn(turn, 'forgotten', None, policies)
		return InspectedMemoryTurn(turn, 'corrected', latest.replacement_content, policies)

	def inspect_recent(self, limit: int = 10) -> list[InspectedMemoryTurn]:
		if limit <= 0 or limit > 100:
			raise ValueError('limit must be between 1 and 100')
		try:
			with self._connect() as connection:
				rows = connection.execute(
					'''
					SELECT turn_id
					FROM episodic_turns
					ORDER BY rowid DESC
					LIMIT ?
					''',
					(limit,),
				).fetchall()
		except (OSError, sqlite3.Error) as exc:
			raise MemoryStoreError('could not inspect recent memory') from exc
		return [self.inspect_turn(row[0]) for row in reversed(rows)]

	def status(self) -> dict[str, int]:
		try:
			with self._connect() as connection:
				turn_count = connection.execute(
					'SELECT COUNT(*) FROM episodic_turns'
				).fetchone()[0]
				exchange_count = connection.execute(
					'SELECT COUNT(DISTINCT exchange_id) FROM episodic_turns'
				).fetchone()[0]
				policy_count = connection.execute(
					'SELECT COUNT(*) FROM memory_policies'
				).fetchone()[0]
				latest_actions = connection.execute(
					'''
					SELECT action
					FROM memory_policies AS policy
					WHERE rowid = (
						SELECT MAX(rowid)
						FROM memory_policies
						WHERE target_turn_id = policy.target_turn_id
					)
					'''
				).fetchall()
		except (OSError, sqlite3.Error) as exc:
			raise MemoryStoreError('could not read memory status') from exc
		return {
			'schema_version': DATABASE_SCHEMA_VERSION,
			'turn_count': turn_count,
			'exchange_count': exchange_count,
			'policy_count': policy_count,
			'corrected_turn_count': sum(action == 'correct' for action, in latest_actions),
			'forgotten_turn_count': sum(action == 'forget' for action, in latest_actions),
		}
