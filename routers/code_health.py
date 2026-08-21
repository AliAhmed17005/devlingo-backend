from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def test_code_health():
    """
    Test endpoint for Code Health router
    """
    return {
        "status": "success",
        "message": "Code Health router is active"
    }
