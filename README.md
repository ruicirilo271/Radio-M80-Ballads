# M80 Ballads — versão Vercel

## Publicar pelo GitHub

1. Cria um repositório novo no GitHub.
2. Envia para a raiz do repositório todos os ficheiros desta pasta.
3. Em Vercel, escolhe **Add New > Project**.
4. Importa o repositório.
5. Em **Framework Preset**, deixa **Other** ou a deteção automática.
6. Não coloques Build Command, Output Directory nem Install Command personalizados.
7. Carrega em **Deploy**.

## Testes depois do deploy

- `/health` deve indicar `ffmpeg_available: true`.
- `/api/stream-check` deve indicar `ok: true`.
- Liga a rádio e aguarda alguns segundos antes da primeira identificação.

## Arquitetura desta versão

- O navegador toca diretamente o stream da M80.
- A Vercel Function só é usada para gravar uma amostra curta e identificar com Shazam.
- O histórico e o Top 10 são guardados no `localStorage` do navegador.
- Não existe `radio_data.json`, porque o armazenamento local da Vercel não é persistente.

## Variável de ambiente opcional

Podes configurar `M80_STREAM_URL` na Vercel para alterar o stream sem editar o código.
