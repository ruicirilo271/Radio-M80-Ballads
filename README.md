# M80 Ballads — Vercel com identificação MP3

Esta versão mantém:

- rádio principal ligada diretamente ao stream oficial;
- spectrum real através de um segundo áudio silencioso;
- renovação automática do spectrum;
- identificação pelo Shazam;
- histórico e Top 10 no `localStorage`;
- visual dourado Super Modo Deus.

## Alteração principal da identificação

A Function grava uma amostra MP3 de 8 segundos em `/tmp`, lê o ficheiro para
memória e envia os bytes ao ShazamIO. O ficheiro é sempre apagado no final.

Também foi incluído:

- `vercel.json` apenas com `"fluid": true`;
- `.python-version` com Python 3.12;
- diagnóstico detalhado por fase;
- cliente Shazam com poucas tentativas e timeout controlado;
- segunda captura curta apenas quando a primeira falha.

## Estrutura obrigatória no GitHub

Todos estes elementos devem ficar na raiz:

```text
app.py
requirements.txt
vercel.json
.python-version
README.md
templates/
static/
```

## Vercel

O `vercel.json` desta versão não contém `functions.app.py`, portanto não provoca
o erro de padrão que não encontra Functions na pasta `api`.

Depois do deploy, abre:

```text
/health
/api/stream-check
/api/identify-diagnostics
```

Em `/api/identify-diagnostics`, os campos importantes devem ser:

```json
{
  "ok": true,
  "tmp_writable": true,
  "ffmpeg_available": true,
  "mp3_encoder": true,
  "sample_format": "mp3"
}
```

No painel da Vercel, confirma também:

```text
Project → Settings → Functions → Function Max Duration
```

Define o máximo para 60 segundos e faz um novo deployment. Em projetos com
Fluid Compute ativo, a plataforma poderá aplicar limites superiores, mas a
identificação foi desenhada para terminar muito antes disso.

## Teste local

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre:

```text
http://127.0.0.1:5000
```
