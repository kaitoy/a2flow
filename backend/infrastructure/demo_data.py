"""Startup registration and removal of the optional demo dataset.

Gated by ``Settings.demo_data`` (the ``DEMO_DATA`` environment variable),
this module keeps a small, self-contained example of everything three
approval-gated, mutating workflows need -- "launch an EC2 instance",
"restart a GKE pod", and "rotate an Azure Key Vault secret" -- all inside the
seeded ``Default`` tenant (see :mod:`infrastructure.bootstrap`):

* three Secrets -- one holding the AWS access key id and secret access key as
  two entries, one holding a Google Cloud credential JSON (a service
  account key, or the authorized-user JSON ``gcloud`` writes) as a single
  entry, and one holding an Azure service principal's tenant id, client id,
  and client secret as three entries, all described for the admin UI,
* six MCPServers -- one stdio server reaching the managed AWS MCP Server
  through the ``mcp-proxy-for-aws`` proxy launched with ``uvx``, referencing
  the AWS entries from its ``env`` via ``${secret:NAME/KEY}``, one
  ``streamable_http`` server reaching the Google-managed GKE (Google
  Kubernetes Engine) remote MCP server, sending an OAuth 2.0 access token
  minted from that credential as its ``Authorization: Bearer`` header via a
  ``${gcp-token:NAME/KEY}`` placeholder, one stdio server launching
  Microsoft's Azure MCP Server with ``npx``, limited to its Key Vault tools
  and referencing the Azure entries from its ``env``, and three read-only
  ``script`` servers showing off in-app scripts: the Python "EC2 Cost
  Estimator", pricing instance types through the AWS Price List Query API
  with ``boto3`` and the same AWS secret entries, the JavaScript
  "Kubernetes Manifest Toolkit", validating manifests and building
  rolling-restart patches with ``js-yaml``, and the JavaScript "Secret Value
  Generator", producing random secret values with ``node:crypto``; all six
  described,
* seven MCPToolMocks that stub the demo run's side-effecting tools so a
  ``draft`` workflow run plays through without reaching AWS, a real GKE
  cluster, a real Key Vault, or waiting on a human -- ``call_aws`` and
  ``run_script`` on the AWS MCP server, each returning a successful EC2
  launch, ``patch_k8s_resource`` and ``delete_k8s_resource`` on the GKE MCP
  server, returning a successful rolling restart and a successful pod
  deletion respectively, ``keyvault_secret_get`` and
  ``keyvault_secret_create`` on the Azure MCP server, returning a list of a
  vault's secrets and a new secret version respectively, and the built-in
  ``request_approval``,
  returning ``approved``,
* three AgentSkills pointing at ``sample_skills/aws-ec2-launch``,
  ``sample_skills/gke-pod-restart``, and
  ``sample_skills/azure-keyvault-secret-rotation`` in this repository,
* four Tags -- ``AWS`` (an **access-control** tag: visible, and its
  attachments usable, only to ``Demo AWS Group`` members and ``admin``/
  ``super_admin``; attached to the AWS secret, AWS MCP server, EC2 Cost
  Estimator, the EC2-launch agent skill, and the ``call_aws`` and
  ``run_script`` tool mocks, showing that one tag classifies across resource
  types), ``GCP`` (also access-control, gated the same way by
  ``Demo GCP Group``; attached to the Google Cloud secret, the GKE MCP
  server, the Kubernetes Manifest Toolkit, the pod-restart agent skill, and
  the ``patch_k8s_resource`` and ``delete_k8s_resource`` tool mocks -- GKE
  is a Google Cloud product, so the same provider tag still applies),
  ``Azure`` (also access-control, gated by ``Demo Azure Group``; attached to
  the Azure secret, the Azure MCP server, the Secret Value Generator, the
  secret-rotation agent skill, and the ``keyvault_secret_get`` and
  ``keyvault_secret_create`` tool mocks), and ``Approval Required`` (a plain, non-gating tag attached to all
  three agent skills, calling out their approval gate),
* eleven Users -- two managers, ``demo-approver-1`` and ``demo-approver-2``,
  either of whom the skill can ask for approval, an AWS trio
  (``demo-aws-developer``, ``demo-aws-reviewer``, ``demo-aws-requester``) who
  build, publish, and run the EC2-launch workflow, a GCP trio
  (``demo-gcp-developer``, ``demo-gcp-reviewer``, ``demo-gcp-requester``) who
  do the same for the GKE-pod-restart workflow, and an Azure trio
  (``demo-azure-developer``, ``demo-azure-reviewer``,
  ``demo-azure-requester``) who do the same for the secret-rotation
  workflow -- each holding **no direct role at all**,
* seven UserGroups -- ``Demo Approvers``, ``Demo Requesters``,
  ``Demo Developers``, and ``Demo Reviewers`` each grant one role to their
  members, so every demo account gets its role purely by inheritance
  (each of the four holds several accounts, showing that a group's
  membership need not be a single user). ``Demo AWS Group``,
  ``Demo GCP Group``, and ``Demo Azure Group`` grant no role at all -- they
  exist solely to hold the matching access-control tag, so their members
  (that provider's developer, reviewer, and requester) can see that
  provider's tagged records and everyone else cannot -- except
  ``admin``/``super_admin``, who bypass access-control tags entirely
  regardless of group membership (see
  ``dependencies.auth.get_access_tag_ids``). That makes both the
  role-inheritance and the access-control side of the group feature visible
  in the demo dataset itself: remove a user from their role group and their
  access disappears on the next request; remove one of a trio from their
  AC group instead and that provider's records disappear from what they can
  see.

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
from models.mcp_server import McpCommand, MCPServer, McpTransport, ScriptLanguage
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

#: Fixed identifier of the demo AWS ``reviewer`` user (who publishes the
#: EC2-launch workflow the AWS developer built).
DEMO_AWS_REVIEWER_USER_ID = "00000000-0000-0000-0000-00000000d007"

#: Fixed identifier of the demo GCP ``reviewer`` user (who publishes the
#: GKE-pod-restart workflow the GCP developer built).
DEMO_GCP_REVIEWER_USER_ID = "00000000-0000-0000-0000-00000000d008"

#: Fixed identifier of the demo Azure ``developer`` user (who builds the
#: secret-rotation workflow).
DEMO_AZURE_DEVELOPER_USER_ID = "00000000-0000-0000-0000-00000000d009"

#: Fixed identifier of the demo Azure ``reviewer`` user (who publishes the
#: secret-rotation workflow the Azure developer built).
DEMO_AZURE_REVIEWER_USER_ID = "00000000-0000-0000-0000-00000000d00a"

#: Fixed identifier of the demo Azure ``requester`` user (who runs the
#: secret-rotation workflow).
DEMO_AZURE_REQUESTER_USER_ID = "00000000-0000-0000-0000-00000000d00b"

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

#: Fixed identifier of the demo ``Demo Reviewers`` user group.
DEMO_REVIEWERS_GROUP_ID = "00000000-0000-0000-0000-00000000d406"

#: Fixed identifier of the demo ``Demo Azure Group`` user group, which grants
#: no role and exists solely to hold the access-control ``Azure`` tag.
DEMO_AZURE_GROUP_ID = "00000000-0000-0000-0000-00000000d407"

#: Fixed identifier of the demo Secret holding the AWS credentials.
DEMO_AWS_SECRET_ID = "00000000-0000-0000-0000-00000000d101"

#: Fixed identifier of the demo Secret holding the Google Cloud API key.
DEMO_GCP_SECRET_ID = "00000000-0000-0000-0000-00000000d102"

#: Fixed identifier of the demo Secret holding the Azure service principal.
DEMO_AZURE_SECRET_ID = "00000000-0000-0000-0000-00000000d103"

#: Fixed identifier of the demo AWS MCP server.
DEMO_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d201"

#: Fixed identifier of the demo GKE MCP server.
DEMO_GKE_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d202"

#: Fixed identifier of the demo EC2 Cost Estimator script MCP server.
DEMO_COST_ESTIMATOR_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d203"

#: Fixed identifier of the demo Kubernetes Manifest Toolkit script MCP server.
DEMO_K8S_TOOLKIT_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d204"

#: Fixed identifier of the demo Azure MCP server.
DEMO_AZURE_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d205"

#: Fixed identifier of the demo Secret Value Generator script MCP server.
DEMO_SECRET_GENERATOR_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d206"

#: Fixed identifier of the demo ``aws-ec2-launch`` agent skill.
DEMO_AGENT_SKILL_ID = "00000000-0000-0000-0000-00000000d301"

#: Fixed identifier of the demo ``gke-pod-restart`` agent skill.
DEMO_GKE_SKILL_ID = "00000000-0000-0000-0000-00000000d302"

#: Fixed identifier of the demo ``azure-keyvault-secret-rotation`` agent skill.
DEMO_AZURE_SKILL_ID = "00000000-0000-0000-0000-00000000d303"

#: Fixed identifier of the demo ``AWS`` tag.
DEMO_AWS_TAG_ID = "00000000-0000-0000-0000-00000000d501"

#: Fixed identifier of the demo ``Approval Required`` tag.
DEMO_APPROVAL_TAG_ID = "00000000-0000-0000-0000-00000000d502"

#: Fixed identifier of the demo ``GCP`` tag.
DEMO_GCP_TAG_ID = "00000000-0000-0000-0000-00000000d503"

#: Fixed identifier of the demo ``Azure`` tag.
DEMO_AZURE_TAG_ID = "00000000-0000-0000-0000-00000000d504"

#: Fixed identifier of the demo ``call_aws`` tool mock (AWS MCP server).
DEMO_CALL_AWS_MOCK_ID = "00000000-0000-0000-0000-00000000d601"

#: Fixed identifier of the demo ``run_script`` tool mock (AWS MCP server).
DEMO_RUN_SCRIPT_MOCK_ID = "00000000-0000-0000-0000-00000000d602"

#: Fixed identifier of the demo ``request_approval`` built-in tool mock.
DEMO_REQUEST_APPROVAL_MOCK_ID = "00000000-0000-0000-0000-00000000d603"

#: Fixed identifier of the demo ``delete_k8s_resource`` tool mock (GKE MCP server).
DEMO_DELETE_POD_MOCK_ID = "00000000-0000-0000-0000-00000000d604"

#: Fixed identifier of the demo ``patch_k8s_resource`` tool mock (GKE MCP server).
DEMO_PATCH_WORKLOAD_MOCK_ID = "00000000-0000-0000-0000-00000000d605"

#: Fixed identifier of the demo ``keyvault_secret_create`` tool mock (Azure MCP
#: server).
DEMO_SECRET_CREATE_MOCK_ID = "00000000-0000-0000-0000-00000000d606"

#: Fixed identifier of the demo ``keyvault_secret_get`` tool mock (Azure MCP
#: server).
DEMO_SECRET_LIST_MOCK_ID = "00000000-0000-0000-0000-00000000d607"

#: Name of the demo tag shared by the secret, MCP server, and agent skill.
DEMO_AWS_TAG_NAME = "AWS"

#: Name of the demo tag shared by the Google Cloud secret and MCP server.
DEMO_GCP_TAG_NAME = "GCP"

#: Name of the demo tag shared by the Azure secret, MCP servers, and skill.
DEMO_AZURE_TAG_NAME = "Azure"

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

#: Name of the demo Secret holding the Google Cloud credential JSON. Its
#: single entry is referenced from the demo GKE MCP server's ``headers`` by a
#: ``${gcp-token:NAME/KEY}`` placeholder, which mints an access token from it.
DEMO_GCP_SECRET_NAME = "demo-gcp-credentials"

#: Entry key of the Google Cloud credential JSON within
#: :data:`DEMO_GCP_SECRET_NAME`.
DEMO_GCP_CREDENTIALS_ENTRY_KEY = "GOOGLE_CREDENTIALS_JSON"

#: Name of the demo Secret holding the Azure service principal. Its three
#: entries are embedded in the demo Azure MCP server's ``env`` as
#: ``${secret:NAME/KEY}`` placeholders, under the same names the Azure SDK's
#: ``EnvironmentCredential`` reads.
DEMO_AZURE_SECRET_NAME = "demo-azure-credentials"

#: Entry key of the Microsoft Entra tenant id within
#: :data:`DEMO_AZURE_SECRET_NAME`.
DEMO_AZURE_TENANT_ENTRY_KEY = "AZURE_TENANT_ID"

#: Entry key of the service principal's client id within
#: :data:`DEMO_AZURE_SECRET_NAME`.
DEMO_AZURE_CLIENT_ID_ENTRY_KEY = "AZURE_CLIENT_ID"

#: Entry key of the service principal's client secret within
#: :data:`DEMO_AZURE_SECRET_NAME`.
DEMO_AZURE_CLIENT_SECRET_ENTRY_KEY = "AZURE_CLIENT_SECRET"

#: Name of the demo MCP server as shown in the admin UI.
DEMO_MCP_SERVER_NAME = "AWS MCP Server"

#: Name of the demo GKE MCP server as shown in the admin UI.
DEMO_GKE_MCP_SERVER_NAME = "GKE MCP Server"

#: Name of the demo EC2 Cost Estimator script server as shown in the admin UI.
DEMO_COST_ESTIMATOR_MCP_SERVER_NAME = "EC2 Cost Estimator"

#: Name of the demo Kubernetes Manifest Toolkit script server in the admin UI.
DEMO_K8S_TOOLKIT_MCP_SERVER_NAME = "Kubernetes Manifest Toolkit"

#: Name of the demo Azure MCP server as shown in the admin UI.
DEMO_AZURE_MCP_SERVER_NAME = "Azure MCP Server"

#: Name of the demo Secret Value Generator script server in the admin UI.
DEMO_SECRET_GENERATOR_MCP_SERVER_NAME = "Secret Value Generator"

#: Name of the demo agent skill as shown in the admin UI.
DEMO_AGENT_SKILL_NAME = "Demo AWS EC2 Launch"

#: Name of the demo GKE pod-restart agent skill in the admin UI.
DEMO_GKE_SKILL_NAME = "Demo GKE Pod Restart"

#: Name of the demo Azure Key Vault secret-rotation agent skill in the admin UI.
DEMO_AZURE_SKILL_NAME = "Demo Azure Key Vault Secret Rotation"

#: Name of the demo ``call_aws`` tool mock as shown in the admin UI.
DEMO_CALL_AWS_MOCK_NAME = "Demo AWS call_aws (EC2 launch success)"

#: Name of the demo ``run_script`` tool mock as shown in the admin UI.
DEMO_RUN_SCRIPT_MOCK_NAME = "Demo AWS run_script (EC2 launch success)"

#: Name of the demo ``request_approval`` tool mock as shown in the admin UI.
DEMO_REQUEST_APPROVAL_MOCK_NAME = "Demo request_approval (always approved)"

#: Name of the demo ``delete_k8s_resource`` tool mock as shown in the admin UI.
DEMO_DELETE_POD_MOCK_NAME = "Demo GKE delete_k8s_resource (pod restart success)"

#: Name of the demo ``patch_k8s_resource`` tool mock as shown in the admin UI.
DEMO_PATCH_WORKLOAD_MOCK_NAME = "Demo GKE patch_k8s_resource (rolling restart success)"

#: Name of the demo ``keyvault_secret_create`` tool mock as shown in the admin UI.
DEMO_SECRET_CREATE_MOCK_NAME = "Demo Azure keyvault_secret_create (rotation success)"

#: Name of the demo ``keyvault_secret_get`` tool mock as shown in the admin UI.
DEMO_SECRET_LIST_MOCK_NAME = "Demo Azure keyvault_secret_get (secret list)"

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

#: Request header the demo GKE MCP server sends its OAuth 2.0 access token
#: in. Its value is ``Bearer`` plus a ``${gcp-token:NAME/KEY}`` placeholder
#: resolved at connection time (see :mod:`infrastructure.google_token`), so
#: neither the credential nor a token ever lands in the ``mcp_servers`` row.
_DEMO_GCP_AUTH_HEADER = "Authorization"

#: Package the demo Azure MCP server is launched from, pinned for the same
#: reason as :data:`_DEMO_MCP_PROXY_PACKAGE`. npm publishes the 3.x line only
#: under prerelease versions, which ``latest`` points at.
_DEMO_AZURE_MCP_PACKAGE = "@azure/mcp@3.0.0-beta.50"

#: Arguments after ``-y <package>`` that start the demo Azure MCP server.
#: ``--namespace keyvault`` keeps it to the Key Vault tools; ``--mode all``
#: exposes each operation as its own tool (``keyvault_secret_create``,
#: ``keyvault_secret_get``, ...) rather than one ``keyvault`` tool taking a
#: command, so a tool mock or an approval can single out the write.
#: ``--dangerously-disable-elicitation`` is required because A2Flow's MCP
#: client does not answer elicitation requests yet: without it the server
#: asks for consent before every secret operation, the request is refused,
#: and the call fails. The consent it would ask for is given by the manager
#: who approves the rotation instead -- the sample skill writes nothing until
#: that approval comes back. Drop the flag once elicitation can be answered
#: in the chat.
_DEMO_AZURE_MCP_ARGS = (
    "server",
    "start",
    "--namespace",
    "keyvault",
    "--mode",
    "all",
    "--dangerously-disable-elicitation",
)

#: Azure SDK credential the demo Azure MCP server is told to use. Pinning it to
#: ``EnvironmentCredential`` makes the server read the service principal from
#: its ``env`` and nothing else, instead of probing a developer sign-in
#: (Azure CLI, Visual Studio Code, a browser) that a headless sandbox lacks.
_DEMO_AZURE_TOKEN_CREDENTIALS = "EnvironmentCredential"

#: Repository the demo agent skills are cloned from, and the path within it to
#: each one's ``SKILL.md``.
_DEMO_SKILL_REPO_URL = "https://github.com/kaitoy/a2flow"
_DEMO_AWS_SKILL_REPO_PATH = "sample_skills/aws-ec2-launch"
_DEMO_GKE_SKILL_REPO_PATH = "sample_skills/gke-pod-restart"
_DEMO_AZURE_SKILL_REPO_PATH = "sample_skills/azure-keyvault-secret-rotation"

#: Stored in place of an AWS credential or Google Cloud credential JSON when
#: the matching ``DEMO_*`` variable is unset. The demo is then complete in shape
#: but cannot reach the provider until an operator edits the secret in the
#: admin UI.
_PLACEHOLDER_SECRET_VALUE = "REPLACE_ME"

#: Description shown on the demo AWS secret in the admin UI.
_DEMO_AWS_SECRET_DESCRIPTION = (
    "AWS access key and secret key used by the demo MCP server to sign "
    "requests to the managed AWS MCP endpoint."
)

#: Description shown on the demo Google Cloud secret in the admin UI.
_DEMO_GCP_SECRET_DESCRIPTION = (
    "Google Cloud credential JSON (a service account key, or the authorized-user "
    "JSON written by gcloud auth application-default login) the demo GKE MCP "
    "server mints its OAuth 2.0 access token from."
)

#: Description shown on the demo Azure secret in the admin UI.
_DEMO_AZURE_SECRET_DESCRIPTION = (
    "Azure service principal (tenant id, client id, and client secret) the "
    "demo Azure MCP server authenticates to Key Vault with."
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
    "including mutating tools such as rolling-restarting a workload or "
    "deleting a pod."
)

#: Description shown on the demo Azure MCP server in the admin UI.
_DEMO_AZURE_MCP_SERVER_DESCRIPTION = (
    "Microsoft's Azure MCP Server, limited to its Key Vault tools, for "
    "listing and writing Key Vault secrets, keys, and certificates. Started "
    "with user confirmation (elicitation) disabled: a manager's approval "
    "stands in for it."
)

#: Description shown on the demo EC2 Cost Estimator server in the admin UI.
_DEMO_COST_ESTIMATOR_DESCRIPTION = (
    "Python script server that estimates the monthly On-Demand cost of EC2 "
    "instance types in a region, from prices fetched live from the AWS Price "
    "List. Read-only."
)

#: Description shown on the demo Kubernetes Manifest Toolkit server in the
#: admin UI.
_DEMO_K8S_TOOLKIT_DESCRIPTION = (
    "JavaScript script server that validates Kubernetes manifests and builds "
    "the patch that rolling-restarts a workload. Computes only; it never "
    "reaches a cluster."
)

#: Description shown on the demo Secret Value Generator server in the admin UI.
_DEMO_SECRET_GENERATOR_DESCRIPTION = (
    "JavaScript script server that generates a cryptographically random "
    "secret value. Computes only; it never reaches Azure."
)

#: Packages the EC2 Cost Estimator installs, pinned for the same reason as
#: :data:`_DEMO_MCP_PROXY_PACKAGE`.
_DEMO_COST_ESTIMATOR_PACKAGES = ["boto3==1.43.103"]

#: Packages the Kubernetes Manifest Toolkit installs, pinned likewise.
_DEMO_K8S_TOOLKIT_PACKAGES = ["js-yaml@5.4.2"]

#: Source of the EC2 Cost Estimator. It prices through the Price List Query
#: API, which needs AWS credentials (with ``pricing:GetProducts``) but returns
#: only the matching products -- the unauthenticated bulk offer file for EC2
#: runs to gigabytes per region.
_DEMO_COST_ESTIMATOR_SOURCE = '''\
"""Estimate EC2 On-Demand costs from the AWS Price List Query API."""

import json

import boto3

#: Average days in a month (365 / 12).
_DAYS_PER_MONTH = 30.42


def _hourly_usd(instance_type: str, region: str) -> float:
    # The Price List Query API is served from us-east-1 whatever region is priced.
    client = boto3.client("pricing", region_name="us-east-1")
    filters = {
        "instanceType": instance_type,
        "regionCode": region,
        "operatingSystem": "Linux",
        "tenancy": "Shared",
        "preInstalledSw": "NA",
        "capacitystatus": "Used",
    }
    response = client.get_products(
        ServiceCode="AmazonEC2",
        Filters=[
            {"Type": "TERM_MATCH", "Field": field, "Value": value}
            for field, value in filters.items()
        ],
        MaxResults=1,
    )
    if not response["PriceList"]:
        raise ValueError(f"No On-Demand Linux price for {instance_type} in {region}")
    product = json.loads(response["PriceList"][0])
    term = next(iter(product["terms"]["OnDemand"].values()))
    dimension = next(iter(term["priceDimensions"].values()))
    return float(dimension["pricePerUnit"]["USD"])


def estimate_monthly_cost(
    instance_type: str, region: str = "us-east-1", hours_per_day: float = 24
) -> dict:
    """Estimate the monthly On-Demand cost of one EC2 instance, in USD.

    Prices a Linux instance on shared tenancy with no pre-installed software,
    fetched live from the AWS Price List. Storage and data transfer are not
    included.

    Args:
        instance_type: Instance type, such as t3.micro.
        region: Region code, such as ap-northeast-1.
        hours_per_day: Hours per day the instance runs.
    """
    hourly = _hourly_usd(instance_type, region)
    return {
        "instance_type": instance_type,
        "region": region,
        "hourly_usd": hourly,
        "hours_per_day": hours_per_day,
        "monthly_usd": round(hourly * hours_per_day * _DAYS_PER_MONTH, 2),
        "assumptions": (
            "Linux, shared tenancy, On-Demand; excludes EBS and data transfer"
        ),
    }


def compare_instance_types(
    instance_types: list[str], region: str = "us-east-1"
) -> list[dict]:
    """Compare the monthly On-Demand cost of EC2 instance types, cheapest first.

    Args:
        instance_types: Instance types to compare, such as ["t3.micro", "t3.small"].
        region: Region code, such as ap-northeast-1.
    """
    estimates = [estimate_monthly_cost(t, region) for t in instance_types]
    return sorted(estimates, key=lambda estimate: estimate["monthly_usd"])
'''

#: Source of the Kubernetes Manifest Toolkit. Each exported function takes the
#: call's arguments object and carries its own ``description`` and
#: ``inputSchema`` (see ``infrastructure/script_runners/node_runner.mjs``).
_DEMO_K8S_TOOLKIT_SOURCE = """\
import { loadAll } from "js-yaml";

