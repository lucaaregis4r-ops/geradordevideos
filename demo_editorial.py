"""Demonstração do Pipeline Editorial (Projeto Mercadoria).

Gera um vídeo vertical 9:16 completo a partir de um roteiro reflexivo, aplicando:
1. Direção semântica e segmentação em 5 atos dramáticos;
2. Busca e curadoria de assets (eliminação de metáforas vazias e ciclos visuais);
3. Efeito Ken Burns com movimento cinematográfico para fotos estáticas;
4. Tipografia em camadas nas áreas seguras para redes sociais;
5. Masterização de áudio em -14.0 LUFS (EBU R128) e automação de ducking da trilha;
6. Geração do Storyboard HTML de pré-visualização.

Uso:
    .venv/bin/python demo_editorial.py
"""

from pathlib import Path
import time
from app.services.factory import ShortsFactory


def main():
    print("=" * 65)
    print("🎬 INICIANDO DEMONSTRAÇÃO DO PIPELINE EDITORIAL — FÁBRICA DE SHORTS")
    print("=" * 65)

    # Roteiro de ensaio audiovisual
    roteiro = (
        "Existe uma pergunta que quase ninguém faz sobre riqueza: de onde vem o valor das coisas? "
        "Um celular custa cinco mil reais. Uma camiseta custa oitenta reais. Um café custa oito. "
        "O mercado coloca um número em objetos que não têm nada em comum. "
        "Mas antes de qualquer preço aparecer, existiram algodão, máquina, transporte e muito trabalho. "
        "Só que quando você compra, você só vê oitenta reais. "
        "Toda a história humana por trás do produto desaparece na etiqueta de preço."
    )

    factory = ShortsFactory(
        base_dir="storage",
        voice_name="pt-BR-AntonioNeural-Male",
    )

    def print_progress(etapa: str, progresso: float):
        porcentagem = int(progresso * 100)
        barra = "█" * (porcentagem // 5) + "░" * (20 - (porcentagem // 5))
        print(f"[{barra}] {porcentagem:3d}% -> {etapa}")

    inicio = time.time()
    task_id = f"demo_mercadoria_{int(inicio)}"

    print(f"\n📝 Roteiro carregado ({len(roteiro.split('.'))} frases).")
    print("🚀 Processando etapas editoriais...")

    draft = factory.produce_draft(
        script_id=task_id,
        script_text=roteiro,
        title="Mercadoria: O Culto do Preço",
        brand_style="editorial",
        voice_name="pt-BR-AntonioNeural-Male",
        on_progress=print_progress,
    )

    tempo_total = time.time() - inicio

    print("\n" + "=" * 65)
    print("🎉 VÍDEO E STORYBOARD PRODUZIDOS COM SUCESSO!")
    print("=" * 65)
    print(f"⏱️  Tempo total: {tempo_total:.1f}s")
    print(f"📹 Vídeo Final (MP4):     {draft.get('video_path')}")
    print(f"📊 Storyboard (HTML):    {draft.get('storyboard_html_path')}")
    print(f"📄 Storyboard (Markdown):{draft.get('storyboard_md_path')}")
    print(f"📋 Plano de Montagem:    {draft.get('plan_path')}")
    
    score = draft.get("quality_score", {})
    print("\n🔍 Relatório do Quality Gate:")
    print(f"   • Status: {'APROVADO ✅' if score.get('passed') else 'REPROVADO ❌'}")
    print(f"   • Score Semântico Médio: {score.get('semantic_match_score', 0):.2f}/1.00")
    print(f"   • Violações de Safe Area: {score.get('text_safe_area_errors', 0)}")
    print(f"   • Assets Duplicados:      {score.get('duplicate_assets', 0)}")
    print("=" * 65)
    print(f"\n💡 Dica: Para abrir o storyboard no navegador:")
    print(f"   xdg-open \"{draft.get('storyboard_html_path')}\"")
    print(f"   Para assistir ao vídeo:")
    print(f"   mpv \"{draft.get('video_path')}\" ou vlc \"{draft.get('video_path')}\"")


if __name__ == "__main__":
    main()
