from mcp_types import ToolAnnotations

# Pure reads: Entity/get, Entity/query. Safe to call repeatedly, never
# changes GroupOffice state.
READ_ONLY_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

# Entity/set (create) or blob upload: adds new state, does not destroy
# anything, calling twice creates two records (not idempotent).
CREATE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)

# Entity/set (update/destroy): mutates or removes existing state. Calling
# twice with the same arguments has the same end state (idempotent), but the
# effect is destructive/irreversible.
MUTATE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=True,
)
