"""Startup registration and removal of the optional demo dataset.

Gated by ``Settings.demo_data`` (the ``DEMO_DATA`` environment variable),
this module keeps a small, self-contained example of everything two
approval-gated, mutating workflows need -- "launch an EC2 instance" and
"restart a GKE pod" -- all inside the seeded ``Default`` tenant (see
:mod:`infrastructure.bootstrap`):

* two Secrets -- one holding the AWS access key id and secret access key as
  two entries, and one holding a Google Cloud API key as a single entry, both
  described for the admin UI,
* two MCPServers -- one stdio server reaching the managed AWS MCP Server
  through the ``mcp-proxy-for-aws`` proxy launched with ``uvx``, referencing
  the AWS entries from its ``env`` via ``${secret:NAME/KEY}``, and one
  ``streamable_http`` server reaching the Google-managed GKE (Google
  Kubernetes Engine) remote MCP server, sending the Google Cloud API key as
  its ``x-goog-api-key`` header via the same ``${secret:NAME/KEY}``
  placeholder, both described,
* four MCPToolMocks that stub the demo run's side-effecting tools so a
  ``draft`` workflow run plays through without reaching AWS, a real GKE
  cluster, or waiting on a human -- ``call_aws`` and ``run_script`` on the AWS
  MCP server, each returning a successful EC2 launch, ``delete_k8s_resource``
  on the GKE MCP server, returning a successful pod deletion, and the
  built-in ``request_approval``, returning ``approved``,
* two AgentSkills pointing at ``sample_skills/aws-ec2-launch`` and
  ``sample_skills/gke-pod-restart`` in this repository,
* three Tags -- ``AWS`` (an **access-control** tag: visible, and its
  attachments usable, only to ``Demo AWS Group`` members and ``admin``/
  ``super_admin``; attached to the AWS secret, AWS MCP server, the
  EC2-launch agent skill, and the ``call_aws`` and ``run_script`` tool mocks,
  showing that one tag classifies across resource types), ``GCP`` (also
  access-control, gated the same way by ``Demo GCP Group``; attached to the
  Google Cloud secret, the GKE MCP server, and the pod-restart agent
  skill -- GKE is a Google Cloud product, so the same provider tag still
  applies), and ``Approval Required`` (a plain, non-gating tag attached to
  both agent skills, calling out their approval gate),
* six Users -- two managers, ``demo-approver-1`` and ``demo-approver-2``,
  either of whom the skill can ask for approval, an AWS pair
  (``demo-aws-developer``, ``demo-aws-requester``) who build and run the
  EC2-launch workflow, and a GCP pair (``demo-gcp-developer``,
  ``demo-gcp-requester``) who do the same for the GKE-pod-restart workflow --
  each holding **no direct role at all**,
* five UserGroups -- ``Demo Approvers``, ``Demo Requesters``, and
  ``Demo Developers`` each grant one role to their members, so every demo
  account gets its role purely by inheritance (``Demo Approvers`` and
  ``Demo Requesters`` each hold two accounts, showing that a group's
  membership need not be a single user). ``Demo AWS Group`` and
  ``Demo GCP Group`` grant no role at all -- they exist solely to hold the
  matching access-control tag, so their members (the AWS or GCP developer and
  requester, plus ``admin``) can see the AWS- or GCP-tagged records and
  everyone else cannot. That makes both the role-inheritance and the
  access-control side of the group feature visible in the demo dataset
  itself: remove a user from their role group and their access disappears on
  the next request; remove them from their AC group instead and the AWS/GCP
  records disappear from what they can see.

The Workflow itself is deliberately *not* seeded — these records are the
ingredients an operator assembles one into. Every tag stays unattached to any
workflow for the same reason; an operator is free to attach one once they
build one.

The flag is declarative in both directions: ``DEMO_DATA=true`` guarantees the
records exist, and leaving it unset (the default) guarantees they do not, so
turning the option off and restarting removes whatever a previous run
registered. Every record is identified by a fixed id constant rather than by
name, which makes both directions exact and idempotent no matter how the rows
were renamed in the admin UI in between -- and it cuts the other way too for
the handful of fields this module itself declares: an existing row (a demo
user seeded under an older username, a tag seeded before it became
access-control) is brought back in line with the current declaration on the
next startup, the same way a demo account's direct roles are stripped back
to none on every restart.

Rows are built as table models directly, not through the ``...Create``
validation models the API uses. That is deliberate: ``AgentSkillCreate``'s
``repo_url`` runs an SSRF check that resolves the host over DNS, which would
make application startup depend on working name resolution.
"""

import logging
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.bootstrap import DEFAULT_TENANT_NAME, resolve_seed_password
from infrastructure.password import hash_password
from infrastructure.secret_cipher import get_secret_cipher
from models.agent_skill import AgentSkill
from models.mcp_server import McpCommand, MCPServer, McpTransport
from models.mcp_tool_mock import REQUEST_APPROVAL_TOOL, MCPToolMock
from models.secret import Secret, SecretType
from models.tag import (
    AgentSkillTag,
    McpServerTag,
    McpToolMockTag,
    SecretTag,
    Tag,
    TagColor,
    TagLink,
    UserGroupTag,
)
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User
from models.user_group import UserGroup, UserGroupMember
from repositories.user import SqlUserRepository

logger = logging.getLogger(__name__)

#: Fixed identifier of the demo ``approver`` user (the manager the sample
#: skill requests approval from).
DEMO_APPROVER_USER_ID = "00000000-0000-0000-0000-00000000d001"

#: Fixed identifier of the demo AWS ``requester`` user (who runs the
#: EC2-launch workflow).
DEMO_AWS_REQUESTER_USER_ID = "00000000-0000-0000-0000-00000000d002"

#: Fixed identifier of the demo AWS ``developer`` user (who builds and
#: registers the EC2-launch workflow, MCP server, and agent skill).
DEMO_AWS_DEVELOPER_USER_ID = "00000000-0000-0000-0000-00000000d003"

#: Fixed identifier of the second demo ``approver`` user, showing that a
#: ``Demo Approvers`` membership need not be a single account.
DEMO_APPROVER_2_USER_ID = "00000000-0000-0000-0000-00000000d004"

#: Fixed identifier of the demo GCP ``requester`` user (who runs the
#: GKE-pod-restart workflow).
DEMO_GCP_REQUESTER_USER_ID = "00000000-0000-0000-0000-00000000d005"

#: Fixed identifier of the demo GCP ``developer`` user (who builds and
#: registers the GKE-pod-restart workflow, MCP server, and agent skill).
DEMO_GCP_DEVELOPER_USER_ID = "00000000-0000-0000-0000-00000000d006"

#: Fixed identifier of the demo ``Demo Approvers`` user group.
DEMO_APPROVERS_GROUP_ID = "00000000-0000-0000-0000-00000000d401"

#: Fixed identifier of the demo ``Demo Requesters`` user group.
DEMO_REQUESTERS_GROUP_ID = "00000000-0000-0000-0000-00000000d402"

#: Fixed identifier of the demo ``Demo Developers`` user group.
DEMO_DEVELOPERS_GROUP_ID = "00000000-0000-0000-0000-00000000d403"

#: Fixed identifier of the demo ``Demo AWS Group`` user group, which grants no
#: role and exists solely to hold the access-control ``AWS`` tag.
DEMO_AWS_GROUP_ID = "00000000-0000-0000-0000-00000000d404"

#: Fixed identifier of the demo ``Demo GCP Group`` user group, which grants no
#: role and exists solely to hold the access-control ``GCP`` tag.
DEMO_GCP_GROUP_ID = "00000000-0000-0000-0000-00000000d405"

#: Fixed identifier of the demo Secret holding the AWS credentials.
DEMO_AWS_SECRET_ID = "00000000-0000-0000-0000-00000000d101"

#: Fixed identifier of the demo Secret holding the Google Cloud API key.
DEMO_GCP_SECRET_ID = "00000000-0000-0000-0000-00000000d102"

