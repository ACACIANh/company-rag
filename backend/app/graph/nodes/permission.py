from core.fga.client import FGAClient


async def permission_node(state: dict, *, fga_client: FGAClient) -> dict:
    folders = await fga_client.get_readable_folders(state["user_id"])
    return {"allowed_folders": folders}
