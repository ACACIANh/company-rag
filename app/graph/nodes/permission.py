from shared.fga.client import FGAClient


def permission_node(state: dict, *, fga_client: FGAClient) -> dict:
    perm = fga_client.get_permission(state["user_id"])
    return {
        "user_teams": perm.teams,
        "personal_doc_ids": perm.personal_docs,
    }
