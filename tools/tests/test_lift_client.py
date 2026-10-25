"""fetch and audit of lift.py. No network: every request goes to a fake opener."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import support  # noqa: F401  (puts tools/ on sys.path)

import lift

KEY = "swk_" + "A1b2C3d4E5" * 4
BASE = "https://dash.spellwarden.ai/api/v1/orgs"
RUN = "0123456789abcdef0123456789abcdef"


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        return None


class FakeOpener:
    """Answers from a table {url: bytes | Exception}; records every request. An unknown URL fails the test."""

    def __init__(self, routes: dict[str, bytes | Exception]) -> None:
        self.routes = routes
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        self.requests.append(request)
        route = self.routes.get(request.full_url)
        if route is None:
            raise AssertionError(f"unexpected request to {request.full_url}")
        if isinstance(route, Exception):
            raise route
        return FakeResponse(route)


def pack_run(run_id: str, started_at: str, *, skill_ids=("sk-1",), status="finished", by="user:builder", skills=None,
             label="Placeholder") -> dict:
    return {"id": run_id, "started_at": started_at, "label": label, "status": status, "started_by": by,
            "started_by_name": None, "target": {"skill_ids": list(skill_ids)},
            "skills": skills if skills is not None else [{"skill_id": "sk-1", "name": "infra-change-safety", "sha256": "aa" * 32}]}


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name)

    def call(self, opener: FakeOpener, *argv: str, env: dict | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = lift.main(list(argv), env={lift.KEY_ENV: KEY} if env is None else env, opener=opener, out=out, err=err)
        return code, out.getvalue(), err.getvalue()


class FetchTest(CommandTest):
    def test_writes_each_answer_unchanged_with_a_bearer_header(self) -> None:
        raw = b'{"tasks": [],\n "run":   {"id": "x"}}\n'
        opener = FakeOpener({f"{BASE}/claude-billing-test/eval-runs/{RUN}": raw})
        code, out, err = self.call(opener, "fetch", "--org", "claude-billing-test", "--out", str(self.path / "runs"), RUN)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual((self.path / "runs" / f"{RUN}.json").read_bytes(), raw)
        request = opener.requests[0]
        self.assertEqual(request.get_header("Authorization"), f"Bearer {KEY}")
        self.assertIn(RUN, out)
        self.assertNotIn(KEY, out)

    def test_refuses_to_run_without_the_variable(self) -> None:
        opener = FakeOpener({})
        code, out, err = self.call(opener, "fetch", "--org", "o1", "--out", str(self.path), RUN, env={})
        self.assertEqual(code, 2)
        self.assertIn("SPELLWARDEN_API_KEY is not set", err)
        self.assertEqual(opener.requests, [])

    def test_a_key_with_whitespace_is_refused_and_not_echoed(self) -> None:
        bad = "swk_abc def\nX-Evil: 1"
        code, out, err = self.call(FakeOpener({}), "fetch", "--org", "o1", "--out", str(self.path), RUN, env={lift.KEY_ENV: bad})
        self.assertEqual(code, 2)
        self.assertNotIn("abc", out + err)

    def test_the_key_is_never_printed_when_a_request_fails(self) -> None:
        url = f"{BASE}/o1/eval-runs/{RUN}"
        for failure in (urllib.error.HTTPError(url, 401, "Unauthorized", {}, None), urllib.error.URLError("no route to host")):
            with self.subTest(failure=type(failure).__name__):
                code, out, err = self.call(FakeOpener({url: failure}), "fetch", "--org", "o1", "--out", str(self.path), RUN)
                self.assertEqual(code, 1)
                self.assertNotIn(KEY, out + err)
                self.assertIn("lift:", err)

    def test_http_error_names_the_status(self) -> None:
        url = f"{BASE}/o1/eval-runs/{RUN}"
        _, _, err = self.call(FakeOpener({url: urllib.error.HTTPError(url, 404, "Not Found", {}, None)}),
                              "fetch", "--org", "o1", "--out", str(self.path), RUN)
        self.assertIn("HTTP 404", err)

    def test_refuses_a_bad_slug_and_a_bad_run_id_before_any_request(self) -> None:
        opener = FakeOpener({})
        for args in (["--org", "../etc", "--out", str(self.path), RUN], ["--org", "o1", "--out", str(self.path), "../x"],
                     ["--org", "o1", "--out", str(self.path), "a/b"]):
            with self.subTest(args=args):
                self.assertEqual(self.call(opener, "fetch", *args)[0], 2)
        self.assertEqual(opener.requests, [])
        self.assertEqual(list(self.path.iterdir()), [])

    def test_refuses_an_answer_that_is_not_json(self) -> None:
        opener = FakeOpener({f"{BASE}/o1/eval-runs/{RUN}": b"<html>"})
        code, _, err = self.call(opener, "fetch", "--org", "o1", "--out", str(self.path / "runs"), RUN)
        self.assertEqual(code, 1)
        self.assertIn("not JSON", err)
        self.assertFalse((self.path / "runs" / f"{RUN}.json").exists())

    def test_only_https_is_accepted(self) -> None:
        with self.assertRaises(lift.LiftError):
            lift.fetch_runs("o1", [RUN], self.path, KEY, FakeOpener({}), base="http://dash.example")

    def test_redirects_are_refused(self) -> None:
        handler = lift._RefuseRedirect()
        request = urllib.request.Request("https://dash.spellwarden.ai/x")
        self.assertIsNone(handler.redirect_request(request, None, 302, "Found", {}, "https://elsewhere.example/"))
        self.assertTrue(any(isinstance(item, lift._RefuseRedirect) for item in lift.build_opener().handlers))


class AuditTest(CommandTest):
    def pages(self, first: list[dict], second: list[dict]) -> FakeOpener:
        base = f"{BASE}/claude-billing-test/eval-runs?suite_id=infra-ops-40"
        return FakeOpener({
            base: json.dumps({"runs": first, "cursor": "c 1/2", "quota": {}}).encode(),
            f"{base}&cursor=c%201%2F2": json.dumps({"runs": second, "cursor": None, "quota": {}}).encode(),
        })

    def test_reads_every_page_and_lists_the_matching_runs_oldest_first(self) -> None:
        queued = pack_run("run-queued", "2026-11-03T09:00:00Z", status="queued", skills=[])
        errored = pack_run("run-error", "2026-11-01T09:00:00Z", status="error", skills=[])
        finished = pack_run("run-done", "2026-11-02T09:00:00Z", skill_ids=("other",),
                            skills=[{"skill_id": "other", "name": "renamed", "sha256": "bb" * 32}])
        foreign = pack_run("run-foreign", "2026-11-04T09:00:00Z", skill_ids=("zzz",),
                           skills=[{"skill_id": "zzz", "name": "ci-pipeline-repair", "sha256": "cc" * 32}])
        unrelated = pack_run("run-unrelated", "2026-11-05T09:00:00Z", skill_ids=("zzz",),
                             skills=[{"skill_id": "zzz", "name": "something-else", "sha256": "dd" * 32}])
        other_hand = pack_run("run-other", "2026-11-06T09:00:00Z", by="user:somebody")
        opener = self.pages([queued, errored, unrelated], [finished, foreign, other_hand])
        code, out, err = self.call(opener, "audit", "--org", "claude-billing-test", "--ids", "sk-1,sk-9",
                                   "--sha256", "bb" * 32, "--build-accounts", "user:builder")
        self.assertEqual((code, err), (0, ""))
        listed = [line.split(" | ")[0].lstrip("| ") for line in out.splitlines() if line.startswith("| run-")]
        # the build's runs first, then another's run, then the name-only run; oldest first inside each table
        self.assertEqual(listed, ["run-error", "run-done", "run-queued", "run-other", "run-foreign"])
        builds, rest = out.split("### Pack runs by others")
        self.assertEqual([x for x in ("run-error", "run-done", "run-queued") if x in builds], ["run-error", "run-done", "run-queued"])
        others, name_only = rest.split("### Runs of a foreign skill")
        self.assertIn("run-other", others)
        self.assertNotIn("run-other", builds)
        self.assertIn("run-foreign", name_only)
        self.assertNotIn("run-unrelated", out)
        self.assertEqual(len(opener.requests), 2)
        self.assertIn("none yet", out)

    def test_an_empty_section_says_so(self) -> None:
        opener = self.pages([], [])
        _, out, _ = self.call(opener, "audit", "--org", "claude-billing-test", "--ids", "sk-1", "--build-accounts", "user:builder")
        self.assertEqual(out.count("No runs."), 3)

    def test_without_build_accounts_the_starter_is_not_classified(self) -> None:
        opener = self.pages([pack_run("run-a", "2026-11-01T09:00:00Z")], [])
        _, out, _ = self.call(opener, "audit", "--org", "claude-billing-test", "--ids", "sk-1")
        unclassified = out.split("### Pack runs, accounts not classified")[1].split("### Runs of a foreign skill")[0]
        self.assertIn("run-a", unclassified)
        self.assertNotIn("run-a", out.split("### Pack runs, accounts not classified")[0])

    def test_cells_cannot_break_the_table_or_carry_forbidden_characters(self) -> None:
        run = pack_run("run-a", "2026-11-01T09:00:00Z", label="a | b—c–d! e\nf")
        opener = self.pages([run], [])
        _, out, _ = self.call(opener, "audit", "--org", "claude-billing-test", "--ids", "sk-1", "--build-accounts", "user:builder")
        row = next(line for line in out.splitlines() if line.startswith("| run-a"))
        self.assertEqual(row.count(" | "), 6)
        for char in ("—", "–", "!"):
            self.assertNotIn(char, out)

    def test_a_repeated_cursor_stops_the_loop(self) -> None:
        base = f"{BASE}/o1/eval-runs?suite_id=infra-ops-40"
        loop = json.dumps({"runs": [], "cursor": "same"}).encode()
        opener = FakeOpener({base: loop, f"{base}&cursor=same": loop})
        code, _, err = self.call(opener, "audit", "--org", "o1", "--ids", "sk-1")
        self.assertEqual(code, 1)
        self.assertIn("repeats a cursor", err)

    def test_a_page_without_runs_is_an_error(self) -> None:
        opener = FakeOpener({f"{BASE}/o1/eval-runs?suite_id=infra-ops-40": b"{}"})
        self.assertEqual(self.call(opener, "audit", "--org", "o1", "--ids", "sk-1")[0], 1)

    def test_audit_needs_the_variable_and_the_ids(self) -> None:
        self.assertEqual(self.call(FakeOpener({}), "audit", "--org", "o1", "--ids", "sk-1", env={})[0], 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.call(FakeOpener({}), "audit", "--org", "o1")


if __name__ == "__main__":
    unittest.main()
