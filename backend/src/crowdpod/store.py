"""SQLite storage for runs, personas, reactions, browser sessions and events."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .models import Archetype, CrowdSummary, Documents, HandsSession, Persona, Reaction, RunEvent, RunRequest

SCHEMA = """
create table if not exists runs (
  id text primary key, created_at real not null, status text not null, provider text not null,
  request text not null, summary text, docs text, error text
);
create table if not exists personas (run_id text, id text, archetype_id text, data text, primary key (run_id, id));
create table if not exists reactions (run_id text, persona_id text, verdict text, data text, primary key (run_id, persona_id));
create table if not exists sessions (run_id text, persona_id text, data text, primary key (run_id, persona_id));
create table if not exists events (run_id text, seq integer, type text, data text, primary key (run_id, seq));
create table if not exists run_extras (run_id text, kind text, data text, primary key (run_id, kind));
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.execute("pragma journal_mode=wal")
            # older databases: runs gained an owner when sign-in arrived
            columns = {r[1] for r in self._db.execute("pragma table_info(runs)")}
            if "owner" not in columns:
                self._db.execute("alter table runs add column owner text")
            self._db.execute("create index if not exists runs_owner on runs (owner, created_at)")
            self._db.commit()

    def _exec(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        with self._lock:
            self._db.execute(sql, args)
            self._db.commit()

    def _many(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        with self._lock:
            self._db.executemany(sql, rows)
            self._db.commit()

    def _all(self, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    # runs
    def create_run(self, run_id: str, request: RunRequest, provider: str, owner: str | None = None) -> None:
        self._exec(
            "insert into runs (id, created_at, status, provider, request, owner) values (?, ?, 'queued', ?, ?, ?)",
            (run_id, time.time(), provider, request.model_dump_json(), owner),
        )

    def run_owner(self, run_id: str) -> tuple[bool, str | None]:
        """(exists, owner id)."""
        rows = self._all("select owner from runs where id = ?", (run_id,))
        return (True, rows[0]["owner"]) if rows else (False, None)

    def count_runs(self, owner: str | None, since: float, *, statuses: tuple[str, ...] | None = None,
                   with_hands: bool = False) -> int:
        sql = "select request, status from runs where created_at >= ? and owner is ?"
        rows = self._all(sql, (since, owner))
        return sum(
            1 for r in rows
            if (statuses is None or r["status"] in statuses)
            and (not with_hands or json.loads(r["request"]).get("hands"))
        )

    def set_status(self, run_id: str, status: str, error: str | None = None) -> None:
        self._exec("update runs set status = ?, error = ? where id = ?", (status, error, run_id))

    def save_summary(self, run_id: str, summary: CrowdSummary) -> None:
        self._exec("update runs set summary = ? where id = ?", (summary.model_dump_json(), run_id))

    def save_docs(self, run_id: str, docs: Documents) -> None:
        self._exec("update runs set docs = ? where id = ?", (docs.model_dump_json(), run_id))

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        rows = self._all("select * from runs where id = ?", (run_id,))
        if not rows:
            return None
        r = rows[0]
        return {
            "id": r["id"], "created_at": r["created_at"], "status": r["status"], "provider": r["provider"],
            "request": json.loads(r["request"]), "error": r["error"],
            "summary": json.loads(r["summary"]) if r["summary"] else None,
            "has_docs": r["docs"] is not None,
        }

    def list_runs(self, limit: int = 50, owner: str | None = None, everyone: bool = False,
                  unowned: bool = False) -> list[dict[str, Any]]:
        """Runs of `owner`; `unowned` adds runs made before runs had owners."""
        if everyone:
            rows = self._all("select id, created_at, status, provider, request from runs order by created_at desc limit ?", (limit,))
        else:
            rows = self._all(
                "select id, created_at, status, provider, request from runs where owner is ? or (? and owner is null) "
                "order by created_at desc limit ?",
                (owner, int(unowned), limit),
            )
        return [
            {"id": r["id"], "created_at": r["created_at"], "status": r["status"], "provider": r["provider"],
             "name": json.loads(r["request"])["brief"]["name"]}
            for r in rows
        ]

    def get_docs(self, run_id: str) -> Documents | None:
        rows = self._all("select docs from runs where id = ?", (run_id,))
        return Documents.model_validate_json(rows[0]["docs"]) if rows and rows[0]["docs"] else None

    # crowd
    def save_personas(self, run_id: str, personas: list[Persona]) -> None:
        self._many(
            "insert or replace into personas values (?, ?, ?, ?)",
            [(run_id, p.id, p.archetype_id, p.model_dump_json()) for p in personas],
        )

    def get_persona(self, run_id: str, persona_id: str) -> Persona | None:
        rows = self._all("select data from personas where run_id = ? and id = ?", (run_id, persona_id))
        return Persona.model_validate_json(rows[0]["data"]) if rows else None

    def save_reaction(self, run_id: str, r: Reaction) -> None:
        self._exec("insert or replace into reactions values (?, ?, ?, ?)", (run_id, r.persona_id, r.verdict, r.model_dump_json()))

    def get_reactions(
        self, run_id: str, *, segment: str | None = None, verdict: str | None = None, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        sql = ("select p.data as persona, r.data as reaction from reactions r join personas p "
               "on p.run_id = r.run_id and p.id = r.persona_id where r.run_id = ?")
        args: list[Any] = [run_id]
        if segment:
            sql += " and p.archetype_id = ?"
            args.append(segment)
        if verdict:
            sql += " and r.verdict = ?"
            args.append(verdict)
        sql += " order by p.id limit ? offset ?"
        args += [limit, offset]
        return [{"persona": json.loads(r["persona"]), "reaction": json.loads(r["reaction"])} for r in self._all(sql, tuple(args))]

    # research and generated audience
    def save_extra(self, run_id: str, kind: str, data: Any) -> None:
        self._exec("insert or replace into run_extras values (?, ?, ?)", (run_id, kind, json.dumps(data, ensure_ascii=False)))

    def get_extra(self, run_id: str, kind: str) -> Any:
        rows = self._all("select data from run_extras where run_id = ? and kind = ?", (run_id, kind))
        return json.loads(rows[0]["data"]) if rows else None

    def get_archetypes(self, run_id: str) -> dict[str, Archetype]:
        return {a["id"]: Archetype.model_validate(a) for a in self.get_extra(run_id, "archetypes") or []}

    # hands
    def save_session(self, run_id: str, s: HandsSession) -> None:
        self._exec("insert or replace into sessions values (?, ?, ?)", (run_id, s.persona_id, s.model_dump_json()))

    def get_sessions(self, run_id: str) -> list[HandsSession]:
        return [HandsSession.model_validate_json(r["data"]) for r in self._all("select data from sessions where run_id = ?", (run_id,))]

    # events
    def save_event(self, e: RunEvent) -> None:
        self._exec("insert into events values (?, ?, ?, ?)", (e.run_id, e.seq, e.type, json.dumps(e.data, ensure_ascii=False)))

    def get_events(self, run_id: str, after: int = 0) -> list[RunEvent]:
        rows = self._all("select * from events where run_id = ? and seq > ? order by seq", (run_id, after))
        return [RunEvent(seq=r["seq"], run_id=r["run_id"], type=r["type"], data=json.loads(r["data"])) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
