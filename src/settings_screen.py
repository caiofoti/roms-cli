import os

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Static

from src import config
from src.metadata_manager import PCSX2_COVERS_FOLDER
from src.utils import find_retroarch


def _diagnostics_text():
    """Resumo do que está/não está configurado — mostrado sempre que /config abre,
    pra deixar claro o que precisa ser ajustado antes do app funcionar 100%."""
    lines = ["[bold]Diagnóstico de configuração[/bold]", ""]

    lines.append(f"Pasta de ROMs: {config.ROMS_ROOT}")
    if not os.path.isdir(config.ROMS_ROOT):
        lines.append("  [red]⚠ pasta não existe/acessível agora (drive desconectado?)[/red]")

    retroarch = find_retroarch()
    if retroarch:
        lines.append(f"RetroArch: [green]encontrado[/green] em {retroarch}")
    else:
        lines.append(
            "RetroArch: [yellow]não encontrado[/yellow] — capas não serão salvas pra "
            "ele, e você precisa apontar as pastas de ROM manualmente nas playlists."
        )

    lines.append(f"Capas PCSX2: {PCSX2_COVERS_FOLDER}")

    rawg_key = os.getenv("RAWG_API_KEY")
    if rawg_key:
        lines.append("RAWG_API_KEY: [green]configurada[/green] (nota/capa/descrição funcionam)")
    else:
        lines.append(
            "RAWG_API_KEY: [red]não configurada[/red] — copie .env.example para .env "
            "e coloque sua chave gratuita de https://rawg.io/apidocs, senão /info, "
            "/top e as capas não vão funcionar."
        )

    return "\n".join(lines)


class SettingsApp(App):
    """Tela de configurações editáveis do Roms Downloader."""

    CSS = """
    Vertical#form { padding: 2 4; }
    Input { margin-bottom: 1; }
    #actions { margin-top: 1; height: auto; }
    #actions Button { margin-right: 2; }
    #status { color: $success; margin-top: 1; }
    #diagnostics { margin-bottom: 2; }
    """

    BINDINGS = [("escape", "quit_app", "Cancelar")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="form"):
            yield Static(_diagnostics_text(), id="diagnostics")

            yield Label("Pasta raiz de ROMs (criada automaticamente se não existir)")
            yield Input(value=config.ROMS_ROOT, id="roms_root")

            yield Label("Limite padrão de resultados por busca")
            yield Input(value=str(config.DEFAULT_RESULT_LIMIT), id="limit")

            yield Label("Similaridade mínima da busca fuzzy (0-100)")
            yield Input(value=str(config.MIN_SIMILARITY), id="min_sim")

            yield Static("", id="status")

            with Horizontal(id="actions"):
                yield Button("Salvar", id="save", variant="success")
                yield Button("Cancelar", id="cancel")
        yield Footer()

    def action_quit_app(self) -> None:
        self.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.exit()
            return

        status = self.query_one("#status", Static)
        root = self.query_one("#roms_root", Input).value.strip()
        limit = self.query_one("#limit", Input).value.strip()
        min_sim = self.query_one("#min_sim", Input).value.strip()

        if not root:
            status.update("[red]Pasta raiz não pode ficar vazia.[/red]")
            return
        if not limit.isdigit() or not (0 < int(limit) <= 500):
            status.update("[red]Limite deve ser um número entre 1 e 500.[/red]")
            return
        if not min_sim.isdigit() or not (0 <= int(min_sim) <= 100):
            status.update("[red]Similaridade deve ser um número entre 0 e 100.[/red]")
            return

        if root != config.ROMS_ROOT:
            config.set_roms_root(root)
        config.set_default_result_limit(int(limit))
        config.set_min_similarity(int(min_sim))

        status.update("[green]Configurações salvas.[/green]")
        self.set_timer(0.6, self.exit)


def run_settings_screen():
    SettingsApp().run()
