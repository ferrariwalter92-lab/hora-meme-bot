# Hora Meme Bot

Bot Telegram per generare testi meme con AI.

## Variabili d'ambiente richieste

```
TELEGRAM_TOKEN=il_tuo_token
ANTHROPIC_API_KEY=la_tua_api_key
CHAT_ID=il_tuo_chat_id
```

## Comandi

- `/genera` — genera 5 testi nuovi
- `/stile` — cambia formato (assurdo, preferiresti, date idea, confessione, update)
- `/ref` — istruzioni per aggiungere una reference
- `/refs` — vedi tutte le ref caricate
- `/salvati` — vedi i testi salvati
- Scrivi qualsiasi testo → viene salvato come reference

Ogni mattina alle 9 il bot manda 5 testi automaticamente.

## Deploy su Railway

1. Crea account su railway.app
2. New Project → Deploy from GitHub repo
3. Aggiungi le variabili d'ambiente
4. Deploy
