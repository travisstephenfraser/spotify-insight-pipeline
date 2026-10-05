"""The spend ledger: every Jev reservation and charge, across all runs, against one cap.

Each row keeps the billing rates in force when it was written. Spend already made never
moves when a rate file is edited; a correction is a new `adjust` row. Totals are held in
memory and can always be rebuilt from the file with `reload()`.
"""

import json
from decimal import Decimal
from pathlib import Path

from pipeline import state

MILLION = Decimal(1_000_000)


class CapReached(Exception):
    """Spent plus reserved plus this reservation would pass the cap. Nothing was written."""


class AlreadyOpened(Exception):
    pass


class Ledger:
    def __init__(self, db, billing_path, cap_usd=Decimal("25")):
        self.db = db
        self.cap = Decimal(cap_usd)
        rates = json.loads(Path(billing_path).read_text(encoding="utf-8"))["jev"]
        self.rate_in, self.rate_out = rates["usd_per_mtok_in"], rates["usd_per_mtok_out"]
        self.reload()

    def reload(self):
        """Rebuild both totals from the file."""
        spent = Decimal(0)
        for r in self.db.execute(
            "SELECT kind, usd_per_mtok_in AS rin, usd_per_mtok_out AS rout, SUM(input_tokens) AS tin, "
            "SUM(output_tokens) AS tout FROM ledger WHERE kind IN ('actual','kept') GROUP BY 1, 2, 3"
        ):
            spent += (r["tin"] * Decimal(r["rin"]) + r["tout"] * Decimal(r["rout"])) / MILLION
        for r in self.db.execute("SELECT usd_fixed FROM ledger WHERE kind IN ('opening','adjust')"):
            spent += Decimal(r["usd_fixed"])
        reserved = Decimal(0)
        for r in self.db.execute(
            "SELECT usd_per_mtok_in AS rin, SUM(input_tokens) AS tin FROM ledger r WHERE kind='reserve' AND NOT EXISTS "
            "(SELECT 1 FROM ledger s WHERE s.request_id = r.request_id AND s.kind IN ('actual','kept')) GROUP BY 1"
        ):
            reserved += r["tin"] * Decimal(r["rin"]) / MILLION
        self._spent, self._reserved = spent, reserved

    def spent_usd(self):
        return self._spent

    def reserved_usd(self):
        return self._reserved

    def _usd(self, tokens):
        return tokens * Decimal(self.rate_in) / MILLION

    def would_pass_cap(self, reserve_tokens):
        return self._spent + self._reserved + self._usd(reserve_tokens) > self.cap

    def reserve(self, request_id, run, reserve_tokens):
        """Hold the worst-case cost of a request about to be sent. Called inside the caller's transaction."""
        if self.would_pass_cap(reserve_tokens):
            raise CapReached(f"spent ${self._spent} + reserved ${self._reserved} + next would pass ${self.cap}")
        self._write(request_id, run, "reserve", reserve_tokens, 0, self.rate_in, self.rate_out)
        self._reserved += self._usd(reserve_tokens)

    def settle(self, request_id, input_tokens=None, output_tokens=None):
        """Replace a reservation with the reported usage, or keep it whole when no usage came back."""
        held = self.db.execute("SELECT * FROM ledger WHERE request_id=? AND kind='reserve'", (request_id,)).fetchone()
        if held is None:
            return
        rin, rout = Decimal(held["usd_per_mtok_in"]), Decimal(held["usd_per_mtok_out"])
        if input_tokens is None:
            kind, tin, tout = "kept", held["input_tokens"], 0
        else:
            kind, tin, tout = "actual", input_tokens, output_tokens or 0
        self._write(request_id, held["run"], kind, tin, tout, held["usd_per_mtok_in"], held["usd_per_mtok_out"])
        self._reserved -= held["input_tokens"] * rin / MILLION
        self._spent += (tin * rin + tout * rout) / MILLION

    def opening(self, usd_measured, usd_estimated):
        """The Jev spend made before this ledger existed. Written once."""
        if self.db.execute("SELECT 1 FROM ledger WHERE kind='opening'").fetchone():
            raise AlreadyOpened("the opening spend is already in the ledger")
        with state.tx(self.db):
            for note, usd in (("measured", usd_measured), ("estimated", usd_estimated)):
                self._write(f"opening-{note}", "-", "opening", 0, 0, self.rate_in, self.rate_out, usd, note)
        self._spent += Decimal(usd_measured) + Decimal(usd_estimated)

    def adjust(self, usd, note):
        """A correction found by reconciling with the provider's usage page. Never a recomputation."""
        n = self.db.execute("SELECT COUNT(*) FROM ledger WHERE kind='adjust'").fetchone()[0]
        self._write(f"adjust-{n + 1}", "-", "adjust", 0, 0, self.rate_in, self.rate_out, usd, note)
        self._spent += Decimal(usd)

    def _write(self, request_id, run, kind, tin, tout, rin, rout, usd_fixed=None, note=None):
        self.db.execute(
            "INSERT INTO ledger (request_id, run, kind, input_tokens, output_tokens, usd_per_mtok_in, usd_per_mtok_out, "
            "usd_fixed, note, created_utc) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (request_id, run, kind, tin, tout, rin, rout, None if usd_fixed is None else str(usd_fixed), note, state.now_utc()),
        )