#: Fixed identifier of the demo AWS MCP server.
DEMO_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d201"

#: Fixed identifier of the demo GKE MCP server.
DEMO_GKE_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d202"

#: Fixed identifier of the demo ``aws-ec2-launch`` agent skill.
DEMO_AGENT_SKILL_ID = "00000000-0000-0000-0000-00000000d301"

#: Fixed identifier of the demo ``gke-pod-restart`` agent skill.
DEMO_GKE_SKILL_ID = "00000000-0000-0000-0000-00000000d302"

#: Fixed identifier of the demo ``AWS`` tag.
DEMO_AWS_TAG_ID = "00000000-0000-0000-0000-00000000d501"

#: Fixed identifier of the demo ``Approval Required`` tag.
DEMO_APPROVAL_TAG_ID = "00000000-0000-0000-0000-00000000d502"

#: Fixed identifier of the demo ``GCP`` tag.
DEMO_GCP_TAG_ID = "00000000-0000-0000-0000-00000000d503"

#: Fixed identifier of the demo ``call_aws`` tool mock (AWS MCP server).
DEMO_CALL_AWS_MOCK_ID = "00000000-0000-0000-0000-00000000d601"

#: Fixed identifier of the demo ``run_script`` tool mock (AWS MCP server).
DEMO_RUN_SCRIPT_MOCK_ID = "00000000-0000-0000-0000-00000000d602"

#: Fixed identifier of the demo ``request_approval`` built-in tool mock.
DEMO_REQUEST_APPROVAL_MOCK_ID = "00000000-0000-0000-0000-00000000d603"

#: Fixed identifier of the demo ``delete_k8s_resource`` tool mock (GKE MCP server).
DEMO_DELETE_POD_MOCK_ID = "00000000-0000-0000-0000-00000000d604"

#: Name of the demo tag shared by the secret, MCP server, and agent skill.
DEMO_AWS_TAG_NAME = "AWS"

#: Name of the demo tag shared by the Google Cloud secret and MCP server.
DEMO_GCP_TAG_NAME = "GCP"

#: Name of the demo tag attached only to the agent skill.
DEMO_APPROVAL_TAG_NAME = "Approval Required"

#: Name of the demo Secret holding both AWS credentials. Its two entries are
#: embedded in the demo MCP server's ``env`` as ``${secret:NAME/KEY}``
#: placeholders.
DEMO_AWS_SECRET_NAME = "demo-aws-credentials"

#: Entry key of the AWS access key id within :data:`DEMO_AWS_SECRET_NAME`.
DEMO_ACCESS_KEY_ENTRY_KEY = "AWS_ACCESS_KEY_ID"

#: Entry key of the AWS secret access key within :data:`DEMO_AWS_SECRET_NAME`.
DEMO_SECRET_KEY_ENTRY_KEY = "AWS_SECRET_ACCESS_KEY"

#: Name of the demo Secret holding the Google Cloud API key. Its single entry
#: is embedded in the demo GKE MCP server's ``headers`` as a
#: ``${secret:NAME/KEY}`` placeholder.
DEMO_GCP_SECRET_NAME = "demo-gcp-credentials"

#: Entry key of the Google Cloud API key within :data:`DEMO_GCP_SECRET_NAME`.
DEMO_GCP_API_KEY_ENTRY_KEY = "GOOGLE_API_KEY"

#: Name of the demo MCP server as shown in the admin UI.
DEMO_MCP_SERVER_NAME = "AWS MCP Server"

#: Name of the demo GKE MCP server as shown in the admin UI.
DEMO_GKE_MCP_SERVER_NAME = "GKE MCP Server"

#: Name of the demo agent skill as shown in the admin UI.
DEMO_AGENT_SKILL_NAME = "Demo AWS EC2 Launch"

#: Name of the demo GKE pod-restart agent skill in the admin UI.
DEMO_GKE_SKILL_NAME = "Demo GKE Pod Restart"

#: Name of the demo ``call_aws`` tool mock as shown in the admin UI.
DEMO_CALL_AWS_MOCK_NAME = "Demo AWS call_aws (EC2 launch success)"

#: Name of the demo ``run_script`` tool mock as shown in the admin UI.
DEMO_RUN_SCRIPT_MOCK_NAME = "Demo AWS run_script (EC2 launch success)"

#: Name of the demo ``request_approval`` tool mock as shown in the admin UI.
DEMO_REQUEST_APPROVAL_MOCK_NAME = "Demo request_approval (always approved)"

#: Name of the demo ``delete_k8s_resource`` tool mock as shown in the admin UI.
DEMO_DELETE_POD_MOCK_NAME = "Demo GKE delete_k8s_resource (pod restart success)"

#: Proxy package the demo MCP server is launched from. Pinned to an exact
#: version rather than ``@latest``, which is what the upstream migration guide
#: recommends.
_DEMO_MCP_PROXY_PACKAGE = "mcp-proxy-for-aws@1.6.4"

#: Managed AWS MCP Server endpoint the proxy forwards SigV4-signed requests to.
#: It replaces the deprecated self-hosted ``awslabs.aws-api-mcp-server``.
_DEMO_MCP_ENDPOINT = "https://aws-mcp.us-east-1.api.aws/mcp"

#: Region :data:`_DEMO_MCP_ENDPOINT` lives in, and therefore the region the
#: proxy must sign for. Deliberately independent of ``DEMO_AWS_REGION``, which
#: selects the region the *tools* operate on: the proxy does not derive the
#: signing region from the endpoint URL, it falls back to ``AWS_REGION``, so
#: leaving it implicit would break signing as soon as the two differ.
_DEMO_MCP_ENDPOINT_REGION = "us-east-1"

#: Google-managed GKE (Google Kubernetes Engine) remote MCP endpoint the demo
#: ``streamable_http`` server connects to -- the full endpoint, not the
#: read-only or delete-only variants, so it also exposes mutating tools such
#: as ``delete_k8s_resource``.
_DEMO_GKE_MCP_ENDPOINT = "https://container.googleapis.com/mcp"

#: Request header the demo GKE MCP server sends its Google Cloud API key in.
#: Its value is a ``${secret:NAME/KEY}`` placeholder resolved at connection
#: time, so the key never lands in the ``mcp_servers`` row.
_DEMO_GCP_API_KEY_HEADER = "x-goog-api-key"

#: Repository the demo agent skills are cloned from, and the path within it to
#: each one's ``SKILL.md``.
_DEMO_SKILL_REPO_URL = "https://github.com/kaitoy/a2flow"
_DEMO_AWS_SKILL_REPO_PATH = "sample_skills/aws-ec2-launch"
_DEMO_GKE_SKILL_REPO_PATH = "sample_skills/gke-pod-restart"

#: Stored in place of an AWS credential or Google Cloud API key when the
#: matching ``DEMO_*`` variable is unset. The demo is then complete in shape but
#: cannot reach the provider until an operator edits the secret in the admin UI.
_PLACEHOLDER_SECRET_VALUE = "REPLACE_ME"

#: Description shown on the demo AWS secret in the admin UI.
_DEMO_AWS_SECRET_DESCRIPTION = (
    "AWS access key and secret key used by the demo MCP server to sign "
    "requests to the managed AWS MCP endpoint."
)

#: Description shown on the demo Google Cloud secret in the admin UI.
_DEMO_GCP_SECRET_DESCRIPTION = (
    "Google Cloud API key the demo GKE MCP server sends as its x-goog-api-key header."
)

#: Description shown on the demo MCP server in the admin UI.
_DEMO_MCP_SERVER_DESCRIPTION = (
    "Managed AWS MCP Server reached through the mcp-proxy-for-aws bridge, "
    "providing tools to launch and manage AWS resources such as EC2 "
    "instances."
)

#: Description shown on the demo GKE MCP server in the admin UI.
_DEMO_GKE_MCP_SERVER_DESCRIPTION = (
    "Google-managed GKE (Google Kubernetes Engine) remote MCP server, "
    "providing tools to manage GKE clusters and their Kubernetes resources -- "
    "including mutating tools such as deleting a pod."
)

