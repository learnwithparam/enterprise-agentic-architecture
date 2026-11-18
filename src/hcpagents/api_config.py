"""What the sign-in screen needs to know before anyone is signed in. No secrets: pool and client ids are public."""

from fastapi import APIRouter

from hcpagents import auth, aws

router = APIRouter()


@router.get("/api/config")
def config():
    if aws.is_local():
        return {"mode": "local", "region": aws.REGION, "pool_id": None, "client_id": None}
    return {"mode": "cognito", "region": aws.REGION, "pool_id": auth.pool(), "client_id": auth.client_id()}
