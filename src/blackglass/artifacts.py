from uuid import uuid4


def new_artifact_id() -> str:
    return f"bg_{uuid4().hex}"
