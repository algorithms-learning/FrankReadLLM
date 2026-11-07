# FrankReadLLM
An intelligent, open-source reading platform that automates the Ilya Frank Reading Method using local, lightweight LLMs.

# Запуск приложения

### 1. Запуск контейнера
Для запуска приложения выполните следующую команду в терминале. Она автоматически свяжет контейнер с Ollama на вашей локальной машине:

```bash
sudo docker run -d --network host -e OLLAMA_URL=http://127.0.0.1:11434 --name my_app frankread:host
```

### 2. Использование
После успешного запуска приложение будет доступно по адресу:
* **http://localhost:5000**
