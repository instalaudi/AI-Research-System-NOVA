import asyncio
import os
from core.proactive import NOVAProactiveSystem

async def main():
    system = NOVAProactiveSystem()
    img_data = await system._generate_vitals_image()
    if img_data:
        with open("tests/vitals_test.png", "wb") as f:
            f.write(img_data)
        print("Imagen generada exitosamente en tests/vitals_test.png")
    else:
        print("Fallo generando la imagen.")

if __name__ == "__main__":
    asyncio.run(main())
