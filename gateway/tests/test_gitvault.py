# SPDX-License-Identifier: AGPL-3.0-or-later
"""The vault-history invariants, written against the failure that actually happened.

Production ran the gateway container as root against vault directories owned
by uid 1000. Git refused every command with exit 128 ("detected dubious
ownership"), six of seven vaults ended up holding zero commits, and nothing
anywhere said so: `memory_write` returned "" where a snapshot id belonged and
`memory_history` returned [].

None of the 1260 tests caught it, because they all run as the same uid that
owns the files they create. These tests don't try to reproduce the ownership
mismatch -- that needs two uids and a container. They reproduce the *shape*:
a repository git will not operate on, and the guarantee that we now fail
loudly instead of returning a plausible-looking nothing.
"""

from __future__ import annotations

import subprocess

import pytest

from memaix_gateway import gitvault
from memaix_gateway.backends.memory_store import MemoryStore


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    MemoryStore._clear_instances()
    return v


def _break_repo(vault):
    """Make git refuse this repository the way production's did.

    Declaring a repository format git is too old to understand, rather than
    faking an owner: uid games need root and two accounts, and don't survive
    CI. What matters is reproducing the *shape* of "dubious ownership" --
    git bailing out at the repository level, before it looks at any data, so
    that even `rev-parse --git-dir` fails. Corrupting HEAD alone is a weaker
    imitation: the repository still opens, and the first draft of this test
    passed against code that would have stayed silent in production.
    """
    (vault / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 99\n")


# ------------------------------------------------------------------
# The invariant the docstring claimed for months while returning ""
# ------------------------------------------------------------------


def test_a_write_returns_a_hash_that_git_can_actually_resolve(vault):
    store = MemoryStore.for_vault(vault)
    commit = store.write("note.md", "hello", "jimmy")

    assert commit, "memory_write returned an empty snapshot id"
    # The point of handing back a hash is that revert() can be given it
    # later. A string that git cannot resolve is not a snapshot id, however
    # convincing it looks.
    resolved = subprocess.run(
        ["git", "-C", str(vault), "rev-parse", "--verify", f"{commit}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    assert resolved.returncode == 0, resolved.stderr


def test_every_write_produces_a_distinct_commit(vault):
    store = MemoryStore.for_vault(vault)
    first = store.write("note.md", "one", "jimmy")
    second = store.write("note.md", "two", "jimmy")
    assert first != second


def test_a_rewrite_with_identical_content_still_yields_a_usable_hash(vault):
    """Writing the same bytes twice stages nothing, and `git commit` exits 1.

    That is the one non-zero exit that must not raise -- it is a no-op, not
    a fault. The caller still gets the hash their note currently lives at.
    """
    store = MemoryStore.for_vault(vault)
    first = store.write("note.md", "same", "jimmy")
    second = store.write("note.md", "same", "jimmy")
    assert second == first


# ------------------------------------------------------------------
# Loudness: the failures that used to be silent
# ------------------------------------------------------------------


def test_a_broken_repository_raises_on_write_instead_of_returning_nothing(vault):
    store = MemoryStore.for_vault(vault)
    store.write("note.md", "before", "jimmy")
    _break_repo(vault)

    with pytest.raises(gitvault.GitError):
        store.write("note.md", "after", "jimmy")


def test_the_failure_carries_gits_own_words(vault):
    store = MemoryStore.for_vault(vault)
    store.write("note.md", "before", "jimmy")
    _break_repo(vault)

    with pytest.raises(gitvault.GitError) as excinfo:
        store.write("note.md", "after", "jimmy")
    # A log line saying "git failed" costs an afternoon. One quoting git
    # names the cause, which for the production outage was a single line
    # about ownership that nobody ever saw.
    assert str(vault) in str(excinfo.value)
    assert "git" in str(excinfo.value)


def test_history_raises_on_a_broken_repo_rather_than_reporting_none(vault):
    """The regression test for the actual production bug.

    `history()` used to end `if r.returncode != 0: return []`, which is the
    production failure mode written down as a fallback. An empty list is a
    truthful answer for an empty vault and a lie for a broken one.
    """
    store = MemoryStore.for_vault(vault)
    store.write("note.md", "content", "jimmy")
    assert store.history() != []

    _break_repo(vault)
    with pytest.raises(gitvault.GitError):
        store.history()


def test_an_empty_vault_still_reports_an_empty_history(vault):
    """The other half: silence must stay legal where it is honest."""
    MemoryStore.for_vault(vault)
    subprocess.run(["git", "-C", str(vault), "checkout", "--orphan", "blank"], capture_output=True)
    subprocess.run(["git", "-C", str(vault), "reset"], capture_output=True)
    store = MemoryStore.for_vault(vault)
    assert store.history() == []


# ------------------------------------------------------------------
# The trap that made production look healthy
# ------------------------------------------------------------------


def test_a_git_directory_that_git_will_not_use_is_not_a_repository(vault):
    """`.git` existing is what the old code checked, and it was never enough.

    `git init` creates the directory before there is any repository to
    distrust, so it succeeded as root; every command after it failed. All
    seven production vaults had a `.git`. Six had nothing in it.
    """
    (vault / ".git").mkdir()
    assert (vault / ".git").exists()
    assert not gitvault.is_repo(vault)


def test_opening_a_store_on_an_unusable_repo_fails_at_the_door(vault):
    subprocess.run(["git", "-C", str(vault), "init"], capture_output=True)
    _break_repo(vault)

    with pytest.raises(gitvault.GitError):
        MemoryStore.for_vault(vault)


def test_an_initialised_but_commitless_vault_gets_its_first_commit(vault):
    """The six vaults on the server are in exactly this state.

    They were `git init`-ed by the container and never committed to. The old
    `_ensure_git` returned early because `.git` existed, so its initial
    commit was reachable only by brand-new vaults -- the ones that didn't
    need rescuing.
    """
    subprocess.run(["git", "-C", str(vault), "init"], capture_output=True)
    assert not gitvault.has_commits(vault)

    MemoryStore.for_vault(vault)
    assert gitvault.has_commits(vault)


def test_commits_carry_an_identity_without_a_global_gitconfig(vault):
    """A container has no ~/.gitconfig, so `git commit` dies on "Author
    identity unknown". memory_store passed identity through the environment;
    pm and onboarding did not, which would have kept them broken after the
    ownership fix landed."""
    store = MemoryStore.for_vault(vault)
    commit = store.write("note.md", "hello", "jimmy")
    author = subprocess.run(
        ["git", "-C", str(vault), "log", "-1", "--format=%an <%ae>", commit],
        capture_output=True,
        text=True,
    )
    assert author.stdout.strip() == "memaix <memaix@localhost>"
