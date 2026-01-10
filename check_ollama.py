import ollama
import sys

try:
    print("Checking Ollama connection...")
    models = ollama.list()
    print("Ollama is running!")
    print(f"Available models: {[m['model'] for m in models['models']]}")
except Exception as e:
    print(f"Error connecting to Ollama: {e}")
    sys.exit(1)
