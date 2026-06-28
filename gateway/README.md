# Memaix gateway

The MCP server at the core of Memaix. Implement against [`../docs/BUILD.md`](../docs/BUILD.md).

## Layout
```
src/memaix_gateway/
  __init__.py
  config.py     # load config/*.yaml, resolve *_ref secrets   [done]
  acl.py        # RBAC enforcement — the security boundary     [done]
  server.py     # MCP server entrypoint                        [stub]
  auth/         # OAuth 2.1 + PKCE + CIMD/DCR                   [todo]
  tools/        # email, calendar, files, memory, backlog      [stub]
```

## Run (once implemented)
```bash
pip install .
python -m memaix_gateway.server
```

`config.py` and `acl.py` are the specified starting points. Build the rest in the phase order in
BUILD.md, verifying RBAC isolation after each phase.
