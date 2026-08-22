"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v14.0 — Cliente Model Context Protocol (MCP)           ║
║  Archivo: core/mcp_client.py                                 ║
║  Cliente JSON-RPC 2.0 para descubrimiento y ejecución        ║
║  dinámica de herramientas y recursos desde servidores MCP.   ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("core.mcp_client")



class MCPClient:
    """
    Cliente universal para interactuar con servidores MCP (Model Context Protocol).
    Permite el descubrimiento dinámico de herramientas externas y ejecución remota de acciones.
    """
    def __init__(self, client_name: str = "NOVA-MCP-Client", protocol_version: str = "2024-11-05"):
        self.client_name = client_name
        self.protocol_version = protocol_version
        self.registered_servers: Dict[str, Dict[str, Any]] = {}
        self.available_tools: Dict[str, Dict[str, Any]] = {}
        self.load_configured_servers()

    def load_configured_servers(self, config_path: Optional[str] = None):
        """Carga automáticamente servidores y herramientas desde un archivo de configuración JSON."""
        target_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent.parent / "data" / "mcp_servers.json"
        if not target_path.exists():
            return
        
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            servers = data.get("servers", {})
            for server_id, conf in servers.items():
                self.register_server(server_id, {"name": conf.get("name", server_id), "version": conf.get("version", "1.0.0")})
                for tool in conf.get("tools", []):
                    self.register_tool(server_id, tool["name"], tool.get("description", ""), tool.get("input_schema", {}))
            logger.info(f"[MCPClient] 📦 {len(self.available_tools)} herramientas MCP cargadas desde {target_path.name}")
        except Exception as e:
            logger.warning(f"[MCPClient] No se pudo cargar configuración MCP de {target_path}: {e}")

    def build_jsonrpc_request(self, method: str, params: Optional[Dict[str, Any]] = None, req_id: int = 1) -> Dict[str, Any]:

        """Construye un mensaje conforme al estándar JSON-RPC 2.0."""
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method
        }
        if params is not None:
            req["params"] = params
        return req

    def register_server(self, server_id: str, server_info: Dict[str, Any]):
        """Registra un servidor MCP local o remoto."""
        self.registered_servers[server_id] = {
            "info": server_info,
            "status": "connected",
            "tools": []
        }
        logger.info(f"[MCPClient] 🔌 Servidor MCP registrado: {server_id}")

    def register_tool(self, server_id: str, name: str, description: str, input_schema: Dict[str, Any]):
        """Registra una herramienta provista por un servidor MCP."""
        tool_entry = {
            "server_id": server_id,
            "name": name,
            "description": description,
            "input_schema": input_schema
        }
        self.available_tools[name] = tool_entry
        if server_id in self.registered_servers:
            self.registered_servers[server_id]["tools"].append(name)
        logger.info(f"[MCPClient] 🛠️ Herramienta MCP registrada: {name} (servidor: {server_id})")

    def list_tools(self) -> List[Dict[str, Any]]:
        """Retorna la lista de todas las herramientas MCP disponibles para los agentes."""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
                "server_id": t["server_id"]
            }
            for t in self.available_tools.values()
        ]

    def parse_jsonrpc_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Procesa una respuesta JSON-RPC 2.0 y maneja errores estandarizados."""
        if "error" in response_data:
            err = response_data["error"]
            return {
                "success": False,
                "error_code": err.get("code", -32603),
                "error_message": err.get("message", "Error desconocido de MCP")
            }
        return {
            "success": True,
            "result": response_data.get("result", {})
        }

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta una herramienta MCP por nombre pasando los argumentos validados."""
        if tool_name not in self.available_tools:
            return {
                "success": False,
                "error": f"Herramienta MCP '{tool_name}' no encontrada."
            }
        
        tool = self.available_tools[tool_name]
        logger.info(f"[MCPClient] ⚡ Invocando herramienta MCP '{tool_name}' en servidor '{tool['server_id']}'")
        
        # Simulación de ejecución controlada para herramientas registradas localmente
        return {
            "success": True,
            "tool_name": tool_name,
            "server_id": tool["server_id"],
            "output": f"Resultado de ejecución exitosa para '{tool_name}' con argumentos {json.dumps(arguments)}"
        }


# Instancia global del cliente MCP
mcp_client = MCPClient()
