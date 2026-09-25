"""Read-only authoritative workflow/evidence projection for Cognitive Cockpit."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping

class CSWOperatorProjection:
    def __init__(self, state_path: Path) -> None:
        self.state_path = Path(state_path)
    def snapshot(self) -> list[dict[str, Any]]:
        if not self.state_path.exists(): return []
        data = json.loads(self.state_path.read_text())
        result=[]
        for key, record in (data.get("subjects") or {}).items():
            identity=dict(record)
            result.append({"workflow_id":identity.get("workflow_id"),
                           "statework_id":identity.get("statework_id"),
                           "subject_ref":identity.get("subject_ref"),
                           "state":identity.get("state"),"revision":identity.get("revision"),
                           "updated_at":identity.get("updated_at"),"provenance":"host_verified"})
        return result
