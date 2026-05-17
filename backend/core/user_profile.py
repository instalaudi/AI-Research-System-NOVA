"""
Módulo de Perfil Inteligente del Usuario.
Gestiona preferencias de frameworks, lenguajes, estilos y patrones en SQLite.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.database import UserProfile as UserProfileModel
from core.logging_config import get_logger

logger = get_logger("core.user_profile")


DEFAULT_PROFILE = {
    "frameworks": {},
    "languages": {},
    "patterns": {},
    "topics": {},
    "code_style": "limpio y modular",
    "last_updated": None
}


class UserProfile:
    """Gestor de preferencias de usuario persistidas en user_profiles."""

    def __init__(self, db: Session):
        self.db = db
        self.decay_factor = 0.95

    def get_profile(self, user_id: int) -> Dict[str, Any]:
        profile = self.db.query(UserProfileModel).filter(UserProfileModel.user_id == user_id).first()
        if not profile:
            return DEFAULT_PROFILE.copy()

        preferences = self._safe_json_load(profile.preferences)
        topics_raw = self._safe_json_load(profile.frequent_topics)

        normalized = {
            "frameworks": self._normalize_counter_map(preferences.get("frameworks", {})),
            "languages": self._normalize_counter_map(preferences.get("languages", {})),
            "patterns": self._normalize_counter_map(preferences.get("patterns", {})),
            "topics": self._normalize_counter_map(topics_raw if isinstance(topics_raw, (dict, list)) else {}),
            "code_style": preferences.get("code_style", "limpio y modular"),
            "persona_summary": profile.persona_summary or "",
            "last_updated": profile.last_updated.isoformat() if profile.last_updated else None
        }
        return normalized

    def get_top_preferences(self, user_id: int, top_n: int = 3) -> Dict[str, List[str]]:
        profile = self.get_profile(user_id)
        top_n = max(1, top_n)
        result: Dict[str, List[str]] = {}
        for category in ["frameworks", "languages", "patterns", "topics"]:
            category_map = profile.get(category, {}) or {}
            sorted_items = sorted(category_map.items(), key=lambda x: x[1], reverse=True)
            result[category] = [item[0] for item in sorted_items[:top_n]]
        return result

    def get_style(self, user_id: int) -> Dict[str, Any]:
        profile = self.get_profile(user_id)
        top = self.get_top_preferences(user_id, top_n=3)
        return {
            "frameworks": top.get("frameworks", []),
            "languages": top.get("languages", []),
            "patterns": top.get("patterns", []),
            "topics": top.get("topics", []),
            "code_style": profile.get("code_style", "limpio y modular")
        }

    def update_preferences(
        self,
        user_id: int,
        frameworks: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        code_style: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        topics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        profile = self.db.query(UserProfileModel).filter(UserProfileModel.user_id == user_id).first()
        if not profile:
            profile = UserProfileModel(
                user_id=user_id,
                preferences=json.dumps(DEFAULT_PROFILE, ensure_ascii=False),
                frequent_topics=json.dumps({}, ensure_ascii=False),
                persona_summary="",
                last_updated=datetime.utcnow()
            )
            self.db.add(profile)
            self.db.flush()

        current_profile = self.get_profile(user_id)
        frameworks_map = current_profile.get("frameworks", {}).copy()
        languages_map = current_profile.get("languages", {}).copy()
        patterns_map = current_profile.get("patterns", {}).copy()
        topics_map = current_profile.get("topics", {}).copy()

        # Decaimiento temporal para priorizar preferencias recientes.
        if self.decay_factor < 1.0:
            frameworks_map = self._apply_decay(frameworks_map)
            languages_map = self._apply_decay(languages_map)
            patterns_map = self._apply_decay(patterns_map)
            topics_map = self._apply_decay(topics_map)

        for fw in (frameworks or []):
            key = fw.lower().strip()
            if key:
                frameworks_map[key] = frameworks_map.get(key, 0.0) + 1.0

        for lang in (languages or []):
            key = lang.lower().strip()
            if key:
                languages_map[key] = languages_map.get(key, 0.0) + 1.0

        for pat in (patterns or []):
            key = pat.lower().strip()
            if key:
                patterns_map[key] = patterns_map.get(key, 0.0) + 1.0

        for topic in (topics or []):
            key = topic.lower().strip()
            if key and len(key) > 2:
                topics_map[key] = topics_map.get(key, 0.0) + 1.0

        if code_style:
            style = code_style
        else:
            style = current_profile.get("code_style", "limpio y modular")

        serialized_profile = {
            "frameworks": frameworks_map,
            "languages": languages_map,
            "patterns": patterns_map,
            "code_style": style,
            "last_updated": datetime.utcnow().isoformat()
        }

        profile.preferences = json.dumps(serialized_profile, ensure_ascii=False)
        profile.frequent_topics = json.dumps(topics_map, ensure_ascii=False)
        profile.persona_summary = self._build_persona_summary(serialized_profile)
        profile.last_updated = datetime.utcnow()
        self.db.commit()

        logger.info(f"Perfil actualizado para user_id={user_id}")
        return self.get_profile(user_id)

    def apply_profile(self, user_id: int) -> str:
        profile = self.get_style(user_id)
        frameworks = profile.get("frameworks", [])
        languages = profile.get("languages", [])
        code_style = profile.get("code_style", "limpio y modular")
        patterns = profile.get("patterns", [])
        return (
            f"- Frameworks preferidos: {', '.join(frameworks) if frameworks else 'sin preferencia'}\n"
            f"- Lenguajes favoritos: {', '.join(languages) if languages else 'sin preferencia'}\n"
            f"- Estilo de código: {code_style}\n"
            f"- Patrones frecuentes: {', '.join(patterns) if patterns else 'sin patrones registrados'}"
        )

    @staticmethod
    def _safe_json_load(raw: Optional[str]) -> Any:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {} if raw.strip().startswith("{") else []

    @staticmethod
    def _normalize_counter_map(value: Any) -> Dict[str, float]:
        if isinstance(value, dict):
            normalized: Dict[str, float] = {}
            for k, v in value.items():
                key = str(k).lower().strip()
                if not key:
                    continue
                try:
                    normalized[key] = float(v)
                except Exception:
                    normalized[key] = 1.0
            return normalized
        if isinstance(value, list):
            # Backward-compat: listas antiguas -> contador uniforme.
            normalized: Dict[str, float] = {}
            for item in value:
                key = str(item).lower().strip()
                if key:
                    normalized[key] = normalized.get(key, 0.0) + 1.0
            return normalized
        return {}

    @staticmethod
    def _apply_decay(counter_map: Dict[str, float], factor: float = 0.95) -> Dict[str, float]:
        decayed: Dict[str, float] = {}
        for k, v in counter_map.items():
            new_value = float(v) * factor
            if new_value >= 0.05:
                decayed[k] = new_value
        return decayed

    @staticmethod
    def _build_persona_summary(preferences: Dict[str, Any]) -> str:
        frameworks_map = UserProfile._normalize_counter_map(preferences.get("frameworks", {}))
        languages_map = UserProfile._normalize_counter_map(preferences.get("languages", {}))
        frameworks = [k for k, _ in sorted(frameworks_map.items(), key=lambda x: x[1], reverse=True)[:3]]
        languages = [k for k, _ in sorted(languages_map.items(), key=lambda x: x[1], reverse=True)[:3]]
        code_style = preferences.get("code_style", "limpio y modular")
        return (
            f"Usuario orientado a {', '.join(frameworks) if frameworks else 'stack generalista'}, "
            f"con preferencia por {', '.join(languages) if languages else 'lenguajes mixtos'} "
            f"y estilo {code_style}."
        )
