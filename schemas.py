"""
Schemas Pydantic VoxQwen — validation des requetes et reponses.

Aucune dependance sur les autres modules du projet.
"""

from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


class DesignRequest(BaseModel):
    """Requete pour Voice Design."""
    text: str = Field(..., min_length=1, max_length=10000, description="Texte a synthetiser")
    voice_instruct: str = Field("", description="Description de la voix en langage naturel")
    language: str = Field("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it, auto")


class BatchPresetRequest(BaseModel):
    """Requete pour batch preset voice."""
    texts: List[str] = Field(..., min_length=1, max_length=100, description="Liste de textes a synthetiser (max 100)")
    voice: str = Field("Serena", description="Nom de la voix (native ou personnalisee)")
    language: str = Field("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it, auto")


class BatchDesignRequest(BaseModel):
    """Requete pour batch voice design."""
    texts: List[str] = Field(..., min_length=1, max_length=100, description="Liste de textes a synthetiser (max 100)")
    voice_instruct: str = Field("", description="Description de la voix en langage naturel")
    language: str = Field("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it, auto")


class TokenizeRequest(BaseModel):
    """Requete pour tokenizer encode."""
    text: str = Field(..., min_length=1, description="Texte a encoder")


class DetokenizeRequest(BaseModel):
    """Requete pour tokenizer decode."""
    tokens: List[int] = Field(..., min_length=1, description="Liste de tokens a decoder")


class LanguagesResponse(BaseModel):
    """Reponse pour la liste des langues."""
    languages: list[dict]
    count: int
    models: dict
    device: str


# ── MCP Models ───────────────────────────────────────────────────────────────


class MCPPresetRequest(BaseModel):
    """Requete MCP pour synthese avec voix preregle."""
    text: str = Field(..., min_length=1, max_length=2000, description="Texte a synthetiser")
    voice: str = Field("Serena", description="Voix native ou custom")
    language: str = Field("fr", description="Code langue ou 'auto'")


class MCPDesignRequest(BaseModel):
    """Requete MCP pour Voice Design."""
    text: str = Field(..., min_length=1, max_length=2000, description="Texte a synthetiser")
    voice_description: str = Field(..., min_length=5, max_length=500, description="Description de la voix")
    language: str = Field("fr", description="Code langue ou 'auto'")


class MCPCloneRequest(BaseModel):
    """Requete MCP pour clonage avec prompt existant."""
    text: str = Field(..., min_length=1, max_length=2000, description="Texte a synthetiser")
    prompt_id: str = Field(..., description="UUID du prompt (VOLATILE: perdu au redemarrage)")
    language: str = Field("fr", description="Code langue ou 'auto'")


class MCPCreatePromptRequest(BaseModel):
    """Requete MCP pour creer un prompt de clonage."""
    reference_audio_base64: str = Field(..., description="Audio WAV/MP3 en base64 (max 5MB, 1-30s)")
    reference_text: str = Field(..., min_length=1, max_length=1000, description="Transcription exacte")
    model: str = Field("1.7B", description="Modele: '1.7B' ou '0.6B'")
    name: Optional[str] = Field(None, max_length=50, description="Nom du prompt")

    @field_validator('model')
    @classmethod
    def validate_model(cls, v):
        if v not in ("1.7B", "0.6B"):
            raise ValueError("model doit etre '1.7B' ou '0.6B'")
        return v


class MCPPresetInstructRequest(BaseModel):
    """Requete MCP pour synthese avec controle emotionnel."""
    text: str = Field(..., min_length=1, max_length=2000, description="Texte a synthetiser")
    voice: str = Field("Serena", description="Voix native uniquement")
    instruct: str = Field("", description="Instruction emotion/style (ex: 'Ton joyeux')")
    language: str = Field("fr", description="Code langue ou 'auto'")


class MCPAudioResponse(BaseModel):
    """Reponse MCP contenant l'audio genere."""
    audio_base64: str = Field(..., description="Audio WAV encode en base64")
    format: str = Field("wav", description="Format audio")
    sample_rate: int = Field(..., description="Frequence d'echantillonnage")
    duration_ms: int = Field(..., description="Duree en millisecondes")
    voice_used: str = Field(..., description="Voix utilisee")
    model_used: str = Field(..., description="Modele utilise")
    warning: Optional[str] = Field(None, description="Avertissement optionnel")


class MCPPromptResponse(BaseModel):
    """Reponse MCP apres creation de prompt."""
    prompt_id: str
    name: Optional[str]
    model: str
    created_at: str
    warning: str = "Prompt stocke en memoire, perdu au redemarrage. Utilisez /voices/custom pour persistance."


class MCPErrorResponse(BaseModel):
    """Format d'erreur MCP standardise."""
    error: str
    code: str
    suggestion: Optional[str] = None
    retry_after: Optional[int] = None
