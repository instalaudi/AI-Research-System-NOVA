"""
Pruebas Unitarias Automatizadas para Cliente MCP y Guardrails Anti-Alucinación (Fase 5)
"""

import pytest
import asyncio
from core.mcp_client import MCPClient
from core.guardrails import HallucinationGuardrail


def test_mcp_client_jsonrpc_request():
    """Valida la generación conforme de mensajes JSON-RPC 2.0."""
    client = MCPClient()
    req = client.build_jsonrpc_request("tools/list", {"filter": "web"}, req_id=42)
    
    assert req["jsonrpc"] == "2.0"
    assert req["id"] == 42
    assert req["method"] == "tools/list"
    assert req["params"]["filter"] == "web"


def test_mcp_client_tool_registration_and_list():
    """Valida el registro y listado dinámico de herramientas MCP."""
    client = MCPClient()
    client.register_server("postgres-mcp", {"version": "1.0", "type": "database"})
    
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"]
    }
    client.register_tool("postgres-mcp", "execute_sql", "Ejecuta consultas en PostgreSQL", schema)
    
    tools = client.list_tools()
    tool_names = [t["name"] for t in tools]
    assert "execute_sql" in tool_names
    postgres_tool = next(t for t in tools if t["name"] == "execute_sql")
    assert postgres_tool["server_id"] == "postgres-mcp"



@pytest.mark.asyncio
async def test_mcp_client_execute_tool():
    """Valida la invocación asíncrona de herramientas registradas en MCP."""
    client = MCPClient()
    client.register_server("system-mcp", {"type": "local"})
    client.register_tool("system-mcp", "get_status", "Obtiene estado del sistema", {})
    
    res = await client.execute_tool("get_status", {})
    assert res["success"] is True
    assert res["tool_name"] == "get_status"
    
    # Herramienta no existente
    res_not_found = await client.execute_tool("non_existent_tool", {})
    assert res_not_found["success"] is False


def test_guardrails_faithfulness_grounded():
    """Valida que una respuesta respaldada por el contexto reciba alta puntuación de fidelidad."""
    guardrail = HallucinationGuardrail()
    context = [
        "FastAPI es un framework web moderno para Python 3.8+ basado en Starlette y Pydantic.",
        "Ofrece alto rendimiento a la par con NodeJS y Go gracias a soporte nativo para async y await."
    ]
    answer = "FastAPI es un framework moderno de Python basado en Starlette y Pydantic con soporte nativo para async."
    
    res = guardrail.evaluate_faithfulness(answer, context)
    assert res["faithfulness_score"] >= 0.7
    assert res["is_hallucination"] is False


def test_guardrails_faithfulness_hallucination():
    """Valida la detección de alucinaciones con términos no presentes en el contexto."""
    guardrail = HallucinationGuardrail()
    context = [
        "El protocolo HTTP/2 utiliza multiplexación binaria sobre una única conexión TCP."
    ]
    # Respuesta con afirmaciones completamente inventadas y no sustentadas
    fabricated_answer = "La nave espacial Voyager 3 fue lanzada en el año 2045 con propulsión cuántica a base de antimateria."
    
    res = guardrail.evaluate_faithfulness(fabricated_answer, context)
    assert res["faithfulness_score"] < 0.55
    assert res["is_hallucination"] is True
    assert len(res["ungrounded_terms"]) > 0


def test_guardrails_relevance_audit():
    """Valida la evaluación de relevancia y auditoría integral."""
    guardrail = HallucinationGuardrail()
    query = "¿Cómo optimizar consultas SQL en PostgreSQL?"
    answer = "Para optimizar PostgreSQL crea índices B-tree, utiliza EXPLAIN ANALYZE y ajusta work_mem."
    context = ["PostgreSQL soporta índices B-tree y la herramienta EXPLAIN ANALYZE para análisis de consultas."]
    
    audit = guardrail.audit_response(query, answer, context)
    assert audit["overall_safe"] is True
    assert audit["relevance"]["is_relevant"] is True
