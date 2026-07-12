"""Clone/pull of an AgentSkill's repository into the shared skill store.

Runs as a background job rather than inside the request that triggers it: a
clone is a network round trip against an arbitrary repository, and neither
registering a skill nor pulling one should hold an HTTP request open for it.
Both routes therefore mark the skill ``pending`` and hand off to
:func:`sync_agent_skill`, which records the outcome on the row for the admin UI
to poll.

Because the job outlives the request, it cannot borrow the request-scoped
database session (FastAPI closes that when the response is sent), so it opens
its own and composes the same collaborators ``dependencies/service.py`` would.
"""

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.database import engine
from infrastructure.locks import LockNotAcquiredError, advisory_lock, skill_sync_key
from infrastructure.secret_cipher import get_secret_cipher
from infrastructure.secret_resolver import SecretResolver
from infrastructure.skill_manager import SkillManager, get_skill_manager
from infrastructure.vault_client import get_vault_client
from models.agent_skill import SkillSyncStatus
from repositories import (
    AgentSkillRepository,
    SqlAgentSkillRepository,
    SqlSecretRepository,
    SqlWorkflowSessionRepository,
    WorkflowSessionRepository,
)
from repositories.exceptions import (
    NotFoundError,
)

logger = logging.getLogger(__name__)

#: Basic-auth username used for a skill clone when the skill names an auth
#: secret but no explicit ``repo_auth_username``. Works for GitHub PATs, where
#: the username is ignored as long as the token is the password.
_DEFAULT_GIT_USERNAME = "x-access-token"

#: How long the job waits for the skill's sync lock. Kept at zero: if another
#: replica is already cloning this skill, that clone will publish the same
#: revision this one would, so queueing behind it is pure duplicate work.
_LOCK_WAIT_SECONDS = 0.0


class AgentSkillSyncService:
    """Publishes a skill's repository into the shared store and records the outcome."""

    def __init__(
        self,
        skills: AgentSkillRepository,
        sessions: WorkflowSessionRepository,
        resolver: SecretResolver,
        skill_manager: SkillManager,
    ) -> None:
        """Initialize the service.

        Args:
            skills: Repository providing AgentSkill persistence.
            sessions: Repository used to find which revisions workflow sessions
                still pin, so a prune does not delete code a session needs.
            resolver: Resolver turning a skill's ``repo_auth_secret`` into the
                clone credential.
            skill_manager: Store that publishes and prunes revision directories.
        """
        self._skills = skills
        self._sessions = sessions
        self._resolver = resolver
        self._skill_manager = skill_manager

    async def sync(self, skill_id: str, *, user_id: str) -> None:
        """Clone the skill's repository at HEAD, publish it, and prune stale revisions.

        Never raises for an unreachable or broken repository: the failure is the
        result the admin UI is waiting for, so it is recorded on the row
        (``sync_status=failed`` plus the reason) rather than surfaced as an
        exception nobody is left to catch. The skill's ``commit_sha`` is left
        alone on failure, so a skill that was already usable stays usable at its
        previous revision.

        A skill whose clone is already in flight on another replica is skipped
        outright: that clone publishes the same revision this one would, and
        touching the row would only race its status writes.

        Args:
            skill_id: Identifier of the skill to sync.
            user_id: ID of the user whose action triggered the sync, recorded as
                the row's ``updated_by``.

        Raises:
            NotFoundError: If no skill exists with the given ID.
        """
        skill = await self._skills.get(skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", skill_id)

        try:
            async with advisory_lock(
                skill_sync_key(skill_id), wait_seconds=_LOCK_WAIT_SECONDS
            ):
                auth: tuple[str, str] | None = None
                if skill.repo_auth_secret is not None:
                    token = await self._resolver.resolve_value(skill.repo_auth_secret)
                    auth = (skill.repo_auth_username or _DEFAULT_GIT_USERNAME, token)

                commit_sha = await self._skill_manager.clone(skill, auth=auth)
                await self._skills.set_sync_state(
                    skill_id,
                    status=SkillSyncStatus.ready,
                    commit_sha=commit_sha,
                    user_id=user_id,
                )
                pinned = await self._sessions.commit_shas_for_skill(skill_id)
                await self._skill_manager.prune(skill_id, pinned | {commit_sha})
        except LockNotAcquiredError:
            logger.info(
                "Skipping sync of skill %s: another replica is already syncing it.",
                skill_id,
            )
        except Exception as exc:
            # Deliberately broad, and the reason is the ``pending`` state itself:
            # it is the admin UI's "still cloning" spinner, and only this handler
            # ever clears it. An exception that slips past leaves the skill
            # spinning forever with no error to show, so every failure -- the
            # expected SkillCloneError and SecretResolutionError, and anything
            # unforeseen -- has to land on the row.
            logger.warning("Sync of skill %s failed: %s", skill_id, exc, exc_info=True)
            await self._skills.set_sync_state(
                skill_id,
                status=SkillSyncStatus.failed,
                error=str(exc),
                user_id=user_id,
            )


async def sync_agent_skill(skill_id: str, *, user_id: str) -> None:
    """Run :meth:`AgentSkillSyncService.sync` on a database session of its own.

    The entry point routers hand to ``BackgroundTasks``. Swallows every error:
    nothing downstream is listening, and :meth:`AgentSkillSyncService.sync` has
    already recorded the ones the admin needs to see on the skill row.

    Args:
        skill_id: Identifier of the skill to sync.
        user_id: ID of the user whose action triggered the sync.
    """
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            secrets = SqlSecretRepository(db)
            service = AgentSkillSyncService(
                skills=SqlAgentSkillRepository(db),
                sessions=SqlWorkflowSessionRepository(db),
                resolver=SecretResolver(
                    secrets, get_secret_cipher(), get_vault_client()
                ),
                skill_manager=get_skill_manager(),
            )
            await service.sync(skill_id, user_id=user_id)
    except Exception:
        logger.exception("Background sync of skill %s crashed.", skill_id)
