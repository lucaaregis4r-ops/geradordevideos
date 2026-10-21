"""Pre-Visualizer — generates reviewable storyboard reports (Markdown & HTML) before rendering.

Provides complete visibility into:
1. Overall video timeline, rhythm, and quality scorecard
2. Visual progression across the 5 narrative phases (promessa -> objeto -> bastidores -> revelacao -> fechamento)
3. Granular segment inspector (query, entities, asset preview, safe-area overlay text, typographic hierarchy)
"""

from __future__ import annotations
from datetime import timedelta
import html
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from app.services.director.schemas import ScenePlan
from .schemas import AssemblyPlan, AssemblySegment, QualityScore

logger = logging.getLogger(__name__)


def _format_timecode(seconds: float) -> str:
    """Formats seconds into MM:SS format."""
    total_sec = max(0, int(seconds))
    mins = total_sec // 60
    secs = total_sec % 60
    millis = int((seconds - total_sec) * 10)
    return f"{mins:02d}:{secs:02d}.{millis}"


class PreVisualizer:
    """Produces Markdown and standalone HTML storyboard reports for an AssemblyPlan."""

    FUNCTION_COLORS = {
        "hook": "#a855f7",        # Purple
        "context": "#3b82f6",     # Blue
        "price_tag": "#eab308",   # Gold / Yellow
        "explanation": "#06b6d4", # Cyan
        "labor": "#f97316",       # Orange
        "contrast": "#ef4444",    # Red
        "joke": "#10b981",        # Emerald green
        "transition": "#64748b",  # Slate
        "reveal": "#ec4899",      # Pink
        "conclusion": "#8b5cf6",  # Violet
    }

    PHASE_COLORS = {
        "promessa": "#3b82f6",
        "objeto": "#eab308",
        "bastidores": "#f97316",
        "revelacao": "#ec4899",
        "fechamento": "#10b981",
    }

    LEVEL_COLORS = {
        "title": "#f59e0b",       # Amber
        "emphasis": "#38bdf8",    # Sky Blue
        "caption": "#94a3b8",     # Slate
    }

    def generate_markdown(
        self,
        plan: AssemblyPlan,
        scene_plan: Optional[ScenePlan] = None,
    ) -> str:
        """Generates a comprehensive Markdown storyboard report."""
        score = plan.quality_score or QualityScore()
        status_badge = "✅ PASSED" if score.passed else "❌ FAILED (Gated)"

        scene_map = {}
        if scene_plan:
            scene_map = {s.scene_id: s for s in scene_plan.scenes}

        lines: List[str] = [
            f"# Storyboard Pre-Render Report: `{plan.project_id}`",
            "",
            f"**Quality Gate Status:** {status_badge}  ",
            f"**Total Duration:** {plan.total_duration:.1f}s | **Segments:** {len(plan.segments)} | **Visual Diversity:** {score.visual_diversity*100:.1f}% | **Safe Area Errors:** {score.text_safe_area_errors}",
            "",
            "## 1. Quality Scorecard",
            "",
            f"- **Unique Assets:** {plan.unique_asset_count} / {len(plan.segments)}",
            f"- **Involuntary Duplicates:** {score.duplicate_assets}",
            f"- **Semantic Match Average:** {score.semantic_match_avg * 100:.1f}%",
            f"- **Segments Without Visual:** {score.segments_without_visual}",
            f"- **Safe Area Violations:** {score.text_safe_area_errors}",
            "",
        ]

        # Timeline table
        lines.extend([
            "## 2. Segments Timeline",
            "",
            "| # | Timecode | Dur | Phase | Function | Query | Overlay Text (Level) | Asset ID / Type | Callback? |",
            "|---|---|---|---|---|---|---|---|---|",
        ])

        for idx, seg in enumerate(plan.segments, 1):
            dur = seg.end - seg.start
            tc = f"{_format_timecode(seg.start)} - {_format_timecode(seg.end)}"
            phase = seg.phase or "—"
            func = seg.purpose
            query = f"`{seg.query}`" if seg.query else "—"
            
            overlay = "—"
            if seg.overlay_text:
                overlay = f"**{seg.overlay_text}** ({seg.text_level.upper()})"

            asset_info = f"`{seg.asset_id[:16]}` ({seg.asset_type})"
            cb = "🔁 Sim" if seg.is_callback else "Não"

            lines.append(
                f"| {idx:02d} | {tc} | {dur:.1f}s | {phase} | {func} | {query} | {overlay} | {asset_info} | {cb} |"
            )

        lines.append("")
        return "\n".join(lines)

    def generate_html(
        self,
        plan: AssemblyPlan,
        scene_plan: Optional[ScenePlan] = None,
        title: Optional[str] = None,
    ) -> str:
        """Generates a standalone, rich HTML document with dark theme and cards."""
        doc_title = title or getattr(scene_plan, "title", None) or f"Video Storyboard: {plan.project_id}"
        score = plan.quality_score or QualityScore()
        scene_map = {}
        if scene_plan:
            scene_map = {s.scene_id: s for s in scene_plan.scenes}

        # Calculate phase counts
        phase_counts: Dict[str, int] = {}
        for s in plan.segments:
            p = (s.phase or "promessa").lower()
            phase_counts[p] = phase_counts.get(p, 0) + 1

        total_segs = max(1, len(plan.segments))
        gate_status_class = "pass" if score.passed else "fail"
        gate_status_text = "APROVADO PARA RENDER" if score.passed else "BLOQUEADO POR QUALIDADE"

        # Build Segment HTML cards
        cards_html = []
        for idx, seg in enumerate(plan.segments, 1):
            dur = seg.end - seg.start
            func_color = self.FUNCTION_COLORS.get(seg.purpose.lower(), "#64748b")
            phase_color = self.PHASE_COLORS.get((seg.phase or "").lower(), "#64748b")
            level_color = self.LEVEL_COLORS.get((seg.text_level or "").lower(), "#94a3b8")

            scene = scene_map.get(seg.scene_ref)
            narration = scene.narration if scene else ""

            # Overlay visual badge
            overlay_html = ""
            if seg.overlay_text and seg.overlay_text.strip():
                lvl = seg.text_level.lower()
                badge_style = "title-badge" if lvl == "title" else ("emphasis-badge" if lvl == "emphasis" else "caption-badge")
                overlay_html = f"""
                <div class="overlay-preview">
                    <span class="level-tag" style="background:{level_color};">{seg.text_level.upper()}</span>
                    <div class="{badge_style}">{html.escape(seg.overlay_text)}</div>
                </div>
                """

            callback_tag = '<span class="tag callback">🔁 Callback</span>' if seg.is_callback else ""

            # Score bar
            score_bar = ""
            if seg.semantic_score > 0:
                pct = int(min(1.0, seg.semantic_score) * 100)
                score_bar = f"""
                <div class="score-container">
                    <span>Match: {pct}%</span>
                    <div class="score-bar"><div class="score-fill" style="width: {pct}%;"></div></div>
                </div>
                """

            card = f"""
            <div class="segment-card">
                <div class="card-header">
                    <div class="index-pill">#{idx:02d}</div>
                    <div class="timecode">{_format_timecode(seg.start)} – {_format_timecode(seg.end)} <span class="dur">({dur:.1f}s)</span></div>
                    <div class="tags">
                        {callback_tag}
                        <span class="tag" style="background:{phase_color};">{html.escape(seg.phase or 'Geral')}</span>
                        <span class="tag" style="background:{func_color};">{html.escape(seg.purpose)}</span>
                    </div>
                </div>
                <div class="card-body">
                    {f'<div class="narration">"{html.escape(narration)}"</div>' if narration else ''}
                    <div class="query-box">
                        <span class="query-icon">🔍</span>
                        <span class="query-text">{html.escape(seg.query or 'Busca automática')}</span>
                    </div>
                    {overlay_html}
                    <div class="asset-meta">
                        <span class="asset-type">{seg.asset_type.upper()}</span>
                        <span class="asset-id" title="{html.escape(seg.asset_path or seg.asset_id)}">{html.escape(seg.asset_id[:24])}</span>
                        {score_bar}
                    </div>
                </div>
            </div>
            """
            cards_html.append(card)

        # Build phase progress bar
        phase_bars = []
        for phase, color in self.PHASE_COLORS.items():
            count = phase_counts.get(phase, 0)
            if count > 0:
                pct = (count / total_segs) * 100
                phase_bars.append(f"""
                <div class="phase-bar-segment" style="width: {pct:.1f}%; background: {color};" title="{phase.capitalize()}: {count} cenas ({pct:.0f}%)">
                    <span>{phase.capitalize()} ({count})</span>
                </div>
                """)

        html_template = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(doc_title)} - {html.escape(plan.project_id)}</title>
    <style>
        :root {{
            --bg-base: #0b0f17;
            --bg-surface: #151b26;
            --bg-card: #1c2433;
            --border: #2d3748;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --success: #10b981;
            --danger: #ef4444;
            --gold: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg-base);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            padding: 32px 24px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 24px;
            margin-bottom: 24px;
        }}
        .title-group h1 {{ font-size: 24px; font-weight: 700; color: #fff; }}
        .title-group p {{ color: var(--text-muted); font-size: 14px; margin-top: 4px; }}
        .gate-pill {{
            padding: 8px 16px;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 13px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        .gate-pill.pass {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid #059669; }}
        .gate-pill.fail {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid #dc2626; }}

        /* Scorecard */
        .scorecard-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }}
        .metric-card {{
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        }}
        .metric-val {{ font-size: 24px; font-weight: 800; color: #fff; margin-top: 4px; }}
        .metric-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}

        /* Phase progress */
        .phase-progression {{ margin-bottom: 32px; background: var(--bg-surface); padding: 16px; border-radius: 12px; border: 1px solid var(--border); }}
        .phase-title {{ font-size: 13px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 10px; }}
        .phase-bar {{ display: flex; height: 28px; border-radius: 6px; overflow: hidden; }}
        .phase-bar-segment {{
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            overflow: hidden;
            white-space: nowrap;
            text-shadow: 0 1px 2px rgba(0,0,0,0.6);
            transition: opacity 0.2s;
        }}
        .phase-bar-segment:hover {{ opacity: 0.85; }}

        /* Segment cards */
        .segments-header {{ font-size: 18px; font-weight: 700; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }}
        .segments-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 20px;
        }}
        .segment-card {{
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: transform 0.15s, border-color 0.15s;
        }}
        .segment-card:hover {{
            transform: translateY(-2px);
            border-color: #4b5563;
        }}
        .card-header {{
            background: var(--bg-card);
            padding: 12px 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            border-bottom: 1px solid var(--border);
        }}
        .index-pill {{
            background: #374151;
            color: #fff;
            font-weight: 700;
            font-size: 12px;
            padding: 2px 8px;
            border-radius: 6px;
        }}
        .timecode {{ font-size: 13px; font-weight: 600; color: #cbd5e1; flex: 1; }}
        .timecode .dur {{ color: var(--text-muted); font-weight: 400; font-size: 12px; }}
        .tags {{ display: flex; gap: 6px; }}
        .tag {{
            font-size: 10px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 9999px;
            color: #fff;
            text-transform: uppercase;
        }}
        .tag.callback {{ background: #4f46e5; }}

        .card-body {{ padding: 16px; display: flex; flex-direction: column; gap: 12px; flex: 1; }}
        .narration {{
            font-size: 13px;
            color: #e2e8f0;
            font-style: italic;
            border-left: 3px solid #3b82f6;
            padding-left: 10px;
            line-height: 1.4;
        }}
        .query-box {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(0, 0, 0, 0.3);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 12px;
            border: 1px solid #1f2937;
        }}
        .query-icon {{ font-size: 14px; }}
        .query-text {{ color: #93c5fd; font-family: ui-monospace, monospace; font-weight: 600; }}

        /* Overlay styles */
        .overlay-preview {{
            background: #0f172a;
            border: 1px dashed #334155;
            border-radius: 8px;
            padding: 10px;
            position: relative;
        }}
        .level-tag {{
            position: absolute;
            top: -8px;
            right: 8px;
            font-size: 9px;
            font-weight: 800;
            padding: 1px 6px;
            border-radius: 4px;
            color: #000;
        }}
        .title-badge {{
            color: #ffd700;
            font-weight: 900;
            font-size: 16px;
            text-align: center;
            letter-spacing: 1px;
            background: rgba(0,0,0,0.7);
            border: 1px solid #ffd700;
            border-radius: 6px;
            padding: 6px 12px;
        }}
        .emphasis-badge {{
            color: #ffffff;
            font-weight: 800;
            font-size: 13px;
            text-align: center;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid #38bdf8;
            border-radius: 6px;
            padding: 4px 10px;
        }}
        .caption-badge {{
            color: #e2e8f0;
            font-size: 12px;
            text-align: center;
            background: rgba(0,0,0,0.6);
            border-radius: 4px;
            padding: 4px 8px;
        }}

        .asset-meta {{
            margin-top: auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 11px;
            color: var(--text-muted);
            border-top: 1px solid var(--border);
            padding-top: 10px;
        }}
        .asset-type {{ font-weight: 700; color: #94a3b8; }}
        .asset-id {{ font-family: ui-monospace, monospace; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .score-container {{ display: flex; align-items: center; gap: 6px; }}
        .score-bar {{ width: 50px; height: 6px; background: #334155; border-radius: 3px; overflow: hidden; }}
        .score-fill {{ height: 100%; background: #10b981; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-group">
                <h1>{html.escape(doc_title)}</h1>
                <p>Projeto: <strong>{html.escape(plan.project_id)}</strong> • Meta EBU R128: <strong>-14.0 LUFS</strong></p>
            </div>
            <div class="gate-pill {gate_status_class}">{gate_status_text}</div>
        </header>

        <section class="scorecard-grid">
            <div class="metric-card">
                <div class="metric-label">Duração Total</div>
                <div class="metric-val">{plan.total_duration:.1f}s</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Cenas</div>
                <div class="metric-val">{len(plan.segments)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Assets Únicos</div>
                <div class="metric-val">{plan.unique_asset_count}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Diversidade Visual</div>
                <div class="metric-val">{score.visual_diversity*100:.0f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Duplicatas Involuntárias</div>
                <div class="metric-val" style="color: {'#34d399' if score.duplicate_assets == 0 else '#f87171'};">{score.duplicate_assets}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Safe Area 9:16</div>
                <div class="metric-val" style="color: {'#34d399' if score.text_safe_area_errors == 0 else '#f87171'};">{score.text_safe_area_errors} erros</div>
            </div>
        </section>

        <section class="phase-progression">
            <div class="phase-title">Progressão Dramática (5 Atos)</div>
            <div class="phase-bar">
                {''.join(phase_bars)}
            </div>
        </section>

        <section>
            <div class="segments-header">
                <span>Segmentos da Linha do Tempo ({len(plan.segments)})</span>
            </div>
            <div class="segments-grid">
                {''.join(cards_html)}
            </div>
        </section>
    </div>
</body>
</html>
"""
        return html_template

    def save_reports(
        self,
        plan: AssemblyPlan,
        output_dir: Union[str, Path],
        scene_plan: Optional[ScenePlan] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Path]:
        """Saves both Markdown and HTML storyboard reports to target directory."""
        folder = Path(output_dir).resolve()
        folder.mkdir(parents=True, exist_ok=True)

        doc_title = title or getattr(scene_plan, "title", None) or f"Video Storyboard: {plan.project_id}"
        md_content = self.generate_markdown(plan, scene_plan=scene_plan)
        html_content = self.generate_html(plan, scene_plan=scene_plan, title=doc_title)

        md_path = folder / "storyboard.md"
        html_path = folder / "storyboard.html"

        with md_path.open("w", encoding="utf-8") as f:
            f.write(md_content)

        with html_path.open("w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info("Saved storyboard reports to %s and %s", md_path.name, html_path.name)
        return {"markdown": md_path, "html": html_path}
