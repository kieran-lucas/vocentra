from __future__ import annotations

from .db import status_snapshot


def format_status(connection, job_id: str) -> str:
    status = status_snapshot(connection, job_id)
    pending = "none" if status["next_pending"] is None else str(status["next_pending"])
    return "\n".join((
        "Oxford A1 Pilot", "",
        f"Target:             {status['target']:>5}", f"Discovered:         {status['discovered']:>5}",
        f"Generated:          {status['generated']:>5}", f"Reviewed PASS:      {status['reviewed']:>5}",
        f"Repair needed:      {status['repair_needed']:>5}", f"Validated:          {status['validated']:>5}",
        f"Audio generated:    {status['audio_generated']:>5}", f"Audio encoded:      {status['audio_encoded']:>5}",
        f"Audio verified:     {status['audio_verified']:>5}", f"Imported:           {status['imported']:>5}", "",
        f"Last contiguous:    {status['last_contiguous']:>5}", f"Next pending:       {pending:>5}",
        f"Pending:            {status['pending']:>5}", f"Failed:             {status['failed']:>5}",
    ))
