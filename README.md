# FrankReadLLM
An intelligent, open-source reading platform that automates the Ilya Frank Reading Method using local, lightweight LLMs.

<img width="1280" height="720" alt="2026-11-07-17-20-03" src="https://github.com/user-attachments/assets/2297f655-0c3b-4186-9876-4358e76d7554" />


# Запуск приложения

### 1. Запуск контейнера
Для запуска приложения выполните следующую команду в терминале. Она автоматически свяжет контейнер с Ollama на вашей локальной машине:

```bash
sudo docker run -d --network host -e OLLAMA_URL=http://127.0.0.1:11434 --name my_app frankread:host
```

### 2. Использование
После успешного запуска приложение будет доступно по адресу:
* **http://localhost:5000**
