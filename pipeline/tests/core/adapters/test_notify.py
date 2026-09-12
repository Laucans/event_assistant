"""La notification de bureau : le seul signal qu'un humain absent recoit.

Rien ici n'appelle `osascript` — `subprocess` est remplace. Ce qui est teste,
c'est qu'elle se tait hors macOS, qu'elle nomme la boucle, et qu'un message ne
peut pas sortir de sa propre citation dans l'AppleScript.

`notify` a deux gardes : la plateforme, puis `shutil.which("osascript")`. Un
test qui veut atteindre l'appel doit donc remplacer les deux — sinon il passe
sur le Mac qui a `osascript` et se tait sur le Linux de la CI.
"""

import sys

from pipeline.core.adapters.shell import notify as notify_mod


def test_the_notification_is_a_macos_only_side_effect(monkeypatch):
    seen = []
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **kw: seen.append(a[0]))
    monkeypatch.setattr(sys, "platform", "linux")
    notify_mod.notify("un message")
    assert seen == []


def test_the_notification_names_the_loop(monkeypatch):
    seen = []
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **kw: seen.append(a[0]))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: "/usr/bin/" + name)
    notify_mod.notify("loop finished: 1 task(s) DONE")
    assert seen and seen[0][0] == "osascript"
    assert 'with title "agent-loop"' in seen[0][2]
    assert "loop finished: 1 task(s) DONE" in seen[0][2]


def test_a_notification_cannot_break_out_of_its_own_quoting(monkeypatch):
    """A quote in a task title would break the AppleScript."""
    seen = []
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **kw: seen.append(a[0]))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: "/usr/bin/" + name)
    notify_mod.notify('un "titre" cite ' + "x" * 400)
    script = seen[0][2]
    assert script.count('"') == 4          # les deux paires du script lui-meme
    assert len(script) < 300               # le corps est borne a 200


def test_an_absent_osascript_is_not_what_ends_a_run(monkeypatch):
    """Le shell faisait `command -v osascript || return 0`, puis `|| true`.

    Sans ca, une boucle lancee depuis cron avec un PATH minimal remplace le
    code de sortie documente par une FileNotFoundError — et ce, sur les
    quatre chemins qui notifient, y compris l'arret propre.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: None)

    def boom(*a, **kw):
        raise AssertionError("osascript ne doit meme pas etre tente")

    monkeypatch.setattr(notify_mod.subprocess, "run", boom)
    notify_mod.notify("la boucle est finie")     # ne leve pas


def test_a_failing_osascript_is_swallowed(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: "/usr/bin/" + name)

    def boom(*a, **kw):
        raise OSError("osascript a disparu entre le which et l'appel")

    monkeypatch.setattr(notify_mod.subprocess, "run", boom)
    notify_mod.notify("la boucle est finie")     # ne leve pas
