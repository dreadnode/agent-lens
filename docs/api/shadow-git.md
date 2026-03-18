# Shadow Git

Invisible change tracking for working directories. Uses `GIT_DIR` + `GIT_WORK_TREE` to maintain a bare git repo that the agent never sees.

::: harness.shadow_git
    options:
      members:
        - ShadowGit