#: Description shown on the demo ``AWS`` tag in the admin UI.
_DEMO_AWS_TAG_DESCRIPTION = (
    "Resources that talk to AWS: credentials, MCP servers, and agent skills "
    "scoped to the AWS provider."
)

#: Description shown on the demo ``GCP`` tag in the admin UI.
_DEMO_GCP_TAG_DESCRIPTION = (
    "Resources that talk to Google Cloud: credentials, MCP servers, and agent "
    "skills scoped to the GCP provider."
)

#: Description shown on the demo ``Approval Required`` tag in the admin UI.
_DEMO_APPROVAL_TAG_DESCRIPTION = (
    "Marks an agent skill whose workflow must pause for a manager's approval "
    "before it proceeds."
)

_RowT = TypeVar("_RowT", bound=SQLModel)


@dataclass(frozen=True)
class _DemoUserSpec:
    """The fixed identity of one demo user, minus its password.

    Carries no role: every demo account is granted its role through the
    matching :class:`_DemoGroupSpec` instead.

    Attributes:
        id: Fixed primary key, so the user can be found again for removal.
        username: Login name, unique within the ``Default`` tenant.
        first_name: Given name shown in the UI.
        last_name: Family name shown in the UI.
    """

    id: str
    username: str
    first_name: str
    last_name: str


@dataclass(frozen=True)
class _DemoGroupSpec:
    """One demo user group: at most one role granted to one or more members.

    Attributes:
        id: Fixed primary key, so the group can be found again for removal.
        name: Group name shown in the admin UI, unique within the tenant.
        description: Sentence shown on the group list and detail pages.
        role: The one role this group grants to its members, or ``None`` for
            a group that grants no role at all -- used for a group whose only
            purpose is to hold an access-control tag (see
            :data:`DEMO_AWS_GROUP_ID` / :data:`DEMO_GCP_GROUP_ID`).
        member_ids: Ids of the demo users placed in the group.
    """

    id: str
    name: str
    description: str
    role: Role | None
    member_ids: tuple[str, ...]


#: The demo accounts, in creation order. Each is created with an empty
#: ``roles`` list and gets its role, and separately its access-control tag,
#: from whichever entries of :data:`_DEMO_GROUPS` list it among their members.
_DEMO_USERS = (
    _DemoUserSpec(
        id=DEMO_APPROVER_USER_ID,
        username="demo-approver-1",
        first_name="Alice",
        last_name="Anderson",
    ),
    _DemoUserSpec(
        id=DEMO_AWS_REQUESTER_USER_ID,
        username="demo-aws-requester",
        first_name="Bob",
        last_name="Martinez",
    ),
    _DemoUserSpec(
        id=DEMO_AWS_DEVELOPER_USER_ID,
        username="demo-aws-developer",
        first_name="Carol",
        last_name="Bennett",
    ),
    _DemoUserSpec(
        id=DEMO_APPROVER_2_USER_ID,
        username="demo-approver-2",
        first_name="Diana",
        last_name="Foster",
    ),
    _DemoUserSpec(
        id=DEMO_GCP_REQUESTER_USER_ID,
        username="demo-gcp-requester",
        first_name="Ethan",
        last_name="Cole",
    ),
    _DemoUserSpec(
        id=DEMO_GCP_DEVELOPER_USER_ID,
        username="demo-gcp-developer",
        first_name="Fiona",
        last_name="Grant",
    ),
)

#: The demo user groups. ``Demo Approvers``, ``Demo Requesters``, and
#: ``Demo Developers`` each grant one role to their members -- the sample
#: skill looks for a user holding ``approver`` to route its approval request
#: to; ``requester`` is the role that may execute a workflow; ``developer`` is
#: the role that may build and register a workflow, MCP server, or agent
#: skill. Granting each through a group rather than directly is what makes
#: the demo exercise role inheritance; all three hold two members, showing
#: that a group's role reaches every one of its members, not just a single
#: account.
#:
#: ``Demo AWS Group`` and ``Demo GCP Group`` grant no role at all (``role=
#: None``) -- their only purpose is to hold the matching access-control tag
#: (see :func:`_seed_demo_tags`), so their members, and only their members,
#: can see the AWS- or GCP-tagged records. Each demo developer/requester
#: therefore belongs to two groups: one for their role, one for their
#: provider's access.
_DEMO_GROUPS = (
    _DemoGroupSpec(
        id=DEMO_APPROVERS_GROUP_ID,
        name="Demo Approvers",
        description="Managers who can be designated as workflow approvers.",
        role=Role.approver,
        member_ids=(DEMO_APPROVER_USER_ID, DEMO_APPROVER_2_USER_ID),
    ),
    _DemoGroupSpec(
        id=DEMO_REQUESTERS_GROUP_ID,
        name="Demo Requesters",
        description="People who can run published workflows.",
        role=Role.requester,
        member_ids=(DEMO_AWS_REQUESTER_USER_ID, DEMO_GCP_REQUESTER_USER_ID),
    ),
    _DemoGroupSpec(
        id=DEMO_DEVELOPERS_GROUP_ID,
        name="Demo Developers",
        description="People who can build workflows, MCP servers, and agent skills.",
        role=Role.developer,
        member_ids=(DEMO_AWS_DEVELOPER_USER_ID, DEMO_GCP_DEVELOPER_USER_ID),
    ),
    _DemoGroupSpec(
        id=DEMO_AWS_GROUP_ID,
        name="Demo AWS Group",
        description=("Holds the access-control 'AWS' tag; grants no role of its own."),
        role=None,
        member_ids=(DEMO_AWS_DEVELOPER_USER_ID, DEMO_AWS_REQUESTER_USER_ID),
    ),
    _DemoGroupSpec(
        id=DEMO_GCP_GROUP_ID,
        name="Demo GCP Group",
        description=("Holds the access-control 'GCP' tag; grants no role of its own."),
        role=None,
        member_ids=(DEMO_GCP_DEVELOPER_USER_ID, DEMO_GCP_REQUESTER_USER_ID),
    ),
)

#: The tool of the demo AWS MCP server that runs one AWS CLI command.
_DEMO_CALL_AWS_TOOL = "aws___call_aws"

#: The tool of the demo AWS MCP server that runs a script (AWS CLI + boto3).
_DEMO_RUN_SCRIPT_TOOL = "aws___run_script"

#: The tool of the demo GKE MCP server that deletes a Kubernetes resource.
#: Connected directly over ``streamable_http`` with no proxy in between, so
#: the tool carries the bare name the Google-managed server itself declares,
#: unlike the AWS tools above (bridged, and namespaced, through
#: ``mcp-proxy-for-aws``).
_DEMO_DELETE_POD_TOOL = "delete_k8s_resource"

#: Instance id shared by the ``call_aws`` and ``run_script`` mock results, so a
#: run that happens to call both still tells one consistent story.
_DEMO_MOCK_INSTANCE_ID = "i-0a1b2c3d4e5f67890"

#: Structured result of the demo ``call_aws`` mock: the JSON an
#: ``aws ec2 run-instances`` call prints, trimmed to the fields the sample skill
#: reads back to the user (the instance id and its state).
_DEMO_CALL_AWS_RESULT: dict[str, Any] = {
    "Instances": [
        {
            "InstanceId": _DEMO_MOCK_INSTANCE_ID,
            "ImageId": "ami-0demoamazonlinux2023",
            "InstanceType": "t3.medium",
            "State": {"Code": 0, "Name": "pending"},
            "PrivateIpAddress": "10.0.12.34",
            "SubnetId": "subnet-0demo1234567890",
            "KeyName": "demo-keypair",
            "SecurityGroups": [
                {"GroupId": "sg-0demo1234567890", "GroupName": "demo-sg"}
            ],
            "Placement": {"AvailabilityZone": "us-east-1a"},
            "Tags": [{"Key": "Name", "Value": "demo-instance"}],
            "LaunchTime": "2026-01-01T00:00:00+00:00",
        }
    ],
    "OwnerId": "123456789012",
    "ReservationId": "r-0demo1234567890",
}

