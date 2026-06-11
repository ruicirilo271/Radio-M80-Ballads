# M80 Ballads — Super Deus Estável (Vercel)

Esta versão resolve o desligamento ao fim de alguns minutos na Vercel.

## Arquitetura

- O áudio que o utilizador ouve toca diretamente do stream oficial da M80.
- O spectrum usa um segundo áudio silencioso através de `/radio-spectrum-stream`.
- Quando a Vercel termina a Function de streaming, apenas o spectrum é renovado.
- A rádio principal continua a tocar sem interrupção.
- O áudio principal também tem recuperação automática para falhas reais do servidor.
- Identificação Shazam, capas, histórico e Top 10 continuam ativos.

## Publicação

Coloca na raiz do repositório:

```text
app.py
requirements.txt
README.md
templates/
static/
```

Não uses `vercel.json` neste projeto, porque a deteção automática do `app.py` já funcionou no deploy anterior.

## Teste local

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre `http://127.0.0.1:5000`.

## Diagnóstico

- `/health`
- `/api/stream-check`
