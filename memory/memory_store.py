import sqlite3
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1


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
				if version not in {0, SCHEMA_VERSION}:
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
					connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
		except MemoryStoreError:
			raise
		except (OSError, sqlite3.Error) as exc:
			raise MemoryStoreError('could not initialize memory store') from exc

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
				schema_version=SCHEMA_VERSION,
			),
			EpisodicTurn(
				turn_id=self.id_factory(),
				exchange_id=exchange_id,
				role='assistant',
				content=assistant_content,
				created_at_utc=created_at_utc,
				schema_version=SCHEMA_VERSION,
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