const RESTARTABLE_KINDS = ["Deployment", "StatefulSet", "DaemonSet"];

export function validate_manifest({ manifest }) {
  let documents;
  try {
    documents = loadAll(manifest).filter((doc) => doc != null);
  } catch (error) {
    return { valid: false, error: String(error.message ?? error), documents: [] };
  }
  const results = documents.map((doc) => {
    if (typeof doc !== "object" || Array.isArray(doc)) {
      return { errors: ["document is not a mapping"] };
    }
    const errors = [];
    if (!doc.apiVersion) errors.push("missing apiVersion");
    if (!doc.kind) errors.push("missing kind");
    if (!doc.metadata?.name) errors.push("missing metadata.name");
    return {
      kind: doc.kind,
      name: doc.metadata?.name,
      namespace: doc.metadata?.namespace ?? "default",
      errors,
    };
  });
  return { valid: results.every((r) => r.errors.length === 0), documents: results };
}
validate_manifest.description =
  "Parse a Kubernetes manifest (one or more YAML documents) and check that " +
  "each document has apiVersion, kind, and metadata.name.";
validate_manifest.inputSchema = {
  type: "object",
  properties: { manifest: { type: "string", description: "The manifest YAML." } },
  required: ["manifest"],
};

export function build_restart_patch({ kind, name, namespace = "default" }) {
  if (!RESTARTABLE_KINDS.includes(kind)) {
    throw new Error(
      `${kind} cannot be rolling-restarted; use one of ${RESTARTABLE_KINDS.join(", ")}`,
    );
  }
  const restartedAt = new Date().toISOString();
  return {
    kind,
    name,
    namespace,
    patchType: "strategic-merge",
    patch: {
      spec: {
        template: {
          metadata: {
            annotations: { "kubectl.kubernetes.io/restartedAt": restartedAt },
          },
        },
      },
    },
  };
}
build_restart_patch.description =
  "Build the patch that rolling-restarts a Deployment, StatefulSet, or " +
  "DaemonSet -- the same one `kubectl rollout restart` applies.";