#: Structured result of the demo ``run_script`` mock: the exit status, captured
#: output, and a small parsed result a script-runner tool returns.
_DEMO_RUN_SCRIPT_RESULT: dict[str, Any] = {
    "status": "success",
    "exit_code": 0,
    "stdout": f"Launched {_DEMO_MOCK_INSTANCE_ID} in us-east-1a; state: pending\n",
    "stderr": "",
    "result": {
        "instance_id": _DEMO_MOCK_INSTANCE_ID,
        "instance_type": "t3.medium",
        "availability_zone": "us-east-1a",
        "state": "pending",
    },
}

#: Pod identity shared by the demo ``delete_k8s_resource`` mock's request and
#: result, so the story it tells is self-consistent.
_DEMO_MOCK_POD_NAME = "api-7d4f8-abc12"
_DEMO_MOCK_POD_NAMESPACE = "prod"

#: Structured result of the demo ``delete_k8s_resource`` mock: the pod
#: identity and status a real deletion call against the GKE MCP server would
#: report back.
_DEMO_DELETE_POD_RESULT: dict[str, Any] = {
    "kind": "Pod",
    "name": _DEMO_MOCK_POD_NAME,
    "namespace": _DEMO_MOCK_POD_NAMESPACE,
    "status": "deleted",
    "message": (
        f"Pod {_DEMO_MOCK_POD_NAME} deleted; its owning ReplicaSet is recreating it."
    ),
}

#: Description shown on the demo ``call_aws`` tool mock in the admin UI.
_DEMO_CALL_AWS_MOCK_DESCRIPTION = (
    "Stubs the AWS MCP Server's call_aws tool with a successful ec2 "
    "run-instances result, so a draft run of the demo workflow completes its "
    "launch step without reaching AWS."
)

#: Description shown on the demo ``run_script`` tool mock in the admin UI.
_DEMO_RUN_SCRIPT_MOCK_DESCRIPTION = (
    "Stubs the AWS MCP Server's run_script tool with a successful EC2 launch, "
    "so a draft run of the demo workflow completes its launch step without "
    "reaching AWS."
)

#: Description shown on the demo ``request_approval`` tool mock in the admin UI.
_DEMO_REQUEST_APPROVAL_MOCK_DESCRIPTION = (
    "Stubs the built-in request_approval tool as approved, so a draft run of "
    "the demo workflow plays through without waiting on a manager's decision."
)

#: Description shown on the demo ``delete_k8s_resource`` tool mock in the admin UI.
_DEMO_DELETE_POD_MOCK_DESCRIPTION = (
    "Stubs the GKE MCP Server's delete_k8s_resource tool with a successful "
    "pod deletion, so a draft run of the demo workflow completes its restart "
    "step without reaching a real GKE cluster."
)


@dataclass(frozen=True)
class _DemoToolMockSpec:
    """One demo tool mock: a single constant response standing in for one tool.

    Attributes:
        id: Fixed primary key, so the mock can be found again for removal.
        name: Mock name shown in the admin UI, unique within the tenant.
        description: Sentence shown on the mock list and the Run dialog.
        mcp_server_id: Id of the registered MCP server the mocked tool belongs
            to, or ``None`` for a built-in agent tool.
        tool_name: The tool this mock stands in for.
        response: The single ``{"kind", "value"}`` response entry, returned for
            every call the run makes to the tool.
    """

    id: str
    name: str
    description: str
    mcp_server_id: str | None
    tool_name: str
    response: dict[str, Any]


#: The demo tool mocks, all in the seeded ``Default`` tenant. The first two stub
#: tools of the demo AWS MCP server (see :func:`_seed_demo_mcp_server`); the
#: third stubs the demo GKE MCP server's tool (see
#: :func:`_seed_demo_gke_mcp_server`); the fourth stubs the built-in
#: :data:`~models.mcp_tool_mock.REQUEST_APPROVAL_TOOL`. Checked in a draft
#: run's Run dialog, together they let either sample workflow -- "launch an
#: EC2 instance" or "restart a GKE pod" -- run end to end without reaching
#: AWS, a real GKE cluster, or an approver.
_DEMO_TOOL_MOCKS = (
    _DemoToolMockSpec(
        id=DEMO_CALL_AWS_MOCK_ID,
        name=DEMO_CALL_AWS_MOCK_NAME,
        description=_DEMO_CALL_AWS_MOCK_DESCRIPTION,
        mcp_server_id=DEMO_MCP_SERVER_ID,
        tool_name=_DEMO_CALL_AWS_TOOL,
        response={"kind": "structured", "value": _DEMO_CALL_AWS_RESULT},
    ),
    _DemoToolMockSpec(
        id=DEMO_RUN_SCRIPT_MOCK_ID,
        name=DEMO_RUN_SCRIPT_MOCK_NAME,
        description=_DEMO_RUN_SCRIPT_MOCK_DESCRIPTION,
        mcp_server_id=DEMO_MCP_SERVER_ID,
        tool_name=_DEMO_RUN_SCRIPT_TOOL,
        response={"kind": "structured", "value": _DEMO_RUN_SCRIPT_RESULT},
    ),
    _DemoToolMockSpec(
        id=DEMO_DELETE_POD_MOCK_ID,
        name=DEMO_DELETE_POD_MOCK_NAME,
        description=_DEMO_DELETE_POD_MOCK_DESCRIPTION,
        mcp_server_id=DEMO_GKE_MCP_SERVER_ID,
        tool_name=_DEMO_DELETE_POD_TOOL,
        response={"kind": "structured", "value": _DEMO_DELETE_POD_RESULT},
    ),
    _DemoToolMockSpec(
        id=DEMO_REQUEST_APPROVAL_MOCK_ID,
        name=DEMO_REQUEST_APPROVAL_MOCK_NAME,
        description=_DEMO_REQUEST_APPROVAL_MOCK_DESCRIPTION,
        mcp_server_id=None,
        tool_name=REQUEST_APPROVAL_TOOL,
        response={"kind": "structured", "value": {"status": "approved"}},
    ),
)


async def sync_demo_data(session: AsyncSession) -> list[str]:
    """Register or remove the demo dataset according to ``DEMO_DATA``.

    Must run **after** :func:`infrastructure.bootstrap.seed_root_user` and
    :func:`infrastructure.bootstrap.seed_default_tenant_and_admin_user`: the
    demo accounts are real (non-system) users, so seeding them first would
    make ``seed_root_user``'s "any real user exists" skip check wrongly fire,
    and the ``Default`` tenant these records hang off has to exist already.

    Args:
        session: Database session used to read, insert, and delete records.

    Returns:
        The ids of the demo AgentSkills this call freshly registered, whose
        repositories have not been cloned yet and whose sync the caller should
        schedule. Empty when every demo skill already existed, none could be
        registered, or the demo data was removed instead.
    """
    if get_settings().demo_data:
        return await _seed_demo_data(session)
    await _remove_demo_data(session)
    return []


async def _seed_demo_data(session: AsyncSession) -> list[str]:
    """Create every missing demo record in the seeded ``Default`` tenant.

    Args:
        session: Database session used to read and insert records.

    Returns:
        The ids of the demo AgentSkills this call created, in seeding order.
    """
    tenant_id = await _default_tenant_id(session)
    if tenant_id is None:
        logger.warning(
            "DEMO_DATA is enabled but the seeded '%s' tenant does not exist; "
            "skipping demo data.",
            DEFAULT_TENANT_NAME,
        )
        return []
    await _seed_demo_users(session, tenant_id)
    await _seed_demo_groups(session, tenant_id)
    await _seed_demo_secrets(session, tenant_id)
    await _seed_demo_mcp_server(session, tenant_id)
    await _seed_demo_gke_mcp_server(session, tenant_id)
    await _seed_demo_tool_mocks(session, tenant_id)
    new_skill_ids = [
        skill_id
        for skill_id in (
            await _seed_demo_agent_skill(session, tenant_id),
            await _seed_demo_gke_agent_skill(session, tenant_id),
        )
        if skill_id is not None
    ]
    await _seed_demo_tags(session, tenant_id)
    return new_skill_ids


