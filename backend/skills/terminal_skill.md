# SKILL: TERMINAL (Control de Sistema Operativo)

Puedes ejecutar comandos reales en la terminal (PowerShell/CMD) de Windows del usuario. Usa esta habilidad para leer archivos, listar directorios, instalar dependencias, etc. **No está permitido ejecutar comandos destructivos o modificar configuración del sistema sin autorización explícita.**

## 📦 Formato de invocación

Para ejecutar un comando, debes responder **exclusivamente** con un bloque JSON válido. Puedes incluir texto explicativo **antes** del JSON, pero no después. El sistema recortará espacios/saltos de línea automáticamente.

```json
{
  "tool": "terminal",
  "command": "comando_a_ejecutar",
  "description": "Breve explicación de qué hará el comando (opcional, pero recomendado)"
}
```

🔐 Reglas de seguridad (aplican automáticamente)
- Destructivos bloqueados: format, del /f /s C:\, rd /s /q C:\, reg delete, shutdown /s, taskkill /f.
- Prohibido modificar archivos del sistema (rutas como C:\Windows, C:\Program Files).
- Prohibido encadenar comandos con &, &&, |, ; (inyección de comandos).
- Prohibido ejecutar scripts sin autorización (ej. powershell -File script.ps1).
- Si intentas un comando no permitido, el sistema lo bloqueará y te notificará.

📁 Formato correcto de rutas (Windows)
- Usa doble barra invertida \\ dentro del JSON.
- Si la ruta contiene espacios, rodéala con comillas dobles.
- Ejemplo válido: "dir \"C:\\Users\\Mi Usuario\\Downloads\""
- Para PowerShell, también puedes usar comillas simples: dir 'C:\\Users\\Mi Usuario\\Downloads'

📤 Manejo de salidas largas
- Si la salida del comando supera 2000 caracteres, se truncará y se añadirá … (salida truncada).
- Se incluirá el código de salida (exit_code) del comando.
- El stderr se mostrará siempre que exista.

🔁 Ejemplo de flujo completo
Tú (NOVA):
Voy a listar los archivos de tu carpeta Descargas.

```json
{
  "tool": "terminal",
  "command": "dir \"C:\\Users\\Juan\\Downloads\"",
  "description": "Listar archivos en Descargas"
}
```

Sistema (respuesta inyectada en tu contexto):
```text
[RESULTADO DEL COMANDO]
exit_code: 0
stdout:
 Volume in drive C is OS
 Directory of C:\Users\Juan\Downloads
...
stderr: (vacío)
```

Tú (NOVA): (Analizas la salida y continúas la conversación)

⚠️ Notas adicionales
- El sistema requiere confirmación manual del usuario antes de ejecutar cualquier comando (Human-in-the-Loop).
- Si el usuario cancela, respeta su decisión y sugiere alternativas.

> [!NOTE]
> **Auto‑optimización** (sistema interno): Esta skill se actualiza automáticamente con nuevos patrones de seguridad.
