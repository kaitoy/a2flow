"""Git-backed store of Agent Skill repositories, laid out one directory per revision.

The store lives under ``Settings.skills_dir`` and is shared by every replica::

    <skills_dir>/
      <skill_id>/
        .tmp-<uuid>/   # a clone in progress
        <commit_sha>/  # an immutable, complete revision

A clone lands in ``.tmp-<uuid>/`` and is published with a single
:func:`os.replace` onto ``<commit_sha>/``. The rename is atomic within the
filesystem, so a replica reading the store never observes a half-written
revision — which the previous "clone straight into the target, and treat the
directory existing as proof it is complete" approach could not promise.

Once published, a revision directory is never modified. That is what lets
readers skip locking entirely: a ``pull`` only ever *adds* a sibling directory,
so an agent loading revision A cannot be disturbed by a pull publishing
revision B. Only the writers contend, and they serialize on the cross-process
advisory lock (``infrastructure/locks.py``) taken by the caller.
"""

import asyncio
import logging
import os
import shutil
import time
import uuid
from functools import lru_cache
from pathlib import Path

import urllib3
from dulwich import porcelain
from dulwich.client import AuthCallbackPoolManager, default_urllib3_manager

from config import get_settings
from infrastructure.url_safety import assert_public_http_url
from models.agent_skill import AgentSkill
from repositories.exceptions import SkillCloneError

logger = logging.getLogger(__name__)

#: Prefix of the working directory a clone is staged in before it is published.
#: Chosen so it can never collide with a revision directory, whose name is
#: always a 40-character hex sha.
_TMP_PREFIX = ".tmp-"

#: Characters of randomness in a staging directory's name. Only has to separate
#: a staging directory from one another writer's, and writers for a skill are
#: already serialized by the sync advisory lock, so this guards little more than
#: a directory a crashed process left behind. Kept short deliberately: every
#: character here lands in the path of every file dulwich writes during the
#: clone, and on Windows a long one pushes deep paths (``.git/objects/pack/
#: pack-<40 hex>.pack``) past the 260-character MAX_PATH limit.
_STAGING_SUFFIX_LENGTH = 8

#: Length of a hex-encoded Git commit sha, used to tell revision directories
#: apart from staging directories when scanning a skill's directory.
_SHA_LENGTH = 40


def _build_no_redirect_pool_manager(
    base_url: str,
) -> urllib3.PoolManager | urllib3.ProxyManager | AuthCallbackPoolManager:
    """Build the urllib3 pool manager dulwich uses for one clone, redirects disabled.

    Mirrors dulwich's own default construction (``default_urllib3_manager``,
    which honours proxy environment variables and TLS verification) but
    replaces its retry policy so a 3xx response is returned as-is instead of
    being followed. ``AbstractHttpGitClient`` treats any non-200 response as a
    ``GitProtocolError``, so a redirect to an internal address surfaces as a
    clone failure instead of being silently fetched.

    Args:
        base_url: The repository URL being cloned (used for proxy-bypass detection).

    Returns:
        A urllib3 pool/proxy manager with redirect-following disabled.
    """
    manager = default_urllib3_manager(config=None, base_url=base_url)
    manager.connection_pool_kw["retries"] = urllib3.util.Retry(
        redirect=0, raise_on_redirect=False
    )
    return manager


def _is_revision_dir(path: Path) -> bool:
    """Return whether ``path`` is a published revision directory.

    A revision directory is named after its commit sha, which distinguishes it
    from the ``.tmp-*`` staging directories that share the same parent.
    """
    name = path.name
    return (
        path.is_dir()
        and len(name) == _SHA_LENGTH
        and all(c in "0123456789abcdef" for c in name)
    )


