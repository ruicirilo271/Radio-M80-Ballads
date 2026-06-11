# M80 Ballads — identificação MP3 de alta qualidade

Esta versão foi ajustada para melhorar o reconhecimento sem duplicar o tempo
de espera na Vercel.

## Configuração da amostra

- Formato: MP3
- Duração capturada: 12 segundos
- Bitrate: 128 kbps
- Frequência: 44,1 kHz
- Canais: mono
- Segmento analisado pelo Shazam: 10 segundos centrais
- Tentativas de gravação por clique: 1

A aplicação não grava automaticamente uma segunda amostra. Caso o Shazam não
encontre correspondência, o utilizador pode tentar novamente alguns segundos
mais tarde. Isto evita esperas próximas de 30 ou 40 segundos.

## Otimizações

- O resultado não fica à espera de uma pesquisa adicional no iTunes.
- O Shazam faz no máximo duas tentativas de rede curtas.
- `/api/warmup` é chamado silenciosamente ao abrir a página para reduzir o
  impacto do primeiro arranque da Function.
- O ficheiro MP3 é guardado em `/tmp` e apagado no bloco `finally`.
- A rádio principal continua ligada diretamente ao stream oficial.
- O spectrum continua a usar a ligação silenciosa separada.

## Estrutura na raiz do GitHub

```text
app.py
requirements.txt
vercel.json
.python-version
README.md
templates/
static/
```

## Diagnóstico depois do deploy

Abre:

```text
/api/identify-diagnostics
```

Deverás encontrar:

```json
{
  "ok": true,
  "sample_format": "mp3",
  "capture_seconds": 12,
  "shazam_segment_seconds": 10,
  "mp3_bitrate": "128k",
  "sample_rate": 44100,
  "tmp_writable": true,
  "ffmpeg_available": true,
  "mp3_encoder": true
}
```

Uma identificação bem-sucedida deverá demorar normalmente pelo menos o tempo
da própria gravação da emissão ao vivo, mais o pedido ao Shazam.
