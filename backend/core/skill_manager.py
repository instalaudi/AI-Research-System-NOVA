import os
from pathlib import Path
import logging

logger = logging.getLogger("core.skill_manager")

class SkillManager:
    """
    Gestiona la carga de Skills (manuales de instrucciones) para inyectar contexto
    experto o comandos estructurados al LLM sin saturar el prompt principal.
    """
    def __init__(self):
        self.base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.skills_dir = self.base_dir / "skills"
        self._ensure_dir()
        self._cache = {}

    def _ensure_dir(self):
        if not self.skills_dir.exists():
            self.skills_dir.mkdir(parents=True, exist_ok=True)

    def load_skill(self, skill_name: str) -> str:
        """Carga una skill por su nombre (ej: 'terminal_skill'). Usa caché."""
        if not skill_name.endswith('.md'):
            skill_name += '.md'
            
        if skill_name in self._cache:
            return self._cache[skill_name]
            
        skill_path = self.skills_dir / skill_name
        if not skill_path.exists():
            logger.warning(f"[SkillManager] Skill no encontrada: {skill_name}")
            return ""
            
        try:
            with open(skill_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                self._cache[skill_name] = content
                return content
        except Exception as e:
            logger.error(f"[SkillManager] Error leyendo skill {skill_name}: {e}")
            return ""

    def list_available_skills(self) -> list[str]:
        """v13.0: Descubrimiento dinámico de todas las habilidades en disco."""
        try:
            files = os.listdir(self.skills_dir)
            return [f.replace('.md', '') for f in files if f.endswith('.md')]
        except Exception as e:
            logger.error(f"[SkillManager] Error listando habilidades: {e}")
            return []

    def learn_and_improve_skill(self, skill_name: str, feedback: str, success: bool):
        """
        v13.0: Auto-Optimización. Permite que un agente (ej: Critic) sugiera
        mejoras a una skill basada en resultados de ejecución.
        """
        if not skill_name.endswith('.md'):
            skill_name += '.md'
            
        skill_path = self.skills_dir / skill_name
        if not skill_path.exists():
            return

        status = "ÉXITO" if success else "FALLO"
        log_entry = f"\n\n> [!NOTE]\n> **Auto-Optimización ({status})**: {feedback}\n"
        
        try:
            # En v13.0 solo añadimos feedback como notas al final del archivo.
            # En v14.0 implementaremos re-escritura cognitiva completa.
            with open(skill_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            # Limpiar caché para que la siguiente carga use la versión actualizada
            if skill_name in self._cache:
                del self._cache[skill_name]
            logger.info(f"[SkillManager] Skill {skill_name} optimizada con nuevo feedback.")
        except Exception as e:
            logger.error(f"[SkillManager] Error en auto-optimización de {skill_name}: {e}")

    def get_active_skills_context(self, active_skills: list[str]) -> str:
        """
        Devuelve el bloque de texto combinado con todas las skills solicitadas.
        Se inyectará en el system_prompt del agente.
        """
        if not active_skills:
            return ""
            
        context_blocks = []
        context_blocks.append("\n" + "="*50)
        context_blocks.append("SKILLS ACTIVAS EN MEMORIA (INSTRUCCIONES ESTRICTAS):")
        context_blocks.append("="*50 + "\n")
        
        # v11.9.23: Inyección Dinámica de Entorno (System Awareness)
        import getpass
        current_user = getpass.getuser()
        home_dir = os.path.expanduser("~").replace("\\", "\\\\") 
        context_blocks.append(f"[ENVIRONMENT_INFO] OS: Windows | User: {current_user}")
        context_blocks.append(f"[ENVIRONMENT_INFO] Home: {home_dir}\n")
        
        # v13.0: Auto-descubrimiento para informar al LLM de qué OTRAS skills existen
        all_skills = self.list_available_skills()
        other_skills = [s for s in all_skills if s not in active_skills]
        if other_skills:
            context_blocks.append(f"[SKILLS_CATALOG] Tienes otras habilidades disponibles pero inactivas: {', '.join(other_skills)}")
            context_blocks.append("[SKILLS_CATALOG] Si necesitas alguna, pídela explícitamente al sistema.\n")

        for skill in active_skills:
            content = self.load_skill(skill)
            if content:
                context_blocks.append(f"--- INICIO SKILL: {skill.upper()} ---")
                context_blocks.append(content)
                context_blocks.append(f"--- FIN SKILL: {skill.upper()} ---\n")
                
        return "\n".join(context_blocks)

skill_manager = SkillManager()
