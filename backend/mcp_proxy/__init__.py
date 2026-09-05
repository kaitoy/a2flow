"""The container that actually reaches a tenant's registered MCP servers.

A registered MCP server is third-party code A2Flow launches on a tenant's
behalf: a stdio one is spawned as a child process, a remote one is reached over
the network. Running either in the backend process puts that code beside the
database credentials, the secret encryption key, the Vault credentials and the
LLM API keys. This package is the process that runs instead, in a container
that holds none of them.

**What it is not.** Not the gateway. Every rule about *whether* a call may
happen -- which tenant, which run, which task, which grant -- is decided in the
backend by :mod:`infrastructure.mcp_gateway`, against the database this process
cannot reach. What lands here is a decision already made, plus the evidence for
it, and this process re-checks that evidence at the boundary rather than taking
it on faith.

**What it holds.** The root CA's *public* certificate, its own server
certificate and key, and nothing else durable. Both arrive on a read-only
volume the backend wrote at startup; see
:mod:`infrastructure.mcp_transport_tls`.
"""