build_restart_patch.inputSchema = {
  type: "object",
  properties: {
    kind: { type: "string", enum: RESTARTABLE_KINDS },
    name: { type: "string", description: "The workload's name." },
    namespace: { type: "string", default: "default" },
  },
  required: ["kind", "name"],
};
"""

#: Source of the Secret Value Generator. Like the Kubernetes Manifest Toolkit,
#: the exported function takes the call's arguments object and carries its own
#: ``description`` and ``inputSchema``. It needs no packages: ``node:crypto``
#: is built in.
_DEMO_SECRET_GENERATOR_SOURCE = """\
import { randomBytes } from "node:crypto";

export function generate_secret_value({ length = 32 }) {
  if (!Number.isInteger(length) || length < 16 || length > 256) {
    throw new Error("length must be an integer from 16 to 256");
  }
  // base64url of ceil(length * 3 / 4) random bytes, cut to the exact length.
  const value = randomBytes(Math.ceil((length * 3) / 4))
    .toString("base64url")
    .slice(0, length);
  return { value, length, alphabet: "base64url (A-Z a-z 0-9 - _)" };
}
generate_secret_value.description =
  "Generate a cryptographically random secret value of the given length, " +
  "using URL-safe base64 characters.";
generate_secret_value.inputSchema = {
  type: "object",
  properties: {
    length: { type: "integer", minimum: 16, maximum: 256, default: 32 },
  },
};
"""

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

#: Description shown on the demo ``Azure`` tag in the admin UI.
_DEMO_AZURE_TAG_DESCRIPTION = (
    "Resources that talk to Azure: credentials, MCP servers, and agent skills "
    "scoped to the Azure provider."
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
        id=DEMO_AWS_REVIEWER_USER_ID,
        username="demo-aws-reviewer",
        first_name="Grace",
        last_name="Holloway",
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
    _DemoUserSpec(
        id=DEMO_GCP_REVIEWER_USER_ID,
        username="demo-gcp-reviewer",
        first_name="Henry",
        last_name="Ito",
    ),
    _DemoUserSpec(
        id=DEMO_AZURE_DEVELOPER_USER_ID,
        username="demo-azure-developer",
        first_name="Isabel",
        last_name="Novak",
    ),
    _DemoUserSpec(
        id=DEMO_AZURE_REVIEWER_USER_ID,
        username="demo-azure-reviewer",
        first_name="Jonas",
        last_name="Keller",
    ),
    _DemoUserSpec(
        id=DEMO_AZURE_REQUESTER_USER_ID,
        username="demo-azure-requester",
        first_name="Kai",
        last_name="Lindqvist",
    ),
)

#: The demo user groups. ``Demo Approvers``, ``Demo Requesters``,
#: ``Demo Developers``, and ``Demo Reviewers`` each grant one role to their
#: members -- the sample skill looks for a user holding ``approver`` to route
#: its approval request to; ``requester`` is the role that may execute a
#: workflow; ``developer`` is the role that may build and register a
#: workflow, MCP server, or agent skill; ``reviewer`` is the role that may
#: publish or deactivate one. Granting each through a group rather than
#: directly is what makes the demo exercise role inheritance; every one of
#: the four holds several members, showing that a group's role reaches every
#: one of its members, not just a single account.
#:
#: ``Demo AWS Group``, ``Demo GCP Group``, and ``Demo Azure Group`` grant no
#: role at all (``role=None``) -- their only purpose is to hold the matching
#: access-control tag (see :func:`_seed_demo_tags`), so their members, and
#: only their members, can see that provider's tagged records. Each demo
#: developer/requester/reviewer therefore belongs to two groups: one for
#: their role, one for their provider's access.
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
        member_ids=(
            DEMO_AWS_REQUESTER_USER_ID,
            DEMO_GCP_REQUESTER_USER_ID,
            DEMO_AZURE_REQUESTER_USER_ID,
        ),
    ),
    _DemoGroupSpec(
        id=DEMO_DEVELOPERS_GROUP_ID,
        name="Demo Developers",
        description="People who can build workflows, MCP servers, and agent skills.",
        role=Role.developer,
        member_ids=(
            DEMO_AWS_DEVELOPER_USER_ID,
            DEMO_GCP_DEVELOPER_USER_ID,
            DEMO_AZURE_DEVELOPER_USER_ID,
        ),
    ),
    _DemoGroupSpec(
        id=DEMO_REVIEWERS_GROUP_ID,
        name="Demo Reviewers",
        description="People who can publish or deactivate a workflow.",
        role=Role.reviewer,
        member_ids=(
            DEMO_AWS_REVIEWER_USER_ID,
            DEMO_GCP_REVIEWER_USER_ID,
            DEMO_AZURE_REVIEWER_USER_ID,
        ),
    ),
    _DemoGroupSpec(
        id=DEMO_AWS_GROUP_ID,
        name="Demo AWS Group",
        description=("Holds the access-control 'AWS' tag; grants no role of its own."),
        role=None,
        member_ids=(
            DEMO_AWS_DEVELOPER_USER_ID,
            DEMO_AWS_REQUESTER_USER_ID,
            DEMO_AWS_REVIEWER_USER_ID,
        ),
    ),
    _DemoGroupSpec(
        id=DEMO_GCP_GROUP_ID,
        name="Demo GCP Group",
        description=("Holds the access-control 'GCP' tag; grants no role of its own."),
        role=None,
        member_ids=(
            DEMO_GCP_DEVELOPER_USER_ID,
            DEMO_GCP_REQUESTER_USER_ID,
            DEMO_GCP_REVIEWER_USER_ID,
        ),
    ),
    _DemoGroupSpec(
        id=DEMO_AZURE_GROUP_ID,
        name="Demo Azure Group",
        description=(
            "Holds the access-control 'Azure' tag; grants no role of its own."
        ),
        role=None,
        member_ids=(
            DEMO_AZURE_DEVELOPER_USER_ID,
            DEMO_AZURE_REQUESTER_USER_ID,
            DEMO_AZURE_REVIEWER_USER_ID,
        ),
    ),
)

#: The tool of the demo AWS MCP server that runs one AWS CLI command.
_DEMO_CALL_AWS_TOOL = "aws___call_aws"

#: The tool of the demo AWS MCP server that runs a script (AWS CLI + boto3).
_DEMO_RUN_SCRIPT_TOOL = "aws___run_script"

#: The tool of the demo GKE MCP server that patches a Kubernetes resource --
#: used here to trigger a rolling restart of a Deployment/StatefulSet by
#: bumping a restart-timestamp annotation on its pod template. Connected
#: directly over ``streamable_http`` with no proxy in between, so the tool
#: carries the bare name the Google-managed server itself declares, unlike
#: the AWS tools above (bridged, and namespaced, through
#: ``mcp-proxy-for-aws``).
_DEMO_PATCH_WORKLOAD_TOOL = "patch_k8s_resource"

#: The tool of the demo GKE MCP server that deletes a Kubernetes resource --
#: used here as the single-pod fallback restart path. Connected the same way
#: as :data:`_DEMO_PATCH_WORKLOAD_TOOL`.
_DEMO_DELETE_POD_TOOL = "delete_k8s_resource"

#: The tool of the demo Azure MCP server that writes a Key Vault secret.
#: Writing under an existing name adds a new version, which is how the sample
#: skill rotates one. Launched with ``--mode all`` and connected over stdio
#: with no proxy in between, so the tool carries the bare name the server
#: itself declares.
_DEMO_SECRET_CREATE_TOOL = "keyvault_secret_create"

#: The tool of the demo Azure MCP server that reads Key Vault secrets. Called
#: with no ``secret`` name it lists the vault's secrets, which is the only way
#: the sample skill uses it -- named, it would return the value.
_DEMO_SECRET_LIST_TOOL = "keyvault_secret_get"

#: Secret name shared by the Azure mocks' list and write results, so the story
#: they tell is self-consistent: the secret the run picks from the list is the
#: one that gets a new version.
_DEMO_MOCK_SECRET_NAME = "db-password"

#: Version id of the new secret version the ``keyvault_secret_create`` mock
#: reports.
_DEMO_MOCK_SECRET_VERSION = "3f0c2a9d8b7e4f6a9c1d2e3f4a5b6c7d"

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

#: Workload and pod identity shared by the demo GKE mocks' requests and
#: results, so the story they tell is self-consistent: the pod belongs to the
#: Deployment.
_DEMO_MOCK_WORKLOAD_KIND = "Deployment"
_DEMO_MOCK_WORKLOAD_NAME = "api"
_DEMO_MOCK_POD_NAME = "api-7d4f8-abc12"
_DEMO_MOCK_POD_NAMESPACE = "prod"

#: Structured result of the demo ``patch_k8s_resource`` mock: the workload
#: identity and rollout status a real pod-template patch against the GKE MCP
#: server would report back.
_DEMO_PATCH_WORKLOAD_RESULT: dict[str, Any] = {
    "kind": _DEMO_MOCK_WORKLOAD_KIND,
    "name": _DEMO_MOCK_WORKLOAD_NAME,
    "namespace": _DEMO_MOCK_POD_NAMESPACE,
    "status": "patched",
    "message": (
        f"{_DEMO_MOCK_WORKLOAD_KIND} {_DEMO_MOCK_WORKLOAD_NAME} pod template "
        "patched; rolling restart in progress (3/3 pods replaced)."
    ),
}

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

#: Structured result of the demo ``keyvault_secret_create`` mock: the
#: identity and attributes of the new secret version, as the Azure MCP server
#: reports a successful write. The value is deliberately absent -- the sample
#: skill never repeats a secret value, and a mock has no reason to make one up.
_DEMO_SECRET_CREATE_RESULT: dict[str, Any] = {
    "name": _DEMO_MOCK_SECRET_NAME,
    "version": _DEMO_MOCK_SECRET_VERSION,
    "id": (
        "https://demo-kv.vault.azure.net/secrets/"
        f"{_DEMO_MOCK_SECRET_NAME}/{_DEMO_MOCK_SECRET_VERSION}"
    ),
    "enabled": True,
    "createdOn": "2026-01-01T00:00:00+00:00",
    "updatedOn": "2026-01-01T00:00:00+00:00",
}

#: Structured result of the demo ``keyvault_secret_get`` mock: a listing of a
#: vault's secrets -- names and attributes, never values -- so a draft run has
#: something to pick the secret to rotate from.
_DEMO_SECRET_LIST_RESULT: dict[str, Any] = {
    "secrets": [
        {"name": _DEMO_MOCK_SECRET_NAME, "enabled": True},
        {"name": "storage-connection-string", "enabled": True},
        {"name": "third-party-api-key", "enabled": True},
    ]
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

#: Description shown on the demo ``keyvault_secret_create`` tool mock in the
#: admin UI.
_DEMO_SECRET_CREATE_MOCK_DESCRIPTION = (
    "Stubs the Azure MCP Server's keyvault_secret_create tool with a new "
    "secret version, so a draft run of the demo workflow completes its "
    "rotation step without reaching a real Key Vault."
)

#: Description shown on the demo ``keyvault_secret_get`` tool mock in the
#: admin UI.
_DEMO_SECRET_LIST_MOCK_DESCRIPTION = (
    "Stubs the Azure MCP Server's keyvault_secret_get tool with a made-up list "
    "of a vault's secrets, so a draft run of the demo workflow can choose the "
    "secret to rotate without reaching a real Key Vault."
)

#: Description shown on the demo ``request_approval`` tool mock in the admin UI.
_DEMO_REQUEST_APPROVAL_MOCK_DESCRIPTION = (
    "Stubs the built-in request_approval tool as approved, so a draft run of "
    "the demo workflow plays through without waiting on a manager's decision."
)

#: Description shown on the demo ``patch_k8s_resource`` tool mock in the admin UI.
_DEMO_PATCH_WORKLOAD_MOCK_DESCRIPTION = (
    "Stubs the GKE MCP Server's patch_k8s_resource tool with a successful "
    "rolling restart, so a draft run of the demo workflow completes its "
    "restart step without reaching a real GKE cluster."
)

#: Description shown on the demo ``delete_k8s_resource`` tool mock in the admin UI.
_DEMO_DELETE_POD_MOCK_DESCRIPTION = (
    "Stubs the GKE MCP Server's delete_k8s_resource tool with a successful "
    "pod deletion, so a draft run of the demo workflow can still complete "
    "the single-pod fallback restart path without reaching a real GKE "
    "cluster."
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
#: third and fourth stub the demo GKE MCP server's tools (see
#: :func:`_seed_demo_gke_mcp_server`) -- rolling-restarting a Deployment/
#: StatefulSet, and, as a fallback, deleting a single pod; the fifth stubs the
#: demo Azure MCP server's secret listing and write (see
#: :func:`_seed_demo_azure_mcp_server`); the seventh stubs the built-in
#: :data:`~models.mcp_tool_mock.REQUEST_APPROVAL_TOOL`. Checked in a draft
#: run's Run dialog, together they let any of the three sample workflows run
#: end to end without reaching AWS, a real GKE cluster, a real Key Vault, or
#: an approver.
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
        id=DEMO_PATCH_WORKLOAD_MOCK_ID,
        name=DEMO_PATCH_WORKLOAD_MOCK_NAME,
        description=_DEMO_PATCH_WORKLOAD_MOCK_DESCRIPTION,
        mcp_server_id=DEMO_GKE_MCP_SERVER_ID,
        tool_name=_DEMO_PATCH_WORKLOAD_TOOL,
        response={"kind": "structured", "value": _DEMO_PATCH_WORKLOAD_RESULT},
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
        id=DEMO_SECRET_CREATE_MOCK_ID,
        name=DEMO_SECRET_CREATE_MOCK_NAME,
        description=_DEMO_SECRET_CREATE_MOCK_DESCRIPTION,
        mcp_server_id=DEMO_AZURE_MCP_SERVER_ID,
        tool_name=_DEMO_SECRET_CREATE_TOOL,
        response={"kind": "structured", "value": _DEMO_SECRET_CREATE_RESULT},
    ),
    _DemoToolMockSpec(
        id=DEMO_SECRET_LIST_MOCK_ID,
        name=DEMO_SECRET_LIST_MOCK_NAME,
        description=_DEMO_SECRET_LIST_MOCK_DESCRIPTION,
        mcp_server_id=DEMO_AZURE_MCP_SERVER_ID,
        tool_name=_DEMO_SECRET_LIST_TOOL,
        response={"kind": "structured", "value": _DEMO_SECRET_LIST_RESULT},
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
    await _seed_demo_cost_estimator_mcp_server(session, tenant_id)
    await _seed_demo_k8s_toolkit_mcp_server(session, tenant_id)
    await _seed_demo_azure_mcp_server(session, tenant_id)
    await _seed_demo_secret_generator_mcp_server(session, tenant_id)
    await _seed_demo_tool_mocks(session, tenant_id)
    new_skill_ids = [
        skill_id
        for skill_id in (
            await _seed_demo_agent_skill(session, tenant_id),
            await _seed_demo_gke_agent_skill(session, tenant_id),
            await _seed_demo_azure_agent_skill(session, tenant_id),
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
    rather than allowed to fail startup. The same holds for the
    ``keyvault_secret_get`` and ``keyvault_secret_create`` mocks and the
    Azure MCP server.

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
        session,
        AgentSkill,
        DEMO_AZURE_SKILL_ID,
        label="Azure secret-rotation agent skill",
    )
    await _delete_demo_row(
        session, MCPServer, DEMO_MCP_SERVER_ID, label="AWS MCP server"
    )
    await _delete_demo_row(
        session, MCPServer, DEMO_GKE_MCP_SERVER_ID, label="GKE MCP server"
    )
    await _delete_demo_row(
        session,
        MCPServer,
        DEMO_COST_ESTIMATOR_MCP_SERVER_ID,
        label="EC2 Cost Estimator MCP server",
    )
    await _delete_demo_row(
        session,
        MCPServer,
        DEMO_K8S_TOOLKIT_MCP_SERVER_ID,
        label="Kubernetes Manifest Toolkit MCP server",
    )
    await _delete_demo_row(
        session, MCPServer, DEMO_AZURE_MCP_SERVER_ID, label="Azure MCP server"
    )
    await _delete_demo_row(
        session,
        MCPServer,
        DEMO_SECRET_GENERATOR_MCP_SERVER_ID,
        label="Secret Value Generator MCP server",
    )
    await _delete_demo_row(
        session, Secret, DEMO_AWS_SECRET_ID, label="AWS credentials secret"
    )
    await _delete_demo_row(
        session, Secret, DEMO_GCP_SECRET_ID, label="Google Cloud API key secret"
    )
    await _delete_demo_row(
        session, Secret, DEMO_AZURE_SECRET_ID, label="Azure credentials secret"
    )
    await _delete_demo_row(
        session, Tag, DEMO_AWS_TAG_ID, label=f"tag '{DEMO_AWS_TAG_NAME}'"
    )
    await _delete_demo_row(
        session, Tag, DEMO_GCP_TAG_ID, label=f"tag '{DEMO_GCP_TAG_NAME}'"
    )
    await _delete_demo_row(
        session, Tag, DEMO_AZURE_TAG_ID, label=f"tag '{DEMO_AZURE_TAG_NAME}'"
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


async def _seed_demo_secrets(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo AWS, Google Cloud, and Azure credential secrets.

    The AWS access key and secret key live in a single secret as two entries,
    the way a Vault KV path holds several keys; the Google Cloud credential
    JSON is a second secret with a single entry; the Azure service
    principal's tenant id, client id, and client secret are a third secret
    with three entries. Values come from ``DEMO_AWS_ACCESS_KEY_ID`` /
    ``DEMO_AWS_SECRET_ACCESS_KEY`` / ``DEMO_GCP_CREDENTIALS_JSON`` /
    ``DEMO_AZURE_TENANT_ID`` / ``DEMO_AZURE_CLIENT_ID`` /
    ``DEMO_AZURE_CLIENT_SECRET`` when set, so a fully working demo is one
    restart away, and fall back to a placeholder otherwise.
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
                    DEMO_GCP_CREDENTIALS_ENTRY_KEY: cipher.encrypt(
                        settings.demo_gcp_credentials_json or _PLACEHOLDER_SECRET_VALUE
                    ),
                },
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            ),
            label=f"secret '{DEMO_GCP_SECRET_NAME}'",
        )
    if await session.get(Secret, DEMO_AZURE_SECRET_ID) is None:
        await _insert(
            session,
            Secret(
                id=DEMO_AZURE_SECRET_ID,
                tenant_id=tenant_id,
                name=DEMO_AZURE_SECRET_NAME,
                description=_DEMO_AZURE_SECRET_DESCRIPTION,
                type=SecretType.local,
                entries={
                    DEMO_AZURE_TENANT_ENTRY_KEY: cipher.encrypt(
                        settings.demo_azure_tenant_id or _PLACEHOLDER_SECRET_VALUE
                    ),
                    DEMO_AZURE_CLIENT_ID_ENTRY_KEY: cipher.encrypt(
                        settings.demo_azure_client_id or _PLACEHOLDER_SECRET_VALUE
                    ),
                    DEMO_AZURE_CLIENT_SECRET_ENTRY_KEY: cipher.encrypt(
                        settings.demo_azure_client_secret or _PLACEHOLDER_SECRET_VALUE
                    ),
                },
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            ),
            label=f"secret '{DEMO_AZURE_SECRET_NAME}'",
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
    delete-only variants Google also publishes. Google Cloud MCP servers do
    not accept API keys, so it authenticates with an OAuth 2.0 access token
    sent as the :data:`_DEMO_GCP_AUTH_HEADER` bearer header; the value is a
    ``${gcp-token:NAME/KEY}`` placeholder that
    :mod:`infrastructure.google_token` turns into a fresh token at connection
    time from the credential JSON in the demo secret, so neither the
    credential nor a token ever lands in the ``mcp_servers`` row. Like the AWS
    demo server, its tools can mutate real infrastructure --
    rolling-restarting a workload or deleting a Pod, in particular.

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
                _DEMO_GCP_AUTH_HEADER: (
                    "Bearer "
                    f"${{gcp-token:{DEMO_GCP_SECRET_NAME}/{DEMO_GCP_CREDENTIALS_ENTRY_KEY}}}"
                ),
            },
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"MCP server '{DEMO_GKE_MCP_SERVER_NAME}'",
    )


async def _seed_demo_cost_estimator_mcp_server(
    session: AsyncSession, tenant_id: str
) -> None:
    """Create the demo EC2 Cost Estimator, a Python script MCP server.

    Its tools price EC2 instance types through the AWS Price List Query API
    with ``boto3``, installed from the row's ``packages``. The credentials
    are the same ``${secret:NAME/KEY}`` placeholders as the AWS MCP server's
    (see :func:`_seed_demo_mcp_server`), and ``AWS_REGION`` carries
    ``DEMO_AWS_REGION`` so boto3 has a default region; the tools themselves
    take the region to price as an argument. Nothing it does mutates AWS, so
    it has no tool mocks.

    Args:
        session: Database session used to read and insert the server.
        tenant_id: Id of the ``Default`` tenant the server belongs to.
    """
    if await session.get(MCPServer, DEMO_COST_ESTIMATOR_MCP_SERVER_ID) is not None:
        return
    await _insert(
        session,
        MCPServer(
            id=DEMO_COST_ESTIMATOR_MCP_SERVER_ID,
            tenant_id=tenant_id,
            name=DEMO_COST_ESTIMATOR_MCP_SERVER_NAME,
            description=_DEMO_COST_ESTIMATOR_DESCRIPTION,
            transport=McpTransport.script,
            language=ScriptLanguage.python,
            source=_DEMO_COST_ESTIMATOR_SOURCE,
            packages=list(_DEMO_COST_ESTIMATOR_PACKAGES),
            headers={},
            env={
                "AWS_ACCESS_KEY_ID": (
                    f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_ACCESS_KEY_ENTRY_KEY}}}"
                ),
                "AWS_SECRET_ACCESS_KEY": (
                    f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_SECRET_KEY_ENTRY_KEY}}}"
                ),
                "AWS_REGION": get_settings().demo_aws_region,
            },
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"MCP server '{DEMO_COST_ESTIMATOR_MCP_SERVER_NAME}'",
    )


async def _seed_demo_k8s_toolkit_mcp_server(
    session: AsyncSession, tenant_id: str
) -> None:
    """Create the demo Kubernetes Manifest Toolkit, a JavaScript script MCP server.

    Its tools parse manifests with ``js-yaml``, installed from the row's
    ``packages``, and build rolling-restart patches. It needs no credentials
    and never reaches a cluster, so it has no tool mocks.

    Args:
        session: Database session used to read and insert the server.
        tenant_id: Id of the ``Default`` tenant the server belongs to.
    """
    if await session.get(MCPServer, DEMO_K8S_TOOLKIT_MCP_SERVER_ID) is not None:
        return
    await _insert(
        session,
        MCPServer(
            id=DEMO_K8S_TOOLKIT_MCP_SERVER_ID,
            tenant_id=tenant_id,
            name=DEMO_K8S_TOOLKIT_MCP_SERVER_NAME,
            description=_DEMO_K8S_TOOLKIT_DESCRIPTION,
            transport=McpTransport.script,
            language=ScriptLanguage.javascript,
            source=_DEMO_K8S_TOOLKIT_SOURCE,
            packages=list(_DEMO_K8S_TOOLKIT_PACKAGES),
            headers={},
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"MCP server '{DEMO_K8S_TOOLKIT_MCP_SERVER_NAME}'",
    )


async def _seed_demo_azure_mcp_server(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo Azure MCP server.

    Microsoft ships the Azure MCP Server as an npm package, so the row is a
    ``stdio`` server launched with ``npx`` (see :data:`_DEMO_AZURE_MCP_ARGS`
    for the flags, including why elicitation is disabled). It authenticates
    as a service principal: the three ``env`` entries are
    ``${secret:NAME/KEY}`` placeholders resolved at connection time, under the
    variable names the Azure SDK's ``EnvironmentCredential`` reads, so the
    plaintext never lands in the ``mcp_servers`` row. Its Key Vault tools can
    write secrets, keys, and certificates, not only read them.

    Args:
        session: Database session used to read and insert the server.
        tenant_id: Id of the ``Default`` tenant the server belongs to.
    """
    if await session.get(MCPServer, DEMO_AZURE_MCP_SERVER_ID) is not None:
        return
    await _insert(
        session,
        MCPServer(
            id=DEMO_AZURE_MCP_SERVER_ID,
            tenant_id=tenant_id,
            name=DEMO_AZURE_MCP_SERVER_NAME,
            description=_DEMO_AZURE_MCP_SERVER_DESCRIPTION,
            transport=McpTransport.stdio,
            command=McpCommand.npx,
            args=["-y", _DEMO_AZURE_MCP_PACKAGE, *_DEMO_AZURE_MCP_ARGS],
            headers={},
            env={
                key: f"${{secret:{DEMO_AZURE_SECRET_NAME}/{key}}}"
                for key in (
                    DEMO_AZURE_TENANT_ENTRY_KEY,
                    DEMO_AZURE_CLIENT_ID_ENTRY_KEY,
                    DEMO_AZURE_CLIENT_SECRET_ENTRY_KEY,
                )
            }
            | {"AZURE_TOKEN_CREDENTIALS": _DEMO_AZURE_TOKEN_CREDENTIALS},
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"MCP server '{DEMO_AZURE_MCP_SERVER_NAME}'",
    )


async def _seed_demo_secret_generator_mcp_server(
    session: AsyncSession, tenant_id: str
) -> None:
    """Create the demo Secret Value Generator, a JavaScript script MCP server.

    Its one tool draws a random value with the built-in ``node:crypto``, so
    the row declares no packages. It needs no credentials and never reaches
    Azure, so it has no tool mocks.

    Args:
        session: Database session used to read and insert the server.
        tenant_id: Id of the ``Default`` tenant the server belongs to.
    """
    if await session.get(MCPServer, DEMO_SECRET_GENERATOR_MCP_SERVER_ID) is not None:
        return
    await _insert(
        session,
        MCPServer(
            id=DEMO_SECRET_GENERATOR_MCP_SERVER_ID,
            tenant_id=tenant_id,
            name=DEMO_SECRET_GENERATOR_MCP_SERVER_NAME,
            description=_DEMO_SECRET_GENERATOR_DESCRIPTION,
            transport=McpTransport.script,
            language=ScriptLanguage.javascript,
            source=_DEMO_SECRET_GENERATOR_SOURCE,
            packages=[],
            headers={},
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"MCP server '{DEMO_SECRET_GENERATOR_MCP_SERVER_NAME}'",
    )


async def _seed_demo_tool_mocks(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo tool mocks that let a draft run play through unattended.

    Seven stubs, all in the seeded ``Default`` tenant: ``call_aws`` and
    ``run_script`` on the demo AWS MCP server, each returning a successful EC2
    launch, ``patch_k8s_resource`` and ``delete_k8s_resource`` on the demo GKE
    MCP server, returning a successful rolling restart and a successful pod
    deletion respectively, ``keyvault_secret_get`` and
    ``keyvault_secret_create`` on the demo Azure MCP server, returning a list
    of a vault's secrets and a new secret version respectively, and the
    built-in
    :data:`~models.mcp_tool_mock.REQUEST_APPROVAL_TOOL`, returning ``approved``.
    Selected in a draft run's Run dialog, they let any of the three sample
    workflows run end to end without reaching AWS, a real GKE cluster, a real
    Key Vault, or waiting on an approver.

    Must run after :func:`_seed_demo_mcp_server`,
    :func:`_seed_demo_gke_mcp_server`, and :func:`_seed_demo_azure_mcp_server`:
    the first six mocks reference ``mcp_servers.id``. Each mock defines a
    single response, so it behaves as a constant however many times the run
    calls the tool. ``responses`` is stored
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

    A second sample skill, this one restarting workloads on a GKE cluster: by
    default it rolling-restarts a Deployment or StatefulSet through the GKE
    MCP server, falling back to deleting a single named pod when that is what
    the user wants gone, gated by a manager's explicit approval of the exact
    target. Registered exactly like :func:`_seed_demo_agent_skill` -- built as
    a table model directly, left ``pending`` for the caller to clone.

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
                "Rolling-restart a Deployment or StatefulSet on a GKE "
                "cluster through the GKE MCP server -- or, when only one "
                "pod should go, delete that pod -- gated by a manager's "
                "explicit approval of the exact target."
            ),
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"agent skill '{DEMO_GKE_SKILL_NAME}'",
    )
    return DEMO_GKE_SKILL_ID if created else None


async def _seed_demo_azure_agent_skill(
    session: AsyncSession, tenant_id: str
) -> str | None:
    """Create the demo agent skill pointing at the ``azure-keyvault-secret-rotation`` sample.

    A third sample skill: it agrees the Key Vault and the existing secret to
    rotate with the user, gets a manager's explicit approval of that exact
    target, then writes a freshly generated value as the secret's new version
    through the Azure MCP server -- never repeating the value in the chat.
    Registered exactly like :func:`_seed_demo_agent_skill` -- built as a table
    model directly, left ``pending`` for the caller to clone.

    Args:
        session: Database session used to read and insert the skill.
        tenant_id: Id of the ``Default`` tenant the skill belongs to.

    Returns:
        The skill's id when this call created it, else ``None``.
    """
    if await session.get(AgentSkill, DEMO_AZURE_SKILL_ID) is not None:
        return None
    created = await _insert(
        session,
        AgentSkill(
            id=DEMO_AZURE_SKILL_ID,
            tenant_id=tenant_id,
            name=DEMO_AZURE_SKILL_NAME,
            repo_url=_DEMO_SKILL_REPO_URL,
            repo_path=_DEMO_AZURE_SKILL_REPO_PATH,
            description=(
                "Rotate an Azure Key Vault secret to a freshly generated value "
                "through the Azure MCP server, gated by a manager's explicit "
                "approval of the exact vault and secret."
            ),
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"agent skill '{DEMO_AZURE_SKILL_NAME}'",
    )
    return DEMO_AZURE_SKILL_ID if created else None


async def _seed_demo_tags(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo tags and attach them across five of the six taggable kinds.

    ``AWS`` lands on the AWS secret, AWS MCP server, EC2 Cost Estimator, the
    EC2-launch agent skill, and the ``call_aws`` and ``run_script`` tool mocks;
    ``GCP`` lands on the Google Cloud secret, the GKE MCP server, the
    Kubernetes Manifest Toolkit, the pod-restart agent skill, and the
    ``patch_k8s_resource`` and ``delete_k8s_resource`` tool mocks; ``Azure``
    lands on the Azure secret, the Azure MCP server, the Secret Value
    Generator, the secret-rotation agent skill, and the
    ``keyvault_secret_get`` and ``keyvault_secret_create`` tool mocks; ``Approval Required`` lands on all
    three agent skills. ``AWS``, ``GCP``, and ``Azure`` are also each
    attached to their matching user group (``Demo AWS Group`` /
    ``Demo GCP Group`` / ``Demo Azure Group``) as access-control tags, which
    is what gates the records above to that group's members. All three are
    additionally attached to ``Demo Approvers`` directly, so either demo
    approver is an eligible destination for a request_approval call whose
    session carries any of them, regardless of which of the three demo skills
    the workflow came from.

    Must run after :func:`_seed_demo_secrets`, :func:`_seed_demo_mcp_server`,
    :func:`_seed_demo_gke_mcp_server`, :func:`_seed_demo_azure_mcp_server`,
    :func:`_seed_demo_secret_generator_mcp_server`,
    :func:`_seed_demo_agent_skill`, :func:`_seed_demo_gke_agent_skill`,
    :func:`_seed_demo_azure_agent_skill`, :func:`_seed_demo_tool_mocks`, and
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
            McpServerTag,
            resource_model=MCPServer,
            resource_id=DEMO_COST_ESTIMATOR_MCP_SERVER_ID,
            tag_id=DEMO_AWS_TAG_ID,
            label=(
                f"tag '{DEMO_AWS_TAG_NAME}' on MCP server "
                f"'{DEMO_COST_ESTIMATOR_MCP_SERVER_NAME}'"
            ),
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
        await _link_tag(
            session,
            UserGroupTag,
            resource_model=UserGroup,
            resource_id=DEMO_APPROVERS_GROUP_ID,
            tag_id=DEMO_AWS_TAG_ID,
            label=f"tag '{DEMO_AWS_TAG_NAME}' on user group 'Demo Approvers'",
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
            McpServerTag,
            resource_model=MCPServer,
            resource_id=DEMO_K8S_TOOLKIT_MCP_SERVER_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=(
                f"tag '{DEMO_GCP_TAG_NAME}' on MCP server "
                f"'{DEMO_K8S_TOOLKIT_MCP_SERVER_NAME}'"
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
            McpToolMockTag,
            resource_model=MCPToolMock,
            resource_id=DEMO_PATCH_WORKLOAD_MOCK_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=(
                f"tag '{DEMO_GCP_TAG_NAME}' on tool mock "
                f"'{DEMO_PATCH_WORKLOAD_MOCK_NAME}'"
            ),
        )
        await _link_tag(
            session,
            McpToolMockTag,
            resource_model=MCPToolMock,
            resource_id=DEMO_DELETE_POD_MOCK_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=(
                f"tag '{DEMO_GCP_TAG_NAME}' on tool mock '{DEMO_DELETE_POD_MOCK_NAME}'"
            ),
        )
        await _link_tag(
            session,
            UserGroupTag,
            resource_model=UserGroup,
            resource_id=DEMO_GCP_GROUP_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=f"tag '{DEMO_GCP_TAG_NAME}' on user group 'Demo GCP Group'",
        )
        await _link_tag(
            session,
            UserGroupTag,
            resource_model=UserGroup,
            resource_id=DEMO_APPROVERS_GROUP_ID,
            tag_id=DEMO_GCP_TAG_ID,
            label=f"tag '{DEMO_GCP_TAG_NAME}' on user group 'Demo Approvers'",
        )
    if await _ensure_demo_tag(
        session,
        tenant_id,
        DEMO_AZURE_TAG_ID,
        DEMO_AZURE_TAG_NAME,
        TagColor.violet,
        _DEMO_AZURE_TAG_DESCRIPTION,
        access_control=True,
    ):
        await _link_tag(
            session,
            SecretTag,
            resource_model=Secret,
            resource_id=DEMO_AZURE_SECRET_ID,
            tag_id=DEMO_AZURE_TAG_ID,
            label=f"tag '{DEMO_AZURE_TAG_NAME}' on secret '{DEMO_AZURE_SECRET_NAME}'",
        )
        for server_id, server_name in (
            (DEMO_AZURE_MCP_SERVER_ID, DEMO_AZURE_MCP_SERVER_NAME),
            (
                DEMO_SECRET_GENERATOR_MCP_SERVER_ID,
                DEMO_SECRET_GENERATOR_MCP_SERVER_NAME,
            ),
        ):
            await _link_tag(
                session,
                McpServerTag,
                resource_model=MCPServer,
                resource_id=server_id,
                tag_id=DEMO_AZURE_TAG_ID,
                label=f"tag '{DEMO_AZURE_TAG_NAME}' on MCP server '{server_name}'",
            )
        await _link_tag(
            session,
            AgentSkillTag,
            resource_model=AgentSkill,
            resource_id=DEMO_AZURE_SKILL_ID,
            tag_id=DEMO_AZURE_TAG_ID,
            label=f"tag '{DEMO_AZURE_TAG_NAME}' on agent skill '{DEMO_AZURE_SKILL_NAME}'",
        )
        for mock_id, mock_name in (
            (DEMO_SECRET_CREATE_MOCK_ID, DEMO_SECRET_CREATE_MOCK_NAME),
            (DEMO_SECRET_LIST_MOCK_ID, DEMO_SECRET_LIST_MOCK_NAME),
        ):
            await _link_tag(
                session,
                McpToolMockTag,
                resource_model=MCPToolMock,
                resource_id=mock_id,
                tag_id=DEMO_AZURE_TAG_ID,
                label=f"tag '{DEMO_AZURE_TAG_NAME}' on tool mock '{mock_name}'",
            )
        for group_id, group_name in (
            (DEMO_AZURE_GROUP_ID, "Demo Azure Group"),
            (DEMO_APPROVERS_GROUP_ID, "Demo Approvers"),
        ):
            await _link_tag(
                session,
                UserGroupTag,
                resource_model=UserGroup,
                resource_id=group_id,
                tag_id=DEMO_AZURE_TAG_ID,
                label=f"tag '{DEMO_AZURE_TAG_NAME}' on user group '{group_name}'",
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
        await _link_tag(
            session,
            AgentSkillTag,
            resource_model=AgentSkill,
            resource_id=DEMO_AZURE_SKILL_ID,
            tag_id=DEMO_APPROVAL_TAG_ID,
            label=(
                f"tag '{DEMO_APPROVAL_TAG_NAME}' on agent skill "
                f"'{DEMO_AZURE_SKILL_NAME}'"
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
