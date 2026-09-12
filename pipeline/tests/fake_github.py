"""GitHub, sur papier : un depot d'issues en memoire derriere `gh`.

Le double que `GitHub(run=...)` existe pour permettre. Il ne simule pas `gh`
en general — il implemente exactement les points d'entree que
`adapters.shell.github` appelle, et refuse le reste bruyamment : un appel que
ce fichier ne connait pas est un appel que personne n'a decrit, et le laisser
rendre `{}` ferait passer un test qui ne prouve rien.

Modele sur le `FakeGh` de `tests/workflows/test_review.py`, qui fait la meme
chose pour la revue de PR.

Les identifiants internes (`id`) ne sont pas les numeros : l'API des
sous-issues et des dependances prend `sub_issue_id` / `issue_id`, et une
implementation qui confondrait les deux passerait ici si le double les
confondait aussi. Ils sont donc distincts (`id = 1000 + numero`).
"""

from __future__ import annotations

import json
import subprocess

from pipeline.workflows.agentic_dev_loop.internals.tasks import LABELS

REPO = "o/r"


class Unknown(AssertionError):
    """Un appel `gh` que ce double ne decrit pas."""


class FakeGitHub:
    """Les issues, leurs liens, et ce qu'on a demande a `gh`."""

    def __init__(self, repo: str = REPO, labels=LABELS) -> None:
        self.repo = repo
        self.repo_code = 0
        self.repo_labels = list(labels)
        self.issues: dict[int, dict] = {}
        self.pulls: list[dict] = []
        self.subs: dict[int, list[int]] = {}
        self.blocked: dict[int, list[int]] = {}
        self.calls: list[tuple] = []
        # Le chemin d'API qui doit echouer : c'est ainsi qu'on exerce la
        # lecture degradee, celle qui ne doit surtout pas se lire « rien a
        # faire ». `refuses_writes` fait l'autre moitie : lire marche,
        # ecrire non — l'etat dans lequel une migration s'arrete en plein
        # milieu.
        self.fails_on: str = ""
        self.refuses_writes = False
        # `gh auth status` : la porte commune la lit avant tout le reste.
        self.authed = True
        self._next = 1

    # -- ce que le test met dedans -----------------------------------------

    def add(self, title: str, *labels: str, body: str = "", state: str = "open",
            number: int | None = None) -> int:
        number = number if number is not None else self._next
        self._next = max(self._next, number) + 1
        self.issues[number] = {
            "number": number, "id": 1000 + number, "title": title,
            "state": state, "body": body,
            "labels": [{"name": l} for l in labels]}
        return number

    def add_pr(self, title: str, body: str = "", base: str = "main_agent",
               merged: bool = True, number: int | None = None) -> int:
        """Une PR sur papier. `merged_at` est ce qui distingue livre de ferme."""
        number = number if number is not None else self._next
        self._next = max(self._next, number) + 1
        self.pulls.append({
            "number": number, "title": title, "body": body,
            "state": "closed", "base": {"ref": base},
            "merged_at": "2026-09-10T12:00:00Z" if merged else None})
        return number

    def link(self, parent: int, child: int) -> None:
        self.subs.setdefault(parent, []).append(child)

    def block(self, number: int, blocker: int) -> None:
        self.blocked.setdefault(number, []).append(blocker)

    def close(self, number: int) -> None:
        self.issues[number]["state"] = "closed"

    def labels_of(self, number: int) -> list[str]:
        return [l["name"] for l in self.issues[number]["labels"]]

    def body_of(self, number: int) -> str:
        return self.issues[number]["body"]

    def wrote(self) -> list[tuple]:
        """Chaque appel qui n'etait pas une lecture — ce qu'un dry-run interdit."""
        return [c for c in self.calls
                if "-X" in c and c[c.index("-X") + 1] != "GET"]

    # -- ce que `gh` recoit -------------------------------------------------

    def __call__(self, *args: str, check: bool = True):
        self.calls.append(args)
        if args[:2] == ("auth", "status"):
            return subprocess.CompletedProcess(
                args, 0 if self.authed else 1, "",
                "" if self.authed else "gh: not logged in")
        if args[:2] == ("repo", "view"):
            return subprocess.CompletedProcess(
                args, self.repo_code, "" if self.repo_code else self.repo + "\n",
                "gh: no repository" if self.repo_code else "")
        if args[0] != "api":
            raise Unknown(f"le double ne connait pas `gh {' '.join(args)}`")
        method, path, fields = _parse(args[1:])
        if self.refuses_writes and method != "GET":
            return subprocess.CompletedProcess(
                args, 1, "", f"gh: HTTP 403 on {method} {path}")
        if self.fails_on and self.fails_on in path:
            return subprocess.CompletedProcess(
                args, 1, "", f"gh: HTTP 401 on {path}")
        try:
            payload = self._route(method, path, fields)
        except KeyError as exc:
            return subprocess.CompletedProcess(
                args, 1, "", f"gh: HTTP 404 — no issue {exc}")
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    def _route(self, method: str, path: str, fields: dict):
        rest = path[len(f"repos/{self.repo}/"):]
        parts = rest.split("/")
        if parts == ["labels"]:
            return [{"name": n} for n in self.repo_labels]
        if parts == ["pulls"] and method == "GET":
            base = fields.get("base")
            return [p for p in self.pulls
                    if base is None or p["base"]["ref"] == base]
        if parts == ["issues"] and method == "GET":
            return [i for i in self.issues.values()
                    if fields.get("labels", "") in
                    [l["name"] for l in i["labels"]]
                    and i["state"] == fields.get("state", i["state"])]
        if parts == ["issues"] and method == "POST":
            number = self.add(fields.get("title", ""),
                              *fields.get("labels[]", []),
                              body=fields.get("body", ""))
            return self.issues[number]
        number = int(parts[1])
        issue = self.issues[number]        # KeyError -> 404, comme GitHub
        tail = parts[2:]
        if not tail:
            if method == "PATCH":
                for name in ("body", "title", "state"):
                    if name in fields:
                        issue[name] = fields[name]
            return issue
        if tail == ["sub_issues"]:
            if method == "POST":
                self.link(number, self._by_id(int(fields["sub_issue_id"])))
                return issue
            return [self.issues[n] for n in self.subs.get(number, [])]
        if tail == ["dependencies", "blocked_by"]:
            if method == "POST":
                self.block(number, self._by_id(int(fields["issue_id"])))
                return issue
            return [self.issues[n] for n in self.blocked.get(number, [])]
        if tail == ["dependencies", "blocking"]:
            return [self.issues[n] for n, blockers in self.blocked.items()
                    if number in blockers]
        if tail[0] == "labels":
            if method == "POST":
                for name in fields.get("labels[]", []):
                    if name not in self.labels_of(number):
                        issue["labels"].append({"name": name})
            elif method == "DELETE":
                issue["labels"] = [l for l in issue["labels"]
                                   if l["name"] != tail[1]]
            return issue["labels"]
        raise Unknown(f"le double ne connait pas `gh api -X {method} {path}`")

    def _by_id(self, internal: int) -> int:
        for number, issue in self.issues.items():
            if issue["id"] == internal:
                return number
        raise Unknown(f"aucune issue ne porte l'id interne {internal}")


def _parse(args: tuple[str, ...]) -> tuple[str, str, dict]:
    """`(methode, chemin, champs)` d'un `gh api ...`.

    Les repetitions de `labels[]=` s'accumulent en liste : c'est ainsi que
    `gh` envoie un tableau, et l'adaptateur en depend.
    """
    method, path, fields = "GET", "", {}
    rest = list(args)
    while rest:
        token = rest.pop(0)
        if token == "-X":
            method = rest.pop(0)
        elif token in ("-f", "-F"):
            name, _, value = rest.pop(0).partition("=")
            if name.endswith("[]"):
                fields.setdefault(name, []).append(value)
            else:
                fields[name] = value
        elif token in ("-q", "--jq"):
            rest.pop(0)
        elif not token.startswith("-"):
            path = token
    return method, path, fields
