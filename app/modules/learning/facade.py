from uuid import UUID
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.modules.learning.service import get_learning_context_for_ai


class LearningFacade:
    """
    Abstracción para interactuar con el módulo Learning sin exponer Session directamente
    en las firmas de los servicios de otros módulos (bajo acoplamiento).
    """

    def __init__(self, db: Session):
        self.db = db

    def get_user_learning_context(self, user_id: str, topic_id: str) -> Dict[str, Any]:
        """
        Retorna el contexto de aprendizaje del usuario para un tema específico.
        """
        try:
            return get_learning_context_for_ai(
                db=self.db, user_id=UUID(user_id), topic_id=UUID(topic_id)
            )
        except Exception:
            return {}
