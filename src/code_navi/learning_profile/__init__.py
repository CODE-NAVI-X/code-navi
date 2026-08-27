"""Student learning portrait: persist learning signals and aggregate a profile.

The portrait is keyed by an anonymous ``profile_id`` (== the practice module's
``learner_id`` UUID).  Detail reads stay session-scoped per CLAUDE.md rule 10,
but the profile endpoint itself aggregates across all sessions that share the
same ``profile_id``.
"""