class SkillManager:
    """Publishes and prunes immutable revision directories of AgentSkill repositories."""

    def __init__(self, root: Path, prune_grace_seconds: int) -> None:
        """Initialize the manager.

        Args:
            root: Root of the skill store (``Settings.skills_dir``). In a
                horizontally scaled deployment this must be a volume shared by
                every replica.
            prune_grace_seconds: How long a revision directory is kept from
                pruning regardless of whether anything references it. See
                :meth:`prune`.
        """
        self._root = root
        self._prune_grace_seconds = prune_grace_seconds

    def version_dir(self, skill_id: str, commit_sha: str) -> Path:
        """Return the directory holding one published revision of a skill's repository."""
        return self._root / skill_id / commit_sha

    def skill_dir(self, skill: AgentSkill, commit_sha: str) -> Path:
        """Return the directory containing SKILL.md for one revision of a skill.

        That is the revision directory joined with the skill's ``repo_path``.

        Args:
            skill: The AgentSkill whose repository revision to locate.
            commit_sha: The published revision to resolve within.

        Returns:
            The path ADK loads the skill from.

        Raises:
            SkillCloneError: If ``skill.repo_path`` resolves outside the
                revision directory. Defense in depth: ``models.constraints
                .RepoPath`` already rejects ``..`` segments and absolute paths
                at the API boundary, but ``table=True`` SQLModel classes skip
                Pydantic validation, so a row written before that check existed
                (or constructed directly rather than through the API) could
                otherwise still reach here.
        """
        version = self.version_dir(skill.id, commit_sha).resolve()
        skill_dir = (
            (version / skill.repo_path).resolve() if skill.repo_path else version
        )
        if not skill_dir.is_relative_to(version):
            raise SkillCloneError(
                skill.id,
                f"repo_path {skill.repo_path!r} escapes the revision directory",
            )
        return skill_dir

    async def clone(
        self, skill: AgentSkill, auth: tuple[str, str] | None = None
    ) -> str:
        """Clone the skill's repository at HEAD and publish it as a revision directory.

        Idempotent: when the remote HEAD is a revision this store already
        published, the freshly cloned copy is discarded and the existing
        directory is left untouched. That is what keeps published revisions
        immutable, and it also means :func:`os.replace` below never has to
        rename onto a non-empty directory (which POSIX rejects and Windows
        rejects outright), so the publish works on both platforms.

        The caller is expected to hold the skill's sync advisory lock
        (``infrastructure.locks.skill_sync_key``); this method does not take it.

        Args:
            skill: The AgentSkill whose repository to clone.
            auth: Optional ``(username, password)`` pair sent as HTTP basic
                auth with the clone, for private repositories.

        Returns:
            The hex commit sha of the published revision.

        Raises:
            SkillCloneError: If the URL is unsafe, the clone fails, or the
                resolved skill directory does not exist in the cloned tree.
        """
        skill_root = self._root / skill.id
        suffix = uuid.uuid4().hex[:_STAGING_SUFFIX_LENGTH]
        staging = skill_root / f"{_TMP_PREFIX}{suffix}"
        repo_url = skill.repo_url

        def _do_clone() -> str:
            pool_manager = _build_no_redirect_pool_manager(repo_url)
            kwargs = {} if auth is None else {"username": auth[0], "password": auth[1]}
            repo = porcelain.clone(
                repo_url,
                str(staging),
                depth=1,
                pool_manager=pool_manager,  # type: ignore[arg-type]
                **kwargs,  # type: ignore[arg-type]
            )
            try:
                return repo.head().decode()
            finally:
                repo.close()

        try:
            skill_root.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(assert_public_http_url, repo_url)
            # porcelain.clone is synchronous; run it in a worker thread so the
            # event loop is not blocked while pack data is fetched.
            commit_sha = await asyncio.to_thread(_do_clone)
            self._assert_skill_dir_present(skill, staging)
            await asyncio.to_thread(self._publish, staging, skill_root / commit_sha)
            return commit_sha
        except SkillCloneError:
            raise
        except Exception as exc:
            # Deliberately broad. Cloning an arbitrary remote repository with a
            # third-party client fails in more ways than can be enumerated —
            # dulwich raises a bare ``Exception`` subclass for an HTTP 401, which
            # is what GitHub answers for a repository that does not exist or that
            # the caller cannot see, i.e. the single most common real failure
            # (wrong URL, private repo, revoked token). Letting any of them
            # escape un-wrapped strands the skill: the caller records the failure
            # by catching SkillCloneError, so anything else leaves the row
            # ``pending`` forever.
            raise SkillCloneError(
                skill.id, f"clone of {repo_url} failed: {exc}"
            ) from exc
        finally:
            if staging.exists():
                await asyncio.to_thread(shutil.rmtree, staging, True)

    def _assert_skill_dir_present(self, skill: AgentSkill, staging: Path) -> None:
        """Raise unless the cloned tree actually contains the skill's ``repo_path``.

        Checked before publishing so a repository whose ``repo_path`` is wrong
        is reported as a clone failure rather than published as a revision that
        every later agent load would choke on.
        """
        staged_root = staging.resolve()
        skill_dir = (
            (staging / skill.repo_path).resolve() if skill.repo_path else staged_root
        )
        if not skill_dir.is_relative_to(staged_root):
            raise SkillCloneError(
                skill.id,
                f"repo_path {skill.repo_path!r} escapes the revision directory",
            )
        if not skill_dir.exists():
            raise SkillCloneError(
                skill.id,
                f"repo_path {skill.repo_path!r} not found in the cloned repository",
            )

    def _publish(self, staging: Path, target: Path) -> None:
        """Move a staged clone into place as an immutable revision directory."""
        if target.exists():
            # The remote HEAD is a revision we already published. Keep the
            # existing directory (the `finally` in `clone` drops the staging
            # copy) rather than replacing an immutable directory in place.
            return
        os.replace(staging, target)

    async def prune(self, skill_id: str, keep: set[str]) -> None:
        """Delete a skill's revision directories that nothing references any more.

        A revision survives when it is named in ``keep`` — the skill's current
        revision plus every revision a WorkflowSession pinned — or when it was
        published within the grace window. The grace window covers the gap
        between a workflow run reading the skill's current ``commit_sha`` and
        inserting the WorkflowSession row that names it: without it, a pull
        landing inside that gap could delete the revision the run just picked.

        Best effort: a directory that cannot be removed (e.g. still open on
        Windows) is logged and left in place, since failing the pull it follows
        would be worse than leaking a directory.

        Args:
            skill_id: The skill whose revision directories to scan.
            keep: Commit shas that must survive regardless of age.
        """
        skill_root = self._root / skill_id
        if not skill_root.is_dir():
            return
        cutoff = time.time() - self._prune_grace_seconds
        for entry in await asyncio.to_thread(lambda: list(skill_root.iterdir())):
            if not _is_revision_dir(entry) or entry.name in keep:
                continue
            if entry.stat().st_mtime > cutoff:
                continue
            try:
                await asyncio.to_thread(shutil.rmtree, entry)
            except OSError:
                logger.warning(
                    "Failed to prune skill revision %s of skill %s.",
                    entry.name,
                    skill_id,
                    exc_info=True,
                )


@lru_cache(maxsize=1)
def get_skill_manager() -> SkillManager:
    """Return the process-wide cached :class:`SkillManager` singleton.

    Lives here rather than in ``dependencies/singletons.py`` (which only
    re-exports it) so the background sync job can reach it without importing the
    dependency package, whose ``__init__`` pulls in the service layer that the
    job is itself part of.
    """
    settings = get_settings()
    return SkillManager(
        root=settings.skills_dir,
        prune_grace_seconds=settings.skills_prune_grace_seconds,
    )
