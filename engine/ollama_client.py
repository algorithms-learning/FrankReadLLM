import json
import time
import requests
from config import MODEL, OLLAMA_URL, TEMPERATURE, TIMEOUT


class OllamaClient:
    def __init__(self, model=MODEL, url=OLLAMA_URL, temperature=TEMPERATURE):
        self.model = model
        self.url = url.rstrip("/")
        self.temperature = temperature
        self.last_stats = {}

    def is_available(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/tags", timeout=3).ok
        except requests.RequestException:
            return False

    def chat(self, messages: list[dict], max_tokens: int = 1500, debug: bool = True) -> str:
        # эта строка — маркер свежего кода, если её нет в логе, файл старый
        print(f"[client] модель={self.model} max_tokens={max_tokens} debug={debug}",
              flush=True)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": False,                      # ← вот это
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,
            },
        }

        t_start = time.time()
        first_token_time = None
        content = ""
        thinking = ""
        n_content_chunks = 0
        n_thinking_chunks = 0
        final_stats = {}

        with requests.post(
            f"{self.url}/api/chat",
            json=payload,
            stream=True,
            timeout=TIMEOUT,
        ) as r:
            r.raise_for_status()

            for raw_line in r.iter_lines():
                if not raw_line:
                    continue
                chunk = json.loads(raw_line)

                if "error" in chunk:
                    raise RuntimeError(f"Ollama error: {chunk['error']}")

                msg = chunk.get("message", {})
                thinking_piece = msg.get("thinking", "")
                content_piece  = msg.get("content", "")

                if thinking_piece:
                    if first_token_time is None:
                        first_token_time = time.time() - t_start
                    n_thinking_chunks += 1
                    thinking += thinking_piece
                    if debug:
                        print(f"[think +{time.time()-t_start:.2f}s] {thinking_piece!r}",
                              flush=True)

                if content_piece:
                    if first_token_time is None:
                        first_token_time = time.time() - t_start
                    n_content_chunks += 1
                    content += content_piece
                    if debug:
                        print(f"[content +{time.time()-t_start:.2f}s] {content_piece!r}",
                              flush=True)

                if chunk.get("done"):
                    final_stats = chunk
                    break

        total_time = time.time() - t_start

        self.last_stats = {
            "done_reason":   final_stats.get("done_reason"),
            "eval_count":    final_stats.get("eval_count", 0),
            "eval_duration": final_stats.get("eval_duration", 0),
            "total_time":    total_time,
            "ttft":          first_token_time,
            "max_tokens":    max_tokens,
            "content_len":   len(content),
        }

        if debug:
            eval_count = final_stats.get("eval_count", 0)
            eval_sec = final_stats.get("eval_duration", 0) / 1e9
            tok_per_sec = eval_count / eval_sec if eval_sec else 0
            print("\n--- СТАТИСТИКА ---", flush=True)
            print(f"TTFT:                 {first_token_time:.2f}s", flush=True)
            print(f"Всего времени:        {total_time:.2f}s", flush=True)
            print(f"Токенов (eval):       {eval_count} / лимит {max_tokens}", flush=True)
            print(f"Скорость:             {tok_per_sec:.2f} tok/s", flush=True)
            print(f"Причина остановки:    {final_stats.get('done_reason', '?')}", flush=True)
            print(f"Длина content:        {len(content)} символов", flush=True)
            print(f"Длина thinking:       {len(thinking)} символов", flush=True)

        return content



    def chat_stream(self, messages: list[dict], max_tokens: int = 800):
        """Генератор. Отдаёт куски content по мере генерации. thinking пропускает."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,
            },
        }
        with requests.post(
            f"{self.url}/api/chat",
            json=payload,
            stream=True,
            timeout=TIMEOUT,
        ) as r:
            r.raise_for_status()
            for raw_line in r.iter_lines():
                if not raw_line:
                    continue
                chunk = json.loads(raw_line)
                if "error" in chunk:
                    raise RuntimeError(f"Ollama error: {chunk['error']}")
                piece = chunk.get("message", {}).get("content", "")
                if piece:
                    yield piece
                if chunk.get("done"):
                    break