async def _remove_demo_data(session: AsyncSession) -> None:
    """Delete every demo record that is still present.

    Deletion follows the direction of the foreign keys — tool mocks, then agent
    skills, then MCP servers, then secrets, then tags, then user groups, then
    users — so a record is never orphaned by the removal of something it points
    at. The tool mocks go first because two of them (``call_aws`` and
    ``run_script``) reference the AWS MCP server with ``ondelete="RESTRICT"``,
    which would otherwise block its removal. A record that other data has come
    to depend on (a Workflow built on a demo skill, a task tool binding on
    one of the demo MCP servers) cannot be deleted; that is logged and skipped
    rather than allowed to fail startup.

    Deleting a tag has no such protection — the join tables cascade rather
    than restrict, by design (see the module docstring of ``models.tag``) —
    so it also detaches the tag from any of an operator's own records that
    happen to carry it, the same as deleting it by hand in the admin UI would.

    Groups go before their members: the membership rows cascade away with the
    group, so the users are then free of them and the roles they granted are
    gone from the accounts' effective roles immediately. Nothing has to be
    recomputed, since inherited roles are never stored on the user.

    Args:
        session: Database session used to read and delete records.
    """
    for mock_spec in _DEMO_TOOL_MOCKS:
        await _delete_demo_row(
            session, MCPToolMock, mock_spec.id, label=f"tool mock {mock_spec.name!r}"
        )
    await _delete_demo_row(
        session, AgentSkill, DEMO_AGENT_SKILL_ID, label="EC2-launch agent skill"
    )
    await _delete_demo_row(
        session,
        AgentSkill,
        DEMO_GKE_SKILL_ID,
        label="GKE pod-restart agent skill",
    )
    await _delete_demo_row(
        session, MCPServer, DEMO_MCP_SERVER_ID, label="AWS MCP server"
    )
    await _delete_demo_row(
        session, MCPServer, DEMO_GKE_MCP_SERVER_ID, label="GKE MCP server"
    )
    await _delete_demo_row(
        session, Secret, DEMO_AWS_SECRET_ID, label="AWS credentials secret"
    )
    await _delete_demo_row(
        session, Secret, DEMO_GCP_SECRET_ID, label="Google Cloud API key secret"
    )
    await _delete_demo_row(
        session, Tag, DEMO_AWS_TAG_ID, label=f"tag '{DEMO_AWS_TAG_NAME}'"
    )
    await _delete_demo_row(
        session, Tag, DEMO_GCP_TAG_ID, label=f"tag '{DEMO_GCP_TAG_NAME}'"
    )
    await _delete_demo_row(
        session, Tag, DEMO_APPROVAL_TAG_ID, label=f"tag '{DEMO_APPROVAL_TAG_NAME}'"
    )
    for group_spec in _DEMO_GROUPS:
        await _delete_demo_row(
            session, UserGroup, group_spec.id, label=f"user group {group_spec.name!r}"
        )
    for spec in _DEMO_USERS:
        await _delete_demo_user(session, spec.id)


async def _default_tenant_id(session: AsyncSession) -> str | None:
    """Return the id of the seeded ``Default`` tenant, or ``None`` if absent.

    Args:
        session: Database session used to read the tenant.

    Returns:
        The tenant's id, or ``None`` when it has not been seeded.
    """
    stmt = select(Tenant).where(col(Tenant.name) == DEFAULT_TENANT_NAME).limit(1)
    tenant = (await session.exec(stmt)).first()
    return None if tenant is None else tenant.id


async def _default_admin_user_id(session: AsyncSession, tenant_id: str) -> str | None:
    """Return the id of the seeded ``Default`` tenant's ``admin`` user, or ``None``.

    ``admin`` is seeded by :func:`infrastructure.bootstrap.seed_default_tenant_and_admin_user`,
    not by this module, and gets an auto-generated UUID7 rather than a fixed
    id, so it must be looked up by ``username`` scoped to the tenant rather
    than referenced by a constant the way every other demo record is.

    Args:
        session: Database session used to read the user.
        tenant_id: Id of the ``Default`` tenant the ``admin`` user belongs to.

    Returns:
        The user's id, or ``None`` when it has not been seeded yet.
    """
    stmt = (
        select(User)
        .where(col(User.username) == "admin", col(User.tenant_id) == tenant_id)
        .limit(1)
    )
    admin = (await session.exec(stmt)).first()
    return None if admin is None else admin.id


async def _insert(session: AsyncSession, row: SQLModel, *, label: str) -> bool:
    """Insert one demo row, skipping it when it collides with existing data.

    The demo names (``demo-approver-1``, ``AWS MCP Server``, ...) are not reserved,
    so an operator may already have a record of their own under one of them.
    The per-tenant unique constraint catches that; the collision is reported
    and the remaining demo records are still registered, rather than the
    ``IntegrityError`` propagating out of the startup hook.

    Args:
        session: Database session used to insert the row.
        row: The fully populated table model to persist.
        label: Human-readable description of the row used in the log message.

    Returns:
        ``True`` when the row was inserted, ``False`` when it was skipped.
    """
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning(
            "Skipped registering the demo %s: it conflicts with an existing "
            "record (most likely one of the same name).",
            label,
        )
        return False
    return True


async def _delete_demo_row(
    session: AsyncSession, model: type[_RowT], row_id: str, *, label: str
) -> None:
    """Delete one demo row by id, tolerating both absence and references.

    Args:
        session: Database session used to read and delete the row.
        model: Table model class the row belongs to.
        row_id: Fixed identifier of the demo row.
        label: Human-readable description of the row used in the log message.
    """
    row = await session.get(model, row_id)
    if row is None:
        return
    try:
        await session.delete(row)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning(
            "Could not remove the demo %s: other records still reference it. "
            "Delete those first, then restart, or remove it in the admin UI.",
            label,
        )


