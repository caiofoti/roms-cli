# Roms Downloader

Busca e baixa ROMs por console, direto no terminal — com busca por
similaridade, verificação de integridade (md5/sha1), extração automática de
`.zip`/`.7z`/`.rar` e capas baixadas automaticamente pro RetroArch e PCSX2.

## Consoles suportados

Game Boy, Game Boy Color, Game Boy Advance, NES, SNES, N64, Nintendo DS,
Master System, Game Gear, Genesis/Mega Drive, PlayStation (PSX),
PlayStation 2, Dreamcast, PSP. Lista atual com `roms-downloader --list-consoles`.

## Instalação

```bash
git clone https://github.com/caiofoti/roms-cli.git
cd roms-cli
python -m venv venv

# Linux/macOS
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1

pip install -e .
```

No Windows, se aparecer erro de SSL/certificado ao buscar (comum com
antivírus que faz inspeção de HTTPS, como Norton), o pacote
`pip-system-certs` já resolve automaticamente — ele já é instalado junto.

## Configuração obrigatória (.env)

Sem isso, a busca/download de ROMs funciona, mas **/info, /top e o download
automático de capas não funcionam**:

```bash
cp .env.example .env
```

Edite `.env` e coloque sua chave gratuita da [RAWG](https://rawg.io/apidocs)
(cadastro simples, sem cartão):

```
RAWG_API_KEY=sua_chave_aqui
```

O app avisa na tela inicial e em `/config` se a chave não estiver
configurada.

## Uso

Sem argumentos abre o modo **chat interativo** (o jeito recomendado de usar):

```bash
roms-downloader
```

Dentro do chat:

| Comando | O que faz |
|---|---|
| `/console <nome>` | escolhe o console (sem nome abre um menu) |
| `<texto>` | busca no console atual, sem precisar de comando |
| `/download <n>[,<n>...]` | baixa o(s) resultado(s) pelo número mostrado |
| `/info <n>` | nota, gêneros e descrição do resultado (via RAWG) |
| `/top` | melhores avaliados (RAWG) já cruzados com o catálogo |
| `/next` / `/prev` | pagina os resultados |
| `/config` | tela de configurações (pasta de ROMs, limites) |
| `/clean` | lista e apaga downloads incompletos (`.partial`) |
| `/help` | lista completa de comandos |
| `/quit` | sai |

Modo direto, sem menus — passa os argumentos e já busca:

```bash
roms-downloader --console "PS2" --query "crash bandicoot"
roms-downloader --console "SNES" --query "zelda" --yes   # baixa tudo que casar, sem perguntar
roms-downloader --list-consoles
```

Definir onde as ROMs ficam salvas (cria a pasta de cada console
automaticamente, pronta pra qualquer emulador apontar pra lá):

```bash
roms-downloader --set-root "D:\Roms"
```

Sem instalar o pacote, dá pra rodar direto por `python run.py` com os
mesmos argumentos.

## O que acontece depois do download

1. Hash (md5/sha1) é conferido contra o valor oficial do archive.org — se
   não bater, o terminal avisa antes de você usar o arquivo.
2. `.zip`/`.7z`/`.rar` são extraídos automaticamente e o arquivo compactado é
   apagado — o jogo já fica pronto pra abrir no emulador.
3. A capa é buscada (RAWG) e salva automaticamente:
   - **PCSX2**: `Documentos/PCSX2/covers/`
   - **RetroArch**: pasta `thumbnails/<Sistema>/Named_Boxarts/` dentro da
     instalação encontrada (detecção automática, ou instale em
     `C:\RetroArch-Win64` / `/usr/bin/retroarch` / local padrão do SO)

## Como funciona a busca

Os nomes digitados não precisam ser exatos — tanto o console quanto o jogo
usam correspondência aproximada (fuzzy matching). Resultados abaixo de um
limiar de similaridade são descartados automaticamente.

A coluna "Downloads"/"★" na lista de resultados vem de estatísticas do
próprio archive.org (nível da coleção/acervo, não por ROM individual — o
archive.org não expõe isso por arquivo) — serve como sinal de quão usada e
confiável é a fonte de onde o jogo vem.

## Emuladores recomendados

- **RetroArch** — cobre todos os consoles exceto PS2.
- **PCSX2** — para PlayStation 2.

Ambos recebem a pasta de ROMs e as capas automaticamente, sem passo manual
(veja acima).

## Adicionar um novo console

Uma linha em `src/config.py`, dicionário `CONSOLES_ARCHIVE`:

```python
"Nome do Console": ("nome_da_pasta", ["identificador_no_archive_org"]),
```

Busca, download, verificação de hash e criação de pasta já funcionam pra
qualquer console adicionado assim.

## Desenvolvimento

```bash
pip install -r requirements.txt
python run.py --help
```

## Licença

MIT — ver [LICENSE](LICENSE).
