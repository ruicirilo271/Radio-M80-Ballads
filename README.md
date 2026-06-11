# M80 Ballads — Super Deus Final para Vercel

## Funcionalidades

- Stream M80 Ballads através de `/radio-stream`.
- Equalizador real com Web Audio API e `AnalyserNode`.
- Identificação Shazam usando uma amostra temporária em `/tmp`.
- Capas Shazam/iTunes.
- Histórico das últimas 10 músicas no `localStorage`.
- Top 10 guardado no navegador.
- Player fino fixo no rodapé.
- Página `/health` e teste `/api/stream-check`.

## Estrutura correta no GitHub

```text
app.py
requirements.txt
README.md
templates/
  index.html
static/
  style.css
  script.js
  default_cover.svg
```

Não incluas `vercel.json`. A publicação que funcionou utilizou a deteção automática do Flask com `app.py` na raiz.

## Publicar na Vercel

1. Coloca os ficheiros diretamente na raiz do repositório GitHub.
2. Confirma que o ficheiro se chama exatamente `app.py`.
3. Na Vercel, deixa Framework Preset em `Other` ou deteção automática.
4. Não definas Build Command, Output Directory ou Install Command.
5. Deixa Root Directory vazio quando `app.py` está na raiz.
6. Faz o deploy sem reutilizar cache antigo.

## Testes

- `/health`
- `/api/stream-check`
- Liga a rádio e confirma que `Spectrum real: frequências ativas` aparece.

## Execução local

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre `http://127.0.0.1:5000`.

## Nota sobre Vercel

O equalizador real depende de a rota `/radio-stream` permanecer aberta enquanto a rádio toca. Em ambientes serverless, a plataforma pode terminar ligações muito longas dependendo do plano, região ou configuração. Se isso acontecer, volta a carregar no botão para restabelecer a ligação.
