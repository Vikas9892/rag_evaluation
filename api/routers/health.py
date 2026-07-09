from fastapi import APIRouter, Depends

from api.dependencies import get_service
from services.rag_service import RAGService

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict:
    return {"status": "healthy"}


@router.get("/metrics")
async def metrics(service: RAGService = Depends(get_service)) -> dict:
    return service.get_metrics()
