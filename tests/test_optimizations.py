import sys
import os
import asyncio
from unittest.mock import AsyncMock, patch

# Añadir el directorio raíz al path para poder importar backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

async def test_routing():
    print("--- Verificando Clasificación de Intención y Enrutamiento ---")
    
    # Mock del llm_client para no depender de Ollama
    with patch('backend.core.llm_client.llm_client.chat', new_callable=AsyncMock) as mock_chat:
        from backend.core.intent_classifier import classify_intent
        
        # Caso 1: Consulta de Sistema
        mock_chat.return_value = "SYSTEM"
        intent = await classify_intent("¿Cuál es tu arquitectura?")
        print(f"Consulta: '¿Cuál es tu arquitectura?' -> Intención Detectada: {intent}")
        assert intent == "SYSTEM"
        
        # Caso 2: Consulta de Conocimiento
        mock_chat.return_value = "KNOWLEDGE"
        intent = await classify_intent("¿Qué es la IA?")
        print(f"Consulta: '¿Qué es la IA?' -> Intención Detectada: {intent}")
        assert intent == "KNOWLEDGE"
        
        # Caso 3: Conversación
        mock_chat.return_value = "CONVERSATION"
        intent = await classify_intent("Hola Jarvis")
        print(f"Consulta: 'Hola Jarvis' -> Intención Detectada: {intent}")
        assert intent == "CONVERSATION"

    print("\n--- Verificando Lógica de Metadatos de Sistema ---")
    # Mock de la base de datos y logger para get_system_info
    with patch('backend.main.SessionLocal'), \
         patch('backend.core.logger.agent_logger.get_data', new_callable=AsyncMock) as mock_logger:
        
        from backend.main import get_system_info
        
        mock_logger.return_value = {"agents": {"Planner": "idle", "Explorer": "idle"}}
        
        # Necesitamos mockear la query de SQLAlchemy también si queremos ser exhaustivos, 
        # pero aquí solo verificaremos que la estructura del info es la correcta (asumiendo mocks)
        with patch('backend.main.KnowledgeEntry') as mock_entry:
            info = await get_system_info()
            print("Metadatos del Sistema obtenidos correctamente:")
            print(f"- Modelo: {info['model']}")
            print(f"- Arquitectura: {info['architecture']}")
            print(f"- Agentes: {list(info['agents_status'].keys())}")
            
            assert "model" in info
            assert "architecture" in info
            assert "agents_status" in info

    print("\n✅ Todas las verificaciones de lógica han pasado.")

if __name__ == "__main__":
    asyncio.run(test_routing())
