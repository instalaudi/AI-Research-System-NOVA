import os
import urllib.request
import sys

def download_file(url, filepath):
    print(f"Descargando {os.path.basename(filepath)}...")
    try:
        def progress(count, block_size, total_size):
            if total_size > 0:
                percent = int(count * block_size * 100 / total_size)
                if percent > 100: percent = 100
                sys.stdout.write(f"\rProgreso: {percent}%")
                sys.stdout.flush()
            else:
                # Si el servidor no envía Content-Length, mostrar bytes
                sys.stdout.write(f"\rDescargados: {count * block_size / 1024 / 1024:.1f} MB")
                sys.stdout.flush()
                
        urllib.request.urlretrieve(url, filepath, reporthook=progress)
        print("\n¡Descarga completada!\n")
    except Exception as e:
        print(f"\nError crítico al descargar {os.path.basename(filepath)}: {e}")

def main():
    # Rutas destino
    base_dir = os.path.dirname(os.path.abspath(__file__))
    kokoro_dir = os.path.join(base_dir, "backend", "models", "kokoro")
    
    # Crear los directorios si no existen
    os.makedirs(kokoro_dir, exist_ok=True)
    
    model_path = os.path.join(kokoro_dir, "model.onnx")
    voices_path = os.path.join(kokoro_dir, "voices.bin")
    
    # URLs oficiales de thewh1teagle/kokoro-onnx 
    model_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
    voices_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
    
    print("===========================================")
    print("   NOVA Kokoro TTS - Instalador de Modelos ")
    print("===========================================")
    print(f"Directorio de destino: {kokoro_dir}\n")
    
    if not os.path.exists(model_path):
        print("-> Iniciando descarga de 'model.onnx' (~80 MB)")
        download_file(model_url, model_path)
    else:
        print("-> model.onnx ya existe. Saltando...")
        
    if not os.path.exists(voices_path):
        print("-> Iniciando descarga de 'voices.bin' (Voces neuronales)")
        download_file(voices_url, voices_path)
    else:
        print("-> voices.bin ya existe. Saltando...")
        
    print("===========================================")
    print("✅ ¡Instalación completa de Kokoro TTS!")
    print("===========================================")

if __name__ == "__main__":
    main()
