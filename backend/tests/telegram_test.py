import asyncio
import os
from core.proactive import NOVAProactiveSystem

async def main():
    system = NOVAProactiveSystem()
    system._is_good_time = lambda: True # Override quiet hours
    system._messages_today = 0
    test_msg = "Probando *caracteres* _especiales_ de Telegram:\n[link visible](http://google.com)\n> Blockquote <escaped>\n```json\n{ \"a\": 1 }\n```\n_Éxito!_"
    print("Enviando mensaje de prueba a Telegram con caracteres especiales...")
    success = await system.notify(test_msg)
    if success:
        print("✅ Mensaje enviado con éxito! El parseo HTML funcionó.")
    else:
        print("❌ Fallo al enviar mensaje. Posible error de parse_mode o credenciales.")

if __name__ == "__main__":
    asyncio.run(main())
