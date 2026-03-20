"""Enregistrement de tous les routeurs VoxQwen."""

from fastapi import FastAPI


def register_all(app: FastAPI):
    from .health import router as health_router
    from .synthesis import router as synthesis_router
    from .clone import router as clone_router
    from .voice_management import router as voice_mgmt_router
    from .batch import router as batch_router
    from .admin import router as admin_router
    from .tokenizer import router as tokenizer_router
    from .mcp_routes import router as mcp_router

    for router in [
        health_router, synthesis_router, clone_router,
        voice_mgmt_router, batch_router, admin_router,
        tokenizer_router, mcp_router,
    ]:
        app.include_router(router)
