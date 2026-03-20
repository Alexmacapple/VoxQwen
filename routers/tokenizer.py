"""Routes tokenizer — POST /tokenizer/encode, /tokenizer/decode."""

import logging

from fastapi import APIRouter, HTTPException

from schemas import TokenizeRequest, DetokenizeRequest
from models import load_preset_voice_model

logger = logging.getLogger("voxqwen")

router = APIRouter()


@router.post("/tokenizer/encode", tags=["Tokenizer"])
async def tokenizer_encode(request: TokenizeRequest):
    """Encode un texte en tokens."""
    try:
        model = load_preset_voice_model()

        tokenizer = None
        if hasattr(model, 'processor') and hasattr(model.processor, 'tokenizer'):
            tokenizer = model.processor.tokenizer
        elif hasattr(model, 'tokenizer'):
            tokenizer = model.tokenizer

        if tokenizer is None:
            raise HTTPException(
                status_code=500,
                detail="Tokenizer non disponible sur ce modele"
            )

        tokens = tokenizer.encode(request.text)

        return {
            "text": request.text,
            "tokens": tokens,
            "count": len(tokens),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tokenizer/decode", tags=["Tokenizer"])
async def tokenizer_decode(request: DetokenizeRequest):
    """Decode une liste de tokens en texte."""
    try:
        model = load_preset_voice_model()

        tokenizer = None
        if hasattr(model, 'processor') and hasattr(model.processor, 'tokenizer'):
            tokenizer = model.processor.tokenizer
        elif hasattr(model, 'tokenizer'):
            tokenizer = model.tokenizer

        if tokenizer is None:
            raise HTTPException(
                status_code=500,
                detail="Tokenizer non disponible sur ce modele"
            )

        text = tokenizer.decode(request.tokens)

        return {
            "tokens": request.tokens,
            "text": text,
            "count": len(request.tokens),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