async def _seed_demo_users(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo approver and requester, reviving them if soft-deleted.

    The shared password is resolved only when at least one account is actually
    missing, so a restart with everything already in place never generates —
    and logs — a password nobody will use.

    A previous removal may have left an account *soft*-deleted rather than
    gone (see :meth:`repositories.user.SqlUserRepository.delete`), because it
    was still referenced through ``created_by`` / ``updated_by``. Re-enabling
    the demo data revives such an account instead of leaving it disabled.

    Args:
        session: Database session used to read, insert, and update users.
        tenant_id: Id of the ``Default`` tenant the accounts belong to.
    """
    missing: list[_DemoUserSpec] = []
    for spec in _DEMO_USERS:
        existing = await session.get(User, spec.id)
        if existing is None:
            missing.append(spec)
        else:
            await _revive_demo_user(session, existing, spec)
    if not missing:
        return
    password = resolve_seed_password(
        get_settings().demo_password, subject="demo users", env_var="DEMO_PASSWORD"
    )
    for spec in missing:
        await _insert(
            session,
            User(
                id=spec.id,
                username=spec.username,
                first_name=spec.first_name,
                last_name=spec.last_name,
                password=hash_password(password),
                email=f"{spec.username}@example.com",
                enabled=True,
                email_verified=False,
                # No direct roles: every demo account inherits its role from
                # the matching group seeded by _seed_demo_groups.
                roles=[],
                tenant_id=tenant_id,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            ),
            label=f"user '{spec.username}'",
        )


async def _revive_demo_user(
    session: AsyncSession, user: User, spec: _DemoUserSpec
) -> None:
    """Normalize an existing demo user back to this module's declared shape.

    Clears a soft delete, re-enables the account, and — for a database seeded
    by an older version of this module, which granted each demo account its
    role directly — strips the direct roles so the account gets them from its
    group instead. Without that last step, upgrading with ``DEMO_DATA`` left
    enabled would leave the role granted twice over, and removing a user from
    their demo group would visibly fail to revoke anything.

    Also brings the account's identity fields back in line with ``spec``: a
    row seeded under an older version of this module may still carry a
    previous generation's username (e.g. ``demo-developer`` before this
    module split it into a per-provider ``demo-aws-developer`` /
    ``demo-gcp-developer`` pair), which would otherwise never be corrected by
    a later restart.

    Args:
        session: Database session used to update the user.
        user: The existing demo user row.
        spec: This account's current declared identity.
    """
    if (
        user.deleted_at is None
        and user.enabled
        and not user.roles
        and user.username == spec.username
        and user.first_name == spec.first_name
        and user.last_name == spec.last_name
    ):
        return
    previous_username = user.username
    user.deleted_at = None
    user.enabled = True
    user.roles = []
    user.username = spec.username
    user.first_name = spec.first_name
    user.last_name = spec.last_name
    user.updated_by = SYSTEM_USER_ID
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning(
            "Could not rename demo user %r to %r: the new username conflicts "
            "with an existing record.",
            previous_username,
            spec.username,
        )


async def _delete_demo_user(session: AsyncSession, user_id: str) -> None:
    """Delete one demo user, falling back to a soft delete when referenced.

    Goes through :class:`repositories.user.SqlUserRepository` rather than
    deleting the row here, to reuse its hard-delete-then-soft-delete fallback:
    a demo user that has signed in and created records cannot be removed
    outright, and must keep resolving as a name on those records.

    Args:
        session: Database session used to read and delete the user.
        user_id: Fixed identifier of the demo user.
    """
    if await session.get(User, user_id) is None:
        return
    await SqlUserRepository(session).delete(user_id)


async def _seed_demo_groups(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo user groups and place each demo account in its group(s).

    Must run after :func:`_seed_demo_users`: the membership rows reference
    ``users.id``. A group whose row already exists is left alone, but its
    membership is re-asserted, so a member removed by hand in the admin UI
    comes back on the next restart — matching this module's declarative
    contract for every other record.

    Nothing needs recomputing afterwards: a member's inherited roles are
    resolved from these rows on every request rather than stored on the user.

    Also places the tenant's ``admin`` user (seeded separately by
    :func:`infrastructure.bootstrap.seed_default_tenant_and_admin_user`, so it
    has no fixed id this module can put in :data:`_DEMO_GROUPS` directly) in
    both :data:`DEMO_AWS_GROUP_ID` and :data:`DEMO_GCP_GROUP_ID`, so it can see
    every AWS- and GCP-tagged demo record without needing a dedicated account.

    Args:
        session: Database session used to read and insert groups and members.
        tenant_id: Id of the ``Default`` tenant the groups belong to.
    """
    for spec in _DEMO_GROUPS:
        if await session.get(UserGroup, spec.id) is None:
            await _insert(
                session,
                UserGroup(
                    id=spec.id,
                    tenant_id=tenant_id,
                    name=spec.name,
                    description=spec.description,
                    roles=[spec.role.value] if spec.role is not None else [],
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                ),
                label=f"user group '{spec.name}'",
            )
        if await session.get(UserGroup, spec.id) is None:
            # The insert collided with an operator's own group of that name;
            # there is nothing to attach a membership to.
            continue
        for member_id in spec.member_ids:
            if await session.get(UserGroupMember, (spec.id, member_id)) is None:
                await _insert(
                    session,
                    UserGroupMember(group_id=spec.id, user_id=member_id),
                    label=f"membership of user group '{spec.name}'",
                )

    admin_id = await _default_admin_user_id(session, tenant_id)
    if admin_id is None:
        return
    for group_id, group_name in (
        (DEMO_AWS_GROUP_ID, "Demo AWS Group"),
        (DEMO_GCP_GROUP_ID, "Demo GCP Group"),
    ):
        if await session.get(UserGroup, group_id) is None:
            continue
        if await session.get(UserGroupMember, (group_id, admin_id)) is None:
            await _insert(
                session,
                UserGroupMember(group_id=group_id, user_id=admin_id),
                label=f"admin membership of user group '{group_name}'",
            )


async def _seed_demo_secrets(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo AWS credentials and Google Cloud API key secrets.

    The AWS access key and secret key live in a single secret as two entries,
    the way a Vault KV path holds several keys; the Google Cloud API key is a
    second secret with a single entry. Values come from ``DEMO_AWS_ACCESS_KEY_ID``
    / ``DEMO_AWS_SECRET_ACCESS_KEY`` / ``DEMO_GCP_API_KEY`` when set, so a fully
    working demo is one restart away, and fall back to a placeholder otherwise.
    They are stored as Fernet ciphertext, the same as any secret created through
    the API — the encryption lives in the service layer, which this
    out-of-request caller cannot use, so the cipher is applied directly here.
    Each secret is guarded by its own id check, so an operator's own record
    under one demo name never blocks seeding the other.

    Args:
        session: Database session used to read and insert secrets.
        tenant_id: Id of the ``Default`` tenant the secrets belong to.
    """
    settings = get_settings()
    cipher = get_secret_cipher()
    if await session.get(Secret, DEMO_AWS_SECRET_ID) is None:
        await _insert(
            session,
            Secret(
                id=DEMO_AWS_SECRET_ID,
                tenant_id=tenant_id,
                name=DEMO_AWS_SECRET_NAME,
                description=_DEMO_AWS_SECRET_DESCRIPTION,
                type=SecretType.local,
                entries={
                    DEMO_ACCESS_KEY_ENTRY_KEY: cipher.encrypt(
                        settings.demo_aws_access_key_id or _PLACEHOLDER_SECRET_VALUE
                    ),
                    DEMO_SECRET_KEY_ENTRY_KEY: cipher.encrypt(
                        settings.demo_aws_secret_access_key or _PLACEHOLDER_SECRET_VALUE
                    ),
                },
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            ),
            label=f"secret '{DEMO_AWS_SECRET_NAME}'",
        )
    if await session.get(Secret, DEMO_GCP_SECRET_ID) is None:
        await _insert(
            session,
            Secret(
                id=DEMO_GCP_SECRET_ID,
                tenant_id=tenant_id,
                name=DEMO_GCP_SECRET_NAME,
                description=_DEMO_GCP_SECRET_DESCRIPTION,
                type=SecretType.local,
                entries={
                    DEMO_GCP_API_KEY_ENTRY_KEY: cipher.encrypt(
                        settings.demo_gcp_api_key or _PLACEHOLDER_SECRET_VALUE
                    ),
                },
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            ),
            label=f"secret '{DEMO_GCP_SECRET_NAME}'",
        )


async def _seed_demo_mcp_server(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo AWS MCP server.

    The AWS MCP Server is a managed remote endpoint rather than something to
    self-host, so the row is registered as a ``stdio`` server launching the
    ``mcp-proxy-for-aws`` bridge with ``uvx``, which the backend image already
    provides. The proxy signs every request to :data:`_DEMO_MCP_ENDPOINT` with
    SigV4 using the AWS credentials it finds in its environment; those are
    ``${secret:NAME/KEY}`` placeholders resolved at connection time by
    :class:`infrastructure.secret_resolver.SecretResolver`, so the plaintext
    never lands in the ``mcp_servers`` row.

    ``DEMO_AWS_REGION`` is carried in this row's own ``env`` (as
    ``AWS_REGION``) and referenced from ``args`` via ``${env:AWS_REGION}`` —
    the remote server reads that metadata value to pick the region its tools
    act on — kept apart from ``--region``, which only governs the signature
    and is not configurable through ``env``.

    Args:
        session: Database session used to read and insert the server.
        tenant_id: Id of the ``Default`` tenant the server belongs to.
    """
    if await session.get(MCPServer, DEMO_MCP_SERVER_ID) is not None:
        return
    settings = get_settings()
    await _insert(
        session,
        MCPServer(
            id=DEMO_MCP_SERVER_ID,
            tenant_id=tenant_id,
            name=DEMO_MCP_SERVER_NAME,
            description=_DEMO_MCP_SERVER_DESCRIPTION,
            transport=McpTransport.stdio,
            command=McpCommand.uvx,
            args=[
                _DEMO_MCP_PROXY_PACKAGE,
                _DEMO_MCP_ENDPOINT,
                "--region",
                _DEMO_MCP_ENDPOINT_REGION,
                "--metadata",
                "AWS_REGION=${env:AWS_REGION}",
            ],
            headers={},
            env={
                "AWS_ACCESS_KEY_ID": (
                    f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_ACCESS_KEY_ENTRY_KEY}}}"
                ),
                "AWS_SECRET_ACCESS_KEY": (
                    f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_SECRET_KEY_ENTRY_KEY}}}"
                ),
                "AWS_REGION": settings.demo_aws_region,
            },
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"MCP server '{DEMO_MCP_SERVER_NAME}'",
    )


