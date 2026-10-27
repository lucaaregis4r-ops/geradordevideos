"""Conservative query rounds: retain subject and action when broadening."""
from app.services.director.schemas import VisualBeat


def plan_queries(beat: VisualBeat) -> list[str]:
    queries = list(beat.queries)
    if beat.subject and beat.action:
        queries.extend([f"{beat.subject} {beat.action} {beat.context}".strip(),
                        f"{beat.subject} {beat.action} close up",
                        f"{beat.subject} {beat.action}"])
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))
