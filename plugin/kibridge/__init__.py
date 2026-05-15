"""
KiBridge - KiCad <-> Copilot bridge plugin (and KiRouter client).

Registers five Action Plugins under the "PSS Tools" menu category:
  1. KiBridge: Inspect Board        - read-only inspection
  2. KiBridge: Open Workspace       - export the AI-bridge workspace folder
  3. KiBridge: Apply Workspace      - validate and apply Copilot's review
  4. KiBridge: Send to KiRouter     - POST board to KiRouter web app
  5. KiBridge: Import from KiRouter - pull routed result from KiRouter
"""
from .action_plugin           import KiBridgeInspector
from .workspace_open          import KiBridgeOpenWorkspace
from .workspace_apply         import KiBridgeApplyWorkspace
from .send_to_kirouter        import KiBridgeSendToKiRouter
from .import_from_kirouter    import KiBridgeImportFromKiRouter

KiBridgeInspector().register()
KiBridgeOpenWorkspace().register()
KiBridgeApplyWorkspace().register()
KiBridgeSendToKiRouter().register()
KiBridgeImportFromKiRouter().register()