async def _seed_demo_gke_mcp_server(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo GKE MCP server.

    Google runs the GKE MCP server as a managed remote endpoint, so the row is
    registered as a ``streamable_http`` server pointed straight at
    :data:`_DEMO_GKE_MCP_ENDPOINT` -- the full endpoint, not the read-only or
    delete-only variants Google also publishes. It authenticates with a
    Google Cloud API key sent as the :data:`_DEMO_GCP_API_KEY_HEADER` request
    header; the value is a ``${secret:NAME/KEY}`` placeholder resolved at
    connection time by :class:`infrastructure.secret_resolver.SecretResolver`,
    so the key never lands in the ``mcp_servers`` row. Like the AWS demo
    server, its tools can mutate real infrastructure -- deleting a Pod, in
    particular.

    Args:
        session: Database session used to read and insert the server.
        tenant_id: Id of the ``Default`` tenant the server belongs to.
    """
    if await session.get(MCPServer, DEMO_GKE_MCP_SERVER_ID) is not None:
        return
    await _insert(
        session,
        MCPServer(
            id=DEMO_GKE_MCP_SERVER_ID,
            tenant_id=tenant_id,
            name=DEMO_GKE_MCP_SERVER_NAME,
            description=_DEMO_GKE_MCP_SERVER_DESCRIPTION,
            transport=McpTransport.streamable_http,
            url=_DEMO_GKE_MCP_ENDPOINT,
            headers={
                _DEMO_GCP_API_KEY_HEADER: (
                    f"${{secret:{DEMO_GCP_SECRET_NAME}/{DEMO_GCP_API_KEY_ENTRY_KEY}}}"
                ),
            },
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"MCP server '{DEMO_GKE_MCP_SERVER_NAME}'",
    )


async def _seed_demo_tool_mocks(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo tool mocks that let a draft run play through unattended.

    Four stubs, all in the seeded ``Default`` tenant: ``call_aws`` and
    ``run_script`` on the demo AWS MCP server, each returning a successful EC2
    launch, ``delete_k8s_resource`` on the demo GKE MCP server, returning a
    successful pod deletion, and the built-in
    :data:`~models.mcp_tool_mock.REQUEST_APPROVAL_TOOL`, returning ``approved``.
    Selected in a draft run's Run dialog, they let either sample workflow --
    "launch an EC2 instance" or "restart a GKE pod" -- run end to end without
    reaching AWS, a real GKE cluster, or waiting on an approver.

    Must run after :func:`_seed_demo_mcp_server` and
    :func:`_seed_demo_gke_mcp_server`: the first three mocks reference
    ``mcp_servers.id``. Each mock defines a single response, so it behaves as a
    constant however many times the run calls the tool. ``responses`` is stored
    as plain ``{"kind", "value"}`` dicts because the table column cannot carry
    the :class:`~models.mcp_tool_mock.MockResponse` type (see
    :class:`~models.mcp_tool_mock.MCPToolMock`).

    Args:
        session: Database session used to read and insert the mocks.
        tenant_id: Id of the ``Default`` tenant the mocks belong to.
    """
    for spec in _DEMO_TOOL_MOCKS:
        if await session.get(MCPToolMock, spec.id) is not None:
            continue
        await _insert(
            session,
            MCPToolMock(
                id=spec.id,
                tenant_id=tenant_id,
                name=spec.name,
                description=spec.description,
                mcp_server_id=spec.mcp_server_id,
                tool_name=spec.tool_name,
                responses=[spec.response],
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            ),
            label=f"tool mock {spec.name!r}",
        )


async def _seed_demo_agent_skill(session: AsyncSession, tenant_id: str) -> str | None:
    """Create the demo agent skill pointing at the ``aws-ec2-launch`` sample.

    The repository is public, so no ``repo_auth_password`` is needed. The row is
    left ``pending``: cloning is the caller's job, since it is a network
    operation that must not block application startup.

    Args:
        session: Database session used to read and insert the skill.
        tenant_id: Id of the ``Default`` tenant the skill belongs to.

    Returns:
        The skill's id when this call created it, else ``None``.
    """
    if await session.get(AgentSkill, DEMO_AGENT_SKILL_ID) is not None:
        return None
    created = await _insert(
        session,
        AgentSkill(
            id=DEMO_AGENT_SKILL_ID,
            tenant_id=tenant_id,
            name=DEMO_AGENT_SKILL_NAME,
            repo_url=_DEMO_SKILL_REPO_URL,
            repo_path=_DEMO_AWS_SKILL_REPO_PATH,
            description=(
                "Launch an AWS EC2 instance through a registered MCP tool, "
                "gated by a manager's explicit approval."
            ),
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"agent skill '{DEMO_AGENT_SKILL_NAME}'",
    )
    return DEMO_AGENT_SKILL_ID if created else None


async def _seed_demo_gke_agent_skill(
    session: AsyncSession, tenant_id: str
) -> str | None:
    """Create the demo agent skill pointing at the ``gke-pod-restart`` sample.

    A second sample skill, this one restarting a Kubernetes Pod on a GKE
    cluster: it deletes a specific pod through the GKE MCP server so its
    owning controller recreates it, gated by a manager's explicit approval of
    exactly which pod. Registered exactly like :func:`_seed_demo_agent_skill`
    -- built as a table model directly, left ``pending`` for the caller to
    clone.

    Args:
        session: Database session used to read and insert the skill.
        tenant_id: Id of the ``Default`` tenant the skill belongs to.

    Returns:
        The skill's id when this call created it, else ``None``.
    """
    if await session.get(AgentSkill, DEMO_GKE_SKILL_ID) is not None:
        return None
    created = await _insert(
        session,
        AgentSkill(
            id=DEMO_GKE_SKILL_ID,
            tenant_id=tenant_id,
            name=DEMO_GKE_SKILL_NAME,
            repo_url=_DEMO_SKILL_REPO_URL,
            repo_path=_DEMO_GKE_SKILL_REPO_PATH,
            description=(
                "Restart a specific Kubernetes Pod on a GKE cluster by "
                "deleting it through the GKE MCP server so its owning "
                "controller recreates it, gated by a manager's explicit "
                "approval of exactly which pod."
            ),
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"agent skill '{DEMO_GKE_SKILL_NAME}'",
    )
    return DEMO_GKE_SKILL_ID if created else None


async def _seed_demo_tags(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo tags and attach them across four of the six taggable kinds.

    ``AWS`` lands on the AWS secret, AWS MCP server, the EC2-launch agent skill,
    and the ``call_aws`` and ``run_script`` tool mocks; ``GCP`` lands on the
    Google Cloud secret, the GKE MCP server, and the pod-restart agent skill;
    ``Approval Required`` lands on both agent skills. ``AWS`` and ``GCP`` are
    also each attached to their matching user group (``Demo AWS Group`` /
    ``Demo GCP Group``) as access-control tags, which is what gates the
    records above to that group's members.

    Must run after :func:`_seed_demo_secrets`, :func:`_seed_demo_mcp_server`,
    :func:`_seed_demo_gke_mcp_server`, :func:`_seed_demo_agent_skill`,
    :func:`_seed_demo_gke_agent_skill`, :func:`_seed_demo_tool_mocks`, and
    :func:`_seed_demo_groups`: attaching a tag looks up the record it attaches
    to, including the two user groups. The demo Workflow does not exist — see
    the module docstring — so no tag is attached to one; an operator is free
    to attach one once they build a workflow from these records themselves.

    Args:
        session: Database session used to read and insert tags and their
            attachments.
        tenant_id: Id of the ``Default`` tenant the tags belong to.
    """
    if await _ensure_demo_tag(
        session,
        tenant_id,
        DEMO_AWS_TAG_ID,
        DEMO_AWS_TAG_NAME,
        TagColor.cyan,
        _DEMO_AWS_TAG_DESCRIPTION,
        access_control=True,
    ):
        await _link_tag(
            session,
            SecretTag,
            resource_model=Secret,
            resource_id=DEMO_AWS_SECRET_ID,
            tag_id=DEMO_AWS_TAG_ID,
            label=f"tag '{DEMO_AWS_TAG_NAME}' on secret '{DEMO_AWS_SECRET_NAME}'",
        )
        await _link_tag(
            session,
            McpServerTag,
            resource_model=MCPServer,
            resource_id=DEMO_MCP_SERVER_ID,
            tag_id=DEMO_AWS_TAG_ID,
            label=f"tag '{DEMO_AWS_TAG_NAME}' on MCP server '{DEMO_MCP_SERVER_NAME}'",
        )
        await _link_tag(
            session,
            AgentSkillTag,
            resource_model=AgentSkill,
            resource_id=DEMO_AGENT_SKILL_ID,
            tag_id=DEMO_AWS_TAG_ID,
            label=f"tag '{DEMO_AWS_TAG_NAME}' on agent skill '{DEMO_AGENT_SKILL_NAME}'",
        )
        await _link_tag(
            session,
            McpToolMockTag,
            resource_model=MCPToolMock,
            resource_id=DEMO_CALL_AWS_MOCK_ID,
            tag_id=DEMO_AWS_TAG_ID,
            label=f"tag '{DEMO_AWS_TAG_NAME}' on tool mock '{DEMO_CALL_AWS_MOCK_NAME}'",
        )
        await _link_tag(
            session,
            McpToolMockTag,
            resource_model=MCPToolMock,
            resource_id=DEMO_RUN_SCRIPT_MOCK_ID,
            tag_id=DEMO_AWS_TAG_ID,
            label=(
                f"tag '{DEMO_AWS_TAG_NAME}' on tool mock '{DEMO_RUN_SCRIPT_MOCK_NAME}'"
            ),
        )
        await _link_tag(
            session,
            UserGroupTag,
            resource_model=UserGroup,
            resource_id=DEMO_AWS_GROUP_ID,
            tag_id=DEMO_AWS_TAG_ID,
            label=f"tag '{DEMO_AWS_TAG_NAME}' on user group 'Demo AWS Group'",
        )
    if await _ensure_demo_tag(
        session,
        tenant_id,
        DEMO_GCP_TAG_ID,
        DEMO_GCP_TAG_NAME,
        TagColor.indigo,
        _DEMO_GCP_TAG_DESCRIPTION,
        access_control=True,
    ):
        await _link_tag(
            session,
            SecretTag,
            resource_model=Secret,
            resource_id=DEMO_GCP_SECRET_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=f"tag '{DEMO_GCP_TAG_NAME}' on secret '{DEMO_GCP_SECRET_NAME}'",
        )
        await _link_tag(
            session,
            McpServerTag,
            resource_model=MCPServer,
            resource_id=DEMO_GKE_MCP_SERVER_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=(
                f"tag '{DEMO_GCP_TAG_NAME}' on MCP server '{DEMO_GKE_MCP_SERVER_NAME}'"
            ),
        )
        await _link_tag(
            session,
            AgentSkillTag,
            resource_model=AgentSkill,
            resource_id=DEMO_GKE_SKILL_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=(f"tag '{DEMO_GCP_TAG_NAME}' on agent skill '{DEMO_GKE_SKILL_NAME}'"),
        )
        await _link_tag(
            session,
            UserGroupTag,
            resource_model=UserGroup,
            resource_id=DEMO_GCP_GROUP_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=f"tag '{DEMO_GCP_TAG_NAME}' on user group 'Demo GCP Group'",
        )
    if await _ensure_demo_tag(
        session,
        tenant_id,
        DEMO_APPROVAL_TAG_ID,
        DEMO_APPROVAL_TAG_NAME,
        TagColor.amber,
        _DEMO_APPROVAL_TAG_DESCRIPTION,
    ):
        await _link_tag(
            session,
            AgentSkillTag,
            resource_model=AgentSkill,
            resource_id=DEMO_AGENT_SKILL_ID,
            tag_id=DEMO_APPROVAL_TAG_ID,
            label=(
                f"tag '{DEMO_APPROVAL_TAG_NAME}' on agent skill "
                f"'{DEMO_AGENT_SKILL_NAME}'"
            ),
        )
        await _link_tag(
            session,
            AgentSkillTag,
            resource_model=AgentSkill,
            resource_id=DEMO_GKE_SKILL_ID,
            tag_id=DEMO_APPROVAL_TAG_ID,
            label=(
                f"tag '{DEMO_APPROVAL_TAG_NAME}' on agent skill '{DEMO_GKE_SKILL_NAME}'"
            ),
        )


async def _ensure_demo_tag(
    session: AsyncSession,
    tenant_id: str,
    tag_id: str,
    name: str,
    color: TagColor,
    description: str,
    *,
    access_control: bool = False,
) -> bool:
    """Create one demo tag if missing, and report whether it now exists.

    An existing row's ``access_control`` flag is reconciled with the
    requested value on every call, the same way :func:`_revive_demo_user`
    brings an existing user's identity fields back in line with its spec —
    without this, a tag seeded by an older version of this module before it
    became access-control would never pick up the flag on a later restart.

    Args:
        session: Database session used to read and insert the tag.
        tenant_id: Id of the ``Default`` tenant the tag belongs to.
        tag_id: Fixed identifier of the demo tag.
        name: Name shown in the admin UI.
        color: Palette slot the tag's chip is drawn in.
        description: Sentence shown on the tag in the admin UI.
        access_control: Whether this tag should gate visibility of the
            records it labels to only the user groups that hold it.

    Returns:
        ``True`` when the tag is present after this call (already existed or
        was just created), ``False`` when creation was skipped by a name
        collision with an operator's own tag.
    """
    existing = await session.get(Tag, tag_id)
    if existing is not None:
        if existing.access_control != access_control:
            existing.access_control = access_control
            existing.updated_by = SYSTEM_USER_ID
            session.add(existing)
            await session.commit()
        return True
    return await _insert(
        session,
        Tag(
            id=tag_id,
            tenant_id=tenant_id,
            name=name,
            color=color,
            description=description,
            access_control=access_control,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"tag '{name}'",
    )


async def _link_tag(
    session: AsyncSession,
    link_model: type[TagLink],
    *,
    resource_model: type[SQLModel],
    resource_id: str,
    tag_id: str,
    label: str,
) -> None:
    """Attach one tag to one record, unless already attached or the record is missing.

    The record may be missing because its own seeding step was skipped by a
    name collision (see :func:`_insert`); attaching to a nonexistent id would
    fail the join table's foreign key, so this checks for it first rather
    than letting that failure propagate.

    Args:
        session: Database session used to read and insert the join row.
        link_model: The join table model, e.g. :class:`~models.tag.SecretTag`.
        resource_model: Table model class the record belongs to.
        resource_id: Id of the record the tag attaches to.
        tag_id: Id of the tag to attach.
        label: Human-readable description of the attachment, used in the log
            message.
    """
    if await session.get(resource_model, resource_id) is None:
        return
    if await session.get(link_model, (resource_id, tag_id)) is not None:
        return
    await _insert(
        session, link_model(resource_id=resource_id, tag_id=tag_id), label=label
    )
